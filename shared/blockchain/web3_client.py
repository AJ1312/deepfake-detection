"""
Web3 Client for Polygon Blockchain Smart Contract Interactions.

Wraps VideoRegistry, TrackingLedger, and AlertManager contract calls
with Pythonic interfaces, automatic type conversion, and error handling.
"""

import json
import logging
import os
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Graceful fallback for web3 dependencies
WEB3_AVAILABLE = False
try:
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware
    from web3.contract import Contract
    from eth_account import Account
    WEB3_AVAILABLE = True
except ImportError:
    Web3 = None
    ExtraDataToPOAMiddleware = None
    Contract = None
    Account = None

logger = logging.getLogger(__name__)

if not WEB3_AVAILABLE:
    logger.warning("web3/eth_account not installed — blockchain features disabled")

# --------------------------------------------------------------------------
# Data classes for type-safe return values
# --------------------------------------------------------------------------

@dataclass
class VideoRecord:
    content_hash: str
    perceptual_hash: str
    is_deepfake: bool
    confidence: float          # 0.0 – 100.0
    lipsync_score: float
    fact_check_score: float
    first_seen: int            # unix timestamp
    last_seen: int
    detection_count: int
    ip_hash: str
    country: str
    city: str
    latitude: float
    longitude: float
    uploader_node: str
    metadata: dict


@dataclass
class SpreadEvent:
    video_hash: str
    timestamp: int
    ip_hash: str
    country: str
    city: str
    latitude: float
    longitude: float
    platform: str
    source_url: str
    reporter_node: str


@dataclass
class LineageRecord:
    video_hash: str
    parent_hash: str
    generation: int
    mutations: List[str]
    child_hashes: List[str]
    registered_at: int


@dataclass
class Alert:
    id: int
    video_hash: str
    alert_type: str
    severity: str
    message: str
    timestamp: int
    acknowledged: bool
    acknowledged_by: str
    acknowledged_at: int
    trigger_ip_hash: str
    trigger_country: str


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _bytes32(hex_string: str) -> bytes:
    """Convert hex string (with or without 0x prefix) to 32-byte value."""
    hex_string = hex_string.replace("0x", "")
    return bytes.fromhex(hex_string.ljust(64, "0")[:64])


def _to_hex(b: bytes) -> str:
    """Return '0x…' hex string from bytes."""
    return "0x" + b.hex()


def _hash_ip(ip_address: str) -> bytes:
    """SHA-256 hash an IP address into bytes32 for privacy."""
    return _bytes32(hashlib.sha256(ip_address.encode()).hexdigest())


def _scale_confidence(value: float) -> int:
    """Scale 0-100 float to 0-10000 basis points."""
    return max(0, min(10000, int(value * 100)))


def _unscale_confidence(basis_points: int) -> float:
    """Unscale 0-10000 basis points to 0-100 float."""
    return basis_points / 100.0


def _scale_geo(value: float) -> int:
    """Scale latitude/longitude to int * 1 000 000."""
    return int(value * 1_000_000)


def _unscale_geo(scaled: int) -> float:
    """Unscale integer back to lat/long float."""
    return scaled / 1_000_000


# --------------------------------------------------------------------------
# Web3 Client
# --------------------------------------------------------------------------

