"""
TritioCoin Database Layer
SQLite persistence for balances, UTXOs, mempool, and blockchain state.
"""
import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger("Database")

DATA_DIR = Path("tritiocoin_data")


class Database:
    """SQLite database for persistent blockchain state."""

    def __init__(self, db_path=None):
        if db_path is None:
            self.db_path = DATA_DIR / "tritiocoin.db"
        elif isinstance(db_path, str):
            self.db_path = Path(db_path)
        else:
            self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS blocks (
                height INTEGER PRIMARY KEY,
                hash TEXT UNIQUE NOT NULL,
                previous_hash TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                nonce INTEGER NOT NULL,
                difficulty INTEGER NOT NULL,
                pow_hash TEXT NOT NULL,
                data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                tx_hash TEXT PRIMARY KEY,
                block_height INTEGER,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                amount REAL NOT NULL,
                fee REAL NOT NULL,
                data TEXT,
                timestamp INTEGER NOT NULL,
                signature TEXT,
                signature_mode TEXT DEFAULT 'ecdsa',
                FOREIGN KEY (block_height) REFERENCES blocks(height)
            );

            CREATE TABLE IF NOT EXISTS balances (
                address TEXT PRIMARY KEY,
                balance REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS utxos (
                tx_hash TEXT PRIMARY KEY,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                amount REAL NOT NULL,
                fee REAL NOT NULL,
                block_height INTEGER NOT NULL,
                spent INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS mempool (
                tx_hash TEXT PRIMARY KEY,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                amount REAL NOT NULL,
                fee REAL NOT NULL,
                data TEXT,
                timestamp INTEGER NOT NULL,
                signature TEXT,
                signature_mode TEXT DEFAULT 'ecdsa'
            );

            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tx_sender ON transactions(sender);
            CREATE INDEX IF NOT EXISTS idx_tx_recipient ON transactions(recipient);
            CREATE INDEX IF NOT EXISTS idx_tx_block ON transactions(block_height);
            CREATE INDEX IF NOT EXISTS idx_utxo_sender ON utxos(sender, spent);
        """)
        self.conn.commit()

    def save_block(self, height: int, block_data: dict):
        self.conn.execute("""
            INSERT OR REPLACE INTO blocks (height, hash, previous_hash, timestamp,
                nonce, difficulty, pow_hash, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            height,
            block_data["hash"],
            block_data["header"]["previous_hash"],
            block_data["header"]["timestamp"],
            block_data["header"]["nonce"],
            block_data["header"]["difficulty"],
            block_data.get("pow_hash", ""),
            json.dumps(block_data)
        ))
        self.conn.commit()

    def get_block(self, height: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT data FROM blocks WHERE height = ?", (height,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def get_block_height(self) -> int:
        row = self.conn.execute("SELECT MAX(height) FROM blocks").fetchone()
        return row[0] if row[0] is not None else -1

    def save_transaction(self, tx_data: dict, block_height: int = None):
        # Support both old (amount) and new (amount_satoshis) formats
        amount = tx_data.get("amount_satoshis", tx_data.get("amount", 0))
        fee = tx_data.get("fee_satoshis", tx_data.get("fee", 0))

        self.conn.execute("""
            INSERT OR REPLACE INTO transactions
                (tx_hash, block_height, sender, recipient, amount, fee,
                 data, timestamp, signature, signature_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_data["hash"],
            block_height,
            tx_data["sender"],
            tx_data["recipient"],
            amount,
            fee,
            tx_data.get("data", ""),
            tx_data["timestamp"],
            tx_data.get("signature"),
            tx_data.get("signature_mode", "ecdsa")
        ))
        self.conn.commit()

    def get_balance(self, address: str) -> float:
        row = self.conn.execute(
            "SELECT balance FROM balances WHERE address = ?", (address,)
        ).fetchone()
        return row[0] if row else 0.0

    def set_balance(self, address: str, balance: float):
        self.conn.execute("""
            INSERT OR REPLACE INTO balances (address, balance) VALUES (?, ?)
        """, (address, balance))
        self.conn.commit()

    def get_all_balances(self) -> Dict[str, float]:
        rows = self.conn.execute("SELECT address, balance FROM balances").fetchall()
        return {row[0]: row[1] for row in rows}

    def save_utxo(self, tx_hash: str, sender: str, recipient: str,
                  amount: float, fee: float, block_height: int):
        self.conn.execute("""
            INSERT OR REPLACE INTO utxos
                (tx_hash, sender, recipient, amount, fee, block_height, spent)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (tx_hash, sender, recipient, amount, fee, block_height))
        self.conn.commit()

    def spend_utxo(self, tx_hash: str):
        self.conn.execute(
            "UPDATE utxos SET spent = 1 WHERE tx_hash = ?", (tx_hash,)
        )
        self.conn.commit()

    def get_utxo_balance(self, address: str) -> float:
        row = self.conn.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM utxos
            WHERE recipient = ? AND spent = 0
        """, (address,)).fetchone()
        return row[0]

    def is_utxo_spent(self, tx_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT spent FROM utxos WHERE tx_hash = ?", (tx_hash,)
        ).fetchone()
        return row and row[0] == 1

    def has_utxo(self, tx_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM utxos WHERE tx_hash = ?", (tx_hash,)
        ).fetchone()
        return row is not None

    def get_unspent_utxos(self, address: str) -> List[dict]:
        """Get all unspent transaction outputs for an address."""
        rows = self.conn.execute("""
            SELECT tx_hash, sender, recipient, amount, fee, block_height
            FROM utxos
            WHERE recipient = ? AND spent = 0
            ORDER BY block_height DESC
        """, (address,)).fetchall()
        cols = ["tx_hash", "sender", "recipient", "amount", "fee", "block_height"]
        return [dict(zip(cols, row)) for row in rows]

    def select_utxos(self, address: str, amount: float) -> List[dict]:
        """
        Select UTXOs to cover the desired amount.
        Uses largest-first algorithm for efficiency.
        Returns selected UTXOs and calculates change.
        """
        utxos = self.get_unspent_utxos(address)
        if not utxos:
            return []

        # Sort by amount descending (largest first)
        utxos.sort(key=lambda x: x["amount"], reverse=True)

        selected = []
        total = 0.0

        for utxo in utxos:
            if total >= amount:
                break
            selected.append(utxo)
            total += utxo["amount"]

        return selected if total >= amount else []

    def create_transaction_inputs(self, sender: str, amount: float,
                                  fee: float = 0.001) -> Tuple[List[dict], float]:
        """
        Create transaction inputs from UTXOs.
        Returns (inputs, change) or raises ValueError if insufficient funds.
        """
        needed = amount + fee
        selected = self.select_utxos(sender, needed)

        if not selected:
            raise ValueError(f"Insufficient funds: need {needed:.8f}")

        total_in = sum(utxo["amount"] for utxo in selected)
        change = total_in - needed

        inputs = []
        for utxo in selected:
            inputs.append({
                "tx_hash": utxo["tx_hash"],
                "amount": utxo["amount"],
                "sender": utxo["sender"]
            })

        return inputs, change

    def add_mempool(self, tx_data: dict):
        self.conn.execute("""
            INSERT OR REPLACE INTO mempool
                (tx_hash, sender, recipient, amount, fee, data,
                 timestamp, signature, signature_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_data["hash"],
            tx_data["sender"],
            tx_data["recipient"],
            tx_data["amount"],
            tx_data.get("fee", 0),
            tx_data.get("data", ""),
            tx_data["timestamp"],
            tx_data.get("signature"),
            tx_data.get("signature_mode", "ecdsa")
        ))
        self.conn.commit()

    def remove_mempool(self, tx_hash: str):
        self.conn.execute("DELETE FROM mempool WHERE tx_hash = ?", (tx_hash,))
        self.conn.commit()

    def get_mempool(self) -> List[dict]:
        rows = self.conn.execute(
            "SELECT * FROM mempool ORDER BY fee DESC"
        ).fetchall()
        cols = ["tx_hash", "sender", "recipient", "amount", "fee",
                "data", "timestamp", "signature", "signature_mode"]
        return [dict(zip(cols, row)) for row in rows]

    def mempool_size(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM mempool").fetchone()
        return row[0]

    def clear_mempool(self):
        self.conn.execute("DELETE FROM mempool")
        self.conn.commit()

    def set_metadata(self, key: str, value: str):
        self.conn.execute("""
            INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)
        """, (key, value))
        self.conn.commit()

    def get_metadata(self, key: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM metadata WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def get_total_supply(self) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions "
            "JOIN blocks ON transactions.block_height = blocks.height "
            "WHERE sender = 'COINBASE'"
        ).fetchone()
        return row[0]

    def get_tx_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
        return row[0]

    def get_address_txs(self, address: str) -> List[dict]:
        rows = self.conn.execute("""
            SELECT * FROM transactions
            WHERE sender = ? OR recipient = ?
            ORDER BY block_height DESC
        """, (address, address)).fetchall()
        cols = ["tx_hash", "block_height", "sender", "recipient",
                "amount", "fee", "data", "timestamp", "signature", "signature_mode"]
        return [dict(zip(cols, row)) for row in rows]

    def get_tx_by_hash(self, tx_hash: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM transactions WHERE tx_hash = ?", (tx_hash,)
        ).fetchone()
        if row:
            cols = ["tx_hash", "block_height", "sender", "recipient",
                    "amount", "fee", "data", "timestamp", "signature", "signature_mode"]
            return dict(zip(cols, row))
        return None

    def prune_blocks(self, keep_blocks: int = 1000):
        """
        Remove old blocks to save disk space.
        Keeps the most recent `keep_blocks` blocks.
        Genesis block is always kept.
        """
        height = self.get_block_height()
        if height <= keep_blocks:
            logger.info(f"No pruning needed: {height} blocks (keeping {keep_blocks})")
            return 0

        cutoff = height - keep_blocks
        logger.info(f"Pruning blocks 1-{cutoff} (keeping {keep_blocks} recent blocks)")

        # Delete old blocks
        self.conn.execute("DELETE FROM blocks WHERE height > 0 AND height <= ?", (cutoff,))

        # Delete old transactions
        self.conn.execute("DELETE FROM transactions WHERE block_height <= ? AND block_height > 0", (cutoff,))

        # Delete spent UTXOs from pruned blocks
        self.conn.execute("DELETE FROM utxos WHERE block_height <= ? AND block_height > 0", (cutoff,))

        self.conn.commit()

        # Update metadata
        self.set_metadata("last_prune", str(height))
        self.set_metadata("pruned_until", str(cutoff))

        pruned = cutoff
        logger.info(f"Pruned {pruned} blocks")
        return pruned

    def get_db_size(self) -> dict:
        """Get database size information."""
        size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        block_count = self.get_block_height() + 1
        tx_count = self.get_tx_count()
        utxo_count = self.conn.execute("SELECT COUNT(*) FROM utxos").fetchone()[0]

        return {
            "size_bytes": size_bytes,
            "size_mb": size_bytes / (1024 * 1024),
            "blocks": block_count,
            "transactions": tx_count,
            "utxos": utxo_count,
            "pruned_until": self.get_metadata("pruned_until") or "0"
        }

    def vacuum(self):
        """Reclaim disk space after pruning."""
        self.conn.execute("VACUUM")
        logger.info("Database vacuumed")

    def close(self):
        self.conn.close()
