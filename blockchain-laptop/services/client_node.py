"""
Client Node — connects to a Host for deepfake detection.

Auto-discovers hosts via mDNS, sends videos for analysis,
receives real-time results via WebSocket, and optionally
writes its own tracking data to the blockchain.
"""

import hashlib
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional, Callable

import requests
import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class ClientNode:
    """
    Client node in the P2P deepfake detection network.
    
    1. Discovers hosts via mDNS (or manual config)
    2. Sends videos to host for analysis
    3. Receives real-time updates via WebSocket
    4. Caches results locally
    5. Optionally writes tracking data to blockchain
    """

    def __init__(self, config_path: str = "config/client_config.yaml"):
        self.config = self._load_config(config_path)
        self.node_name = self.config.get("node", {}).get("name", "deepfake-client")
        self._running = False

        # Current host connection
        self.current_host: Optional[dict] = None
        self._host_url: Optional[str] = None

        # Services
        self.discovery = None
        self.load_balancer = None
        self.blockchain_client = None
        self.local_cache = {}  # Simple in-memory cache
        self._ws_client = None

        # Callbacks
        self._on_result: Optional[Callable] = None
        self._on_progress: Optional[Callable] = None
        self._on_alert: Optional[Callable] = None

        self._init_discovery()
        self._init_blockchain()

        # Stats
        self.stats = {
            "videos_submitted": 0,
            "results_received": 0,
            "deepfakes_found": 0,
            "host_switches": 0,
            "start_time": None,
        }

        logger.info(f"Client node '{self.node_name}' initialized")

    @staticmethod
    def _load_config(path: str) -> dict:
        try:
            with open(path) as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"Config not found: {path}")
            return {}

    def _init_discovery(self):
        """Initialize peer discovery."""
        try:
            from network.peer_discovery import PeerDiscovery
            from network.load_balancer import LoadBalancer

            disc_cfg = self.config.get("discovery", {})
            self.discovery = PeerDiscovery(disc_cfg)
            self.load_balancer = LoadBalancer(strategy="lowest_latency")

            # Set callbacks
            self.discovery.set_callbacks(
                on_found=self._on_host_found,
                on_lost=self._on_host_lost,
            )

            # Manual host override
            manual = disc_cfg.get("manual_host", "")
            if manual and ":" in manual:
                host, port = manual.rsplit(":", 1)
                peer = self.discovery.add_manual_peer(host, int(port), role="host")
                self.load_balancer.update_host(peer)
                self._host_url = peer.url
                logger.info(f"Using manual host: {self._host_url}")

        except Exception as e:
            logger.error(f"Discovery init failed: {e}")

    def _init_blockchain(self):
        """Initialize optional blockchain client for tracking."""
        bc_cfg = self.config.get("blockchain", {})
        if not bc_cfg.get("enabled", False):
            return

        try:
            from shared.blockchain.web3_client import create_client_from_env
            self.blockchain_client = create_client_from_env()
            if self.blockchain_client:
                logger.info("Blockchain client initialized (client-side tracking)")
            else:
                logger.warning("Blockchain not configured — tracking disabled")
        except Exception as e:
            logger.error(f"Blockchain init failed: {e}")

    # ---- Host Discovery Callbacks ----

    def _on_host_found(self, peer):
        """Called when a new host is discovered via mDNS."""
        logger.info(f"Host discovered: {peer.node_id} at {peer.url}")
        if self.load_balancer:
            self.load_balancer.update_host(peer)

        # Connect to first available host if we don't have one
        if not self._host_url:
            self._connect_to_host(peer)

    def _on_host_lost(self, peer):
        """Called when a host goes offline."""
        logger.warning(f"Host lost: {peer.node_id}")
        if self.load_balancer:
            self.load_balancer.remove_host(peer.node_id)

        # If it was our current host, find another
        if self._host_url == peer.url:
            self._host_url = None
            self.current_host = None
            self._find_new_host()

    def _connect_to_host(self, peer):
        """Connect to a host and start WebSocket."""
        self._host_url = peer.url
        self.current_host = {
            "node_id": peer.node_id,
            "url": peer.url,
            "connected_at": time.time(),
        }
        logger.info(f"Connected to host: {peer.url}")

        # Start WebSocket connection
        self._connect_websocket(peer.url)

    def _find_new_host(self):
        """Find and connect to a new host."""
        if not self.load_balancer:
            return

        best = self.load_balancer.select_host()
        if best:
            self._connect_to_host(best)
            self.stats["host_switches"] += 1
        else:
            logger.warning("No hosts available")

    def _connect_websocket(self, host_url: str):
        """Connect to host's WebSocket for real-time updates."""
        try:
            import socketio as sio_client
            self._ws_client = sio_client.Client()

            @self._ws_client.on("detection_progress")
            def on_progress(data):
                if self._on_progress:
                    self._on_progress(data)

            @self._ws_client.on("detection_complete")
            def on_complete(data):
                result = data.get("result", {})
                video_hash = data.get("video_hash", "")
                self.local_cache[video_hash] = result
                self.stats["results_received"] += 1
                if result.get("is_deepfake"):
                    self.stats["deepfakes_found"] += 1
                if self._on_result:
                    self._on_result(result)

            @self._ws_client.on("new_alert")
            def on_alert(data):
                if self._on_alert:
                    self._on_alert(data)

            ws_url = host_url.replace("http://", "ws://")
            self._ws_client.connect(host_url, transports=["websocket"])
            self._ws_client.emit("subscribe", {"room": "detection"})
            self._ws_client.emit("subscribe", {"room": "alerts"})
            logger.info(f"WebSocket connected to {host_url}")

        except Exception as e:
            logger.warning(f"WebSocket connection failed: {e} — will use polling")
            self._ws_client = None

    # ---- Analysis API ----

    def analyze_video(self, video_path: str, metadata: dict = None) -> dict:
        """
        Send a video to the host for analysis.
        
        Falls back to polling if WebSocket is unavailable.
        """
        if not self._host_url:
            self._find_new_host()
            if not self._host_url:
                return {"error": "No host available", "status": "error"}

        metadata = metadata or {}
        self.stats["videos_submitted"] += 1

        try:
            with open(video_path, "rb") as f:
                files = {"video": (Path(video_path).name, f)}
                data = {}
                if metadata:
                    data["metadata"] = json.dumps(metadata)

                resp = requests.post(
                    f"{self._host_url}/api/analyze",
                    files=files,
                    data=data,
                    timeout=120,  # Detection can take a while
                )

            if resp.status_code == 200:
                result = resp.json()
                video_hash = result.get("video_hash", "")
                self.local_cache[video_hash] = result
                self.stats["results_received"] += 1
                if result.get("is_deepfake"):
                    self.stats["deepfakes_found"] += 1

                # Optionally write client-side tracking
                if self.blockchain_client and result.get("is_deepfake"):
                    self._record_client_tracking(result)

                return result
            else:
                return {"error": f"Host returned {resp.status_code}", "status": "error"}

        except requests.exceptions.ConnectionError:
            logger.warning(f"Host {self._host_url} unreachable — finding new host")
            self._host_url = None
            self._find_new_host()
            return {"error": "Host unreachable", "status": "error"}

        except Exception as e:
            logger.error(f"Analysis request failed: {e}")
            return {"error": str(e), "status": "error"}

    def _record_client_tracking(self, result: dict):
        """Write client-side spread tracking to blockchain."""
        if not self.blockchain_client:
            return
        try:
            self.blockchain_client.record_spread_event(
                content_hash=result["video_hash"],
                source_ip="client",
                latitude=0.0,
                longitude=0.0,
                country_code="XX",
                platform="client_upload",
                url="",
                additional_info=json.dumps({"client": self.node_name}),
            )
        except Exception as e:
            logger.error(f"Client tracking write failed: {e}")

    # ---- Lookup ----

    def lookup_video(self, video_hash: str) -> Optional[dict]:
        """Look up a video — local cache first, then host."""
        # Local cache
        if video_hash in self.local_cache:
            return self.local_cache[video_hash]

        # Ask host
        if self._host_url:
            try:
                resp = requests.get(f"{self._host_url}/api/video/{video_hash}", timeout=10)
                if resp.status_code == 200:
                    result = resp.json()
                    self.local_cache[video_hash] = result
                    return result
            except Exception:
                pass

        return None

    def get_video_spread(self, video_hash: str) -> list:
        """Get spread history from host."""
        if self._host_url:
            try:
                resp = requests.get(f"{self._host_url}/api/video/{video_hash}/spread", timeout=10)
                if resp.status_code == 200:
                    return resp.json().get("spread_events", [])
            except Exception:
                pass
        return []

    # ---- Callbacks ----

    def on_result(self, callback: Callable):
        """Set callback for detection results."""
        self._on_result = callback

    def on_progress(self, callback: Callable):
        """Set callback for progress updates."""
        self._on_progress = callback

    def on_alert(self, callback: Callable):
        """Set callback for alerts."""
        self._on_alert = callback

    # ---- Lifecycle ----

    def start(self):
        """Start the client node."""
        self._running = True
        self.stats["start_time"] = time.time()

        # Start discovery
        if self.discovery:
            self.discovery.start_discovery()

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info(f"Client node '{self.node_name}' started")

        # Start client API
        self._start_api()

    def _start_api(self):
        """Start the client's local Flask server."""
        from services.client_api import create_client_app

        api_cfg = self.config.get("api", {})
        port = api_cfg.get("port", 5060)

        app = create_client_app(self)
        logger.info(f"Client API on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False)

    def _shutdown(self, signum=None, frame=None):
        """Graceful shutdown."""
        logger.info("Shutting down client node...")
        self._running = False

        if self._ws_client:
            try:
                self._ws_client.disconnect()
            except Exception:
                pass
        if self.discovery:
            self.discovery.stop()

        sys.exit(0)

    def get_status(self) -> dict:
        """Get client status."""
        uptime = time.time() - self.stats["start_time"] if self.stats["start_time"] else 0
        return {
            "node_name": self.node_name,
            "role": "client",
            "uptime_seconds": int(uptime),
            "host_connected": self._host_url is not None,
            "current_host": self.current_host,
            "stats": self.stats,
            "cached_results": len(self.local_cache),
            "blockchain_enabled": self.blockchain_client is not None,
        }
