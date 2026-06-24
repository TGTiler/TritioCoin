"""
TritioCoin Mining Pool
Cooperative mining with proportional reward distribution.
"""
import hashlib
import time
import logging
import json
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

from core.constants import trc_to_satoshis

logger = logging.getLogger("MiningPool")


@dataclass
class MinerStats:
    """Statistics for a pool miner."""
    address: str
    shares: int = 0
    valid_shares: int = 0
    invalid_shares: int = 0
    last_share_time: float = 0
    total_earned: float = 0
    connected: bool = False
    hashrate: float = 0

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "shares": self.shares,
            "valid_shares": self.valid_shares,
            "invalid_shares": self.invalid_shares,
            "last_share": self.last_share_time,
            "total_earned": self.total_earned,
            "connected": self.connected,
            "hashrate": self.hashrate
        }


class MiningPool:
    """
    Mining pool for cooperative mining.
    
    Features:
    - Share-based reward distribution
    - PPLNS (Pay Per Last N Shares) payout
    - Stratum-like protocol
    - Real-time hashrate monitoring
    - Automatic payout when threshold reached
    """

    # Pool configuration
    MIN_PAYOUT = 100000000  # 1 TRC in satoshis
    PAYOUT_INTERVAL = 3600  # Payout every hour
    DIFF_TARGET_TIME = 300  # Target time between shares (5 min)
    SHARE_DIFF_MULTIPLIER = 1  # Share difficulty multiplier

    def __init__(self, blockchain=None, mempool=None, db=None, wallet=None):
        self.miners: Dict[str, MinerStats] = {}
        self.shares: List[dict] = []  # Recent shares
        self.total_shares = 0
        self.total_blocks = 0
        self.pool_hashrate = 0
        self.last_payout = time.time()
        self.pending_payouts: Dict[str, int] = {}  # address -> satoshis
        self.active: bool = False
        self.blockchain = blockchain
        self.mempool = mempool
        self.db = db
        self.wallet = wallet

    def register_miner(self, address: str) -> bool:
        """Register a miner to the pool."""
        if address in self.miners:
            self.miners[address].connected = True
            return True

        self.miners[address] = MinerStats(address=address)
        self.miners[address].connected = True
        logger.info(f"Miner registered: {address[:16]}...")
        return True

    def unregister_miner(self, address: str):
        """Unregister a miner from the pool."""
        if address in self.miners:
            self.miners[address].connected = False
            logger.info(f"Miner disconnected: {address[:16]}...")

    def submit_share(self, miner_address: str, nonce: int, hash_value: str,
                     difficulty: int) -> bool:
        """
        Submit a mining share.
        Returns True if share is valid.
        """
        miner = self.miners.get(miner_address)
        if not miner:
            logger.warning(f"Unknown miner: {miner_address[:16]}...")
            return False

        # Check if hash meets share difficulty
        if not hash_value.startswith("0" * difficulty):
            miner.invalid_shares += 1
            return False

        # Record share
        share = {
            "miner": miner_address,
            "nonce": nonce,
            "hash": hash_value,
            "difficulty": difficulty,
            "timestamp": time.time()
        }

        self.shares.append(share)
        miner.shares += 1
        miner.valid_shares += 1
        miner.last_share_time = time.time()
        self.total_shares += 1

        # Keep only recent shares (last 1000)
        if len(self.shares) > 1000:
            self.shares = self.shares[-1000:]

        logger.debug(f"Share submitted: {miner_address[:16]}... nonce={nonce}")
        return True

    def find_block(self, miner_address: str, block_hash: str, nonce: int,
                   difficulty: int) -> bool:
        """
        Called when a miner finds a valid block.
        Returns True if block is accepted.
        """
        miner = self.miners.get(miner_address)
        if not miner:
            return False

        if not block_hash.startswith("0" * difficulty):
            logger.warning(f"Invalid block hash from {miner_address[:16]}...")
            return False

        self.total_blocks += 1
        logger.info(f"Block found by {miner_address[:16]}... hash={block_hash[:16]}...")

        return True

    def distribute_rewards(self, block_reward_satoshis: int, fee_satoshis: int):
        """
        Distribute block rewards to miners based on shares.
        Uses PPLNS (Pay Per Last N Shares).
        """
        total_reward = block_reward_satoshis + fee_satoshis

        # Pool fee (1%)
        pool_fee = total_reward // 100
        miner_reward = total_reward - pool_fee

        # Count shares in window
        window_shares = self.shares[-1000:]  # Last 1000 shares
        if not window_shares:
            logger.warning("No shares to distribute rewards")
            return

        # Group shares by miner
        miner_shares: Dict[str, int] = {}
        for share in window_shares:
            addr = share["miner"]
            miner_shares[addr] = miner_shares.get(addr, 0) + 1

        total_shares = sum(miner_shares.values())
        if total_shares == 0:
            return

        # Distribute proportionally
        for addr, shares in miner_shares.items():
            proportion = shares / total_shares
            reward = int(miner_reward * proportion)

            if addr not in self.pending_payouts:
                self.pending_payouts[addr] = 0
            self.pending_payouts[addr] += reward

            miner = self.miners.get(addr)
            if miner:
                miner.total_earned += reward

            logger.debug(f"Reward: {addr[:16]}... +{reward} sat ({proportion*100:.2f}%)")

        logger.info(f"Rewards distributed: {miner_reward} sat to {len(miner_shares)} miners")

    def process_payouts(self) -> List[dict]:
        """
        Process pending payouts and create on-chain transactions.
        Returns list of tx hashes for tracking.
        """
        tx_hashes = []

        if not self.blockchain or not self.mempool or not self.wallet:
            logger.warning("Pool sem blockchain/mempool/wallet, payouts so em memoria")
            return tx_hashes

        from core.transaction import TransactionBuilder

        for addr, amount in list(self.pending_payouts.items()):
            if amount >= self.MIN_PAYOUT:
                utxos = self.db.get_unspent_utxos(self.wallet.address)
                if not utxos:
                    logger.warning(f"Sem UTXOs na pool wallet para payout de {addr[:16]}...")
                    continue

                total_input = sum(u['amount'] for u in utxos)
                if total_input < amount:
                    logger.warning(f"Saldo insuficiente na pool: {total_input} < {amount}")
                    continue

                inputs = [{"tx_hash": u['tx_hash'], "amount": u['amount']} for u in utxos]
                fee_sat = trc_to_satoshis(0.0001)
                change_sat = total_input - amount - fee_sat

                tx = TransactionBuilder.create_transfer(
                    self.wallet.address, addr, amount, fee_sat, inputs
                )
                tx.change = change_sat / 1e8
                tx.timestamp = int(time.time())

                tx_data = bytes.fromhex(tx.compute_hash())
                sigs = self.wallet.sign_tx(tx_data)
                tx.signature = sigs["ecdsa_signature"]
                tx.signature_mode = sigs["signature_mode"]
                tx.tx_hash = tx.compute_hash()

                self.mempool.add(tx)
                tx_hashes.append(tx.tx_hash)
                del self.pending_payouts[addr]
                logger.info(f"Payout enviado: {addr[:16]}... {amount} sat -> {tx.tx_hash[:16]}...")

        return tx_hashes

    def get_mining_difficulty(self) -> int:
        """Calculate dynamic difficulty based on pool hashrate."""
        # Simple difficulty adjustment
        target = self.DIFF_TARGET_TIME
        if self.pool_hashrate <= 0:
            return 2

        # Estimate time to find block at current difficulty
        estimated_time = 2 ** 24 / self.pool_hashrate  # Rough estimate

        if estimated_time < target / 2:
            return min(6, self.SHARE_DIFF_MULTIPLIER + 1)
        elif estimated_time > target * 2:
            return max(1, self.SHARE_DIFF_MULTIPLIER - 1)
        return self.SHARE_DIFF_MULTIPLIER

    def update_hashrate(self):
        """Update pool hashrate estimate."""
        now = time.time()
        recent_shares = [s for s in self.shares if now - s["timestamp"] < 300]
        if recent_shares:
            time_span = now - recent_shares[0]["timestamp"]
            if time_span > 0:
                self.pool_hashrate = len(recent_shares) / time_span

        # Update individual miner hashrates
        for miner in self.miners.values():
            if miner.last_share_time > 0:
                elapsed = now - miner.last_share_time
                if elapsed < 300:
                    miner.hashrate = miner.valid_shares / max(elapsed, 1)

    def get_miner_stats(self, address: str) -> Optional[dict]:
        """Get statistics for a specific miner."""
        miner = self.miners.get(address)
        if not miner:
            return None

        stats = miner.to_dict()
        stats["pending_payout"] = self.pending_payouts.get(address, 0)

        # Calculate share percentage
        if self.total_shares > 0:
            stats["share_percentage"] = (miner.valid_shares / self.total_shares) * 100
        else:
            stats["share_percentage"] = 0

        return stats

    def get_pool_stats(self) -> dict:
        """Get pool statistics."""
        connected = sum(1 for m in self.miners.values() if m.connected)
        total_pending = sum(self.pending_payouts.values())

        return {
            "active": self.active,
            "miners": len(self.miners),
            "connected_miners": connected,
            "total_shares": self.total_shares,
            "total_blocks": self.total_blocks,
            "pool_hashrate": f"{self.pool_hashrate:.2f} H/s",
            "difficulty": self.get_mining_difficulty(),
            "pending_payouts": total_pending,
            "pool_fee_percent": 1.0
        }

    def get_work(self, miner_address: str) -> dict:
        """Get mining work for a miner (stratum-like)."""
        self.register_miner(miner_address)

        prev_hash = "0" * 64
        coinbase_tx = "0" * 64
        merkle_root = "0" * 64
        block_height = 0

        if self.blockchain:
            latest = self.blockchain.latest()
            prev_hash = latest.hash
            block_height = latest.header.index + 1

            from core.transaction import TransactionBuilder
            coinbase = TransactionBuilder.create_coinbase(
                miner_address,
                self.blockchain.reward_at_satoshis(),
                block_height
            )
            coinbase_tx = coinbase.tx_hash or "0" * 64

            pending = self.mempool.get(500) if self.mempool else []
            if pending:
                tx_hashes = [t.tx_hash for t in pending if t.tx_hash]
                if tx_hashes:
                    combined = "".join(tx_hashes)
                    merkle_root = hashlib.sha256(combined.encode()).hexdigest()

        return {
            "type": "mining.notify",
            "job_id": hashlib.sha256(str(time.time()).encode()).hexdigest()[:16],
            "difficulty": self.get_mining_difficulty(),
            "timestamp": int(time.time()),
            "prev_hash": prev_hash,
            "coinbase_tx": coinbase_tx,
            "merkle_root": merkle_root,
            "block_height": block_height,
            "miners": len(self.miners)
        }

    def start(self):
        """Start the mining pool."""
        self.active = True
        logger.info("Mining pool started")

    def stop(self):
        """Stop the mining pool."""
        self.active = False
        logger.info("Mining pool stopped")
