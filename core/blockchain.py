"""
TritioCoin Blockchain
- SQLite persistence
- 19M supply cap with halving
- Satoshis for precision (8 decimal places)
- Balance verification
- Double-spend protection (UTXOs)
- Burn mechanism
- Testnet/Mainnet support
"""
import hashlib
import json
import time
import logging
from typing import List, Optional

from core.block import Block
from core.transaction import Transaction
from core.database import Database
from core.network_config import NetworkConfig, MAINNET
from core.constants import SATOSHIS_PER_TRC, MAX_FUTURE_DRIFT, MAX_PAST_DRIFT, MTP_WINDOW, CHECKPOINT_INTERVAL, MAX_REORG_DEPTH

logger = logging.getLogger("Blockchain")


class Blockchain:
    def __init__(self, config: NetworkConfig = None, db: Database = None):
        self.config = config or MAINNET
        self.db = db or Database()
        self.chain: List[Block] = []
        self.difficulty = self.config.difficulty
        self._load_or_create()

    def _load_or_create(self):
        height = self.db.get_block_height()
        if height >= 0:
            self._load_from_db()
            logger.info(f"Chain loaded: {self.height()} blocks from database")
        else:
            self._genesis()

    def _load_from_db(self):
        self.chain = []
        self.difficulty = int(self.db.get_metadata("difficulty") or self.config.difficulty)
        db_height = self.db.get_block_height()
        loaded = 0
        for i in range(db_height + 1):
            block_data = self.db.get_block(i)
            if block_data:
                b = Block.deserialize(block_data)
                # Validate each block on load
                if i > 0 and not self._validate_loaded_block(b, loaded):
                    logger.warning(f"Invalid block at height {i}, stopping load")
                    break
                self.chain.append(b)
                loaded += 1
        logger.info(f"Loaded {loaded}/{db_height + 1} blocks from database")

    def _validate_loaded_block(self, block: Block, prev_index: int) -> bool:
        """Validate a block when loading from database."""
        if len(self.chain) == 0:
            return True  # Genesis block

        prev = self.chain[-1]

        # Check block hash matches content
        if block.hash and block.hash != block.content_hash():
            logger.warning(f"Block hash mismatch at height {block.header.index}")
            return False

        # Check previous hash links
        if block.header.previous_hash.hex() != prev.hash:
            logger.warning(f"Block chain broken at height {block.header.index}")
            return False

        # Check PoW hash
        if block.pow_hash and not block.pow_hash.startswith("0" * block.header.difficulty):
            logger.warning(f"Invalid PoW at height {block.header.index}")
            return False

        return True

    def _genesis(self):
        # Genesis timestamp fixo para todos os nodes (1 Jan 2026)
        GENESIS_TIMESTAMP = 1767225600
        g = Block(0, "0" * 64, [], self.difficulty)
        g.header.timestamp = GENESIS_TIMESTAMP
        g.hash = g.content_hash()
        g.pow_hash = "0" * self.difficulty + "genesis"
        self.chain.append(g)
        self.db.save_block(0, g.serialize())
        self.db.set_metadata("difficulty", str(self.difficulty))
        self.db.set_metadata("total_mined_satoshis", "0")
        self.db.set_metadata("total_burned_satoshis", "0")
        logger.info(f"Genesis block created [{self.config.name}] hash={g.hash[:16]}...")

    def latest(self) -> Block:
        return self.chain[-1]

    def height(self) -> int:
        return len(self.chain)

    def add_block(self, block: Block) -> bool:
        # Bloco duplicado: mesmo hash ja existe
        if block.hash and self.db.has_block_with_hash(block.hash):
            logger.debug(f"Duplicate block rejected: {block.hash[:16]}...")
            return False

        # Bloco na posicao esperada (proximo da chain)
        if block.header.index == self.height():
            # Verificar se e o mesmo bloco
            existing = self.db.get_block(block.header.index)
            if existing and block.hash == existing.get("hash"):
                logger.debug(f"Duplicate block at height {block.header.index}")
                return False

            if not self._validate(block):
                return False
            self._apply(block)
            self.chain.append(block)
            self.db.save_block(block.header.index, block.serialize())
            self.db.set_metadata("difficulty", str(self.difficulty))

            if block.header.index % CHECKPOINT_INTERVAL == 0 and block.header.index > 0:
                self.db.save_checkpoint(block.header.index, block.hash)
                logger.info(f"Checkpoint saved at height {block.header.index}")

            logger.info(f"Block #{block.header.index} added | "
                        f"Supply: {self.total_mined_satoshis()/SATOSHIS_PER_TRC:.2f}/{self.config.max_supply_trc:.0f} TRC")
            return True

        # Bloco concorrente (mesmo height ou chain mais longa)
        if block.header.index <= self.height():
            return self._handle_reorg(block)

        # Bloco muito a frente (height > self.height() + 1) - orphan
        logger.debug(f"Block #{block.header.index} ahead of chain (height={self.height()})")
        return False

    def _handle_reorg(self, block: Block) -> bool:
        """Handle chain reorganization when a competing chain arrives."""
        fork_height = block.header.index

        # Reorg protection: check max depth
        depth = self.height() - fork_height
        if depth > MAX_REORG_DEPTH:
            logger.warning(f"Reorg depth {depth} exceeds max {MAX_REORG_DEPTH}")
            return False

        # Reorg protection: check checkpoint
        if self._is_past_checkpoint(fork_height):
            logger.warning(f"Cannot reorg past checkpoint at height {fork_height}")
            return False

        # Find fork point (common ancestor)
        fork_point = fork_height - 1
        if fork_point < 0:
            fork_point = 0

        # Compare cumulative work
        current_work = sum(2 ** b.header.difficulty for b in self.chain[fork_point:])
        new_work = 2 ** block.header.difficulty

        if new_work <= current_work:
            logger.debug(f"Competing chain has less work ({new_work} <= {current_work})")
            return False

        # Reorganize: undo blocks from fork_point to current tip
        logger.warning(f"Chain reorganization: undoing {self.height() - fork_point} blocks")
        for i in range(self.height() - 1, fork_point - 1, -1):
            if i < len(self.chain):
                self._undo_block(self.chain[i])
                self.chain.pop()

        # Apply new block
        if not self._validate(block):
            logger.warning("Reorg block validation failed")
            return False

        self._apply(block)
        self.chain.append(block)
        self.db.save_block(block.header.index, block.serialize())
        self.db.set_metadata("difficulty", str(self.difficulty))

        if block.header.index % CHECKPOINT_INTERVAL == 0 and block.header.index > 0:
            self.db.save_checkpoint(block.header.index, block.hash)

        logger.info(f"Reorg complete: now at height {self.height()}")
        return True

    def _validate(self, block: Block) -> bool:
        """Validate a block before adding to chain."""
        prev = self.latest()

        # Check block height
        if block.header.index != prev.header.index + 1:
            logger.warning(f"Invalid height: {block.header.index} != {prev.header.index + 1}")
            return False

        # Check previous hash
        if block.header.previous_hash.hex() != prev.hash:
            logger.warning(f"Invalid previous hash at height {block.header.index}: {block.header.previous_hash.hex()[:16]}... != {prev.hash[:16]}...")
            return False

        # Check PoW hash
        if not block.pow_hash or not block.pow_hash.startswith("0" * block.header.difficulty):
            logger.warning(f"Invalid PoW hash at height {block.header.index}: pow_hash={block.pow_hash[:16] if block.pow_hash else 'None'}...")
            return False

        # Check timestamp (not too far in future)
        if block.header.timestamp > int(time.time()) + MAX_FUTURE_DRIFT:
            logger.warning(f"Block timestamp too far in future: {block.header.timestamp}")
            return False

        # Check timestamp not too far in past (median time past)
        if self.height() >= MTP_WINDOW:
            mtp = self._median_time_past()
            if block.header.timestamp <= mtp - MAX_PAST_DRIFT:
                logger.warning(f"Block timestamp too far in past: {block.header.timestamp} <= MTP-{MAX_PAST_DRIFT}")
                return False

        # Check block hash matches content
        if block.hash and block.hash != block.content_hash():
            logger.warning(f"Block hash mismatch at height {block.header.index}")
            return False

        # Validate transactions
        expected_reward = self.reward_at_satoshis()
        miner_reward = int(expected_reward * 0.7)  # Miner gets 70%
        coinbase_count = 0
        block_total_satoshis = 0

        for tx_data in block.transactions:
            tx = Transaction.from_dict(tx_data)
            if not tx.is_valid():
                logger.warning(f"Invalid transaction in block {block.header.index}")
                return False
            if tx.sender_pubkey != "COINBASE" and tx.is_expired():
                logger.warning(f"Expired transaction in block {block.header.index}")
                return False

            if tx.sender_pubkey == "COINBASE":
                coinbase_count += 1
                tx_amount_sat = trc_to_satoshis(tx.amount)
                if tx_amount_sat != miner_reward:
                    logger.warning(f"Wrong miner reward: {tx_amount_sat} != {miner_reward}")
                    return False
                block_total_satoshis += tx_amount_sat
            else:
                sender_balance = self.balance_satoshis(tx.sender_pubkey)
                needed = tx.amount_satoshis + tx.fee_satoshis
                if sender_balance < needed:
                    logger.warning(f"Insufficient balance in block {block.header.index}")
                    return False
                if self.db.has_utxo(tx.tx_hash):
                    logger.warning(f"Double-spend in block {block.header.index}")
                    return False
                block_total_satoshis += tx.fee_satoshis

        # Check coinbase count
        if coinbase_count > 1:
            logger.warning("Multiple coinbase transactions")
            return False

        # Check supply cap
        total_mined = self.total_mined_satoshis()
        if total_mined + block_total_satoshis > self.config.max_supply_satoshis:
            logger.warning("Supply cap exceeded")
            return False

        return True

    def _median_time_past(self) -> int:
        """Calculate median time past from last MTP_WINDOW blocks."""
        n = min(MTP_WINDOW, self.height())
        if n <= 0:
            return int(time.time())
        start = max(0, self.height() - n)
        timestamps = [self.chain[i].header.timestamp
                      for i in range(start, self.height())]
        timestamps.sort()
        return timestamps[len(timestamps) // 2]

    def _apply(self, block: Block):
        for tx_data in block.transactions:
            tx = Transaction.from_dict(tx_data)

            if tx.sender_pubkey == "COINBASE":
                amount_sat = trc_to_satoshis(tx.amount)
                self.db.save_utxo(tx.tx_hash, "COINBASE", tx.recipient_pubkey,
                                  amount_sat, 0, block.header.index)
                self._credit_satoshis(tx.recipient_pubkey, amount_sat)
                current = self.total_mined_satoshis()
                self.db.set_metadata("total_mined_satoshis", str(current + amount_sat))
                self.db.save_transaction(tx.to_dict(), block.header.index)
            else:
                for inp in getattr(tx, 'inputs', []) or []:
                    self.db.spend_utxo(inp["tx_hash"])

                amount_sat = trc_to_satoshis(tx.amount)
                fee_sat = trc_to_satoshis(tx.fee)
                burn_sat = int(fee_sat * self.config.burn_rate)

                self.db.save_utxo(tx.tx_hash, tx.sender_pubkey,
                                  tx.recipient_pubkey, amount_sat, fee_sat,
                                  block.header.index)

                change_sat = getattr(tx, 'change', 0) or 0
                change_sat = trc_to_satoshis(change_sat)
                if change_sat > 0:
                    change_hash = f"{tx.tx_hash}_change"
                    self.db.save_utxo(change_hash, tx.sender_pubkey,
                                      tx.sender_pubkey, change_sat, 0,
                                      block.header.index)

                self._debit_satoshis(tx.sender_pubkey, amount_sat + fee_sat)
                self._credit_satoshis(tx.recipient_pubkey, amount_sat)
                self.db.save_transaction(tx.to_dict(), block.header.index)

                # Track burned amount
                total_burned = self.total_burned_satoshis()
                self.db.set_metadata("total_burned_satoshis", str(total_burned + burn_sat))

        # Re-verify supply cap after applying all transactions
        total_mined = self.total_mined_satoshis()
        if total_mined > self.config.max_supply_satoshis:
            logger.critical(f"Supply cap exceeded after apply: {total_mined} > {self.config.max_supply_satoshis}")

    def _credit_satoshis(self, addr: str, amount_sat: int):
        current = self.db.get_balance(addr)
        self.db.set_balance(addr, current + amount_sat)

    def _debit_satoshis(self, addr: str, amount_sat: int) -> bool:
        current = self.db.get_balance(addr)
        if current < amount_sat:
            logger.warning(f"Debit underflow: {addr[:16]}... {current} < {amount_sat}")
            return False
        self.db.set_balance(addr, current - amount_sat)
        return True

    def cumulative_work(self) -> int:
        """Calculate total cumulative PoW work (sum of 2^difficulty for each block)."""
        work = 0
        for block in self.chain:
            work += 2 ** block.header.difficulty
        return work

    def _undo_block(self, block: Block):
        """Reverse all effects of a block (for chain reorganization)."""
        for tx_data in reversed(block.transactions):
            tx = Transaction.from_dict(tx_data)
            if tx.sender_pubkey == "COINBASE":
                amount_sat = trc_to_satoshis(tx.amount)
                self._debit_satoshis(tx.recipient_pubkey, amount_sat)
                current = self.total_mined_satoshis()
                self.db.set_metadata("total_mined_satoshis", str(max(0, current - amount_sat)))
            else:
                for inp in getattr(tx, 'inputs', []) or []:
                    self.db.unspend_utxo(inp["tx_hash"])

                amount_sat = trc_to_satoshis(tx.amount)
                fee_sat = trc_to_satoshis(tx.fee)
                self._credit_satoshis(tx.sender_pubkey, amount_sat + fee_sat)
                self._debit_satoshis(tx.recipient_pubkey, amount_sat)

        logger.info(f"Undone block #{block.header.index}")

    def _is_past_checkpoint(self, height: int) -> bool:
        """Check if a height has a checkpoint that would be crossed by a reorg."""
        latest_cp = self.db.get_latest_checkpoint_height()
        return latest_cp > 0 and height < latest_cp

    def get_confirmations(self, block_hash: str) -> int:
        """Get number of confirmations for a block hash."""
        for i in range(len(self.chain) - 1, -1, -1):
            if self.chain[i].hash == block_hash:
                return len(self.chain) - 1 - i
        return 0

    def verify_block(self, block: Block) -> bool:
        """Verify a block is valid without adding it to chain."""
        return self._validate(block)

    def get_block_hash(self, height: int) -> Optional[str]:
        """Get block hash by height."""
        if 0 <= height < len(self.chain):
            return self.chain[height].hash
        return None

    def is_chain_valid(self) -> bool:
        """Verify the entire chain is valid."""
        if len(self.chain) == 0:
            return True

        # Check genesis
        genesis = self.chain[0]
        if genesis.header.index != 0:
            return False
        if genesis.hash != genesis.content_hash():
            return False

        # Check each block
        for i in range(1, len(self.chain)):
            block = self.chain[i]
            prev = self.chain[i - 1]

            # Structural integrity
            if block.header.previous_hash.hex() != prev.hash:
                logger.warning(f"Chain broken at height {i}")
                return False

            if block.hash and block.hash != block.content_hash():
                logger.warning(f"Block hash mismatch at height {i}")
                return False

            # PoW verification
            if not block.pow_hash or not block.pow_hash.startswith("0" * block.header.difficulty):
                logger.warning(f"Invalid PoW at height {i}")
                return False

            # Checkpoint verification
            expected_hash = self.db.get_checkpoint(block.header.index)
            if expected_hash and block.hash != expected_hash:
                logger.warning(f"Checkpoint mismatch at height {block.header.index}")
                return False

        return True

    def balance_satoshis(self, address: str) -> int:
        return self.db.get_balance(address)

    def balance(self, address: str) -> float:
        """Get balance in TRC (for display)."""
        return self.db.get_balance(address) / SATOSHIS_PER_TRC

    def total_mined_satoshis(self) -> int:
        val = self.db.get_metadata("total_mined_satoshis")
        return int(val) if val else 0

    def total_mined(self) -> float:
        return self.total_mined_satoshis() / SATOSHIS_PER_TRC

    def total_burned_satoshis(self) -> int:
        val = self.db.get_metadata("total_burned_satoshis")
        return int(val) if val else 0

    def total_burned(self) -> float:
        return self.total_burned_satoshis() / SATOSHIS_PER_TRC

    def circulating_supply_satoshis(self) -> int:
        return self.total_mined_satoshis() - self.total_burned_satoshis()

    def circulating_supply(self) -> float:
        return self.circulating_supply_satoshis() / SATOSHIS_PER_TRC

    def supply_remaining_satoshis(self) -> int:
        return max(0, self.config.max_supply_satoshis - self.total_mined_satoshis())

    def supply_remaining(self) -> float:
        return self.supply_remaining_satoshis() / SATOSHIS_PER_TRC

    def reward_at_satoshis(self) -> int:
        halvings = self.height() // self.config.halving_interval
        reward = self.config.initial_reward_satoshis // (2 ** halvings)
        return max(reward, 1)

    def reward_at(self) -> float:
        return self.reward_at_satoshis() / SATOSHIS_PER_TRC

    def halving_at(self) -> int:
        current_halving = self.height() // self.config.halving_interval
        return (current_halving + 1) * self.config.halving_interval

    def adjust_difficulty(self) -> int:
        if self.height() < 20:
            return self.difficulty

        # TritioHash: larger window (30 blocks) for stability with slow algorithm
        window = 30
        ref = self.chain[max(0, self.height() - window)]
        actual_time = self.latest().header.timestamp - ref.header.timestamp
        expected_time = self.config.block_time * window

        if actual_time <= 0:
            actual_time = 1

        ratio = expected_time / actual_time
        raw_new = self.difficulty * ratio

        # TritioHash: more dampening (70/30) for slower algorithm
        dampened = 0.7 * self.difficulty + 0.3 * raw_new

        # TritioHash: smaller max jump (15%) for stability
        max_jump = self.difficulty * 0.15
        clamped = max(self.difficulty - max_jump, min(self.difficulty + max_jump, dampened))

        self.difficulty = max(self.config.difficulty, int(round(clamped)))
        return self.difficulty

    def history(self, address: str) -> list:
        result = []
        for block in self.chain:
            for tx_data in block.transactions:
                tx = Transaction.from_dict(tx_data)
                if tx.sender_pubkey == address or tx.recipient_pubkey == address:
                    result.append({
                        "block": block.header.index,
                        "hash": tx.tx_hash,
                        "from": tx.sender_pubkey[:16] + "...",
                        "to": tx.recipient_pubkey[:16] + "...",
                        "amount": tx.amount,
                        "fee": tx.fee,
                        "time": tx.timestamp
                    })
        return result

    def is_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            cur = self.chain[i]
            prev = self.chain[i - 1]
            if cur.header.previous_hash.hex() != prev.hash:
                return False
            if not cur.pow_hash or not cur.pow_hash.startswith("0" * cur.header.difficulty):
                return False
            if cur.hash != cur.content_hash():
                return False
        return True

    def serialize(self) -> dict:
        return {
            "network": self.config.name,
            "difficulty": self.difficulty,
            "blocks": [b.serialize() for b in self.chain]
        }

    @classmethod
    def deserialize(cls, data: dict, config: NetworkConfig = None, db: Database = None) -> 'Blockchain':
        cfg = config or MAINNET
        bc = cls.__new__(cls)
        bc.config = cfg
        bc.db = db or Database()
        bc.chain = []
        bc.difficulty = data.get("difficulty", cfg.difficulty)
        for bd in data["blocks"]:
            b = Block.deserialize(bd)
            bc.chain.append(b)
            for tx_data in b.transactions:
                tx = Transaction.from_dict(tx_data)
                if tx.sender_pubkey == "COINBASE":
                    amount_sat = trc_to_satoshis(tx.amount)
                    bc.db.save_utxo(tx.tx_hash, "COINBASE", tx.recipient_pubkey,
                                    amount_sat, 0, b.header.index)
                    current = bc.db.get_balance(tx.recipient_pubkey)
                    bc.db.set_balance(tx.recipient_pubkey, current + amount_sat)
                else:
                    amount_sat = trc_to_satoshis(tx.amount)
                    fee_sat = trc_to_satoshis(tx.fee)
                    bc.db.save_utxo(tx.tx_hash, tx.sender_pubkey,
                                    tx.recipient_pubkey, amount_sat, fee_sat,
                                    b.header.index)
                    sender_bal = bc.db.get_balance(tx.sender_pubkey)
                    bc.db.set_balance(tx.sender_pubkey, sender_bal - amount_sat - fee_sat)
                    recip_bal = bc.db.get_balance(tx.recipient_pubkey)
                    bc.db.set_balance(tx.recipient_pubkey, recip_bal + amount_sat)
                bc.db.save_transaction(tx.to_dict(), b.header.index)
        return bc

    def stats(self) -> dict:
        return {
            "network": self.config.name,
            "height": self.height(),
            "transactions": self.db.get_tx_count(),
            "difficulty": self.difficulty,
            "reward_trc": self.reward_at(),
            "reward_satoshis": self.reward_at_satoshis(),
            "total_mined_trc": self.total_mined(),
            "total_mined_satoshis": self.total_mined_satoshis(),
            "total_burned_trc": self.total_burned(),
            "total_burned_satoshis": self.total_burned_satoshis(),
            "circulating_trc": self.circulating_supply(),
            "circulating_satoshis": self.circulating_supply_satoshis(),
            "supply_remaining_trc": self.supply_remaining(),
            "supply_remaining_satoshis": self.supply_remaining_satoshis(),
            "max_supply_trc": self.config.max_supply_trc,
            "max_supply_satoshis": self.config.max_supply_satoshis,
            "next_halving": self.halving_at(),
            "addresses": len(self.db.get_all_balances()),
            "mempool": self.db.mempool_size(),
            "burn_rate": self.config.burn_rate,
            "valid": self.is_valid()
        }


def trc_to_satoshis(trc: float) -> int:
    """Convert TRC to satoshis."""
    return int(round(trc * SATOSHIS_PER_TRC))
