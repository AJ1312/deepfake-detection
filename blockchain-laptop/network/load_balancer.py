"""
Load Balancer for distributing detection requests across host nodes.

Supports multiple host nodes if available. Primary use case: 
client picks the best host based on health, latency, and load.
"""

import logging
import random
import threading
import time
from typing import Dict, List, Optional

import requests

from network.peer_discovery import PeerInfo

logger = logging.getLogger(__name__)


class LoadBalancer:
    """
    Distributes analysis requests to the best available host.
    
    Strategies:
      - round_robin: Cycle through hosts
      - least_loaded: Pick host with least active jobs
      - lowest_latency: Pick host with best ping
      - random: Random selection
    """

    def __init__(self, strategy: str = "lowest_latency"):
        self.strategy = strategy
        self._hosts: Dict[str, HostStatus] = {}
        self._rr_index = 0
        self._lock = threading.Lock()

    def update_host(self, peer: PeerInfo, active_jobs: int = 0,
                    max_jobs: int = 10):
        """Update or add a host entry."""
        with self._lock:
            self._hosts[peer.node_id] = HostStatus(
                peer=peer,
                active_jobs=active_jobs,
                max_jobs=max_jobs,
                last_checked=time.time(),
                healthy=True,
            )

    def remove_host(self, node_id: str):
        """Remove a host from the pool."""
        with self._lock:
            self._hosts.pop(node_id, None)

    def select_host(self) -> Optional[PeerInfo]:
        """Select the best host based on current strategy."""
        with self._lock:
            available = [h for h in self._hosts.values()
                         if h.healthy and h.active_jobs < h.max_jobs]

        if not available:
            return None

        if self.strategy == "round_robin":
            return self._round_robin(available)
        elif self.strategy == "least_loaded":
            return self._least_loaded(available)
        elif self.strategy == "lowest_latency":
            return self._lowest_latency(available)
        elif self.strategy == "random":
            return random.choice(available).peer
        else:
            return available[0].peer

    def _round_robin(self, hosts: List['HostStatus']) -> PeerInfo:
        self._rr_index = (self._rr_index + 1) % len(hosts)
        return hosts[self._rr_index].peer

    def _least_loaded(self, hosts: List['HostStatus']) -> PeerInfo:
        return min(hosts, key=lambda h: h.active_jobs).peer

    def _lowest_latency(self, hosts: List['HostStatus']) -> PeerInfo:
        return min(hosts, key=lambda h: h.peer.latency_ms if h.peer.latency_ms > 0 else 9999).peer

    def mark_job_started(self, node_id: str):
        """Increment active job count for a host."""
        with self._lock:
            if node_id in self._hosts:
                self._hosts[node_id].active_jobs += 1

    def mark_job_completed(self, node_id: str):
        """Decrement active job count for a host."""
        with self._lock:
            if node_id in self._hosts:
                self._hosts[node_id].active_jobs = max(0, self._hosts[node_id].active_jobs - 1)

    def health_check_all(self):
        """Check health of all hosts."""
        with self._lock:
            hosts = list(self._hosts.values())

        for host_status in hosts:
            try:
                resp = requests.get(
                    f"{host_status.peer.url}/api/health",
                    timeout=5,
                )
                start = time.time()
                host_status.healthy = resp.status_code == 200
                host_status.peer.latency_ms = (time.time() - start) * 1000
                host_status.peer.last_seen = time.time()

                if resp.status_code == 200:
                    data = resp.json()
                    host_status.active_jobs = data.get("active_jobs", 0)

            except Exception:
                host_status.healthy = False
                logger.warning(f"Host {host_status.peer.node_id} health check failed")

        with self._lock:
            for host_status in hosts:
                self._hosts[host_status.peer.node_id] = host_status

    def get_status(self) -> dict:
        """Get load balancer status."""
        with self._lock:
            return {
                "strategy": self.strategy,
                "total_hosts": len(self._hosts),
                "healthy_hosts": sum(1 for h in self._hosts.values() if h.healthy),
                "hosts": [
                    {
                        "node_id": h.peer.node_id,
                        "url": h.peer.url,
                        "healthy": h.healthy,
                        "active_jobs": h.active_jobs,
                        "max_jobs": h.max_jobs,
                        "latency_ms": round(h.peer.latency_ms, 1),
                    }
                    for h in self._hosts.values()
                ],
            }


class HostStatus:
    """Tracks status of a host node."""

    def __init__(self, peer: PeerInfo, active_jobs: int = 0,
                 max_jobs: int = 10, last_checked: float = 0,
                 healthy: bool = True):
        self.peer = peer
        self.active_jobs = active_jobs
        self.max_jobs = max_jobs
        self.last_checked = last_checked
        self.healthy = healthy
