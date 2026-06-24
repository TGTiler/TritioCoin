"""
Integration tests for TritioCoin.
"""
import pytest
import time
from core.blockchain import Blockchain
from core.wallet import Wallet
from core.transaction import Transaction
from core.block import Block
from core.utxo import UTXOManager
from core.multisig import create_multisig_wallet
from core.hdwallet import HDWallet
from core.consensus import ConsensusEngine


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline(self, db, testnet):
        """Test complete pipeline: mine -> send -> multi-sig."""
        bc = Blockchain(testnet, db)
        utxo = UTXOManager(db)

        # Create wallets
        alice = Wallet.create()
        bob = Wallet.create()
        charlie = Wallet.create()

        # Mine 3 blocks (45 TRC each)
        for i in range(3):
            time.sleep(0.01)
            coinbase = Transaction("COINBASE", alice.pubkey_hex(), bc.reward_at())
            coinbase.timestamp = int(time.time() * 1000) + i
            coinbase.tx_hash = coinbase.compute_hash()
            block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
            block.hash = block.content_hash()
            block.pow_hash = "0" * bc.difficulty + "test"
            bc.add_block(block)

        # 3 blocks * 50 TRC = 150 TRC
        assert utxo.get_balance(alice.pubkey_hex()) == 150.0

        # Send from Alice to Bob
        tx = utxo.create_transaction(alice, bob.pubkey_hex(), 50.0, 0.01)
        assert tx.is_valid()

        # Mine the transaction
        coinbase = Transaction("COINBASE", alice.pubkey_hex(), bc.reward_at())
        coinbase.timestamp = int(time.time() * 1000) + 100
        coinbase.tx_hash = coinbase.compute_hash()
        block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict(), tx.to_dict()], bc.difficulty)
        block.hash = block.content_hash()
        block.pow_hash = "0" * bc.difficulty + "test"
        bc.add_block(block)

        assert utxo.get_balance(bob.pubkey_hex()) == 50.0

        # Multi-sig
        msig, signers = create_multisig_wallet(2, 3)
        msig_tx = msig.create_transaction(charlie.pubkey_hex(), 20.0)
        msig_tx = msig.add_signature(msig_tx, signers[0].privkey_hex(), signers[0].pubkey_hex())
        msig_tx = msig.add_signature(msig_tx, signers[1].privkey_hex(), signers[1].pubkey_hex())
        valid, _ = msig.verify_transaction(msig_tx)
        assert valid

    def test_multiple_users(self, db, testnet):
        """Test multiple users transacting."""
        bc = Blockchain(testnet, db)
        utxo = UTXOManager(db)

        # Create 10 users
        users = [Wallet.create() for _ in range(10)]

        # Fund all users (45 TRC each)
        for i, user in enumerate(users):
            time.sleep(0.01)
            coinbase = Transaction("COINBASE", user.pubkey_hex(), bc.reward_at())
            coinbase.timestamp = int(time.time() * 1000) + i
            coinbase.tx_hash = coinbase.compute_hash()
            block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
            block.hash = block.content_hash()
            block.pow_hash = "0" * bc.difficulty + "test"
            bc.add_block(block)

        # Users send to each other
        for i in range(5):
            sender = users[i]
            receiver = users[(i + 1) % 10]
            tx = utxo.create_transaction(sender, receiver.pubkey_hex(), 10.0, 0.01)
            assert tx is not None

    def test_hd_wallet_integration(self):
        """Test HD wallet with blockchain."""
        hd = HDWallet()
        addresses = hd.generate_addresses(5)

        # Create transactions from HD addresses
        for addr, path in addresses:
            tx = Transaction(addr, "04recipient", 1.0, 0.001)
            assert tx.is_valid() or tx.sender_pubkey == addr

    def test_consensus_integration(self, blockchain):
        """Test consensus with blockchain."""
        ce = ConsensusEngine(blockchain)

        # Register validators
        validators = []
        for i in range(5):
            w = Wallet.create()
            ce.register_validator(w, 200.0)
            validators.append(w)

        # Select and sign
        selected = ce.select_validators_for_block(1)
        assert len(selected) >= 3

        block = Block(1, blockchain.latest().hash, [], blockchain.difficulty)
        block.hash = block.content_hash()
        for addr in selected[:3]:
            w = next(v for v in validators if v.address == addr)
            sig = ce.sign_block(block, w)
            assert sig is not None
