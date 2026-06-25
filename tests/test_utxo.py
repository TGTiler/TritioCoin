"""
Tests for UTXO module.
"""
import pytest
import time
from core.blockchain import Blockchain
from core.wallet import Wallet
from core.transaction import Transaction
from core.block import Block
from core.utxo import UTXOManager
from core.constants import SATOSHIS_PER_TRC


class TestUTXO:
    """Test UTXO selection and transaction creation."""

    def test_utxo_balance(self, db, testnet):
        """Test UTXO balance calculation."""
        bc = Blockchain(testnet, db)
        utxo = UTXOManager(db)
        w = Wallet.create()
        miner_reward = int(bc.reward_at() * 0.7)

        for i in range(3):
            time.sleep(0.01)
            coinbase = Transaction("COINBASE", w.pubkey_hex(), miner_reward)
            coinbase.timestamp = int(time.time() * 1000) + i
            coinbase.tx_hash = coinbase.compute_hash()
            block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
            block.hash = block.content_hash()
            block.pow_hash = "0" * bc.difficulty + "test"
            bc.add_block(block)

        # 3 blocks * 35 TRC (70% of 50) = 105 TRC
        assert utxo.get_balance(w.pubkey_hex()) == 105.0

    def test_utxo_selection(self, db, testnet):
        """Test UTXO selection algorithm."""
        bc = Blockchain(testnet, db)
        w = Wallet.create()
        miner_reward = int(bc.reward_at() * 0.7)

        for i in range(3):
            time.sleep(0.01)
            coinbase = Transaction("COINBASE", w.pubkey_hex(), miner_reward)
            coinbase.timestamp = int(time.time() * 1000) + i
            coinbase.tx_hash = coinbase.compute_hash()
            block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
            block.hash = block.content_hash()
            block.pow_hash = "0" * bc.difficulty + "test"
            bc.add_block(block)

        # Select 80 TRC worth (in satoshis)
        selected = db.select_utxos(w.pubkey_hex(), 80 * SATOSHIS_PER_TRC)
        assert len(selected) > 0
        assert sum(s["amount"] for s in selected) >= 80 * SATOSHIS_PER_TRC

    def test_create_transaction(self, db, testnet):
        """Test UTXO-based transaction creation."""
        bc = Blockchain(testnet, db)
        utxo = UTXOManager(db)
        w1 = Wallet.create()
        w2 = Wallet.create()
        miner_reward = int(bc.reward_at() * 0.7)

        for i in range(3):
            time.sleep(0.01)
            coinbase = Transaction("COINBASE", w1.pubkey_hex(), miner_reward)
            coinbase.timestamp = int(time.time() * 1000) + i
            coinbase.tx_hash = coinbase.compute_hash()
            block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
            block.hash = block.content_hash()
            block.pow_hash = "0" * bc.difficulty + "test"
            bc.add_block(block)

        tx = utxo.create_transaction(w1, w2.pubkey_hex(), 30.0, 0.01)
        assert tx is not None
        assert tx.is_valid()

    def test_insufficient_funds(self, db, testnet):
        """Test transaction with insufficient funds."""
        bc = Blockchain(testnet, db)
        utxo = UTXOManager(db)
        w1 = Wallet.create()
        w2 = Wallet.create()

        tx = utxo.create_transaction(w1, w2.pubkey_hex(), 100.0, 0.01)
        assert tx is None

    def test_utxo_get_unspent(self, db, testnet):
        """Test getting unspent UTXOs."""
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

        utxos = db.get_unspent_utxos(w.pubkey_hex())
        assert len(utxos) == 1
        assert utxos[0]["amount"] == miner_reward * SATOSHIS_PER_TRC
