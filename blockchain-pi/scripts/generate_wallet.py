#!/usr/bin/env python3
"""
Generate or display the Pi node wallet.
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.alerts.crypto_authenticator import CryptoAuthenticator


def main():
    parser = argparse.ArgumentParser(description="Generate or display Pi node wallet")
    parser.add_argument("--name", default="Pi-Node-001", help="Node name")
    parser.add_argument("--type", default="pi", help="Node type")
    parser.add_argument("--keystore", default="keystore", help="Keystore directory")
    parser.add_argument("--show", action="store_true", help="Show existing wallet info")
    args = parser.parse_args()

    auth = CryptoAuthenticator(args.keystore)

    if args.show:
        identity = auth.load_identity(args.name)
        if identity:
            print(f"Name:    {identity.name}")
            print(f"Type:    {identity.node_type}")
            print(f"Address: {identity.address}")
            print(f"Key:     {identity.private_key[:8]}…{'*' * 56}")
        else:
            print(f"No wallet found for '{args.name}' in {args.keystore}/")
            sys.exit(1)
    else:
        identity = auth.load_or_create(args.name, args.type)
        print(f"\nWallet Address: {identity.address}")
        print(f"Node Name:      {identity.name}")
        print(f"Node Type:      {identity.node_type}")
        print(f"\nIMPORTANT:")
        print(f"  1. Fund this address with MATIC for gas fees")
        print(f"  2. Authorize this address on smart contracts (owner must call authorizeNode)")
        print(f"  3. Add PRIVATE_KEY to your .env file")


if __name__ == "__main__":
    main()
