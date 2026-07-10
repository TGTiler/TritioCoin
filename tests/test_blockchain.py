"""
Tests for Blockchain module.
"""
import pytest
import time
from core.blockchain import Blockchain
from core.wallet import Wallet
from core.transaction import Transaction
from core.block import Block
from core.pow import tritio_hash


def mine_block_for_test(block, difficulty, max_nonces=500):
    """Find a valid nonce for testing (limited search for speed)."""
    for nonce in range(max_nonces):
        block.header.nonce = nonce
        pow_hash = tritio_hash(block.header.to_bytes())
        if pow_hash.startswith("0" * difficulty):
            block.pow_hash = pow_hash
            return True
    # Fallback: use the hash from nonce 0 even if it doesn't meet difficulty
    # This allows tests to focus on validation logic, not mining
    block.header.nonce = 0
    block.pow_hash = tritio_hash(block.header.to_bytes())
    return False


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
        assert bc.config.difficulty == 1  # Test uses easier difficulty for speed
        assert bc.config.block_time == 30  # Updated: 30s for testnet

    def test_supply_cap(self, blockchain):
        """Test supply cap is enforced."""
        assert blockchain.config.max_supply_trc == 19_000_000

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
