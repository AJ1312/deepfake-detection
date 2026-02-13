"""
Blockchain Uploader for Raspberry Pi — batch writes with offline queue.

Wraps the shared BlockchainClient + TransactionManager and adds:
  • Local Redis cache lookups (skip known videos)
  • Offline queue for when blockchain is unreachable
  • Batch coalescing tuned for Pi resource limits
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BlockchainUploader:
    """
    Handles uploading detection results and tracking events to Polygon
    from a Raspberry Pi node, with offline fallback.
    """

    def __init__(
        self,
        blockchain_client=None,
        transaction_manager=None,
        local_cache=None,         # LocalCache instance
        offline_queue_dir: str = "/var/lib/deepfake-pi/offline_queue",
        batch_size: int = 10,
    ):
        self.client = blockchain_client
        self.tx_manager = transaction_manager
        self.cache = local_cache
        self.offline_dir = Path(offline_queue_dir)
        self.offline_dir.mkdir(parents=True, exist_ok=True)
        self.batch_size = batch_size
        self._connected = False

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """Test blockchain connectivity."""
        try:
            if self.client and self.client.is_connected():
                self._connected = True
                return True
        except Exception as exc:
            logger.warning("Blockchain connection check failed: %s", exc)
        self._connected = False
        return False

    # ------------------------------------------------------------------
    # Upload detection result
    # ------------------------------------------------------------------

    def upload_detection(
        self,
        content_hash: str,
        perceptual_hash: str,
        is_deepfake: bool,
        confidence: float,
        lipsync_score: float = 0.0,
        ip_address: str = "0.0.0.0",
        country: str = "",
        city: str = "",
        latitude: float = 0.0,
        longitude: float = 0.0,
        metadata: Optional[dict] = None,
    ) -> Dict:
        """
        Upload a video detection result. Falls back to offline queue
        if blockchain is unreachable.
        """
        payload = {
            "content_hash": content_hash,
            "perceptual_hash": perceptual_hash,
            "is_deepfake": is_deepfake,
            "confidence": confidence,
            "lipsync_score": lipsync_score,
            "fact_check_score": 0.0,
            "ip_address": ip_address,
            "country": country,
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
            "metadata": metadata or {},
        }

        # Check local cache first
        if self.cache and self.cache.has_video(content_hash):
            logger.info("Video %s… already known (cached), skipping upload", content_hash[:16])
            return {"status": "cached", "content_hash": content_hash}

        # Try online upload
        if self.check_connection() and self.tx_manager:
            try:
                queue_id = self.tx_manager.enqueue("register_video", payload)
                # Cache locally
                if self.cache:
                    self.cache.set_video(content_hash, payload)
                return {"status": "queued", "queue_id": queue_id, "content_hash": content_hash}
            except Exception as exc:
                logger.error("Failed to enqueue TX: %s", exc)

        # Fallback to offline queue
        return self._save_offline("register_video", payload)

    # ------------------------------------------------------------------
    # Upload spread event
    # ------------------------------------------------------------------

    def upload_spread_event(
        self,
        video_hash: str,
        ip_address: str,
        country: str,
        city: str,
        latitude: float = 0.0,
        longitude: float = 0.0,
        platform: str = "Direct Upload",
        source_url: str = "",
    ) -> Dict:
        """Upload a spread/sighting event."""
        payload = {
            "video_hash": video_hash,
            "ip_address": ip_address,
            "country": country,
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
            "platform": platform,
            "source_url": source_url,
        }

        if self.check_connection() and self.tx_manager:
            try:
                queue_id = self.tx_manager.enqueue("spread_event", payload)
                return {"status": "queued", "queue_id": queue_id}
            except Exception as exc:
                logger.error("Failed to enqueue spread event: %s", exc)

        return self._save_offline("spread_event", payload)

    # ------------------------------------------------------------------
    # Upload alert triggers
    # ------------------------------------------------------------------

    def trigger_alert(self, alert_type: str, payload: dict) -> Dict:
        """Trigger an on-chain alert."""
        if self.check_connection() and self.tx_manager:
            try:
                queue_id = self.tx_manager.enqueue(alert_type, payload)
                return {"status": "queued", "queue_id": queue_id}
            except Exception:
                pass
        return self._save_offline(alert_type, payload)

    # ------------------------------------------------------------------
    # Offline queue
    # ------------------------------------------------------------------

    def _save_offline(self, tx_type: str, payload: dict) -> Dict:
        """Save transaction to offline filesystem queue."""
        entry = {
            "tx_type": tx_type,
            "payload": payload,
            "timestamp": time.time(),
        }
        filename = f"{int(time.time() * 1000)}_{tx_type}.json"
        filepath = self.offline_dir / filename
        filepath.write_text(json.dumps(entry, indent=2))
        logger.info("Saved to offline queue: %s", filename)
        return {"status": "offline", "file": filename}

    def sync_offline_queue(self) -> Dict[str, int]:
        """
        Replay all offline-queued transactions when connection is restored.
        Returns counts of synced/failed items.
        """
        if not self.check_connection() or not self.tx_manager:
            return {"synced": 0, "failed": 0, "remaining": self.get_offline_count()}

        synced = 0
        failed = 0

        for filepath in sorted(self.offline_dir.glob("*.json")):
            try:
                entry = json.loads(filepath.read_text())
                self.tx_manager.enqueue(entry["tx_type"], entry["payload"])
                filepath.unlink()
                synced += 1
            except Exception as exc:
                logger.error("Failed to sync %s: %s", filepath.name, exc)
                failed += 1

        logger.info("Offline sync: %d synced, %d failed", synced, failed)
        return {"synced": synced, "failed": failed, "remaining": self.get_offline_count()}

    def get_offline_count(self) -> int:
        """Get number of items in offline queue."""
        return len(list(self.offline_dir.glob("*.json")))

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict:
        """Get uploader statistics."""
        stats = {
            "connected": self._connected,
            "offline_queue_size": self.get_offline_count(),
        }
        if self.tx_manager:
            stats["tx_queue"] = self.tx_manager.get_stats()
        if self.client and self._connected:
            try:
                stats["wallet_balance_matic"] = self.client.get_balance()
                stats["block_number"] = self.client.get_block_number()
            except Exception:
                pass
        return stats
