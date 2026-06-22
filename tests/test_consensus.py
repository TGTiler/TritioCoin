"""
Tests for Consensus module.
"""
import pytest
from core.consensus import ConsensusEngine
from core.wallet import Wallet
from core.block import Block


class TestConsensus:
    """Test PoS consensus functionality."""

    def test_register_validator(self, consensus):
        """Test validator registration."""
        assert len(consensus.validators) == 5

    def test_min_stake(self, blockchain):
        """Test minimum stake enforcement."""
        ce = ConsensusEngine(blockchain)
        w = Wallet.create()
        assert not ce.register_validator(w, 50.0)
        assert ce.register_validator(w, 100.0)

    def test_select_validators(self, consensus):
        """Test validator selection."""
        selected = consensus.select_validators_for_block(1)
        assert len(selected) >= 3

    def test_sign_block(self, consensus):
        """Test block signing."""
        w = Wallet.create()
        consensus.register_validator(w, 200.0)
        block = Block(1, "0" * 64, [], 2)
        block.hash = block.content_hash()
        sig = consensus.sign_block(block, w)
        assert sig is not None

    def test_verify_signature(self, consensus):
        """Test signature verification."""
        w = Wallet.create()
        consensus.register_validator(w, 200.0)
        block = Block(1, "0" * 64, [], 2)
        block.hash = block.content_hash()
        sig = consensus.sign_block(block, w)
        assert consensus.verify_block_signature(block, w.address, sig)

    def test_get_stats(self, consensus):
        """Test validator statistics."""
        stats = consensus.get_validator_stats()
        assert stats["total_validators"] == 5
        assert stats["active_validators"] == 5
        assert stats["total_stake"] == 1000.0

    def test_unregister_validator(self, consensus):
        """Test validator unregistration."""
        w = Wallet.create()
        consensus.register_validator(w, 200.0)
        assert consensus.unregister_validator(w.address)
        assert w.address not in consensus.validators

    def test_add_stake(self, consensus):
        """Test adding stake."""
        w = Wallet.create()
        consensus.register_validator(w, 100.0)
        assert consensus.add_stake(w.address, 50.0)
        assert consensus.validators[w.address].stake == 150.0