class BlockchainClient:
    """
    High-level Python client for interacting with the Polygon deepfake
    detection smart contracts (VideoRegistry, TrackingLedger, AlertManager).
    """

    def __init__(
        self,
        rpc_url: str,
        private_key: str,
        contracts_dir: Optional[str] = None,
        video_registry_address: Optional[str] = None,
        tracking_ledger_address: Optional[str] = None,
        alert_manager_address: Optional[str] = None,
        chain_id: int = 137,
        gas_price_gwei: Optional[float] = None,
    ):
        """
        Initialise the blockchain client.

        Args:
            rpc_url: Polygon RPC endpoint (e.g. Alchemy / Infura URL).
            private_key: Hex-encoded private key of the authorised node wallet.
            contracts_dir: Path to compiled contract artifacts (Hardhat
                           ``artifacts/contracts/``).  If *None* fall back to
                           ``deployed-addresses.json`` for addresses and look
                           for ABI files relative to this module.
            video_registry_address: Deployed VideoRegistry address (overrides file).
            tracking_ledger_address: Deployed TrackingLedger address.
            alert_manager_address: Deployed AlertManager address.
            chain_id: Polygon chain ID (137 mainnet, 80002 Amoy testnet).
            gas_price_gwei: Fixed gas price; *None* = auto-estimate.
        """
        # ---- Web3 provider ----
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        # PoA middleware for Polygon
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        if not self.w3.is_connected():
            raise ConnectionError(f"Cannot connect to RPC: {rpc_url}")

        self.chain_id = chain_id
        self.gas_price_gwei = gas_price_gwei
        self.account = Account.from_key(private_key)
        self.address = self.account.address
        logger.info("Blockchain client initialised — wallet %s on chain %s",
                     self.address, chain_id)

        # ---- Contract ABIs and addresses ----
        base = Path(contracts_dir) if contracts_dir else self._default_artifacts_dir()
        addresses = self._load_addresses(
            base, video_registry_address, tracking_ledger_address, alert_manager_address
        )

        self.video_registry: Any = self._load_contract(
            base, "VideoRegistry", addresses["VideoRegistry"]
        )
        self.tracking_ledger: Any = self._load_contract(
            base, "TrackingLedger", addresses["TrackingLedger"]
        )
        self.alert_manager: Any = self._load_contract(
            base, "AlertManager", addresses["AlertManager"]
        )

    # ------------------------------------------------------------------
    # Contract loading helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _default_artifacts_dir() -> Path:
        """Return ``shared/contracts/artifacts/contracts`` relative to this file."""
        return Path(__file__).resolve().parent.parent / "contracts" / "artifacts" / "contracts"

    def _load_addresses(
        self,
        base: Path,
        vr: Optional[str],
        tl: Optional[str],
        am: Optional[str],
    ) -> Dict[str, str]:
        """Resolve deployed contract addresses."""
        addr_file = base.parent / "deployed-addresses.json" if not base.name.endswith(".json") else base
        # Allow overriding with explicit file in contracts root
        contracts_root = Path(__file__).resolve().parent.parent / "contracts"
        addr_file = contracts_root / "deployed-addresses.json"

        saved: Dict[str, str] = {}
        if addr_file.exists():
            saved = json.loads(addr_file.read_text())

        return {
            "VideoRegistry": vr or saved.get("VideoRegistry", ""),
            "TrackingLedger": tl or saved.get("TrackingLedger", ""),
            "AlertManager": am or saved.get("AlertManager", ""),
        }

    def _load_contract(self, base: Path, name: str, address: str) -> Any:
        """Load a compiled contract ABI and return a Contract instance."""
        if not address:
            raise ValueError(f"No address for {name}. Deploy contracts first.")

        # Try Hardhat artifact path
        abi_path = base / f"{name}.sol" / f"{name}.json"
        if not abi_path.exists():
            # Try flat ABI directory
            abi_path = base / f"{name}.json"
        if not abi_path.exists():
            # Try ABI-only directory we ship for convenience
            abi_path = Path(__file__).resolve().parent / "abi" / f"{name}.json"

        if not abi_path.exists():
            raise FileNotFoundError(f"ABI not found for {name} at {abi_path}")

        artifact = json.loads(abi_path.read_text())
        abi = artifact.get("abi", artifact)  # Hardhat bundles abi inside a wrapper
        return self.w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)

    # ------------------------------------------------------------------
    # Transaction helpers
    # ------------------------------------------------------------------

    def _build_tx(self, fn, value: int = 0) -> dict:
        """Build a transaction dict for *fn* (a ContractFunction)."""
        tx = fn.build_transaction({
            "from": self.address,
            "chainId": self.chain_id,
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "value": value,
        })
        if self.gas_price_gwei:
            tx["gasPrice"] = Web3.to_wei(self.gas_price_gwei, "gwei")
        else:
            tx["gasPrice"] = self.w3.eth.gas_price
        return tx

    def _send(self, fn, value: int = 0, wait: bool = True) -> dict:
        """Sign, send, and (optionally) wait for a transaction receipt."""
        tx = self._build_tx(fn, value)
        signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info("TX sent: %s", tx_hash.hex())

        if wait:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt["status"] != 1:
                raise RuntimeError(f"TX failed: {tx_hash.hex()}")
            logger.info("TX confirmed in block %s (gas used: %s)",
                        receipt["blockNumber"], receipt["gasUsed"])
            return dict(receipt)
        return {"transactionHash": tx_hash.hex()}

    # ==================================================================
    #  VideoRegistry interactions
    # ==================================================================

    def register_video(
        self,
        content_hash: str,
        perceptual_hash: str,
        is_deepfake: bool,
        confidence: float,
        lipsync_score: float = 0.0,
        fact_check_score: float = 0.0,
        ip_address: str = "0.0.0.0",
        country: str = "",
        city: str = "",
        latitude: float = 0.0,
        longitude: float = 0.0,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Register (or re-detect) a video on-chain.

        Args:
            content_hash: SHA-256 hex digest of the video file.
            perceptual_hash: DCT perceptual hash string.
            is_deepfake: Whether the video was detected as a deepfake.
            confidence: Confidence score 0–100.
            lipsync_score: Lip-sync score 0–100.
            fact_check_score: Fact-check score 0–100.
            ip_address: Uploader's IP (will be hashed before sending).
            country: Country code / name.
            city: City name.
            latitude: Latitude in degrees.
            longitude: Longitude in degrees.
            metadata: Optional dict serialised to JSON string.

        Returns:
            Transaction receipt dict.
        """
        fn = self.video_registry.functions.registerVideo(
            _bytes32(content_hash),
            perceptual_hash,
            is_deepfake,
            _scale_confidence(confidence),
            _scale_confidence(lipsync_score),
            _scale_confidence(fact_check_score),
            _hash_ip(ip_address),
            country,
            city,
            _scale_geo(latitude),
            _scale_geo(longitude),
            json.dumps(metadata or {}),
        )
        return self._send(fn)

    def batch_register_videos(
        self, videos: List[Dict[str, Any]]
    ) -> dict:
        """
        Register up to 50 videos in a single transaction.

        Each dict in *videos* must contain keys:
            content_hash, perceptual_hash, is_deepfake, confidence,
            ip_address, country, city
        """
        if len(videos) > 50:
            raise ValueError("Batch size exceeds 50")

        fn = self.video_registry.functions.batchRegisterVideos(
            [_bytes32(v["content_hash"]) for v in videos],
            [v["perceptual_hash"] for v in videos],
            [v["is_deepfake"] for v in videos],
            [_scale_confidence(v["confidence"]) for v in videos],
            [_hash_ip(v.get("ip_address", "0.0.0.0")) for v in videos],
            [v.get("country", "") for v in videos],
            [v.get("city", "") for v in videos],
        )
        return self._send(fn)

    def get_video(self, content_hash: str) -> VideoRecord:
        """Fetch a video record from the registry."""
        raw = self.video_registry.functions.getVideo(_bytes32(content_hash)).call()
        return VideoRecord(
            content_hash=_to_hex(raw[0]),
            perceptual_hash=raw[1],
            is_deepfake=raw[2],
            confidence=_unscale_confidence(raw[3]),
            lipsync_score=_unscale_confidence(raw[4]),
            fact_check_score=_unscale_confidence(raw[5]),
            first_seen=raw[6],
            last_seen=raw[7],
            detection_count=raw[8],
            ip_hash=_to_hex(raw[9]),
            country=raw[10],
            city=raw[11],
            latitude=_unscale_geo(raw[12]),
            longitude=_unscale_geo(raw[13]),
            uploader_node=raw[14],
            metadata=json.loads(raw[15]) if raw[15] else {},
        )

    def video_exists(self, content_hash: str) -> bool:
        return self.video_registry.functions.videoExists(_bytes32(content_hash)).call()

    def find_similar_videos(self, perceptual_hash: str) -> List[str]:
        """Return content hashes of videos with the same perceptual hash."""
        raw = self.video_registry.functions.findSimilarVideos(perceptual_hash).call()
        return [_to_hex(h) for h in raw]

    def get_stats(self) -> Dict[str, int]:
        total, deepfakes, authentic = self.video_registry.functions.getStats().call()
        return {"total": total, "deepfakes": deepfakes, "authentic": authentic}

    def get_total_videos(self) -> int:
        return self.video_registry.functions.getTotalVideos().call()

    def get_deepfake_hashes(self) -> List[str]:
        raw = self.video_registry.functions.getDeepfakeHashes().call()
        return [_to_hex(h) for h in raw]

    def get_video_hashes_paginated(self, offset: int, limit: int) -> List[str]:
        raw = self.video_registry.functions.getVideoHashesPaginated(offset, limit).call()
        return [_to_hex(h) for h in raw]

    # ==================================================================
    #  TrackingLedger interactions
    # ==================================================================

    def record_spread_event(
        self,
        video_hash: str,
        ip_address: str,
        country: str,
        city: str,
        latitude: float = 0.0,
        longitude: float = 0.0,
        platform: str = "Direct Upload",
        source_url: str = "",
    ) -> dict:
        """Record a video spread / sighting event on-chain."""
        fn = self.tracking_ledger.functions.recordSpreadEvent(
            _bytes32(video_hash),
            _hash_ip(ip_address),
            country,
            city,
            _scale_geo(latitude),
            _scale_geo(longitude),
            platform,
            source_url,
        )
        return self._send(fn)

    def register_lineage(
        self,
        child_hash: str,
        parent_hash: str,
        generation: int,
        mutations: List[str],
    ) -> dict:
        """Register a parent→child lineage relationship."""
        fn = self.tracking_ledger.functions.registerLineage(
            _bytes32(child_hash),
            _bytes32(parent_hash),
            generation,
            mutations,
        )
        return self._send(fn)

    def get_spread_events(self, video_hash: str) -> List[SpreadEvent]:
        raw = self.tracking_ledger.functions.getSpreadEvents(_bytes32(video_hash)).call()
        return [
            SpreadEvent(
                video_hash=_to_hex(evt[0]),
                timestamp=evt[1],
                ip_hash=_to_hex(evt[2]),
                country=evt[3],
                city=evt[4],
                latitude=_unscale_geo(evt[5]),
                longitude=_unscale_geo(evt[6]),
                platform=evt[7],
                source_url=evt[8],
                reporter_node=evt[9],
            )
            for evt in raw
        ]

    def get_spread_count(self, video_hash: str) -> int:
        return self.tracking_ledger.functions.getSpreadCount(_bytes32(video_hash)).call()

    def get_lineage(self, video_hash: str) -> LineageRecord:
        raw = self.tracking_ledger.functions.getLineage(_bytes32(video_hash)).call()
        return LineageRecord(
            video_hash=_to_hex(raw[0]),
            parent_hash=_to_hex(raw[1]),
            generation=raw[2],
            mutations=list(raw[3]),
            child_hashes=[_to_hex(h) for h in raw[4]],
            registered_at=raw[5],
        )

    def trace_to_origin(self, video_hash: str, max_depth: int = 10) -> List[str]:
        raw = self.tracking_ledger.functions.traceToOrigin(
            _bytes32(video_hash), max_depth
        ).call()
        return [_to_hex(h) for h in raw]

    def get_ip_upload_count(self, video_hash: str, ip_address: str) -> int:
        return self.tracking_ledger.functions.getIPUploadCount(
            _bytes32(video_hash), _hash_ip(ip_address)
        ).call()

    def get_unique_country_count(self, video_hash: str) -> int:
        return self.tracking_ledger.functions.getUniqueCountryCount(
            _bytes32(video_hash)
        ).call()

    # ==================================================================
    #  AlertManager interactions
    # ==================================================================

    def trigger_first_detection_alert(
        self,
        video_hash: str,
        confidence: float,
        country: str,
        ip_address: str,
    ) -> dict:
        """Trigger alert when a new deepfake is first detected."""
        fn = self.alert_manager.functions.triggerFirstDetectionAlert(
            _bytes32(video_hash),
            _scale_confidence(confidence),
            country,
            _hash_ip(ip_address),
        )
        return self._send(fn)

    def trigger_reupload_alert(
        self,
        video_hash: str,
        ip_address: str,
        reupload_count: int,
        country: str,
    ) -> dict:
        """Trigger alert for same-IP re-upload of a flagged video."""
        fn = self.alert_manager.functions.triggerReuploadAlert(
            _bytes32(video_hash),
            _hash_ip(ip_address),
            reupload_count,
            country,
        )
        return self._send(fn)

    def trigger_geo_spread_alert(
        self,
        video_hash: str,
        from_country: str,
        to_country: str,
        unique_countries: int,
    ) -> dict:
        """Trigger alert for geographic spread."""
        fn = self.alert_manager.functions.triggerGeoSpreadAlert(
            _bytes32(video_hash),
            from_country,
            to_country,
            unique_countries,
        )
        return self._send(fn)

    def check_thresholds(
        self,
        video_hash: str,
        detection_count: int,
        spread_count: int,
        unique_countries: int,
    ) -> dict:
        """Check and trigger any threshold-based alerts."""
        fn = self.alert_manager.functions.checkThresholds(
            _bytes32(video_hash),
            detection_count,
            spread_count,
            unique_countries,
        )
        return self._send(fn)

    def acknowledge_alert(self, alert_id: int) -> dict:
        fn = self.alert_manager.functions.acknowledgeAlert(alert_id)
        return self._send(fn)

    def batch_acknowledge_alerts(self, alert_ids: List[int]) -> dict:
        fn = self.alert_manager.functions.batchAcknowledgeAlerts(alert_ids)
        return self._send(fn)

    def get_video_alerts(self, video_hash: str) -> List[Alert]:
        raw = self.alert_manager.functions.getVideoAlerts(_bytes32(video_hash)).call()
        return [self._parse_alert(a) for a in raw]

    def get_alert(self, alert_id: int) -> Alert:
        raw = self.alert_manager.functions.getAlert(alert_id).call()
        return self._parse_alert(raw)

    def get_total_alerts(self) -> int:
        return self.alert_manager.functions.getTotalAlerts().call()

    def get_unacknowledged_count(self) -> int:
        return self.alert_manager.functions.getUnacknowledgedCount().call()

    def get_alerts_paginated(self, offset: int, limit: int) -> List[Alert]:
        raw = self.alert_manager.functions.getAlertsPaginated(offset, limit).call()
        return [self._parse_alert(a) for a in raw]

    # ------------------------------------------------------------------
    # Alert rule management
    # ------------------------------------------------------------------

    def set_global_rules(
        self,
        detection_threshold: int = 100,
        spread_threshold: int = 50,
        country_threshold: int = 5,
        reupload_threshold: int = 3,
        enabled: bool = True,
    ) -> dict:
        fn = self.alert_manager.functions.setGlobalRules(
            detection_threshold, spread_threshold,
            country_threshold, reupload_threshold, enabled,
        )
        return self._send(fn)

    def set_video_rules(
        self,
        video_hash: str,
        detection_threshold: int,
        spread_threshold: int,
        country_threshold: int,
        reupload_threshold: int,
    ) -> dict:
        fn = self.alert_manager.functions.setVideoRules(
            _bytes32(video_hash),
            detection_threshold,
            spread_threshold,
            country_threshold,
            reupload_threshold,
        )
        return self._send(fn)

    def set_alert_cooldown(self, seconds: int) -> dict:
        fn = self.alert_manager.functions.setAlertCooldown(seconds)
        return self._send(fn)

    # ------------------------------------------------------------------
    # AccessControl / admin helpers
    # ------------------------------------------------------------------

    def authorize_node(self, address: str, name: str, node_type: str) -> dict:
        """Authorize a node on all three contracts."""
        receipts = {}
        for label, contract in [
            ("VideoRegistry", self.video_registry),
            ("TrackingLedger", self.tracking_ledger),
            ("AlertManager", self.alert_manager),
        ]:
            fn = contract.functions.authorizeNode(
                Web3.to_checksum_address(address), name, node_type,
            )
            receipts[label] = self._send(fn)
        return receipts

    def deauthorize_node(self, address: str) -> dict:
        receipts = {}
        for label, contract in [
            ("VideoRegistry", self.video_registry),
            ("TrackingLedger", self.tracking_ledger),
            ("AlertManager", self.alert_manager),
        ]:
            fn = contract.functions.deauthorizeNode(
                Web3.to_checksum_address(address),
            )
            receipts[label] = self._send(fn)
        return receipts

    # ------------------------------------------------------------------
    # Event listeners (for off-chain alert service)
    # ------------------------------------------------------------------

    def get_deepfake_detected_events(
        self, from_block: int = 0, to_block: str = "latest"
    ) -> list:
        """Fetch DeepfakeDetected events from VideoRegistry."""
        return self.video_registry.events.DeepfakeDetected().get_logs(
            fromBlock=from_block, toBlock=to_block
        )

    def get_spread_recorded_events(
        self, from_block: int = 0, to_block: str = "latest"
    ) -> list:
        return self.tracking_ledger.events.SpreadEventRecorded().get_logs(
            fromBlock=from_block, toBlock=to_block
        )

    def get_same_ip_reupload_events(
        self, from_block: int = 0, to_block: str = "latest"
    ) -> list:
        return self.tracking_ledger.events.SameIPReupload().get_logs(
            fromBlock=from_block, toBlock=to_block
        )

    def get_alert_created_events(
        self, from_block: int = 0, to_block: str = "latest"
    ) -> list:
        return self.alert_manager.events.AlertCreated().get_logs(
            fromBlock=from_block, toBlock=to_block
        )

    # ------------------------------------------------------------------
    # Network / wallet info
    # ------------------------------------------------------------------

    def get_balance(self) -> float:
        """Return wallet MATIC balance in ether units."""
        wei = self.w3.eth.get_balance(self.address)
        return float(Web3.from_wei(wei, "ether"))

    def get_block_number(self) -> int:
        return self.w3.eth.block_number

    def is_connected(self) -> bool:
        return self.w3.is_connected()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_alert(raw) -> Alert:
        return Alert(
            id=raw[0],
            video_hash=_to_hex(raw[1]),
            alert_type=raw[2],
            severity=raw[3],
            message=raw[4],
            timestamp=raw[5],
            acknowledged=raw[6],
            acknowledged_by=raw[7],
            acknowledged_at=raw[8],
            trigger_ip_hash=_to_hex(raw[9]),
            trigger_country=raw[10],
        )


# --------------------------------------------------------------------------
# Convenience factory
# --------------------------------------------------------------------------

def create_client_from_env() -> Optional['BlockchainClient']:
    """
    Create a BlockchainClient using environment variables:
        POLYGON_RPC_URL, PRIVATE_KEY, CHAIN_ID,
        VIDEO_REGISTRY_ADDRESS, TRACKING_LEDGER_ADDRESS, ALERT_MANAGER_ADDRESS
    
    Returns None if web3 is not available or required env vars are missing.
    """
    if not WEB3_AVAILABLE:
        logger.warning("Cannot create blockchain client — web3 not installed")
        return None
    
    rpc_url = os.environ.get("POLYGON_RPC_URL")
    private_key = os.environ.get("PRIVATE_KEY") or os.environ.get("WALLET_PRIVATE_KEY")
    
    if not rpc_url or not private_key:
        logger.warning("POLYGON_RPC_URL or PRIVATE_KEY not set — blockchain disabled")
        return None
    
    # Check for placeholder values
    if private_key in ("your_private_key_here", "your_64_char_hex_private_key"):
        logger.warning("PRIVATE_KEY contains placeholder — blockchain disabled")
        return None
    
    try:
        return BlockchainClient(
            rpc_url=rpc_url,
            private_key=private_key,
            chain_id=int(os.environ.get("CHAIN_ID", "137")),
            video_registry_address=os.environ.get("VIDEO_REGISTRY_ADDRESS"),
            tracking_ledger_address=os.environ.get("TRACKING_LEDGER_ADDRESS"),
            alert_manager_address=os.environ.get("ALERT_MANAGER_ADDRESS"),
        )
    except Exception as e:
        logger.error(f"Failed to create blockchain client: {e}")
        return None
