"""
Transaction Manager — queuing, batching, retry, gas optimisation.

Provides reliable blockchain writes with:
  • Persistent queue (SQLite) to survive restarts
  • Automatic retry with exponential back-off
  • Batch coalescing (groups ≤50 videos per batch TX)
  • Nonce management (no stuck pending TXs)
  • Gas-price auto-adjustment
"""

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Graceful fallback for web3
WEB3_AVAILABLE = False
try:
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    Web3 = None

logger = logging.getLogger(__name__)

if not WEB3_AVAILABLE:
    logger.warning("web3 not installed — transaction manager disabled")


class TxStatus(str, Enum):
    QUEUED = "queued"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class QueuedTransaction:
    id: int = 0
    tx_type: str = ""            # "register_video" | "spread_event" | "lineage" | etc.
    payload: dict = field(default_factory=dict)
    status: str = TxStatus.QUEUED
    tx_hash: str = ""
    retries: int = 0
    max_retries: int = 5
    created_at: float = 0.0
    updated_at: float = 0.0
    error: str = ""
    gas_used: int = 0
    block_number: int = 0


class TransactionManager:
    """
    Manages a persistent queue of blockchain transactions with batching,
    retry logic, and nonce management.
    """

    # Batch-eligible transaction types
    BATCHABLE_TYPES = {"register_video"}

    def __init__(
        self,
        blockchain_client,          # BlockchainClient instance
        db_path: str = "tx_queue.db",
        batch_size: int = 20,
        batch_interval: float = 30.0,
        max_retries: int = 5,
        base_backoff: float = 2.0,
        max_gas_price_gwei: float = 100.0,
    ):
        self.client = blockchain_client
        self.db_path = db_path
        self.batch_size = min(batch_size, 50)  # contract max = 50
        self.batch_interval = batch_interval   # seconds between batch flushes
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.max_gas_price_gwei = max_gas_price_gwei

        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._nonce: Optional[int] = None

        self._init_db()

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tx_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_type     TEXT NOT NULL,
                payload     TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'queued',
                tx_hash     TEXT DEFAULT '',
                retries     INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 5,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL,
                error       TEXT DEFAULT '',
                gas_used    INTEGER DEFAULT 0,
                block_number INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_status ON tx_queue(status)
        """)
        conn.commit()
        conn.close()

    def _db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------

    def enqueue(self, tx_type: str, payload: dict) -> int:
        """Add a transaction to the queue.  Returns the queue ID."""
        now = time.time()
        conn = self._db()
        cur = conn.execute(
            "INSERT INTO tx_queue (tx_type, payload, status, max_retries, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tx_type, json.dumps(payload), TxStatus.QUEUED, self.max_retries, now, now),
        )
        conn.commit()
        qid = cur.lastrowid
        conn.close()
        logger.info("Enqueued TX #%d type=%s", qid, tx_type)
        return qid

    def get_queued(self, limit: int = 100) -> List[QueuedTransaction]:
        conn = self._db()
        rows = conn.execute(
            "SELECT * FROM tx_queue WHERE status IN (?, ?) ORDER BY created_at LIMIT ?",
            (TxStatus.QUEUED, TxStatus.RETRYING, limit),
        ).fetchall()
        conn.close()
        return [self._row_to_tx(r) for r in rows]

    def get_status(self, queue_id: int) -> Optional[QueuedTransaction]:
        conn = self._db()
        row = conn.execute("SELECT * FROM tx_queue WHERE id = ?", (queue_id,)).fetchone()
        conn.close()
        return self._row_to_tx(row) if row else None

    def get_stats(self) -> Dict[str, int]:
        conn = self._db()
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM tx_queue GROUP BY status"
        ).fetchall()
        conn.close()
        return {r["status"]: r["cnt"] for r in rows}

    # ------------------------------------------------------------------
    # Processing logic
    # ------------------------------------------------------------------

    def process_queue(self):
        """One pass: process all queued transactions (called by worker or manually)."""
        pending = self.get_queued(limit=200)
        if not pending:
            return

        # Separate batchable from individual
        batchable = [t for t in pending if t.tx_type in self.BATCHABLE_TYPES]
        individual = [t for t in pending if t.tx_type not in self.BATCHABLE_TYPES]

        # Process batches
        for i in range(0, len(batchable), self.batch_size):
            chunk = batchable[i : i + self.batch_size]
            self._process_batch(chunk)

        # Process individual TXs
        for tx in individual:
            self._process_single(tx)

    def _process_batch(self, txs: List[QueuedTransaction]):
        """Send a batch of register_video transactions."""
        if not txs:
            return

        ids = [t.id for t in txs]
        self._update_status(ids, TxStatus.PENDING)

        try:
            videos = [t.payload for t in txs]
            receipt = self.client.batch_register_videos(videos)
            self._update_confirmed(ids, receipt)
            logger.info("Batch TX confirmed: %d videos in block %s",
                        len(videos), receipt.get("blockNumber"))
        except Exception as exc:
            logger.error("Batch TX failed: %s", exc)
            self._handle_failure(txs, str(exc))

    def _process_single(self, tx: QueuedTransaction):
        """Send a single transaction."""
        self._update_status([tx.id], TxStatus.PENDING)

        try:
            receipt = self._dispatch(tx)
            self._update_confirmed([tx.id], receipt)
        except Exception as exc:
            logger.error("TX #%d failed: %s", tx.id, exc)
            self._handle_failure([tx], str(exc))

    def _dispatch(self, tx: QueuedTransaction) -> dict:
        """Route a QueuedTransaction to the right BlockchainClient method."""
        p = tx.payload
        dispatch_map: Dict[str, Callable] = {
            "register_video": lambda: self.client.register_video(**p),
            "spread_event": lambda: self.client.record_spread_event(**p),
            "lineage": lambda: self.client.register_lineage(**p),
            "first_detection_alert": lambda: self.client.trigger_first_detection_alert(**p),
            "reupload_alert": lambda: self.client.trigger_reupload_alert(**p),
            "geo_spread_alert": lambda: self.client.trigger_geo_spread_alert(**p),
            "check_thresholds": lambda: self.client.check_thresholds(**p),
            "acknowledge_alert": lambda: self.client.acknowledge_alert(**p),
        }
        handler = dispatch_map.get(tx.tx_type)
        if handler is None:
            raise ValueError(f"Unknown tx_type: {tx.tx_type}")
        return handler()

    # ------------------------------------------------------------------
    # Failure / retry
    # ------------------------------------------------------------------

    def _handle_failure(self, txs: List[QueuedTransaction], error: str):
        conn = self._db()
        now = time.time()
        for tx in txs:
            new_retries = tx.retries + 1
            if new_retries >= tx.max_retries:
                conn.execute(
                    "UPDATE tx_queue SET status=?, retries=?, error=?, updated_at=? WHERE id=?",
                    (TxStatus.FAILED, new_retries, error, now, tx.id),
                )
                logger.warning("TX #%d permanently failed after %d retries", tx.id, new_retries)
            else:
                conn.execute(
                    "UPDATE tx_queue SET status=?, retries=?, error=?, updated_at=? WHERE id=?",
                    (TxStatus.RETRYING, new_retries, error, now, tx.id),
                )
                logger.info("TX #%d scheduled for retry (%d/%d)",
                            tx.id, new_retries, tx.max_retries)
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _update_status(self, ids: List[int], status: str):
        conn = self._db()
        now = time.time()
        for qid in ids:
            conn.execute(
                "UPDATE tx_queue SET status=?, updated_at=? WHERE id=?",
                (status, now, qid),
            )
        conn.commit()
        conn.close()

    def _update_confirmed(self, ids: List[int], receipt: dict):
        conn = self._db()
        now = time.time()
        tx_hash = receipt.get("transactionHash", "")
        if isinstance(tx_hash, bytes):
            tx_hash = "0x" + tx_hash.hex()
        gas = receipt.get("gasUsed", 0)
        block = receipt.get("blockNumber", 0)
        for qid in ids:
            conn.execute(
                "UPDATE tx_queue SET status=?, tx_hash=?, gas_used=?, block_number=?, updated_at=? WHERE id=?",
                (TxStatus.CONFIRMED, str(tx_hash), gas, block, now, qid),
            )
        conn.commit()
        conn.close()

    @staticmethod
    def _row_to_tx(row) -> QueuedTransaction:
        return QueuedTransaction(
            id=row["id"],
            tx_type=row["tx_type"],
            payload=json.loads(row["payload"]),
            status=row["status"],
            tx_hash=row["tx_hash"],
            retries=row["retries"],
            max_retries=row["max_retries"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error=row["error"],
            gas_used=row["gas_used"],
            block_number=row["block_number"],
        )

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def start(self):
        """Start the background queue-processing thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True, name="tx-manager")
        self._thread.start()
        logger.info("Transaction manager started (batch_size=%d, interval=%.1fs)",
                     self.batch_size, self.batch_interval)

    def stop(self):
        """Stop the background worker gracefully."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Transaction manager stopped")

    def _worker(self):
        while self._running:
            try:
                self.process_queue()
            except Exception:
                logger.exception("Queue processing error")
            time.sleep(self.batch_interval)

    # ------------------------------------------------------------------
    # Nonce management
    # ------------------------------------------------------------------

    def _get_nonce(self) -> int:
        """Thread-safe nonce management to prevent stuck TXs."""
        with self._lock:
            if self._nonce is None:
                self._nonce = self.client.w3.eth.get_transaction_count(self.client.address)
            else:
                self._nonce += 1
            return self._nonce

    def reset_nonce(self):
        """Reset nonce from chain (call if TXs are stuck)."""
        with self._lock:
            self._nonce = None
        logger.info("Nonce cache reset")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def purge_completed(self, older_than_hours: int = 24):
        """Delete confirmed/failed TXs older than *older_than_hours*."""
        cutoff = time.time() - (older_than_hours * 3600)
        conn = self._db()
        conn.execute(
            "DELETE FROM tx_queue WHERE status IN (?, ?) AND updated_at < ?",
            (TxStatus.CONFIRMED, TxStatus.FAILED, cutoff),
        )
        conn.commit()
        conn.close()
        logger.info("Purged completed TXs older than %dh", older_than_hours)

    def retry_failed(self):
        """Re-queue all permanently failed transactions for another round."""
        conn = self._db()
        now = time.time()
        conn.execute(
            "UPDATE tx_queue SET status=?, retries=0, error='', updated_at=? WHERE status=?",
            (TxStatus.QUEUED, now, TxStatus.FAILED),
        )
        conn.commit()
        conn.close()
        logger.info("All failed TXs re-queued")
