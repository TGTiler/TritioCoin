"""
Tests for Wallet module.
"""
import pytest
import os
from core.wallet import Wallet


class TestWallet:
    """Test wallet creation, encryption, and recovery."""

    def test_create_wallet(self, tmp_dir):
        """Test creating a new wallet."""
        w = Wallet.create()
        assert w.address.startswith("T")
        assert len(w.mnemonic.split()) == 24
        assert w.privkey_hex()
        assert w.pubkey_hex()

    def test_create_quantum_wallet(self, tmp_dir):
        """Test creating a quantum-resistant wallet."""
        w = Wallet.create(quantum=True)
        assert w.address.startswith("Q")
        assert w.hybrid_keys is not None

    def test_recover_from_mnemonic(self):
        """Test wallet recovery from mnemonic."""
        w1 = Wallet.create()
        w2 = Wallet.from_mnemonic(w1.mnemonic)
        assert w1.address == w2.address
        assert w1.pubkey_hex() == w2.pubkey_hex()

    def test_invalid_mnemonic(self):
        """Test that invalid mnemonic is rejected."""
        with pytest.raises(ValueError):
            Wallet.from_mnemonic("invalid words here")

    def test_encrypt_decrypt(self, tmp_dir):
        """Test wallet encryption and decryption."""
        w = Wallet.create()
        path = str(tmp_dir / "test_wallet.json")
        w.save(path, "test_password")
        w2 = Wallet.load(path, "test_password")
        assert w.address == w2.address

    def test_wrong_password(self, tmp_dir):
        """Test that wrong password is rejected."""
        w = Wallet.create()
        path = str(tmp_dir / "test_wallet.json")
        w.save(path, "correct_password")
        with pytest.raises(Exception):
            Wallet.load(path, "wrong_password")

    def test_address_format(self):
        """Test address format."""
        w = Wallet.create()
        assert w.address[0] == "T"
        assert len(w.address) > 20

    def test_sign_transaction(self):
        """Test transaction signing."""
        w = Wallet.create()
        sigs = w.sign_tx(b"test data")
        assert "ecdsa_signature" in sigs
        assert sigs["ecdsa_signature"] is not None

    def test_sign_quantum(self):
        """Test quantum transaction signing."""
        w = Wallet.create(quantum=True)
        sigs = w.sign_tx(b"test data")
        assert "ecdsa_signature" in sigs
        assert "quantum_signature" in sigs
        assert sigs["signature_mode"] == "hybrid"

    def test_pubkey_hex(self):
        """Test public key hex format."""
        w = Wallet.create()
        pubkey = w.pubkey_hex()
        assert len(pubkey) == 128  # 64 bytes hex
        assert all(c in '0123456789abcdef' for c in pubkey)

    def test_privkey_hex(self):
        """Test private key hex format."""
        w = Wallet.create()
        privkey = w.privkey_hex()
        assert len(privkey) == 64  # 32 bytes hex
        assert all(c in '0123456789abcdef' for c in privkey)
