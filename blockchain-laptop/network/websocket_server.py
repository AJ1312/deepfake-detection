"""
WebSocket Server using Flask-SocketIO.

Provides real-time communication between host and client nodes:
- Live detection progress updates
- Network topology changes
- Alert broadcasts
"""

import logging
import time
from typing import Dict, Set

logger = logging.getLogger(__name__)

try:
    from flask_socketio import SocketIO, emit, join_room, leave_room
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    logger.warning("flask-socketio not installed — WebSocket disabled")


class WebSocketServer:
    """
    Manages real-time WebSocket communication.
    """

    def __init__(self, socketio: 'SocketIO' = None):
        self.socketio = socketio
        self.connected_clients: Dict[str, dict] = {}
        self._rooms: Dict[str, Set[str]] = {
            "detection": set(),
            "network": set(),
            "alerts": set(),
        }

        if socketio:
            self._register_handlers()

    def init_app(self, socketio: 'SocketIO'):
        """Initialize with a SocketIO instance (deferred init)."""
        self.socketio = socketio
        self._register_handlers()

    def _register_handlers(self):
        """Register SocketIO event handlers."""
        sio = self.socketio

        @sio.on("connect")
        def handle_connect():
            from flask import request
            sid = request.sid
            logger.info(f"Client connected: {sid}")
            self.connected_clients[sid] = {
                "connected_at": time.time(),
                "rooms": set(),
            }
            emit("welcome", {
                "message": "Connected to Deepfake Detection Host",
                "server_time": time.time(),
            })

        @sio.on("disconnect")
        def handle_disconnect():
            from flask import request
            sid = request.sid
            client = self.connected_clients.pop(sid, None)
            if client:
                for room in client.get("rooms", []):
                    self._rooms.get(room, set()).discard(sid)
            logger.info(f"Client disconnected: {sid}")

        @sio.on("subscribe")
        def handle_subscribe(data):
            from flask import request
            sid = request.sid
            room = data.get("room", "detection")
            if room in self._rooms:
                join_room(room)
                self._rooms[room].add(sid)
                if sid in self.connected_clients:
                    self.connected_clients[sid].setdefault("rooms", set()).add(room)
                emit("subscribed", {"room": room})
                logger.debug(f"Client {sid} subscribed to {room}")

        @sio.on("unsubscribe")
        def handle_unsubscribe(data):
            from flask import request
            sid = request.sid
            room = data.get("room")
            if room in self._rooms:
                leave_room(room)
                self._rooms[room].discard(sid)
                emit("unsubscribed", {"room": room})

        @sio.on("ping_host")
        def handle_ping():
            emit("pong_host", {"time": time.time()})

        @sio.on("auth_challenge")
        def handle_auth(data):
            """Client sends signed wallet challenge for authentication."""
            from flask import request
            sid = request.sid
            wallet = data.get("wallet_address", "")
            signature = data.get("signature", "")
            if sid in self.connected_clients:
                self.connected_clients[sid]["wallet"] = wallet
                self.connected_clients[sid]["authenticated"] = bool(wallet and signature)
            emit("auth_result", {
                "authenticated": bool(wallet and signature),
                "wallet": wallet,
            })

    # ---- Broadcast Methods ----

    def emit_detection_started(self, video_hash: str, filename: str):
        """Broadcast that a detection has started."""
        if self.socketio:
            self.socketio.emit("detection_started", {
                "video_hash": video_hash,
                "filename": filename,
                "timestamp": time.time(),
            }, room="detection")

    def emit_detection_progress(self, video_hash: str, stage: str, progress: float,
                                 details: dict = None):
        """Broadcast detection progress update."""
        if self.socketio:
            self.socketio.emit("detection_progress", {
                "video_hash": video_hash,
                "stage": stage,
                "progress": progress,
                "details": details or {},
                "timestamp": time.time(),
            }, room="detection")

    def emit_detection_complete(self, video_hash: str, result: dict):
        """Broadcast completed detection result."""
        if self.socketio:
            self.socketio.emit("detection_complete", {
                "video_hash": video_hash,
                "result": result,
                "timestamp": time.time(),
            }, room="detection")

    def emit_blockchain_tx(self, tx_hash: str, tx_type: str, status: str):
        """Broadcast blockchain transaction status."""
        if self.socketio:
            self.socketio.emit("blockchain_tx", {
                "tx_hash": tx_hash,
                "tx_type": tx_type,
                "status": status,
                "timestamp": time.time(),
            }, room="detection")

    def emit_peer_joined(self, peer_info: dict):
        """Broadcast that a new peer joined the network."""
        if self.socketio:
            self.socketio.emit("peer_joined", {
                "peer": peer_info,
                "timestamp": time.time(),
            }, room="network")

    def emit_peer_left(self, peer_info: dict):
        """Broadcast that a peer left the network."""
        if self.socketio:
            self.socketio.emit("peer_left", {
                "peer": peer_info,
                "timestamp": time.time(),
            }, room="network")

    def emit_network_status(self, status: dict):
        """Broadcast network status update."""
        if self.socketio:
            self.socketio.emit("network_status", {
                "status": status,
                "timestamp": time.time(),
            }, room="network")

    def emit_alert(self, alert: dict):
        """Broadcast a new alert."""
        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert": alert,
                "timestamp": time.time(),
            }, room="alerts")

    def emit_alert_acknowledged(self, alert_id: str):
        """Broadcast alert acknowledgment."""
        if self.socketio:
            self.socketio.emit("alert_acknowledged", {
                "alert_id": alert_id,
                "timestamp": time.time(),
            }, room="alerts")

    # ---- Stats ----

    def get_stats(self) -> dict:
        """Get WebSocket connection statistics."""
        return {
            "total_connected": len(self.connected_clients),
            "rooms": {room: len(members) for room, members in self._rooms.items()},
            "authenticated": sum(
                1 for c in self.connected_clients.values() if c.get("authenticated")
            ),
        }
