"""
Client API — Flask endpoints for the client node.

Provides a local web UI for uploading videos and viewing results,
plus REST endpoints for programmatic access.
"""

import json
import logging
import os
import tempfile
import time

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS

logger = logging.getLogger(__name__)


def create_client_app(client_node):
    """
    Factory to create the client's Flask app.
    """
    template_dir = os.path.join(os.path.dirname(__file__), "..", "web", "templates")
    static_dir = os.path.join(os.path.dirname(__file__), "..", "web", "static")

    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir,
    )
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
    CORS(app)

    # ---- Web UI ----

    @app.route("/")
    def index():
        try:
            return render_template("client_upload.html", node=client_node.get_status())
        except Exception:
            return jsonify(client_node.get_status())

    @app.route("/network")
    def network_page():
        try:
            return render_template("network_map.html", node=client_node.get_status())
        except Exception:
            return jsonify({"page": "network_map", "status": client_node.get_status()})

    # ---- Analysis API ----

    @app.route("/api/analyze", methods=["POST"])
    def analyze_video():
        """Upload a video for analysis (sends to host)."""
        if "video" not in request.files:
            return jsonify({"error": "No video file provided"}), 400

        video_file = request.files["video"]
        if not video_file.filename:
            return jsonify({"error": "Empty filename"}), 400

        metadata = {}
        if request.form.get("metadata"):
            try:
                metadata = json.loads(request.form["metadata"])
            except json.JSONDecodeError:
                pass

        suffix = os.path.splitext(video_file.filename)[1] or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            video_file.save(tmp)
            tmp_path = tmp.name

        try:
            result = client_node.analyze_video(
                video_path=tmp_path,
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
        """Look up a video result."""
        result = client_node.lookup_video(video_hash)
        if result:
            return jsonify(result)
        return jsonify({"error": "Video not found"}), 404

    @app.route("/api/video/<video_hash>/spread", methods=["GET"])
    def get_spread(video_hash):
        """Get spread history for a video."""
        events = client_node.get_video_spread(video_hash)
        return jsonify({"hash": video_hash, "spread_events": events})

    # ---- Host Connection ----

    @app.route("/api/host", methods=["GET"])
    def get_host():
        """Get current host connection info."""
        return jsonify({
            "connected": client_node._host_url is not None,
            "host": client_node.current_host,
        })

    @app.route("/api/host/connect", methods=["POST"])
    def connect_host():
        """Manually connect to a host."""
        data = request.get_json() or {}
        address = data.get("address", "")
        port = data.get("port", 5050)

        if not address:
            return jsonify({"error": "Address required"}), 400

        if client_node.discovery:
            peer = client_node.discovery.add_manual_peer(address, port, role="host")
            client_node._connect_to_host(peer)
            return jsonify({"status": "connected", "url": peer.url})

        return jsonify({"error": "Discovery not available"}), 503

    @app.route("/api/hosts/discover", methods=["POST"])
    def discover_hosts():
        """Trigger a discovery refresh."""
        if client_node.discovery:
            client_node.discovery.refresh_peers()
            hosts = client_node.discovery.get_hosts()
            return jsonify({
                "hosts": [
                    {"node_id": h.node_id, "url": h.url, "latency_ms": round(h.latency_ms, 1)}
                    for h in hosts
                ]
            })
        return jsonify({"hosts": []})

    # ---- Cache ----

    @app.route("/api/cache", methods=["GET"])
    def get_cache():
        """Get cached results summary."""
        return jsonify({
            "count": len(client_node.local_cache),
            "hashes": list(client_node.local_cache.keys())[:100],
        })

    @app.route("/api/cache/clear", methods=["POST"])
    def clear_cache():
        """Clear local cache."""
        count = len(client_node.local_cache)
        client_node.local_cache.clear()
        return jsonify({"cleared": count})

    # ---- Status ----

    @app.route("/api/stats", methods=["GET"])
    def get_stats():
        return jsonify(client_node.get_status())

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "healthy",
            "node": client_node.node_name,
            "role": "client",
            "host_connected": client_node._host_url is not None,
            "timestamp": time.time(),
        })

    return app
