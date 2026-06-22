"""
Tests for HD Wallet module.
"""
import pytest
from core.hdwallet import HDWallet, HDKey


class TestHDWallet:
    """Test HD wallet functionality."""

    def test_create_hd_wallet(self):
        """Test creating an HD wallet."""
        hd = HDWallet()
        assert hd.mnemonic
        assert len(hd.mnemonic.split()) == 24

    def test_generate_addresses(self):
        """Test address generation."""
        hd = HDWallet()
        addrs = hd.generate_addresses(10)
        assert len(addrs) == 10
        # All addresses should be unique
        addr_list = [a[0] for a in addrs]
        assert len(addr_list) == len(set(addr_list))

    def test_address_format(self):
        """Test address format."""
        hd = HDWallet()
        addr = hd.get_address()
        assert addr.startswith("T")
        assert len(addr) > 20

    def test_derive_path(self):
        """Test path derivation."""
        hd = HDWallet()
        key = hd.get_private_key(0, 0, 0)
        assert key is not None
        assert key.private_key

    def test_sign_verify(self):
        """Test signing and verification."""
        hd = HDWallet()
        key = hd.get_private_key(0, 0, 0)
        msg = b"test message"
        sig = key.sign(msg)
        assert key.verify(msg, sig)

    def test_wrong_message_verify(self):
        """Test verification fails with wrong message."""
        hd = HDWallet()
        key = hd.get_private_key(0, 0, 0)
        sig = key.sign(b"correct message")
        assert not key.verify(b"wrong message", sig)

    def test_save_load(self, tmp_dir):
        """Test save and load HD wallet."""
        hd = HDWallet()
        path = str(tmp_dir / "hd_wallet.json")
        hd.save(path, "password")
        hd2 = HDWallet.load(path, "password")
        assert hd2.mnemonic == hd.mnemonic

    def test_export_xpub(self):
        """Test extended public key export."""
        hd = HDWallet()
        xpub = hd.export_xpub()
        assert len(xpub) > 0

    def test_multiple_accounts(self):
        """Test multiple account derivation."""
        hd = HDWallet()
        addr0 = hd.get_address(account_index=0)
        addr1 = hd.get_address(account_index=1)
        assert addr0 != addr1

    def test_change_addresses(self):
        """Test change address derivation."""
        hd = HDWallet()
        addr_ext = hd.get_address(account_index=0, change=0, address_index=0)
        addr_int = hd.get_address(account_index=0, change=1, address_index=0)
        assert addr_ext != addr_int

    def test_deterministic(self):
        """Test deterministic address generation."""
        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        hd1 = HDWallet(mnemonic=mnemonic)
        hd2 = HDWallet(mnemonic=mnemonic)
        assert hd1.get_address() == hd2.get_address()
