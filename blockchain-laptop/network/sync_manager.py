"""
Sync Manager — keeps detection results and caches consistent
between host and client nodes over the P2P network.
"""

import hashlib
import json
import logging
import threading
import time
from typing import Dict, List, Optional

import requests

from network.peer_discovery import PeerDiscovery, PeerInfo

logger = logging.getLogger(__name__)


class SyncManager:
    """
    Periodically syncs detection results, video hashes, and
    alert states between host and connected clients.
    """

    def __init__(self, discovery: PeerDiscovery, config: dict = None):
        config = config or {}
        self.discovery = discovery
        self.sync_interval = config.get("sync_interval_seconds", 60)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._local_state: Dict[str, dict] = {}      # hash -> detection result
        self._sync_log: List[dict] = []
        self._lock = threading.Lock()

    # ---- State Management ----

    def add_result(self, video_hash: str, result: dict):
        """Add a detection result to local state."""
        with self._lock:
            self._local_state[video_hash] = {
                "result": result,
                "timestamp": time.time(),
                "synced_to": [],
            }

    def get_result(self, video_hash: str) -> Optional[dict]:
        """Get a cached detection result."""
        with self._lock:
            entry = self._local_state.get(video_hash)
            return entry["result"] if entry else None

    def get_all_hashes(self) -> List[str]:
        """Get all known video hashes."""
        with self._lock:
            return list(self._local_state.keys())

    # ---- Sync Operations ----

    def sync_with_peer(self, peer: PeerInfo) -> dict:
        """
        Perform a bidirectional sync with a peer.
        
        1. Send our hash list
        2. Receive their hash list
        3. Exchange missing results
        """
        stats = {"sent": 0, "received": 0, "errors": 0}

        try:
            # Get peer's hash list
            resp = requests.post(
                f"{peer.url}/api/sync/hashes",
                json={"hashes": self.get_all_hashes()},
                timeout=10,
            )
            if resp.status_code != 200:
                stats["errors"] += 1
                return stats

            data = resp.json()
            peer_hashes = set(data.get("hashes", []))
            local_hashes = set(self.get_all_hashes())

            # Hashes we have that they don't
            to_send = local_hashes - peer_hashes
            # Hashes they have that we don't
            to_receive = peer_hashes - local_hashes

            # Send our missing results to peer
            for h in to_send:
                result = self.get_result(h)
                if result:
                    try:
                        requests.post(
                            f"{peer.url}/api/sync/result",
                            json={"hash": h, "result": result},
                            timeout=5,
                        )
                        stats["sent"] += 1
                    except Exception:
                        stats["errors"] += 1

            # Request missing results from peer
            if to_receive:
                try:
                    resp = requests.post(
                        f"{peer.url}/api/sync/fetch",
                        json={"hashes": list(to_receive)},
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        results = resp.json().get("results", {})
                        for h, result in results.items():
                            self.add_result(h, result)
                            stats["received"] += 1
                except Exception:
                    stats["errors"] += 1

            self._sync_log.append({
                "peer": peer.node_id,
                "timestamp": time.time(),
                "stats": stats,
            })

        except Exception as e:
            logger.error(f"Sync with {peer.node_id} failed: {e}")
            stats["errors"] += 1

        return stats

    def sync_all(self):
        """Sync with all known peers."""
        peers = self.discovery.get_all_peers()
        total_stats = {"sent": 0, "received": 0, "errors": 0, "peers_synced": 0}

        for peer in peers:
            stats = self.sync_with_peer(peer)
            total_stats["sent"] += stats["sent"]
            total_stats["received"] += stats["received"]
            total_stats["errors"] += stats["errors"]
            if stats["sent"] > 0 or stats["received"] > 0:
                total_stats["peers_synced"] += 1

        logger.info(
            f"Sync complete: {total_stats['peers_synced']} peers, "
            f"sent={total_stats['sent']}, received={total_stats['received']}"
        )
        return total_stats

    # ---- Background Sync ----

    def start(self):
        """Start background sync loop."""
        self._running = True
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()
        logger.info(f"Sync manager started (interval={self.sync_interval}s)")

    def stop(self):
        """Stop the background sync."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Sync manager stopped")

    def _sync_loop(self):
        """Background sync loop."""
        while self._running:
            try:
                self.sync_all()
            except Exception as e:
                logger.error(f"Sync loop error: {e}")

            # Sleep in small increments for responsive shutdown
            for _ in range(int(self.sync_interval)):
                if not self._running:
                    break
                time.sleep(1)

    # ---- Stats ----

    def get_stats(self) -> dict:
        """Get sync statistics."""
        with self._lock:
            return {
                "cached_results": len(self._local_state),
                "sync_log_entries": len(self._sync_log),
                "last_sync": self._sync_log[-1] if self._sync_log else None,
                "running": self._running,
            }
