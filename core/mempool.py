"""
TritioCoin Mempool
- SQLite persistent storage
- Real-time balance validation
- Fee-based prioritization
- Satoshis for precision
"""
import time
import logging
from typing import List, Optional
from core.transaction import Transaction
from core.database import Database
from core.constants import SATOSHIS_PER_TRC, satoshis_to_trc, format_trc, MAX_TXS_PER_SENDER, MAX_TX_AGE

logger = logging.getLogger("Mempool")


class Mempool:
    def __init__(self, db: Database = None, max_size: int = 5000, min_fee_sat: int = 10000):
        self.db = db or Database()
        self.max_size = max_size
        self.min_fee_sat = min_fee_sat  # Minimum fee in satoshis

    def add(self, tx: Transaction, blockchain_balance=None) -> bool:
        """
        Add transaction to mempool after validation.
        blockchain_balance: callable to check sender balance (addr -> float)
        """
        if tx.tx_hash in self._get_hashes():
            return False

        if not tx.is_valid():
            return False

        if tx.is_expired():
            logger.warning(f"Expired transaction rejected: {tx.tx_hash[:16]}")
            return False

        effective_min_fee = self._dynamic_min_fee()
        if tx.fee_satoshis < effective_min_fee:
            logger.warning(f"Fee too low: {tx.fee_satoshis} < {effective_min_fee} sat")
            return False

        # Per-sender limit
        if tx.sender_pubkey != "COINBASE":
            sender_count = sum(1 for t in self.db.get_mempool()
                             if t.get("sender") == tx.sender_pubkey)
            if sender_count >= MAX_TXS_PER_SENDER:
                logger.warning(f"Per-sender limit reached: {tx.sender_pubkey[:16]}")
                return False

        # Real-time balance check
        if blockchain_balance and tx.sender_pubkey != "COINBASE":
            sender_balance = blockchain_balance(tx.sender_pubkey)
            needed = tx.amount + tx.fee
            if sender_balance < needed:
                logger.warning(f"Insufficient balance: {tx.sender_pubkey[:16]} "
                               f"has {sender_balance:.4f}, needs {needed:.4f}")
                return False

        # Double-spend check against UTXO set
        if self.db.has_utxo(tx.tx_hash):
            logger.warning(f"Double-spend attempt: {tx.tx_hash[:16]}")
            return False

        # Check if already spent
        if self.db.is_utxo_spent(tx.tx_hash):
            logger.warning(f"Already spent: {tx.tx_hash[:16]}")
            return False

        # Evict if full
        if self.db.mempool_size() >= self.max_size:
            self._evict()

        self.db.add_mempool(tx.to_dict())
        logger.info(f"Tx accepted: {tx}")
        return True

    def remove(self, tx_hash: str):
        self.db.remove_mempool(tx_hash)

    def get(self, limit: int = 100) -> List[dict]:
        return self.db.get_mempool()[:limit]

    def get_hashes(self) -> set:
        return set(self._get_hashes())

    def _get_hashes(self) -> list:
        return [tx["tx_hash"] for tx in self.db.get_mempool()]

    def remove_many(self, hashes: list):
        for h in hashes:
            self.db.remove_mempool(h)

    def _evict(self):
        """Evict all transactions at the lowest fee level."""
        mempool = self.db.get_mempool()
        if not mempool:
            return
        fees = [tx.get("fee", 0) for tx in mempool]
        if not fees:
            return
        min_fee = min(fees)
        evicted = 0
        for tx in mempool:
            if tx.get("fee", 0) == min_fee:
                self.db.remove_mempool(tx["tx_hash"])
                evicted += 1
        logger.warning(f"Mempool full, evicted {evicted} txs at fee {min_fee}")

    def cleanup_expired(self):
        """Remove expired transactions from mempool."""
        now = int(time.time())
        for tx in self.db.get_mempool():
            if now - tx.get("timestamp", 0) > MAX_TX_AGE:
                self.db.remove_mempool(tx["tx_hash"])
                logger.debug(f"Expired tx removed: {tx['tx_hash'][:16]}")

    def _dynamic_min_fee(self) -> int:
        """Calculate dynamic minimum fee based on mempool congestion."""
        fill_ratio = self.db.mempool_size() / max(self.max_size, 1)
        if fill_ratio > 0.8:
            return self.min_fee_sat * 5
        elif fill_ratio > 0.5:
            return self.min_fee_sat * 2
        return self.min_fee_sat

    def total_fees_satoshis(self, n: int = None) -> int:
        """Get total fees in satoshis."""
        txs = self.db.get_mempool()[:n]
        return sum(tx.get("fee", 0) for tx in txs)

    def total_fees(self, n: int = None) -> float:
        """Get total fees in TRC."""
        return satoshis_to_trc(self.total_fees_satoshis(n))

    def size(self) -> int:
        return self.db.mempool_size()

    def clear(self):
        self.db.clear_mempool()
