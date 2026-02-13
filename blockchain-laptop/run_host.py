#!/usr/bin/env python3
"""
Launch the Host Node.

Usage:
    python run_host.py                      # Default config
    python run_host.py --config path.yaml   # Custom config
    python run_host.py --port 5050          # Override port
    python run_host.py --debug              # Debug logging
"""

import argparse
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def main():
    parser = argparse.ArgumentParser(description="Start the Deepfake Detection Host Node")
    parser.add_argument("--config", default="config/host_config.yaml", help="Config file path")
    parser.add_argument("--port", type=int, default=None, help="Override API port")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Load .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Launch host
    from services.host_node import HostNode

    node = HostNode(config_path=args.config)

    if args.port:
        node.config.setdefault("api", {})["port"] = args.port

    try:
        node.start()
    except KeyboardInterrupt:
        logging.info("Shutting down...")


if __name__ == "__main__":
    main()
