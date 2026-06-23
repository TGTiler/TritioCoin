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
from core.constants import SATOSHIS_PER_TRC

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
        g = Block(0, "0" * 64, [], self.difficulty)
        g.hash = g.content_hash()
        g.pow_hash = "0" * self.difficulty + "genesis"
        self.chain.append(g)
        self.db.save_block(0, g.serialize())
        self.db.set_metadata("difficulty", str(self.difficulty))
        self.db.set_metadata("total_mined_satoshis", "0")
        self.db.set_metadata("total_burned_satoshis", "0")
        logger.info(f"Genesis block created [{self.config.name}]")

    def latest(self) -> Block:
        return self.chain[-1]

    def height(self) -> int:
        return len(self.chain)

    def add_block(self, block: Block) -> bool:
        # Bloco duplicado: mesmo hash ja existe
        if block.hash and self.db.has_block_with_hash(block.hash):
            logger.debug(f"Duplicate block rejected: {block.hash[:16]}...")
            return False

        # Bloco no mesmo height: ja existe outro bloco nessa posicao
        existing = self.db.get_block(block.header.index)
        if existing:
            logger.debug(f"Block at height {block.header.index} already exists, rejecting duplicate")
            return False

        if not self._validate(block):
            return False
        self._apply(block)
        self.chain.append(block)
        self.db.save_block(block.header.index, block.serialize())
        self.db.set_metadata("difficulty", str(self.difficulty))
        logger.info(f"Block #{block.header.index} added | "
                    f"Supply: {self.total_mined_satoshis()/SATOSHIS_PER_TRC:.2f}/{self.config.max_supply_trc:.0f} TRC")
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
            logger.warning(f"Invalid previous hash at height {block.header.index}")
            return False

        # Check PoW hash
        if not block.pow_hash or not block.pow_hash.startswith("0" * block.header.difficulty):
            logger.warning(f"Invalid PoW hash at height {block.header.index}")
            return False

        # Check timestamp (not too far in future)
        if block.header.timestamp > int(time.time()) + 300:
            logger.warning(f"Block timestamp too far in future: {block.header.timestamp}")
            return False

        # Check block hash matches content
        if block.hash and block.hash != block.content_hash():
            logger.warning(f"Block hash mismatch at height {block.header.index}")
            return False

        # Validate transactions
        expected_reward = self.reward_at_satoshis()
        coinbase_count = 0
        block_total_satoshis = 0

        for tx_data in block.transactions:
            tx = Transaction.from_dict(tx_data)
            if not tx.is_valid():
                logger.warning(f"Invalid transaction in block {block.header.index}")
                return False

            if tx.sender_pubkey == "COINBASE":
                coinbase_count += 1
                tx_amount_sat = trc_to_satoshis(tx.amount)
                if tx_amount_sat != expected_reward:
                    logger.warning(f"Wrong reward: {tx_amount_sat} != {expected_reward}")
                    return False
                block_total_satoshis += tx_amount_sat
            else:
                sender_balance = self.balance_satoshis(tx.sender_pubkey)
                needed = trc_to_satoshis(tx.amount + tx.fee)
                if sender_balance < needed:
                    logger.warning(f"Insufficient balance in block {block.header.index}")
                    return False
                if self.db.has_utxo(tx.tx_hash):
                    logger.warning(f"Double-spend in block {block.header.index}")
                    return False
                block_total_satoshis += trc_to_satoshis(tx.fee)

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

    def _credit_satoshis(self, addr: str, amount_sat: int):
        current = self.db.get_balance(addr)
        self.db.set_balance(addr, current + amount_sat)

    def _debit_satoshis(self, addr: str, amount_sat: int):
        current = self.db.get_balance(addr)
        self.db.set_balance(addr, current - amount_sat)

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

        # Check each block
        for i in range(1, len(self.chain)):
            block = self.chain[i]
            prev = self.chain[i - 1]

            if block.header.previous_hash.hex() != prev.hash:
                logger.warning(f"Chain broken at height {i}")
                return False

            if block.hash and block.hash != block.content_hash():
                logger.warning(f"Block hash mismatch at height {i}")
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
        ref = self.chain[max(0, self.height() - 10)]
        dt = self.latest().header.timestamp - ref.header.timestamp
        target = self.config.block_time * 10
        if dt < target // 2:
            self.difficulty += 1
        elif dt > target * 2:
            self.difficulty = max(1, self.difficulty - 1)
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
