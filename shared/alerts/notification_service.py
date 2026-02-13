"""
Notification Service — multi-channel alert delivery.

Channels:
  • Telegram Bot
  • Email (SMTP)
  • Discord Webhook
  • Console / log (always active)
"""

import json
import logging
import os
import smtplib
import threading
from collections import deque
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Deque, Dict, List, Optional
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


@dataclass
class NotificationRecord:
    channel: str
    alert_type: str
    severity: str
    message: str
    timestamp: float
    success: bool
    error: str = ""


class NotificationService:
    """
    Sends alert notifications through configured channels.
    """

    SEVERITY_PRIORITY = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

    def __init__(
        self,
        telegram_bot_token: str = "",
        telegram_chat_id: str = "",
        discord_webhook_url: str = "",
        email_smtp_host: str = "",
        email_smtp_port: int = 587,
        email_username: str = "",
        email_password: str = "",
        email_from: str = "",
        email_to: str = "",
        min_severity: str = "MEDIUM",
        history_size: int = 1000,
    ):
        self.telegram_token = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.discord_url = discord_webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        self.email_host = email_smtp_host or os.getenv("SMTP_HOST", "")
        self.email_port = email_smtp_port
        self.email_user = email_username or os.getenv("SMTP_USER", "")
        self.email_pass = email_password or os.getenv("SMTP_PASSWORD", "")
        self.email_from = email_from or os.getenv("ALERT_EMAIL_FROM", "")
        self.email_to = email_to or os.getenv("ALERT_EMAIL_TO", "")
        self.min_severity = min_severity

        self._history: Deque[NotificationRecord] = deque(maxlen=history_size)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_alert(self, alert_type: str, message: str, severity: str = "MEDIUM"):
        """
        Send alert through all configured channels (async).
        """
        if self.SEVERITY_PRIORITY.get(severity, 0) < self.SEVERITY_PRIORITY.get(self.min_severity, 0):
            logger.debug("Alert suppressed (severity %s < %s)", severity, self.min_severity)
            return

        # Always log
        log_fn = {
            "LOW": logger.info,
            "MEDIUM": logger.warning,
            "HIGH": logger.error,
            "CRITICAL": logger.critical,
        }.get(severity, logger.warning)
        log_fn("[%s] %s — %s", severity, alert_type, message)

        # Fire-and-forget for external channels
        t = threading.Thread(
            target=self._dispatch_all,
            args=(alert_type, message, severity),
            daemon=True,
        )
        t.start()

    def get_history(self, limit: int = 50) -> List[NotificationRecord]:
        with self._lock:
            return list(self._history)[-limit:]

    def get_channel_status(self) -> Dict[str, bool]:
        """Return which channels are configured."""
        return {
            "telegram": bool(self.telegram_token and self.telegram_chat_id),
            "discord": bool(self.discord_url),
            "email": bool(self.email_host and self.email_to),
            "console": True,
        }

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch_all(self, alert_type: str, message: str, severity: str):
        import time

        if self.telegram_token and self.telegram_chat_id:
            self._send_telegram(alert_type, message, severity, time.time())

        if self.discord_url:
            self._send_discord(alert_type, message, severity, time.time())

        if self.email_host and self.email_to:
            self._send_email(alert_type, message, severity, time.time())

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------

    def _send_telegram(self, alert_type: str, message: str, severity: str, ts: float):
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            text = f"*[{severity}] {alert_type}*\n\n{message}"
            payload = json.dumps({
                "chat_id": self.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }).encode()

            req = Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=10) as resp:
                resp.read()

            self._record("telegram", alert_type, severity, message, ts, True)
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            self._record("telegram", alert_type, severity, message, ts, False, str(exc))

    # ------------------------------------------------------------------
    # Discord
    # ------------------------------------------------------------------

    def _send_discord(self, alert_type: str, message: str, severity: str, ts: float):
        try:
            color_map = {"LOW": 0x3498DB, "MEDIUM": 0xF39C12, "HIGH": 0xE74C3C, "CRITICAL": 0x8E44AD}
            payload = json.dumps({
                "embeds": [{
                    "title": f"[{severity}] {alert_type}",
                    "description": message,
                    "color": color_map.get(severity, 0x95A5A6),
                }]
            }).encode()

            req = Request(self.discord_url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=10) as resp:
                resp.read()

            self._record("discord", alert_type, severity, message, ts, True)
        except Exception as exc:
            logger.error("Discord send failed: %s", exc)
            self._record("discord", alert_type, severity, message, ts, False, str(exc))

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------

    def _send_email(self, alert_type: str, message: str, severity: str, ts: float):
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{severity}] Deepfake Alert: {alert_type}"
            msg["From"] = self.email_from
            msg["To"] = self.email_to

            body = (
                f"<h2 style='color:{'red' if severity in ('HIGH','CRITICAL') else 'orange'}'>"
                f"[{severity}] {alert_type}</h2>"
                f"<pre>{message}</pre>"
                f"<hr><small>Deepfake Detection Blockchain System</small>"
            )
            msg.attach(MIMEText(body, "html"))

            with smtplib.SMTP(self.email_host, self.email_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if self.email_user:
                    server.login(self.email_user, self.email_pass)
                server.sendmail(self.email_from, [self.email_to], msg.as_string())

            self._record("email", alert_type, severity, message, ts, True)
        except Exception as exc:
            logger.error("Email send failed: %s", exc)
            self._record("email", alert_type, severity, message, ts, False, str(exc))

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record(
        self, channel: str, alert_type: str, severity: str,
        message: str, ts: float, success: bool, error: str = ""
    ):
        with self._lock:
            self._history.append(NotificationRecord(
                channel=channel,
                alert_type=alert_type,
                severity=severity,
                message=message[:200],
                timestamp=ts,
                success=success,
                error=error,
            ))
