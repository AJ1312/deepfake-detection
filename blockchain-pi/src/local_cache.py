"""
Local Redis Cache for Raspberry Pi — fast lookups to avoid
redundant blockchain writes and video re-analysis.
"""

import json
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LocalCache:
    """
    Redis-backed cache for the Pi node.
    Stores: video hashes, detection results, IP tracking data.
    """

    VIDEO_PREFIX = "video:"
    IP_PREFIX = "ip:"
    STATS_KEY = "node:stats"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        ttl: int = 86400,
        max_entries: int = 10000,
    ):
        try:
            import redis
            self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)
            self.redis.ping()
            self._available = True
            logger.info("Redis cache connected (%s:%d db=%d)", host, port, db)
        except Exception as exc:
            logger.warning("Redis unavailable, using in-memory fallback: %s", exc)
            self._available = False
            self._memory_cache: Dict[str, Any] = {}

        self.ttl = ttl
        self.max_entries = max_entries

    # ------------------------------------------------------------------
    # Video cache
    # ------------------------------------------------------------------

    def has_video(self, content_hash: str) -> bool:
        key = f"{self.VIDEO_PREFIX}{content_hash}"
        if self._available:
            return bool(self.redis.exists(key))
        return key in self._memory_cache

    def get_video(self, content_hash: str) -> Optional[dict]:
        key = f"{self.VIDEO_PREFIX}{content_hash}"
        if self._available:
            data = self.redis.get(key)
            return json.loads(data) if data else None
        return self._memory_cache.get(key)

    def set_video(self, content_hash: str, data: dict):
        key = f"{self.VIDEO_PREFIX}{content_hash}"
        if self._available:
            self.redis.setex(key, self.ttl, json.dumps(data))
        else:
            self._memory_cache[key] = data
            self._enforce_memory_limit()

    def delete_video(self, content_hash: str):
        key = f"{self.VIDEO_PREFIX}{content_hash}"
        if self._available:
            self.redis.delete(key)
        else:
            self._memory_cache.pop(key, None)

    # ------------------------------------------------------------------
    # IP tracking cache
    # ------------------------------------------------------------------

    def record_ip_upload(self, content_hash: str, ip_hash: str) -> int:
        """Increment and return upload count for this IP+video combo."""
        key = f"{self.IP_PREFIX}{content_hash}:{ip_hash}"
        if self._available:
            count = self.redis.incr(key)
            self.redis.expire(key, self.ttl * 7)  # Keep IP data longer
            return count
        count = self._memory_cache.get(key, 0) + 1
        self._memory_cache[key] = count
        return count

    def get_ip_upload_count(self, content_hash: str, ip_hash: str) -> int:
        key = f"{self.IP_PREFIX}{content_hash}:{ip_hash}"
        if self._available:
            val = self.redis.get(key)
            return int(val) if val else 0
        return self._memory_cache.get(key, 0)

    # ------------------------------------------------------------------
    # Node stats
    # ------------------------------------------------------------------

    def increment_stat(self, field: str, amount: int = 1):
        if self._available:
            self.redis.hincrby(self.STATS_KEY, field, amount)
        else:
            stats = self._memory_cache.setdefault(self.STATS_KEY, {})
            stats[field] = stats.get(field, 0) + amount

    def get_stats(self) -> Dict[str, int]:
        if self._available:
            raw = self.redis.hgetall(self.STATS_KEY)
            return {k: int(v) for k, v in raw.items()}
        return dict(self._memory_cache.get(self.STATS_KEY, {}))

    # ------------------------------------------------------------------
    # General
    # ------------------------------------------------------------------

    def get_cache_size(self) -> int:
        if self._available:
            return self.redis.dbsize()
        return len(self._memory_cache)

    def clear(self):
        if self._available:
            self.redis.flushdb()
        else:
            self._memory_cache.clear()

    def _enforce_memory_limit(self):
        """Evict oldest entries when exceeding max_entries (in-memory only)."""
        if len(self._memory_cache) > self.max_entries:
            excess = len(self._memory_cache) - self.max_entries
            keys_to_remove = list(self._memory_cache.keys())[:excess]
            for k in keys_to_remove:
                del self._memory_cache[k]
