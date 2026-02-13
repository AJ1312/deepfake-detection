"""
Host Node — Full Deepfake Detection + Blockchain + P2P Server.

Runs the complete pipeline (CNN + Gemini), writes results to
Polygon blockchain, serves connected clients via WebSocket,
and registers itself for mDNS auto-discovery.
"""

import hashlib
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# Add project root so we can import the existing detection pipeline
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class HostNode:
    """
    Orchestrates:
      1. Detection pipeline (CNN + Gemini from existing src/)
      2. Blockchain writes (via shared/ Web3 client)
      3. P2P hosting (mDNS + WebSocket)
      4. Alert monitoring
    """

    def __init__(self, config_path: str = "config/host_config.yaml"):
        self.config = self._load_config(config_path)
        self.node_name = self.config.get("node", {}).get("name", "deepfake-host")
        self._running = False

        # --- Detection Pipeline ---
        self.detector = None
        self._init_detector()

        # --- Blockchain ---
        self.blockchain_client = None
        self.tx_manager = None
        self._init_blockchain()

        # --- Networking ---
        self.discovery = None
        self.ws_server = None
        self.sync_manager = None
        self._init_networking()

        # --- Alerts ---
        self.alert_listener = None
        self._init_alerts()

        # Stats
        self.stats = {
            "videos_analyzed": 0,
            "deepfakes_found": 0,
            "blockchain_writes": 0,
            "clients_served": 0,
            "start_time": None,
        }

        logger.info(f"Host node '{self.node_name}' initialized")

    # ---- Initialization ----

    @staticmethod
    def _load_config(path: str) -> dict:
        try:
            with open(path) as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"Config not found: {path}, using defaults")
            return {}

    def _init_detector(self):
        """Initialize the existing detection pipeline."""
        try:
            from src.pipeline.enhanced_detector import EnhancedDeepfakeDetector
            det_config = self.config.get("detection", {})
            model_path = det_config.get("model_path", "models/best_model.pth")
            self.detector = EnhancedDeepfakeDetector(model_path=model_path)
            logger.info("Detection pipeline loaded (CNN + Gemini)")
        except Exception as e:
            logger.error(f"Failed to load detection pipeline: {e}")
            logger.warning("Running without detection — API-only mode")

    def _init_blockchain(self):
        """Initialize blockchain client and TX manager."""
        try:
            from shared.blockchain.web3_client import create_client_from_env
            from shared.blockchain.transaction_manager import TransactionManager

            self.blockchain_client = create_client_from_env()
            if self.blockchain_client is None:
                logger.warning("Blockchain not configured — running in offline mode")
                return
            
            tx_cfg = self.config.get("blockchain", {}).get("tx_manager", {})
            self.tx_manager = TransactionManager(
                client=self.blockchain_client,
                batch_size=tx_cfg.get("batch_size", 20),
                flush_interval=tx_cfg.get("flush_interval_seconds", 30),
            )
            logger.info("Blockchain client + TX manager initialized")
        except Exception as e:
            logger.error(f"Blockchain init failed: {e}")
            logger.warning("Running without blockchain — results will not be on-chain")

    def _init_networking(self):
        """Initialize P2P networking."""
        try:
            from network.peer_discovery import PeerDiscovery
            from network.sync_manager import SyncManager

            net_cfg = self.config.get("networking", {})
            self.discovery = PeerDiscovery(net_cfg)
            self.sync_manager = SyncManager(self.discovery, net_cfg)
            logger.info("P2P networking initialized")
        except Exception as e:
            logger.error(f"Networking init failed: {e}")

    def _init_alerts(self):
        """Initialize alert listener."""
        try:
            from shared.alerts.alert_listener import AlertListener
            if self.blockchain_client:
                self.alert_listener = AlertListener(self.blockchain_client)
                logger.info("Alert listener initialized")
        except Exception as e:
            logger.error(f"Alert listener init failed: {e}")

    # ---- Core Pipeline ----

    def analyze_video(self, video_path: str, source_ip: str = "",
                      metadata: dict = None) -> dict:
        """
        Run the full detection pipeline and write results to blockchain.
        
        Returns a dict with detection result + blockchain TX info.
        """
        start = time.time()
        metadata = metadata or {}

        if not self.detector:
            return {"error": "Detection pipeline not available", "status": "error"}

        # Broadcast start via WebSocket
        video_hash = self._compute_hash(video_path)
        if self.ws_server:
            self.ws_server.emit_detection_started(video_hash, Path(video_path).name)

        # Progress callback
        def on_progress(stage, pct):
            if self.ws_server:
                self.ws_server.emit_detection_progress(video_hash, stage, pct)

        try:
            # Run detection
            on_progress("analyzing", 0.1)
            result = self.detector.analyze_video(video_path)
            on_progress("detection_complete", 0.6)

            # Build result dict
            result_dict = {
                "video_hash": result.video_hash,
                "is_deepfake": result.is_deepfake,
                "confidence": result.confidence,
                "lipsync_score": result.lipsync_score,
                "fact_check_score": result.fact_check_score,
                "gemini_verdict": result.gemini_verdict,
                "detection_method": result.detection_method,
                "processing_time": time.time() - start,
                "node": self.node_name,
            }

            # Write to blockchain
            tx_hash = self._write_to_blockchain(result, source_ip, metadata)
            if tx_hash:
                result_dict["blockchain_tx"] = tx_hash
                self.stats["blockchain_writes"] += 1
                on_progress("blockchain_write", 0.8)

            # Track spread if deepfake
            if result.is_deepfake and source_ip:
                self._record_spread(result.video_hash, source_ip, metadata)

            # Update stats
            self.stats["videos_analyzed"] += 1
            if result.is_deepfake:
                self.stats["deepfakes_found"] += 1

            # Sync to peers
            if self.sync_manager:
                self.sync_manager.add_result(video_hash, result_dict)

            # Broadcast completion
            on_progress("complete", 1.0)
            if self.ws_server:
                self.ws_server.emit_detection_complete(video_hash, result_dict)

            return result_dict

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return {"error": str(e), "status": "error", "video_hash": video_hash}

    def _write_to_blockchain(self, result, source_ip: str, metadata: dict) -> Optional[str]:
        """Write detection result to blockchain via TX manager."""
        if not self.tx_manager:
            return None

        try:
            geo = self._resolve_geo(source_ip)
            self.tx_manager.enqueue(
                tx_type="register_video",
                params={
                    "content_hash": result.video_hash,
                    "perceptual_hash": getattr(result, "perceptual_hash", "") or "",
                    "is_deepfake": result.is_deepfake,
                    "confidence": result.confidence,
                    "lipsync_score": result.lipsync_score,
                    "fact_check_score": result.fact_check_score or 0.0,
                    "latitude": geo.get("latitude", 0.0),
                    "longitude": geo.get("longitude", 0.0),
                    "country_code": geo.get("country_code", "XX"),
                    "ip_address": source_ip,
                    "metadata": json.dumps(metadata) if metadata else "",
                },
            )
            return "queued"
        except Exception as e:
            logger.error(f"Blockchain write failed: {e}")
            return None

    def _record_spread(self, video_hash: str, source_ip: str, metadata: dict):
        """Record a spread event for a deepfake video."""
        if not self.tx_manager:
            return
        try:
            geo = self._resolve_geo(source_ip)
            self.tx_manager.enqueue(
                tx_type="record_spread",
                params={
                    "content_hash": video_hash,
                    "source_ip": source_ip,
                    "latitude": geo.get("latitude", 0.0),
                    "longitude": geo.get("longitude", 0.0),
                    "country_code": geo.get("country_code", "XX"),
                    "platform": metadata.get("platform", "direct_upload"),
                    "url": metadata.get("url", ""),
                    "additional_info": json.dumps(metadata),
                },
            )
        except Exception as e:
            logger.error(f"Spread recording failed: {e}")

    def _resolve_geo(self, ip: str) -> dict:
        """Resolve IP to geographic location."""
        try:
            from src.utils.geo_utils import resolve_ip_location
            return resolve_ip_location(ip) or {}
        except Exception:
            return {}

    @staticmethod
    def _compute_hash(video_path: str) -> str:
        h = hashlib.sha256()
        with open(video_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # ---- Lookup ----

    def lookup_video(self, video_hash: str) -> Optional[dict]:
        """Look up a video by hash (cache → blockchain)."""
        # Check sync cache first
        if self.sync_manager:
            cached = self.sync_manager.get_result(video_hash)
            if cached:
                return cached

        # Check blockchain
        if self.blockchain_client:
            try:
                record = self.blockchain_client.get_video(video_hash)
                if record:
                    return record.__dict__
            except Exception:
                pass
        return None

    # ---- Lifecycle ----

    def start(self):
        """Start all services."""
        import json
        self._running = True
        self.stats["start_time"] = time.time()

        # Register on mDNS
        if self.discovery:
            port = self.config.get("networking", {}).get("api_port", 5050)
            self.discovery.register_host(
                node_id=self.node_name,
                port=port,
                capabilities=["cnn", "gemini", "lipsync", "blockchain"],
            )

        # Start TX manager
        if self.tx_manager:
            self.tx_manager.start()

        # Start sync
        if self.sync_manager:
            self.sync_manager.start()

        # Start alert listener
        if self.alert_listener:
            self.alert_listener.start()

        # Signal handlers
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info(f"Host node '{self.node_name}' started")

        # Start the Flask API (blocking)
        self._start_api()

    def _start_api(self):
        """Start the Flask + SocketIO API server."""
        from services.host_api import create_host_app

        api_cfg = self.config.get("api", {})
        port = api_cfg.get("port", 5050)
        
        app, socketio = create_host_app(self)

        # Link WebSocket server
        from network.websocket_server import WebSocketServer
        self.ws_server = WebSocketServer(socketio)

        logger.info(f"Starting API on port {port}")
        socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)

    def _shutdown(self, signum=None, frame=None):
        """Graceful shutdown."""
        logger.info("Shutting down host node...")
        self._running = False

        if self.tx_manager:
            self.tx_manager.stop()
        if self.sync_manager:
            self.sync_manager.stop()
        if self.alert_listener:
            self.alert_listener.stop()
        if self.discovery:
            self.discovery.stop()

        logger.info("Host node stopped")
        sys.exit(0)

    def get_status(self) -> dict:
        """Get full node status."""
        uptime = time.time() - self.stats["start_time"] if self.stats["start_time"] else 0

        status = {
            "node_name": self.node_name,
            "role": "host",
            "uptime_seconds": int(uptime),
            "stats": self.stats,
            "detector_available": self.detector is not None,
            "blockchain_connected": self.blockchain_client is not None,
        }

        if self.discovery:
            status["peers"] = [
                {"node_id": p.node_id, "role": p.role, "url": p.url}
                for p in self.discovery.get_all_peers()
            ]

        if self.ws_server:
            status["websocket"] = self.ws_server.get_stats()

        if self.sync_manager:
            status["sync"] = self.sync_manager.get_stats()

        return status
