#!/usr/bin/env python3
"""
Launch the Client Node.

Usage:
    python run_client.py                     # Auto-discover host via mDNS
    python run_client.py --host 192.168.1.5  # Connect to specific host
    python run_client.py --port 5060         # Override client port
    python run_client.py --debug             # Debug logging
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def main():
    parser = argparse.ArgumentParser(description="Start the Deepfake Detection Client Node")
    parser.add_argument("--config", default="config/client_config.yaml", help="Config file path")
    parser.add_argument("--host", type=str, default=None, help="Host address (e.g. 192.168.1.5:5050)")
    parser.add_argument("--port", type=int, default=None, help="Override client API port")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    from services.client_node import ClientNode

    node = ClientNode(config_path=args.config)

    # Manual host override
    if args.host:
        parts = args.host.split(":")
        address = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 5050
        if node.discovery:
            peer = node.discovery.add_manual_peer(address, port, role="host")
            node._connect_to_host(peer)

    if args.port:
        node.config.setdefault("api", {})["port"] = args.port

    try:
        node.start()
    except KeyboardInterrupt:
        logging.info("Shutting down...")


if __name__ == "__main__":
    main()
