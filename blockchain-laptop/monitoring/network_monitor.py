"""
Network Monitor — tracks P2P network health and metrics.
"""

import logging
import threading
import time
from typing import Dict, List

logger = logging.getLogger(__name__)


class NetworkMonitor:
    """
    Periodically checks peer health, collects latency metrics,
    and detects network issues.
    """

    def __init__(self, discovery, config: dict = None):
        config = config or {}
        self.discovery = discovery
        self.check_interval = config.get("check_interval_seconds", 30)
        self._running = False
        self._thread = None
        self._history: List[dict] = []

    def start(self):
        """Start monitoring loop."""
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Network monitor started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _monitor_loop(self):
        while self._running:
            try:
                snapshot = self._take_snapshot()
                self._history.append(snapshot)
                # Keep last 1000 snapshots
                if len(self._history) > 1000:
                    self._history = self._history[-500:]
            except Exception as e:
                logger.error(f"Monitor error: {e}")

            for _ in range(int(self.check_interval)):
                if not self._running:
                    break
                time.sleep(1)

    def _take_snapshot(self) -> dict:
        """Take a network health snapshot."""
        if self.discovery:
            self.discovery.refresh_peers()

        peers = self.discovery.get_all_peers() if self.discovery else []
        hosts = [p for p in peers if p.role == "host"]
        clients = [p for p in peers if p.role == "client"]

        latencies = [p.latency_ms for p in peers if p.latency_ms > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        return {
            "timestamp": time.time(),
            "total_peers": len(peers),
            "hosts": len(hosts),
            "clients": len(clients),
            "avg_latency_ms": round(avg_latency, 1),
            "max_latency_ms": round(max(latencies), 1) if latencies else 0,
            "stale_peers": sum(1 for p in peers if p.is_stale),
        }

    def get_current(self) -> dict:
        """Get latest snapshot."""
        return self._history[-1] if self._history else self._take_snapshot()

    def get_history(self, count: int = 50) -> List[dict]:
        """Get recent history."""
        return self._history[-count:]
