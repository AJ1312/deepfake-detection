"""
Peer Discovery via mDNS/Zeroconf.

Allows host and client nodes to automatically find each other
on the same local network without manual IP configuration.
"""

import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False
    logger.warning("zeroconf not installed — mDNS discovery disabled")


@dataclass
class PeerInfo:
    """Represents a discovered peer node."""
    node_id: str
    role: str              # "host" or "client"
    address: str
    port: int
    wallet_address: str = ""
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    last_seen: float = 0.0
    latency_ms: float = 0.0

    @property
    def url(self) -> str:
        return f"http://{self.address}:{self.port}"

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.last_seen) > 60


class PeerDiscovery:
    """
    mDNS-based peer discovery for the laptop P2P network.
    
    Host registers itself as a service.
    Client browses for hosts.
    """

    SERVICE_TYPE = "_deepfake-detect._tcp.local."

    def __init__(self, config: dict = None):
        config = config or {}
        self.service_type = config.get("mdns_service_name", self.SERVICE_TYPE)
        self.peers: Dict[str, PeerInfo] = {}
        self._lock = threading.Lock()
        self._zeroconf: Optional[Zeroconf] = None
        self._browser = None
        self._on_peer_found: Optional[Callable] = None
        self._on_peer_lost: Optional[Callable] = None
        self._running = False

    def set_callbacks(self, on_found: Callable = None, on_lost: Callable = None):
        """Set callbacks for peer events."""
        self._on_peer_found = on_found
        self._on_peer_lost = on_lost

    # ---- Host: Register as service ----

    def register_host(self, node_id: str, port: int, wallet_address: str = "",
                      capabilities: List[str] = None):
        """Register this node as a discoverable host service."""
        if not ZEROCONF_AVAILABLE:
            logger.error("zeroconf not available — cannot register")
            return False

        try:
            self._zeroconf = Zeroconf()
            local_ip = self._get_local_ip()

            properties = {
                b"node_id": node_id.encode(),
                b"role": b"host",
                b"wallet": wallet_address.encode(),
                b"version": b"1.0.0",
                b"capabilities": ",".join(capabilities or ["cnn", "gemini", "lipsync"]).encode(),
            }

            service_name = f"{node_id}.{self.service_type}"
            info = ServiceInfo(
                self.service_type,
                service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=port,
                properties=properties,
            )

            self._zeroconf.register_service(info)
            logger.info(f"Registered host service: {service_name} at {local_ip}:{port}")
            self._running = True
            return True

        except Exception as e:
            logger.error(f"Failed to register mDNS service: {e}")
            return False

    # ---- Client: Browse for hosts ----

    def start_discovery(self):
        """Start browsing for available host services."""
        if not ZEROCONF_AVAILABLE:
            logger.error("zeroconf not available — cannot discover")
            return False

        try:
            self._zeroconf = Zeroconf()
            self._browser = ServiceBrowser(
                self._zeroconf,
                self.service_type,
                handlers=[self._on_service_state_change],
            )
            self._running = True
            logger.info(f"Started mDNS discovery for {self.service_type}")
            return True

        except Exception as e:
            logger.error(f"Failed to start discovery: {e}")
            return False

    def _on_service_state_change(self, zeroconf: Zeroconf, service_type: str,
                                  name: str, state_change: ServiceStateChange):
        """Handle mDNS service events."""
        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info:
                self._handle_service_found(info)
        elif state_change == ServiceStateChange.Removed:
            self._handle_service_lost(name)

    def _handle_service_found(self, info: ServiceInfo):
        """Process a newly discovered service."""
        try:
            addresses = info.parsed_addresses()
            if not addresses:
                return

            props = {}
            if info.properties:
                props = {k.decode(): v.decode() for k, v in info.properties.items()}

            node_id = props.get("node_id", info.name)
            peer = PeerInfo(
                node_id=node_id,
                role=props.get("role", "host"),
                address=addresses[0],
                port=info.port,
                wallet_address=props.get("wallet", ""),
                version=props.get("version", "1.0.0"),
                capabilities=props.get("capabilities", "").split(","),
                last_seen=time.time(),
            )

            with self._lock:
                self.peers[node_id] = peer

            logger.info(f"Discovered peer: {peer.node_id} at {peer.url} (role={peer.role})")

            if self._on_peer_found:
                self._on_peer_found(peer)

        except Exception as e:
            logger.error(f"Error processing discovered service: {e}")

    def _handle_service_lost(self, name: str):
        """Handle a service going offline."""
        # Extract node_id from service name
        node_id = name.split(".")[0] if "." in name else name

        with self._lock:
            peer = self.peers.pop(node_id, None)

        if peer:
            logger.info(f"Peer lost: {peer.node_id} at {peer.url}")
            if self._on_peer_lost:
                self._on_peer_lost(peer)

    # ---- Manual Discovery ----

    def add_manual_peer(self, address: str, port: int, role: str = "host") -> PeerInfo:
        """Manually add a peer (for when mDNS is unavailable)."""
        node_id = f"manual-{address}:{port}"
        peer = PeerInfo(
            node_id=node_id,
            role=role,
            address=address,
            port=port,
            last_seen=time.time(),
        )
        with self._lock:
            self.peers[node_id] = peer
        logger.info(f"Added manual peer: {peer.url}")
        return peer

    # ---- Peer Queries ----

    def get_hosts(self) -> List[PeerInfo]:
        """Get all known host peers."""
        with self._lock:
            return [p for p in self.peers.values() if p.role == "host" and not p.is_stale]

    def get_clients(self) -> List[PeerInfo]:
        """Get all known client peers."""
        with self._lock:
            return [p for p in self.peers.values() if p.role == "client"]

    def get_best_host(self) -> Optional[PeerInfo]:
        """Get the host with lowest latency."""
        hosts = self.get_hosts()
        if not hosts:
            return None
        return min(hosts, key=lambda h: h.latency_ms if h.latency_ms > 0 else float("inf"))

    def get_all_peers(self) -> List[PeerInfo]:
        """Get all known peers."""
        with self._lock:
            return list(self.peers.values())

    # ---- Health Ping ----

    def ping_peer(self, peer: PeerInfo) -> float:
        """Ping a peer and return latency in ms. Returns -1 on failure."""
        import requests
        try:
            start = time.time()
            resp = requests.get(f"{peer.url}/api/health", timeout=5)
            latency = (time.time() - start) * 1000
            if resp.status_code == 200:
                peer.latency_ms = latency
                peer.last_seen = time.time()
                return latency
        except Exception:
            pass
        return -1.0

    def refresh_peers(self):
        """Ping all peers and remove stale ones."""
        with self._lock:
            peers_list = list(self.peers.items())

        stale = []
        for node_id, peer in peers_list:
            latency = self.ping_peer(peer)
            if latency < 0:
                stale.append(node_id)

        with self._lock:
            for node_id in stale:
                removed = self.peers.pop(node_id, None)
                if removed:
                    logger.info(f"Removed stale peer: {removed.node_id}")
                    if self._on_peer_lost:
                        self._on_peer_lost(removed)

    # ---- Shutdown ----

    def stop(self):
        """Stop discovery and unregister services."""
        self._running = False
        if self._zeroconf:
            try:
                self._zeroconf.unregister_all_services()
                self._zeroconf.close()
            except Exception:
                pass
            self._zeroconf = None
        logger.info("Peer discovery stopped")

    # ---- Utility ----

    @staticmethod
    def _get_local_ip() -> str:
        """Get the local network IP."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
