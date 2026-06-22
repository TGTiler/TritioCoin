"""
Tests for Multi-Signature module.
"""
import pytest
from core.multisig import MultiSigWallet, create_multisig_wallet
from core.wallet import Wallet


class TestMultiSig:
    """Test multi-signature wallet functionality."""

    def test_create_multisig(self):
        """Test creating a multi-sig wallet."""
        msig, wallets = create_multisig_wallet(2, 3)
        assert msig.required == 2
        assert msig.total_keys == 3
        assert msig.address.startswith("M")
        assert len(wallets) == 3

    def test_collect_signatures(self):
        """Test collecting signatures."""
        msig, wallets = create_multisig_wallet(2, 3)
        tx = msig.create_transaction("04abc", 50.0)
        tx = msig.add_signature(tx, wallets[0].privkey_hex(), wallets[0].pubkey_hex())
        assert len(tx["signatures"]) == 1
        tx = msig.add_signature(tx, wallets[1].privkey_hex(), wallets[1].pubkey_hex())
        assert len(tx["signatures"]) == 2

    def test_verify_transaction(self):
        """Test transaction verification."""
        msig, wallets = create_multisig_wallet(2, 3)
        tx = msig.create_transaction("04abc", 50.0)
        tx = msig.add_signature(tx, wallets[0].privkey_hex(), wallets[0].pubkey_hex())
        tx = msig.add_signature(tx, wallets[1].privkey_hex(), wallets[1].pubkey_hex())
        valid, msg = msig.verify_transaction(tx)
        assert valid
        assert msg == "Valid"

    def test_insufficient_signatures(self):
        """Test rejection with insufficient signatures."""
        msig, wallets = create_multisig_wallet(2, 3)
        tx = msig.create_transaction("04abc", 50.0)
        tx = msig.add_signature(tx, wallets[0].privkey_hex(), wallets[0].pubkey_hex())
        valid, msg = msig.verify_transaction(tx)
        assert not valid
        assert "2" in msg

    def test_unauthorized_signer(self):
        """Test rejection of unauthorized signer."""
        msig, wallets = create_multisig_wallet(2, 3)
        outsider = Wallet.create()
        tx = msig.create_transaction("04abc", 50.0)
        with pytest.raises(ValueError):
            msig.add_signature(tx, outsider.privkey_hex(), outsider.pubkey_hex())

    def test_is_signed(self):
        """Test is_signed check."""
        msig, wallets = create_multisig_wallet(2, 3)
        tx = msig.create_transaction("04abc", 50.0)
        assert not msig.is_signed(tx)
        tx = msig.add_signature(tx, wallets[0].privkey_hex(), wallets[0].pubkey_hex())
        assert not msig.is_signed(tx)
        tx = msig.add_signature(tx, wallets[1].privkey_hex(), wallets[1].pubkey_hex())
        assert msig.is_signed(tx)

    def test_save_load(self, tmp_dir):
        """Test save and load multi-sig wallet."""
        msig, wallets = create_multisig_wallet(2, 3)
        path = str(tmp_dir / "msig.json")
        msig.save(path)
        msig2 = MultiSigWallet.load(path)
        assert msig2.address == msig.address
        assert msig2.required == msig.required

    def test_redeem_script(self):
        """Test redeem script generation."""
        msig, _ = create_multisig_wallet(2, 3)
        script = msig.create_redeem_script()
        assert len(script) > 0
        assert script[-1] == 0xae  # CHECKMULTISIG opcode
