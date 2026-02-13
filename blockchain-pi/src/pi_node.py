"""
Pi Node — Main entry point.

Initialises all services and starts the Pi edge node:
  • VideoAnalyzer (lightweight detection)
  • BlockchainUploader (with transaction manager)
  • LocalCache (Redis)
  • AlertListener (event monitoring)
  • Pi API (Flask REST endpoint)
  • Health monitoring
"""

import logging
import os
import signal
import sys
import time
from pathlib import Path

import yaml

# Add project root to path for shared imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parent))

from src.video_analyzer import VideoAnalyzer
from src.blockchain_uploader import BlockchainUploader
from src.local_cache import LocalCache
from src.health_check import HealthMonitor

logger = logging.getLogger(__name__)


class PiNode:
    """
    Main orchestrator for the Raspberry Pi edge node.
    """

    def __init__(self, config_path: str = "config/pi_config.yaml"):
        self.config = self._load_config(config_path)
        self._setup_logging()
        self._running = False

        logger.info("Initialising Pi Node: %s", self.config["node"]["name"])

        # ---- Initialise services ----
        self.cache = self._init_cache()
        self.analyzer = self._init_analyzer()
        self.blockchain_client = self._init_blockchain()
        self.tx_manager = self._init_tx_manager()
        self.uploader = self._init_uploader()
        self.alert_listener = self._init_alert_listener()
        self.health_monitor = HealthMonitor(self.config.get("health", {}))

        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _load_config(self, path: str) -> dict:
        config_path = PROJECT_ROOT / path
        if config_path.exists():
            with open(config_path) as f:
                return yaml.safe_load(f)
        logger.warning("Config not found at %s, using defaults", config_path)
        return {"node": {"name": "Pi-Node", "type": "pi"}}

    def _setup_logging(self):
        log_cfg = self.config.get("logging", {})
        level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)

        log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        handlers = [logging.StreamHandler()]

        log_file = log_cfg.get("file")
        if log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_file))

        logging.basicConfig(level=level, format=log_format, handlers=handlers)

    def _init_cache(self) -> LocalCache:
        cache_cfg = self.config.get("cache", {})
        return LocalCache(
            host=cache_cfg.get("redis_host", "localhost"),
            port=cache_cfg.get("redis_port", 6379),
            db=cache_cfg.get("redis_db", 0),
            ttl=cache_cfg.get("ttl_seconds", 86400),
            max_entries=cache_cfg.get("max_entries", 10000),
        )

    def _init_analyzer(self) -> VideoAnalyzer:
        analysis_cfg = self.config.get("analysis", {})
        return VideoAnalyzer(
            max_frames=analysis_cfg.get("max_frames", 5),
            frame_interval=analysis_cfg.get("frame_interval", 30),
            confidence_threshold=analysis_cfg.get("confidence_threshold", 65),
            max_file_size_mb=analysis_cfg.get("max_file_size_mb", 200),
            temp_dir=analysis_cfg.get("temp_dir", "/tmp/deepfake-pi"),
        )

    def _init_blockchain(self):
        bc_cfg = self.config.get("blockchain", {})
        rpc_url = os.environ.get("POLYGON_RPC_URL", bc_cfg.get("rpc_url", ""))
        private_key = os.environ.get("PRIVATE_KEY", bc_cfg.get("private_key", ""))

        if not rpc_url or not private_key or private_key == "your_private_key_here":
            logger.warning("Blockchain not configured — running in offline mode")
            return None

        try:
            from shared.blockchain.web3_client import BlockchainClient
            contracts = bc_cfg.get("contracts", {})
            client = BlockchainClient(
                rpc_url=rpc_url,
                private_key=private_key,
                chain_id=bc_cfg.get("chain_id", 80002),
                video_registry_address=os.environ.get("VIDEO_REGISTRY_ADDRESS",
                                                      contracts.get("video_registry")),
                tracking_ledger_address=os.environ.get("TRACKING_LEDGER_ADDRESS",
                                                       contracts.get("tracking_ledger")),
                alert_manager_address=os.environ.get("ALERT_MANAGER_ADDRESS",
                                                     contracts.get("alert_manager")),
            )
            logger.info("Blockchain client connected (balance: %.4f MATIC)",
                        client.get_balance())
            return client
        except Exception as exc:
            logger.error("Failed to connect to blockchain: %s", exc)
            return None

    def _init_tx_manager(self):
        if not self.blockchain_client:
            return None

        from shared.blockchain.transaction_manager import TransactionManager
        batch_cfg = self.config.get("batching", {})
        return TransactionManager(
            blockchain_client=self.blockchain_client,
            db_path=batch_cfg.get("db_path", "data/tx_queue.db"),
            batch_size=batch_cfg.get("batch_size", 10),
            batch_interval=batch_cfg.get("flush_interval_seconds", 60),
        )

    def _init_uploader(self) -> BlockchainUploader:
        offline_cfg = self.config.get("offline", {})
        batch_cfg = self.config.get("batching", {})
        return BlockchainUploader(
            blockchain_client=self.blockchain_client,
            transaction_manager=self.tx_manager,
            local_cache=self.cache,
            offline_queue_dir=offline_cfg.get("queue_dir", "data/offline_queue"),
            batch_size=batch_cfg.get("batch_size", 10),
        )

    def _init_alert_listener(self):
        if not self.blockchain_client:
            return None
        try:
            from shared.alerts.alert_listener import AlertListener
            from shared.alerts.notification_service import NotificationService
            notifier = NotificationService()
            listener = AlertListener(
                blockchain_client=self.blockchain_client,
                notification_service=notifier,
                poll_interval=self.config.get("alert_listener", {}).get("poll_interval_seconds", 30),
            )
            return listener
        except Exception as exc:
            logger.error("Failed to init alert listener: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def start(self):
        """Start all background services."""
        self._running = True
        logger.info("Starting Pi Node: %s", self.config["node"]["name"])

        # Start transaction manager
        if self.tx_manager:
            self.tx_manager.start()
            logger.info("Transaction manager started")

        # Start alert listener
        if self.alert_listener:
            self.alert_listener.start()
            logger.info("Alert listener started")

        # Sync offline queue if reconnected
        if self.blockchain_client and self.uploader.get_offline_count() > 0:
            logger.info("Syncing %d offline-queued items...", self.uploader.get_offline_count())
            result = self.uploader.sync_offline_queue()
            logger.info("Offline sync: %s", result)

        # Start API server
        self._start_api()

    def _start_api(self):
        """Start the Flask API server."""
        from src.pi_api import create_pi_app

        api_cfg = self.config.get("api", {})
        app = create_pi_app(self)
        app.run(
            host=api_cfg.get("host", "0.0.0.0"),
            port=api_cfg.get("port", 8080),
            debug=False,
        )

    def stop(self):
        """Graceful shutdown."""
        logger.info("Shutting down Pi Node...")
        self._running = False

        if self.tx_manager:
            # Process remaining queue items
            logger.info("Flushing transaction queue...")
            self.tx_manager.process_queue()
            self.tx_manager.stop()

        if self.alert_listener:
            self.alert_listener.stop()

        logger.info("Pi Node stopped")

    def _shutdown_handler(self, signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        self.stop()
        sys.exit(0)

    # ------------------------------------------------------------------
    # Analysis API (called by pi_api)
    # ------------------------------------------------------------------

    def analyze_video(
        self,
        video_path: str,
        ip_address: str = "0.0.0.0",
        country: str = "",
        city: str = "",
        latitude: float = 0.0,
        longitude: float = 0.0,
    ) -> dict:
        """
        Main pipeline: analyze video → upload to blockchain.
        """
        # Step 1: Analyze
        result = self.analyzer.analyze(video_path)
        if result.error:
            return {"error": result.error}

        # Step 2: Upload to blockchain
        upload_result = self.uploader.upload_detection(
            content_hash=result.content_hash,
            perceptual_hash=result.perceptual_hash,
            is_deepfake=result.is_deepfake,
            confidence=result.confidence,
            lipsync_score=result.lipsync_score,
            ip_address=ip_address,
            country=country,
            city=city,
            latitude=latitude,
            longitude=longitude,
            metadata={
                "feature_scores": result.feature_scores,
                "frame_count": result.frame_count,
                "duration": result.duration_seconds,
                "node": self.config["node"]["name"],
            },
        )

        # Step 3: Record spread event if deepfake
        if result.is_deepfake:
            self.uploader.upload_spread_event(
                video_hash=result.content_hash,
                ip_address=ip_address,
                country=country,
                city=city,
                latitude=latitude,
                longitude=longitude,
                platform="Direct Upload",
            )

            # Trigger first detection alert
            self.uploader.trigger_alert("first_detection_alert", {
                "video_hash": result.content_hash,
                "confidence": result.confidence,
                "country": country,
                "ip_address": ip_address,
            })

        # Update stats
        self.cache.increment_stat("videos_analyzed")
        if result.is_deepfake:
            self.cache.increment_stat("deepfakes_found")

        return {
            "content_hash": result.content_hash,
            "perceptual_hash": result.perceptual_hash,
            "is_deepfake": result.is_deepfake,
            "confidence": result.confidence,
            "lipsync_score": result.lipsync_score,
            "feature_scores": result.feature_scores,
            "frame_count": result.frame_count,
            "duration_seconds": result.duration_seconds,
            "blockchain": upload_result,
        }


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main():
    node = PiNode()
    try:
        node.start()
    except KeyboardInterrupt:
        node.stop()


if __name__ == "__main__":
    main()
