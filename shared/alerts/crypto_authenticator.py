"""
Crypto Authenticator — wallet-based identity and message signing.

Provides:
  • Wallet generation (Ethereum-compatible)
  • Message signing and verification using EIP-191
  • Node identity management
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Graceful fallback for crypto dependencies
CRYPTO_AVAILABLE = False
try:
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from web3 import Web3
    CRYPTO_AVAILABLE = True
except ImportError:
    Account = None
    encode_defunct = None
    Web3 = None

logger = logging.getLogger(__name__)

if not CRYPTO_AVAILABLE:
    logger.warning("eth_account/web3 not installed — crypto authenticator disabled")


@dataclass
class NodeIdentity:
    address: str
    private_key: str
    name: str
    node_type: str  # "pi" | "laptop-host" | "laptop-client"


class CryptoAuthenticator:
    """
    Handles wallet-based authentication for blockchain nodes.
    """

    def __init__(self, keystore_path: str = "keystore"):
        self.keystore_dir = Path(keystore_path)
        self.keystore_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Wallet generation
    # ------------------------------------------------------------------

    def generate_wallet(self, name: str, node_type: str) -> NodeIdentity:
        """Generate a new Ethereum wallet and save to keystore."""
        account = Account.create()
        identity = NodeIdentity(
            address=account.address,
            private_key=account.key.hex(),
            name=name,
            node_type=node_type,
        )
        self._save_identity(identity)
        logger.info("Generated wallet %s for %s (%s)", account.address, name, node_type)
        return identity

    def load_identity(self, name: str) -> Optional[NodeIdentity]:
        """Load a saved identity by name."""
        path = self.keystore_dir / f"{name}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return NodeIdentity(**data)

    def load_or_create(self, name: str, node_type: str) -> NodeIdentity:
        """Load existing identity or create a new one."""
        identity = self.load_identity(name)
        if identity:
            logger.info("Loaded existing wallet %s for %s", identity.address, name)
            return identity
        return self.generate_wallet(name, node_type)

    def _save_identity(self, identity: NodeIdentity):
        path = self.keystore_dir / f"{identity.name}.json"
        data = {
            "address": identity.address,
            "private_key": identity.private_key,
            "name": identity.name,
            "node_type": identity.node_type,
        }
        path.write_text(json.dumps(data, indent=2))
        # Restrict permissions on key file
        os.chmod(path, 0o600)
        logger.info("Saved identity to %s", path)

    # ------------------------------------------------------------------
    # Message signing
    # ------------------------------------------------------------------

    @staticmethod
    def sign_message(message: str, private_key: str) -> str:
        """Sign a message using EIP-191 personal sign. Returns hex signature."""
        msg = encode_defunct(text=message)
        signed = Account.sign_message(msg, private_key=private_key)
        return signed.signature.hex()

    @staticmethod
    def verify_signature(message: str, signature: str, expected_address: str) -> bool:
        """Verify that signature was produced by expected_address."""
        try:
            msg = encode_defunct(text=message)
            recovered = Account.recover_message(msg, signature=bytes.fromhex(
                signature.replace("0x", "")
            ))
            return recovered.lower() == expected_address.lower()
        except Exception as exc:
            logger.error("Signature verification failed: %s", exc)
            return False

    @staticmethod
    def sign_detection_result(
        content_hash: str,
        is_deepfake: bool,
        confidence: float,
        private_key: str,
    ) -> str:
        """
        Create a signed attestation of a detection result.

        The signed payload is: f"{content_hash}:{is_deepfake}:{confidence}"
        """
        payload = f"{content_hash}:{is_deepfake}:{confidence:.2f}"
        return CryptoAuthenticator.sign_message(payload, private_key)

    @staticmethod
    def verify_detection_result(
        content_hash: str,
        is_deepfake: bool,
        confidence: float,
        signature: str,
        expected_address: str,
    ) -> bool:
        """Verify a signed detection attestation."""
        payload = f"{content_hash}:{is_deepfake}:{confidence:.2f}"
        return CryptoAuthenticator.verify_signature(payload, signature, expected_address)

    # ------------------------------------------------------------------
    # P2P authentication (for laptop mode)
    # ------------------------------------------------------------------

    @staticmethod
    def create_auth_challenge() -> str:
        """Generate a random challenge string for P2P auth."""
        return os.urandom(32).hex()

    @staticmethod
    def respond_to_challenge(challenge: str, private_key: str) -> str:
        """Sign a challenge to prove identity."""
        return CryptoAuthenticator.sign_message(challenge, private_key)

    @staticmethod
    def verify_challenge_response(
        challenge: str, response: str, expected_address: str
    ) -> bool:
        """Verify that the challenge response was signed by the expected wallet."""
        return CryptoAuthenticator.verify_signature(challenge, response, expected_address)
