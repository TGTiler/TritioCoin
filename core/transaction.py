"""
TritioCoin Transaction System
Uses satoshis (8 decimal places) for precision-safe monetary operations.
"""
import hashlib
import json
import time
from typing import Optional, List, Dict
from core.constants import SATOSHIS_PER_TRC, trc_to_satoshis, satoshis_to_trc, format_trc

import ecdsa


class Transaction:
    """
    Represents a TritioCoin transaction.
    
    All amounts are stored internally as satoshis (integers).
    Displayed as TRC (float with 8 decimals).
    """
    __slots__ = ('sender_pubkey', 'recipient_pubkey', 'amount_satoshis', 'fee_satoshis',
                 'data', 'timestamp', 'signature', 'tx_hash',
                 'quantum_signature', 'signature_mode', 'inputs', 'change_satoshis')

    def __init__(self, sender: str, recipient: str, amount_trc: float,
                 fee_trc: float = 0.0, data: str = ""):
        self.sender_pubkey = sender
        self.recipient_pubkey = recipient
        self.amount_satoshis = trc_to_satoshis(amount_trc)
        self.fee_satoshis = trc_to_satoshis(fee_trc)
        self.data = data
        self.timestamp = int(time.time())
        self.signature: Optional[bytes] = None
        self.tx_hash: Optional[str] = None
        self.quantum_signature: Optional[dict] = None
        self.signature_mode: str = "ecdsa"
        self.inputs: Optional[list] = None
        self.change_satoshis: int = 0

    @property
    def amount(self) -> float:
        """Get amount in TRC (for display/compatibility)."""
        return satoshis_to_trc(self.amount_satoshis)

    @property
    def fee(self) -> float:
        """Get fee in TRC (for display/compatibility)."""
        return satoshis_to_trc(self.fee_satoshis)

    @property
    def change(self) -> float:
        """Get change in TRC (for display/compatibility)."""
        return satoshis_to_trc(self.change_satoshis)

    def payload(self) -> dict:
        """Get transaction payload for hashing."""
        return {
            "sender": self.sender_pubkey,
            "recipient": self.recipient_pubkey,
            "amount_satoshis": self.amount_satoshis,
            "fee_satoshis": self.fee_satoshis,
            "data": self.data,
            "timestamp": self.timestamp
        }

    def compute_hash(self) -> str:
        """Compute transaction hash from payload."""
        raw = json.dumps(self.payload(), sort_keys=True).encode()
        return hashlib.sha256(hashlib.sha256(raw).digest()).hexdigest()

    def sign(self, private_key, quantum_keys: dict = None):
        """Sign the transaction."""
        self.tx_hash = self.compute_hash()
        msg = bytes.fromhex(self.tx_hash)
        self.signature = private_key.sign(msg)
        if quantum_keys:
            from core.quantum import HybridSignature
            h = HybridSignature()
            h.ecdsa_key = private_key
            self.quantum_signature = h.sign(msg)
            self.signature_mode = "hybrid"

    def verify(self) -> bool:
        """Verify transaction signature."""
        if not self.signature or not self.sender_pubkey:
            return False
        if self.sender_pubkey == "COINBASE":
            return True
        try:
            vk = ecdsa.VerifyingKey.from_string(
                bytes.fromhex(self.sender_pubkey), curve=ecdsa.SECP256k1
            )
            msg = bytes.fromhex(self.tx_hash)
            return vk.verify(self.signature, msg)
        except Exception:
            return False

    def is_valid(self) -> bool:
        """Validate the transaction."""
        if self.amount_satoshis <= 0 or self.fee_satoshis < 0:
            return False
        if not self.sender_pubkey or not self.recipient_pubkey:
            return False
        if self.sender_pubkey == "COINBASE":
            return True
        if self.tx_hash != self.compute_hash():
            return False
        return self.verify()

    def to_dict(self) -> dict:
        """Serialize transaction to dictionary."""
        d = {
            "sender": self.sender_pubkey,
            "recipient": self.recipient_pubkey,
            "amount_satoshis": self.amount_satoshis,
            "fee_satoshis": self.fee_satoshis,
            "data": self.data,
            "timestamp": self.timestamp,
            "signature": self.signature.hex() if self.signature else None,
            "hash": self.tx_hash,
            "signature_mode": self.signature_mode
        }
        if self.quantum_signature:
            d["quantum_signature"] = self.quantum_signature
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'Transaction':
        """Deserialize transaction from dictionary."""
        # Support both old (float) and new (satoshis) formats
        if "amount_satoshis" in data:
            amount_sat = data["amount_satoshis"]
            fee_sat = data.get("fee_satoshis", 0)
        else:
            amount_sat = trc_to_satoshis(data.get("amount", 0))
            fee_sat = trc_to_satoshis(data.get("fee", 0))

        tx = cls(data["sender"], data["recipient"],
                 satoshis_to_trc(amount_sat),
                 satoshis_to_trc(fee_sat),
                 data.get("data", ""))
        tx.timestamp = data["timestamp"]
        tx.signature_mode = data.get("signature_mode", "ecdsa")
        tx.quantum_signature = data.get("quantum_signature")
        tx.tx_hash = data.get("hash") or tx.compute_hash()
        if data.get("signature"):
            try:
                tx.signature = bytes.fromhex(data["signature"])
            except (ValueError, TypeError):
                pass
        return tx

    def __repr__(self):
        tag = "Q+" if self.signature_mode == "hybrid" else ""
        h = self.tx_hash[:8] if self.tx_hash else "????????"
        return f"Tx({tag}{h} {format_trc(self.amount_satoshis)} TRC)"


class TransactionBuilder:
    """
    Builder for creating transactions with proper UTXO selection.
    """

    @staticmethod
    def create_coinbase(recipient: str, amount_satoshis: int, block_index: int) -> Transaction:
        """Create a coinbase (mining reward) transaction."""
        tx = Transaction("COINBASE", recipient, satoshis_to_trc(amount_satoshis))
        tx.timestamp = int(time.time())
        tx.data = f"Block #{block_index} reward"
        tx.tx_hash = tx.compute_hash()
        return tx

    @staticmethod
    def create_transfer(sender_pubkey: str, recipient: str,
                        amount_satoshis: int, fee_satoshis: int,
                        inputs: List[dict] = None) -> Transaction:
        """Create a transfer transaction."""
        tx = Transaction(sender_pubkey, recipient,
                        satoshis_to_trc(amount_satoshis),
                        satoshis_to_trc(fee_satoshis))
        tx.inputs = inputs
        return tx

    @staticmethod
    def calculate_change(total_input_satoshis: int, amount_satoshis: int,
                         fee_satoshis: int) -> int:
        """Calculate change amount in satoshis."""
        return total_input_satoshis - amount_satoshis - fee_satoshis

    @staticmethod
    def validate_amounts(amount_satoshis: int, fee_satoshis: int) -> bool:
        """Validate transaction amounts."""
        if amount_satoshis <= 0:
            return False
        if fee_satoshis < 0:
            return False
        return True

    @staticmethod
    def format_amount(satoshis: int) -> str:
        """Format satoshis as TRC string."""
        return f"{satoshis_to_trc(satoshis):.8f} TRC"

    @staticmethod
    def parse_amount(trc_str: str) -> int:
        """Parse TRC string to satoshis."""
        return trc_to_satoshis(float(trc_str))
