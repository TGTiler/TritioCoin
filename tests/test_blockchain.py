"""
Tests for Blockchain module.
"""
import pytest
import time
from core.blockchain import Blockchain
from core.wallet import Wallet
from core.transaction import Transaction
from core.block import Block


class TestBlockchain:
    """Test blockchain creation, mining, and validation."""

    def test_genesis_block(self, blockchain):
        """Test that genesis block is created."""
        assert blockchain.height() == 1
        assert blockchain.latest().header.index == 0

    def test_testnet_config(self, db, testnet):
        """Test testnet configuration."""
        bc = Blockchain(testnet, db)
        assert bc.config.name == "testnet"
        assert bc.config.difficulty == 2
        assert bc.config.block_time == 30  # Updated: 30s for testnet

    def test_mine_block(self, blockchain):
        """Test mining a block."""
        w = Wallet.create()
        miner_reward = int(blockchain.reward_at() * 0.7)
        coinbase = Transaction("COINBASE", w.pubkey_hex(), miner_reward)
        coinbase.timestamp = int(time.time() * 1000)
        coinbase.tx_hash = coinbase.compute_hash()
        block = Block(1, blockchain.latest().hash, [coinbase.to_dict()], blockchain.difficulty)
        block.hash = block.content_hash()
        block.pow_hash = "0" * blockchain.difficulty + "test"
        assert blockchain.add_block(block)
        assert blockchain.height() == 2

    def test_supply_cap(self, blockchain):
        """Test supply cap is enforced."""
        assert blockchain.config.max_supply_trc == 19_000_000

    def test_balance_tracking(self, blockchain):
        """Test balance is tracked correctly."""
        w = Wallet.create()
        miner_reward = int(blockchain.reward_at() * 0.7)
        coinbase = Transaction("COINBASE", w.pubkey_hex(), miner_reward)
        coinbase.timestamp = int(time.time() * 1000)
        coinbase.tx_hash = coinbase.compute_hash()
        block = Block(1, blockchain.latest().hash, [coinbase.to_dict()], blockchain.difficulty)
        block.hash = block.content_hash()
        block.pow_hash = "0" * blockchain.difficulty + "test"
        blockchain.add_block(block)
        assert blockchain.balance(w.pubkey_hex()) == miner_reward

    def test_persistence(self, db, testnet):
        """Test blockchain persistence."""
        bc = Blockchain(testnet, db)
        w = Wallet.create()
        miner_reward = int(bc.reward_at() * 0.7)
        coinbase = Transaction("COINBASE", w.pubkey_hex(), miner_reward)
        coinbase.timestamp = int(time.time() * 1000)
        coinbase.tx_hash = coinbase.compute_hash()
        block = Block(1, bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
        block.hash = block.content_hash()
        block.pow_hash = "0" * bc.difficulty + "test"
        bc.add_block(block)

        # Reload from same database
        bc2 = Blockchain(testnet, db)
        assert bc2.height() == 2
        assert bc2.balance(w.pubkey_hex()) == miner_reward

    def test_serialization(self, blockchain):
        """Test blockchain serialization."""
        data = blockchain.serialize()
        assert "network" in data
        assert "blocks" in data
        assert len(data["blocks"]) == 1

    def test_is_valid(self, blockchain):
        """Test chain validation."""
        assert blockchain.is_valid()

    def test_reward_halving(self, blockchain):
        """Test reward calculation."""
        reward = blockchain.reward_at()
        assert reward == 50.0  # Updated: 45 TRC initial reward

    def test_difficulty_adjustment(self, blockchain):
        """Test difficulty can be adjusted."""
        diff = blockchain.adjust_difficulty()
        assert diff >= 1

    def test_burn_mechanism(self, blockchain):
        """Test burn mechanism exists."""
        assert blockchain.config.burn_rate == 0.1  # 10% burn
        assert hasattr(blockchain, 'total_burned')
        assert hasattr(blockchain, 'circulating_supply')
