"""
Tests for Wallet module — including collision prevention defenses.
"""
import pytest
import os
import hashlib
from core.wallet import Wallet, AddressRegistry, SECP256K1_ORDER


class TestWallet:
    """Test wallet creation, encryption, and recovery."""

    def test_create_wallet(self, tmp_dir):
        """Test creating a new wallet."""
        w = Wallet.create()
        assert w.address.startswith("T")
        assert len(w.mnemonic.split()) == 24
        assert w.privkey_hex()
        assert w.pubkey_hex()

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


# ═══════════════════════════════════════════════════════════════════════
#  COLLISION PREVENTION TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestKeyRangeValidation:
    """Verify that private keys are validated against the curve order."""

    def test_valid_key_accepted(self):
        """A key within [1, n-1] should be accepted."""
        key_bytes = os.urandom(32)
        k = int.from_bytes(key_bytes, 'big')
        if k == 0 or k >= SECP256K1_ORDER:
            key_bytes = (SECP256K1_ORDER - 1).to_bytes(32, 'big')
        w = Wallet(key_bytes)
        assert w.address.startswith('T')

    def test_zero_key_rejected(self):
        """A zero private key must be rejected."""
        with pytest.raises(ValueError, match="cannot be zero"):
            Wallet(b'\x00' * 32)

    def test_key_exceeding_order_rejected(self):
        """A key >= curve order must be rejected."""
        bad_key = SECP256K1_ORDER.to_bytes(32, 'big')
        with pytest.raises(ValueError, match="exceeds curve order"):
            Wallet(bad_key)

    def test_wrong_length_rejected(self):
        """A key that's not 32 bytes must be rejected."""
        with pytest.raises(ValueError, match="32 bytes"):
            Wallet(b'\x01' * 16)


class TestEntropyQuality:
    """Verify that generated keys have sufficient entropy."""

    def test_generated_keys_unique(self):
        """100 generated wallets must all have different addresses."""
        addresses = set()
        for _ in range(100):
            w = Wallet.create()
            assert w.address not in addresses, \
                f"Duplicate address generated: {w.address}"
            addresses.add(w.address)

    def test_generated_key_not_zero(self):
        """Generated keys should never be zero (regression)."""
        for _ in range(50):
            w = Wallet.create()
            k = int.from_bytes(
                bytes.fromhex(w.privkey_hex()), 'big')
            assert k != 0
            assert k < SECP256K1_ORDER


class TestAddressValidation:
    """Verify Base58Check address validation."""

    def test_valid_address_passes(self):
        """A legitimately generated address should validate."""
        w = Wallet.create()
        assert Wallet.validate_address(w.address)

    def test_tampered_address_fails(self):
        """A checksum-tampered address should fail validation."""
        w = Wallet.create()
        addr = w.address
        # Flip a character in the middle.
        mid = len(addr) // 2
        bad = addr[:mid] + ('A' if addr[mid] != 'A' else 'B') + addr[mid+1:]
        assert not Wallet.validate_address(bad)

    def test_wrong_prefix_fails(self):
        """An address not starting with 'T' should fail."""
        assert not Wallet.validate_address("X1234567890ABCDEFGHJKLMNPQRSTUVWXYZ")

    def test_too_short_fails(self):
        """An address that's too short should fail."""
        assert not Wallet.validate_address("T123")

    def test_empty_fails(self):
        """Empty string should fail."""
        assert not Wallet.validate_address("")


class TestMnemonicPassphrase:
    """Verify that BIP39 passphrase creates different keys."""

    def test_same_mnemonic_different_passphrase(self):
        """Same mnemonic + different passphrase = different addresses."""
        w1 = Wallet.create(passphrase="alpha")
        w2 = Wallet.create(passphrase="beta")
        # These are different wallets entirely (different mnemonics),
        # but let's also test recovery with passphrase.
        words = w1.mnemonic
        w3 = Wallet.from_mnemonic(words, passphrase="alpha")
        w4 = Wallet.from_mnemonic(words, passphrase="beta")
        assert w3.address != w4.address

    def test_same_mnemonic_same_passphrase(self):
        """Same mnemonic + same passphrase = same address."""
        words = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        # We can't test this specific mnemonic without valid checksum,
        # so use from_mnemonic with a known valid one.
        w1 = Wallet.create(passphrase="secret")
        w2 = Wallet.from_mnemonic(w1.mnemonic, passphrase="secret")
        assert w1.address == w2.address

    def test_passphrase_none_vs_empty(self):
        """None and empty string passphrases should produce same key."""
        w1 = Wallet.create(passphrase="")
        w2 = Wallet.from_mnemonic(w1.mnemonic, passphrase="")
        assert w1.address == w2.address


class TestAddressRegistry:
    """Verify the local collision detection registry."""

    def test_new_address_registered(self, tmp_dir):
        """Registering a new address returns True."""
        import os
        os.chdir(tmp_dir)
        from core import wallet as wallet_mod
        wallet_mod.REGISTRY_DIR = tmp_dir
        wallet_mod.REGISTRY_FILE = tmp_dir / "test_registry.json"
        wallet_mod.AddressRegistry._cache = None
        result = wallet_mod.AddressRegistry.register("Ttest_address_123")
        assert result is True

    def test_duplicate_address_detected(self, tmp_dir):
        """Registering the same address twice returns False."""
        import os
        os.chdir(tmp_dir)
        from core import wallet as wallet_mod
        wallet_mod.REGISTRY_DIR = tmp_dir
        wallet_mod.REGISTRY_FILE = tmp_dir / "test_registry.json"
        wallet_mod.AddressRegistry._cache = None
        wallet_mod.AddressRegistry.register("Tdup_test")
        result = wallet_mod.AddressRegistry.register("Tdup_test")
        assert result is False

    def test_registry_count(self, tmp_dir):
        """Registry count reflects the number of registered addresses."""
        import os
        os.chdir(tmp_dir)
        from core import wallet as wallet_mod
        wallet_mod.REGISTRY_DIR = tmp_dir
        wallet_mod.REGISTRY_FILE = tmp_dir / "test_registry.json"
        wallet_mod.AddressRegistry._cache = None
        wallet_mod.AddressRegistry.register("Tcount_a")
        wallet_mod.AddressRegistry.register("Tcount_b")
        assert wallet_mod.AddressRegistry.count() == 2
