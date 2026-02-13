"""
Pi REST API — Flask endpoints for the Pi edge node.
"""

import logging
import os
import tempfile
import time

from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)


def create_pi_app(pi_node) -> Flask:
    """Create Flask app wired to a PiNode instance."""

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = (
        pi_node.config.get("api", {}).get("max_upload_size_mb", 200) * 1024 * 1024
    )

    # ------------------------------------------------------------------
    # Analysis endpoint
    # ------------------------------------------------------------------

    @app.route("/api/analyze", methods=["POST"])
    def analyze_video():
        """Upload and analyse a video file."""
        if "video" not in request.files:
            return jsonify({"error": "No video file provided"}), 400

        video_file = request.files["video"]
        if not video_file.filename:
            return jsonify({"error": "Empty filename"}), 400

        # Get uploader info
        ip_address = request.remote_addr or "0.0.0.0"
        country = request.form.get("country", "")
        city = request.form.get("city", "")
        lat = float(request.form.get("latitude", 0))
        lon = float(request.form.get("longitude", 0))

        # Resolve geo from IP if not provided
        if not country:
            try:
                from shared.utils.geo_utils import resolve_ip_location
                geo = resolve_ip_location(ip_address)
                country = geo.get("country", "")
                city = geo.get("city", "")
                lat = geo.get("lat", 0)
                lon = geo.get("lon", 0)
            except Exception:
                pass

        # Save to temp file
        temp_dir = pi_node.config.get("analysis", {}).get("temp_dir", "/tmp/deepfake-pi")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f"{int(time.time())}_{video_file.filename}")
        video_file.save(temp_path)

        try:
            result = pi_node.analyze_video(
                video_path=temp_path,
                ip_address=ip_address,
                country=country,
                city=city,
                latitude=lat,
                longitude=lon,
            )
            return jsonify(result)
        finally:
            # Cleanup temp file
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Lookup endpoints
    # ------------------------------------------------------------------

    @app.route("/api/video/<content_hash>", methods=["GET"])
    def get_video(content_hash):
        """Look up a video by content hash."""
        # Try local cache first
        cached = pi_node.cache.get_video(content_hash)
        if cached:
            return jsonify({"source": "cache", "data": cached})

        # Try blockchain
        if pi_node.blockchain_client:
            try:
                record = pi_node.blockchain_client.get_video(content_hash)
                return jsonify({"source": "blockchain", "data": record.__dict__})
            except Exception as exc:
                return jsonify({"error": str(exc)}), 404

        return jsonify({"error": "Video not found"}), 404

    @app.route("/api/video/<content_hash>/spread", methods=["GET"])
    def get_spread(content_hash):
        """Get spread events for a video."""
        if not pi_node.blockchain_client:
            return jsonify({"error": "Blockchain not configured"}), 503

        try:
            events = pi_node.blockchain_client.get_spread_events(content_hash)
            return jsonify({
                "video_hash": content_hash,
                "spread_count": len(events),
                "events": [e.__dict__ for e in events],
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/video/<content_hash>/alerts", methods=["GET"])
    def get_alerts(content_hash):
        """Get alerts for a video."""
        if not pi_node.blockchain_client:
            return jsonify({"error": "Blockchain not configured"}), 503

        try:
            alerts = pi_node.blockchain_client.get_video_alerts(content_hash)
            return jsonify({
                "video_hash": content_hash,
                "alert_count": len(alerts),
                "alerts": [a.__dict__ for a in alerts],
            })
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # Stats & health
    # ------------------------------------------------------------------

    @app.route("/api/stats", methods=["GET"])
    def get_stats():
        """Get node statistics."""
        stats = {
            "node": pi_node.config.get("node", {}),
            "cache": pi_node.cache.get_stats(),
            "uploader": pi_node.uploader.get_stats(),
        }
        if pi_node.blockchain_client:
            try:
                stats["blockchain"] = pi_node.blockchain_client.get_stats()
            except Exception:
                stats["blockchain"] = {"error": "unavailable"}
        return jsonify(stats)

    @app.route("/api/health", methods=["GET"])
    def health_check():
        """Health check endpoint."""
        health = pi_node.health_monitor.check()
        status_code = 200 if health.get("status") == "healthy" else 503
        return jsonify(health), status_code

    @app.route("/api/queue/stats", methods=["GET"])
    def queue_stats():
        """Get transaction queue stats."""
        if pi_node.tx_manager:
            return jsonify(pi_node.tx_manager.get_stats())
        return jsonify({"error": "Transaction manager not available"}), 503

    @app.route("/api/queue/sync", methods=["POST"])
    def sync_offline():
        """Manually trigger offline queue sync."""
        result = pi_node.uploader.sync_offline_queue()
        return jsonify(result)

    # ------------------------------------------------------------------
    # Root
    # ------------------------------------------------------------------

    @app.route("/", methods=["GET"])
    def index():
        return jsonify({
            "service": "Deepfake Detection Pi Node",
            "version": pi_node.config.get("node", {}).get("version", "1.0.0"),
            "node": pi_node.config.get("node", {}).get("name", "Pi-Node"),
            "endpoints": [
                "POST /api/analyze",
                "GET  /api/video/<hash>",
                "GET  /api/video/<hash>/spread",
                "GET  /api/video/<hash>/alerts",
                "GET  /api/stats",
                "GET  /api/health",
                "GET  /api/queue/stats",
                "POST /api/queue/sync",
            ],
        })

    return app
