#!/usr/bin/env python3
"""
Launcher for the Raspberry Pi Deepfake Detection Node.

Usage:
    python run_pi.py                     # Uses default config
    python run_pi.py --config path.yaml  # Custom config
    python run_pi.py --debug             # Debug logging
"""

import argparse
import logging
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="Start the Pi Deepfake Detection Node")
    parser.add_argument("--config", default="config/pi_config.yaml", help="Path to config file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--port", type=int, default=None, help="Override API port")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Ensure .env is loaded
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Check required env vars
    if not os.environ.get("POLYGON_RPC_URL"):
        logging.warning("POLYGON_RPC_URL not set — blockchain features will use fallback/offline mode")

    from src.pi_node import PiNode

    node = PiNode(config_path=args.config)

    if args.port:
        node.config.setdefault("api", {})["port"] = args.port

    try:
        node.start()
    except KeyboardInterrupt:
        logging.info("Shutting down...")


if __name__ == "__main__":
    main()
