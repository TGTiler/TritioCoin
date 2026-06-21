"""
Tests for Database module.
"""
import pytest
from core.database import Database


class TestDatabase:
    """Test database operations."""

    def test_create_tables(self, db):
        """Test that tables are created."""
        assert db.get_block_height() >= -1

    def test_save_get_block(self, db):
        """Test block save and retrieval."""
        block_data = {
            "hash": "abc123",
            "header": {"previous_hash": "0" * 64, "timestamp": 1234567890,
                       "nonce": 0, "difficulty": 2},
            "transactions": []
        }
        db.save_block(0, block_data)
        retrieved = db.get_block(0)
        assert retrieved is not None
        assert retrieved["hash"] == "abc123"

    def test_save_get_transaction(self, db):
        """Test transaction save and retrieval."""
        tx_data = {
            "hash": "tx123",
            "sender": "sender1",
            "recipient": "recv1",
            "amount": 50.0,
            "fee": 0.01,
            "data": "",
            "timestamp": 1234567890
        }
        db.save_transaction(tx_data, 1)
        tx = db.get_tx_by_hash("tx123")
        assert tx is not None
        assert tx["amount"] == 50.0

    def test_balance_operations(self, db):
        """Test balance get/set."""
        db.set_balance("addr1", 100.0)
        assert db.get_balance("addr1") == 100.0
        db.set_balance("addr1", 200.0)
        assert db.get_balance("addr1") == 200.0

    def test_utxo_operations(self, db):
        """Test UTXO save/spend/query."""
        db.save_utxo("tx1", "sender1", "recv1", 100.0, 0.01, 1)
        utxos = db.get_unspent_utxos("recv1")
        assert len(utxos) == 1
        assert utxos[0]["amount"] == 100.0

        db.spend_utxo("tx1")
        assert db.is_utxo_spent("tx1")
        utxos = db.get_unspent_utxos("recv1")
        assert len(utxos) == 0

    def test_select_utxos(self, db):
        """Test UTXO selection algorithm."""
        db.save_utxo("tx1", "s", "r", 50.0, 0.01, 1)
        db.save_utxo("tx2", "s", "r", 30.0, 0.01, 2)
        db.save_utxo("tx3", "s", "r", 20.0, 0.01, 3)

        selected = db.select_utxos("r", 60.0)
        assert len(selected) > 0
        assert sum(s["amount"] for s in selected) >= 60.0

    def test_mempool_operations(self, db):
        """Test mempool add/remove/query."""
        tx_data = {
            "tx_hash": "mempool_tx1",
            "sender": "s1",
            "recipient": "r1",
            "amount": 10.0,
            "fee": 0.001,
            "data": "",
            "timestamp": 1234567890,
            "signature": None,
            "signature_mode": "ecdsa",
            "hash": "mempool_tx1"
        }
        db.add_mempool(tx_data)
        assert db.mempool_size() == 1

        db.remove_mempool("mempool_tx1")
        assert db.mempool_size() == 0

    def test_prune_blocks(self, db):
        """Test block pruning."""
        for i in range(5):
            db.save_block(i, {"hash": f"block{i}", "header": {"previous_hash": "0" * 64, "timestamp": 1234567890, "nonce": 0, "difficulty": 2}, "transactions": []})

        pruned = db.prune_blocks(keep_blocks=2)
        assert pruned > 0

    def test_db_size(self, db):
        """Test database size reporting."""
        size = db.get_db_size()
        assert "size_bytes" in size
        assert "blocks" in size
