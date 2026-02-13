"""
Blockchain Event Listener — monitors on-chain events and dispatches
notifications through the notification service.

Continuously polls for new events from:
  • VideoRegistry  — DeepfakeDetected, VideoRedetected
  • TrackingLedger — SameIPReupload, NewLocationSpread, ViralSpreadWarning
  • AlertManager   — AlertCreated
"""

import logging
import time
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EventSubscription:
    contract_name: str
    event_name: str
    callback: Callable
    last_block: int = 0


class AlertListener:
    """
    Polls Polygon for contract events and routes them to callbacks.
    """

    def __init__(
        self,
        blockchain_client,          # BlockchainClient
        notification_service=None,  # NotificationService (optional)
        poll_interval: float = 10.0,
        max_blocks_per_poll: int = 1000,
    ):
        self.client = blockchain_client
        self.notifier = notification_service
        self.poll_interval = poll_interval
        self.max_blocks_per_poll = max_blocks_per_poll

        self._subscriptions: List[EventSubscription] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Register default subscriptions
        self._register_defaults()

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe(self, contract_name: str, event_name: str, callback: Callable):
        """Register a callback for a specific contract event."""
        sub = EventSubscription(
            contract_name=contract_name,
            event_name=event_name,
            callback=callback,
            last_block=self.client.get_block_number(),
        )
        self._subscriptions.append(sub)
        logger.info("Subscribed to %s.%s", contract_name, event_name)

    def _register_defaults(self):
        """Register built-in handlers for all important events."""
        defaults = [
            ("VideoRegistry", "DeepfakeDetected", self._on_deepfake_detected),
            ("VideoRegistry", "VideoRedetected", self._on_video_redetected),
            ("TrackingLedger", "SameIPReupload", self._on_same_ip_reupload),
            ("TrackingLedger", "NewLocationSpread", self._on_new_location_spread),
            ("TrackingLedger", "ViralSpreadWarning", self._on_viral_spread),
            ("AlertManager", "AlertCreated", self._on_alert_created),
        ]
        current_block = 0
        try:
            current_block = self.client.get_block_number()
        except Exception:
            pass

        for contract_name, event_name, handler in defaults:
            self._subscriptions.append(
                EventSubscription(
                    contract_name=contract_name,
                    event_name=event_name,
                    callback=handler,
                    last_block=current_block,
                )
            )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_deepfake_detected(self, event):
        args = event["args"]
        msg = (
            f"🚨 NEW DEEPFAKE DETECTED\n"
            f"Hash: {args.get('contentHash', b'').hex()[:16]}…\n"
            f"Confidence: {args.get('confidence', 0) / 100:.1f}%\n"
            f"Location: {args.get('city', '?')}, {args.get('country', '?')}"
        )
        logger.warning(msg)
        if self.notifier:
            self.notifier.send_alert("DEEPFAKE_DETECTED", msg, severity="HIGH")

    def _on_video_redetected(self, event):
        args = event["args"]
        count = args.get("detectionCount", 0)
        msg = (
            f"🔁 VIDEO RE-DETECTED (#{count})\n"
            f"Hash: {args.get('contentHash', b'').hex()[:16]}…\n"
            f"New IP: {args.get('newIpHash', b'').hex()[:16]}…"
        )
        logger.info(msg)
        if self.notifier and count >= 3:
            self.notifier.send_alert("VIDEO_REDETECTED", msg, severity="MEDIUM")

    def _on_same_ip_reupload(self, event):
        args = event["args"]
        msg = (
            f"⚠️ SAME IP RE-UPLOAD\n"
            f"Hash: {args.get('videoHash', b'').hex()[:16]}…\n"
            f"IP: {args.get('ipHash', b'').hex()[:16]}…\n"
            f"Upload #{args.get('uploadCount', 0)} | "
            f"Time since first: {args.get('timeSinceFirst', 0)}s"
        )
        logger.warning(msg)
        if self.notifier:
            self.notifier.send_alert("SAME_IP_REUPLOAD", msg, severity="HIGH")

    def _on_new_location_spread(self, event):
        args = event["args"]
        msg = (
            f"🌍 GEO SPREAD DETECTED\n"
            f"Hash: {args.get('videoHash', b'').hex()[:16]}…\n"
            f"From: {args.get('previousCountry', '?')} → {args.get('newCountry', '?')}\n"
            f"Unique countries: {args.get('uniqueCountries', 0)}"
        )
        logger.warning(msg)
        if self.notifier:
            severity = "CRITICAL" if args.get("uniqueCountries", 0) >= 5 else "HIGH"
            self.notifier.send_alert("GEO_SPREAD", msg, severity=severity)

    def _on_viral_spread(self, event):
        args = event["args"]
        msg = (
            f"🔥 VIRAL SPREAD WARNING\n"
            f"Hash: {args.get('videoHash', b'').hex()[:16]}…\n"
            f"Spread events: {args.get('spreadCount', 0)}\n"
            f"Countries: {args.get('uniqueCountries', 0)}"
        )
        logger.critical(msg)
        if self.notifier:
            self.notifier.send_alert("VIRAL_SPREAD", msg, severity="CRITICAL")

    def _on_alert_created(self, event):
        args = event["args"]
        msg = (
            f"📢 ALERT #{args.get('alertId', '?')}\n"
            f"Type: {args.get('alertType', '?')}\n"
            f"Severity: {args.get('severity', '?')}\n"
            f"{args.get('message', '')}"
        )
        logger.info(msg)
        # On-chain alerts are already handled by specific event handlers
        # This one is for logging / audit purposes

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    def poll_once(self):
        """Single poll pass — check all subscriptions for new events."""
        current_block = self.client.get_block_number()

        for sub in self._subscriptions:
            if sub.last_block >= current_block:
                continue

            from_block = sub.last_block + 1
            to_block = min(current_block, from_block + self.max_blocks_per_poll - 1)

            try:
                contract = self._get_contract(sub.contract_name)
                event_filter = getattr(contract.events, sub.event_name)()
                logs = event_filter.get_logs(fromBlock=from_block, toBlock=to_block)

                for log in logs:
                    try:
                        sub.callback(log)
                    except Exception:
                        logger.exception("Error in callback for %s.%s",
                                         sub.contract_name, sub.event_name)

                sub.last_block = to_block

            except Exception:
                logger.exception("Error polling %s.%s (blocks %d–%d)",
                                 sub.contract_name, sub.event_name,
                                 from_block, to_block)

    def _get_contract(self, name: str):
        mapping = {
            "VideoRegistry": self.client.video_registry,
            "TrackingLedger": self.client.tracking_ledger,
            "AlertManager": self.client.alert_manager,
        }
        return mapping[name]

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="alert-listener")
        self._thread.start()
        logger.info("Alert listener started (poll_interval=%.1fs)", self.poll_interval)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=15)
        logger.info("Alert listener stopped")

    def _loop(self):
        while self._running:
            try:
                self.poll_once()
            except Exception:
                logger.exception("Listener poll error")
            time.sleep(self.poll_interval)
