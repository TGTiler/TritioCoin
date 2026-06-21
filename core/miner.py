"""
TritioCoin Mining System
Proof-of-Work with Argon2id (ASIC-resistant).
"""
import hashlib
import json
import time
import logging
from typing import Optional, List, Dict
from core.block import Block
from core.blockchain import Blockchain
from core.mempool import Mempool
from core.transaction import Transaction, TransactionBuilder
from core.constants import SATOSHIS_PER_TRC, format_trc

logger = logging.getLogger("Miner")

try:
    from argon2.low_level import hash_secret_raw, Type
    HAS_ARGON2 = True
except ImportError:
    HAS_ARGON2 = False
    logger.warning("argon2-cffi not installed, using SHA256 fallback")


class MiningStats:
    """Tracks mining statistics."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.mining = False
        self.nonce = 0
        self.hashes = 0
        self.start_time = 0.0
        self.blocks_found = 0
        self.total_hashes = 0
        self.best_hash_rate = 0.0

    def start_mining(self):
        self.mining = True
        self.nonce = 0
        self.hashes = 0
        self.start_time = time.time()

    def stop_mining(self):
        self.mining = False
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            rate = self.hashes / elapsed
            self.best_hash_rate = max(self.best_hash_rate, rate)
        self.total_hashes += self.hashes

    def increment(self):
        self.nonce += 1
        self.hashes += 1
        self.total_hashes += 1

    def get_hash_rate(self) -> float:
        elapsed = time.time() - self.start_time
        if elapsed <= 0:
            return 0.0
        return self.hashes / elapsed

    def to_dict(self) -> dict:
        elapsed = time.time() - self.start_time if self.start_time else 0
        rate = self.hashes / elapsed if elapsed > 0 else 0
        return {
            "mining": self.mining,
            "nonce": self.nonce,
            "hashes_session": self.hashes,
            "hashes_total": self.total_hashes,
            "hash_rate": f"{rate:.0f} H/s",
            "best_hash_rate": f"{self.best_hash_rate:.0f} H/s",
            "blocks_found": self.blocks_found,
            "elapsed": f"{elapsed:.1f}s"
        }


class Miner:
    """
    TritioCoin Miner with Argon2id Proof-of-Work.
    
    Features:
    - Argon2id hashing (ASIC-resistant)
    - SHA256 fallback if argon2 not available
    - Dynamic difficulty adjustment
    - Block template creation
    - Mining statistics
    """

    # Argon2id parameters (tuned for CPU mining)
    ARGON_TIME_COST = 1
    ARGON_MEMORY_COST = 65536  # 64 MB
    ARGON_PARALLELISM = 1
    ARGON_HASH_LEN = 32
    ARGON_SALT = b"tritiocoin_v1"

    def __init__(self, blockchain: Blockchain, mempool: Mempool):
        self.blockchain = blockchain
        self.mempool = mempool
        self.stats = MiningStats()
        self.current_block: Optional[Block] = None

    def _pow_hash(self, data: bytes) -> str:
        """Compute proof-of-work hash."""
        if HAS_ARGON2:
            return hash_secret_raw(
                secret=data,
                salt=self.ARGON_SALT,
                time_cost=self.ARGON_TIME_COST,
                memory_cost=self.ARGON_MEMORY_COST,
                parallelism=self.ARGON_PARALLELISM,
                hash_len=self.ARGON_HASH_LEN,
                type=Type.ID
            ).hex()
        # SHA256 fallback
        return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()

    def create_block_template(self, address: str) -> Block:
        """Create a new block template for mining."""
        prev = self.blockchain.latest()
        diff = self.blockchain.adjust_difficulty()
        pending = self.mempool.get(500)

        # Create coinbase transaction
        reward = self.blockchain.reward_at()
        coinbase = TransactionBuilder.create_coinbase(
            address,
            self.blockchain.reward_at_satoshis(),
            self.blockchain.height()
        )

        # Build transaction list
        txs = [coinbase.to_dict()] + [t.to_dict() for t in pending]

        # Create block
        block = Block(prev.header.index + 1, prev.hash, txs, diff)

        return block

    def mine(self, address: str) -> Optional[Block]:
        """
        Mine a new block.
        Returns the mined block or None if interrupted.
        """
        self.stats.start_mining()
        self.current_block = self.create_block_template(address)

        target = "0" * self.current_block.header.difficulty
        logger.info(f"Mining block #{self.current_block.header.index} "
                    f"(difficulty={self.current_block.header.difficulty})")

        while self.stats.mining:
            self.current_block.header.nonce = self.stats.nonce
            pow_hash = self._pow_hash(self.current_block.pow_data())

            if pow_hash.startswith(target):
                # Block found!
                self.current_block.hash = self.current_block.content_hash()
                self.current_block.pow_hash = pow_hash

                # Remove mined transactions from mempool
                pending = self.mempool.get(500)
                self.mempool.remove_many([t.tx_hash for t in pending])

                self.stats.stop_mining()
                self.stats.blocks_found += 1

                logger.info(f"Block #{self.current_block.header.index} mined! "
                            f"Nonce={self.current_block.header.nonce} "
                            f"Hash={self.current_block.hash[:16]}... "
                            f"Rate={self.stats.get_hash_rate():.0f} H/s")

                return self.current_block

            self.stats.increment()

            if self.stats.nonce % 10000 == 0:
                rate = self.stats.get_hash_rate()
                logger.debug(f"Mining... nonce={self.stats.nonce} rate={rate:.0f} H/s")

        self.stats.stop_mining()
        return None

    def stop(self):
        """Stop mining."""
        self.stats.stop_mining()
        logger.info("Mining stopped")

    def get_stats(self) -> dict:
        """Get mining statistics."""
        stats = self.stats.to_dict()
        stats["difficulty"] = self.blockchain.difficulty
        stats["reward"] = self.blockchain.reward_at()
        stats["reward_satoshis"] = self.blockchain.reward_at_satoshis()
        return stats

    def get_block_template_info(self) -> dict:
        """Get current block template information."""
        pending = self.mempool.get(10)
        return {
            "height": self.blockchain.height() + 1,
            "difficulty": self.blockchain.difficulty,
            "reward": self.blockchain.reward_at(),
            "pending_txs": len(pending),
            "estimated_fee": sum(t.get("fee", 0) for t in pending)
        }
