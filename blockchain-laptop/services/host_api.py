"""
Host API — Flask + SocketIO endpoints for the host node.

Serves both the web UI and the REST API that clients connect to.
Includes sync endpoints for peer-to-peer result sharing.
"""

import json
import logging
import os
import tempfile
import time

from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS

logger = logging.getLogger(__name__)

try:
    from flask_socketio import SocketIO
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False


def create_host_app(host_node):
    """
    Factory to create the Flask + SocketIO app for the host node.
    
    Returns (app, socketio).
    """
    template_dir = os.path.join(os.path.dirname(__file__), "..", "web", "templates")
    static_dir = os.path.join(os.path.dirname(__file__), "..", "web", "static")

    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir,
    )
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB
    CORS(app)

    socketio = SocketIO(app, cors_allowed_origins="*") if SOCKETIO_AVAILABLE else None

    # ---- Web UI ----

    @app.route("/")
    def index():
        try:
            return render_template("host_dashboard.html", node=host_node.get_status())
        except Exception:
            return jsonify(host_node.get_status())

    # ---- Detection API ----

    @app.route("/api/analyze", methods=["POST"])
    def analyze_video():
        """Upload and analyze a video."""
        if "video" not in request.files:
            return jsonify({"error": "No video file provided"}), 400

        video_file = request.files["video"]
        if not video_file.filename:
            return jsonify({"error": "Empty filename"}), 400

        source_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        metadata = {}
        if request.form.get("metadata"):
            try:
                metadata = json.loads(request.form["metadata"])
            except json.JSONDecodeError:
                pass

        # Save to temp file
        suffix = os.path.splitext(video_file.filename)[1] or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            video_file.save(tmp)
            tmp_path = tmp.name

        try:
            result = host_node.analyze_video(
                video_path=tmp_path,
                source_ip=source_ip,
                metadata=metadata,
            )
            return jsonify(result)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @app.route("/api/video/<video_hash>", methods=["GET"])
    def get_video(video_hash):
        """Look up a video detection result."""
        result = host_node.lookup_video(video_hash)
        if result:
            return jsonify(result)
        return jsonify({"error": "Video not found"}), 404

    @app.route("/api/video/<video_hash>/spread", methods=["GET"])
    def get_video_spread(video_hash):
        """Get spread events for a video."""
        if host_node.blockchain_client:
            try:
                events = host_node.blockchain_client.get_spread_history(video_hash)
                return jsonify({"hash": video_hash, "spread_events": [e.__dict__ for e in events]})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        return jsonify({"error": "Blockchain not available"}), 503

    @app.route("/api/video/<video_hash>/alerts", methods=["GET"])
    def get_video_alerts(video_hash):
        """Get alerts for a video."""
        if host_node.blockchain_client:
            try:
                alerts = host_node.blockchain_client.get_video_alerts(video_hash)
                return jsonify({"hash": video_hash, "alerts": [a.__dict__ for a in alerts]})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        return jsonify({"error": "Blockchain not available"}), 503

    # ---- Network API ----

    @app.route("/api/network/peers", methods=["GET"])
    def get_peers():
        """Get all connected peers."""
        if host_node.discovery:
            peers = host_node.discovery.get_all_peers()
            return jsonify({
                "peers": [
                    {
                        "node_id": p.node_id,
                        "role": p.role,
                        "address": p.address,
                        "port": p.port,
                        "latency_ms": round(p.latency_ms, 1),
                        "last_seen": p.last_seen,
                    }
                    for p in peers
                ]
            })
        return jsonify({"peers": []})

    @app.route("/api/network/status", methods=["GET"])
    def network_status():
        """Get overall network status."""
        status = {"host": host_node.node_name, "peers": 0}
        if host_node.discovery:
            status["peers"] = len(host_node.discovery.get_all_peers())
        if host_node.ws_server:
            status["websocket"] = host_node.ws_server.get_stats()
        if host_node.sync_manager:
            status["sync"] = host_node.sync_manager.get_stats()
        return jsonify(status)

    # ---- Sync API (peer-to-peer) ----

    @app.route("/api/sync/hashes", methods=["POST"])
    def sync_hashes():
        """Exchange hash lists with a peer."""
        data = request.get_json() or {}
        local_hashes = []
        if host_node.sync_manager:
            local_hashes = host_node.sync_manager.get_all_hashes()
        return jsonify({"hashes": local_hashes})

    @app.route("/api/sync/result", methods=["POST"])
    def sync_result():
        """Receive a detection result from a peer."""
        data = request.get_json() or {}
        h = data.get("hash")
        result = data.get("result")
        if h and result and host_node.sync_manager:
            host_node.sync_manager.add_result(h, result)
            return jsonify({"status": "ok"})
        return jsonify({"error": "Invalid data"}), 400

    @app.route("/api/sync/fetch", methods=["POST"])
    def sync_fetch():
        """Peer requests specific results by hash."""
        data = request.get_json() or {}
        hashes = data.get("hashes", [])
        results = {}
        if host_node.sync_manager:
            for h in hashes[:100]:  # Limit to 100
                r = host_node.sync_manager.get_result(h)
                if r:
                    results[h] = r
        return jsonify({"results": results})

    # ---- Stats & Health ----

    @app.route("/api/stats", methods=["GET"])
    def get_stats():
        """Get node statistics."""
        return jsonify(host_node.get_status())

    @app.route("/api/health", methods=["GET"])
    def health_check():
        """Health check endpoint."""
        try:
            import psutil
            return jsonify({
                "status": "healthy",
                "node": host_node.node_name,
                "role": "host",
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "active_jobs": 0,
                "timestamp": time.time(),
            })
        except ImportError:
            return jsonify({
                "status": "healthy",
                "node": host_node.node_name,
                "role": "host",
                "timestamp": time.time(),
            })

    # ---- Queue Management ----

    @app.route("/api/queue/stats", methods=["GET"])
    def queue_stats():
        """Get TX queue stats."""
        if host_node.tx_manager:
            return jsonify(host_node.tx_manager.get_stats())
        return jsonify({"error": "TX manager not available"}), 503

    @app.route("/api/queue/retry", methods=["POST"])
    def queue_retry():
        """Retry failed transactions."""
        if host_node.tx_manager:
            count = host_node.tx_manager.retry_failed()
            return jsonify({"retried": count})
        return jsonify({"error": "TX manager not available"}), 503

    return app, socketio
