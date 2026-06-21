"""
TritioCoin Multi-Signature Wallet
Supports M-of-N signature schemes (e.g., 2-of-3, 3-of-5).
"""
import hashlib
import json
import os
import ecdsa
from typing import List, Optional, Tuple, Dict
from core.wallet import Wallet


class MultiSigWallet:
    """
    Multi-signature wallet requiring M-of-N signatures.
    
    Example: 2-of-3 means 2 out of 3 key holders must sign to spend.
    """

    def __init__(self, required_signatures: int, public_keys: List[str],
                 address: str = None):
        """
        Create a multi-signature wallet.
        
        Args:
            required_signatures: Number of signatures required (M)
            public_keys: List of public key hex strings (N keys)
            address: Optional pre-computed address
        """
        if required_signatures < 1:
            raise ValueError("Required signatures must be >= 1")
        if required_signatures > len(public_keys):
            raise ValueError("Required signatures cannot exceed total keys")

        self.required = required_signatures
        self.public_keys = sorted(public_keys)  # Sort for determinism
        self.total_keys = len(public_keys)
        self.address = address or self._compute_address()

    def _compute_address(self) -> str:
        """Compute multi-sig address from all public keys."""
        # Combine all public keys deterministically
        combined = b""
        for pubkey_hex in self.public_keys:
            combined += bytes.fromhex(pubkey_hex)

        # Hash with SHA256 + RIPEMD160
        sha256 = hashlib.sha256(combined).digest()
        ripemd160 = hashlib.new('ripemd160', sha256).digest()

        # Add version byte (0x05 for multi-sig)
        versioned = b'\x05' + ripemd160

        # Add checksum
        checksum = hashlib.sha256(hashlib.sha256(versioned).digest()).digest()[:4]

        # Base58 encode
        return "M" + self._base58(versioned + checksum)

    @staticmethod
    def _base58(data: bytes) -> str:
        abc = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        n = int.from_bytes(data, 'big')
        out = ""
        while n > 0:
            n, r = divmod(n, 58)
            out = abc[r] + out
        for b in data:
            if b == 0:
                out = '1' + out
            else:
                break
        return out

    def create_redeem_script(self) -> bytes:
        """
        Create a redeem script for the multi-sig wallet.
        Format: <M> <pubkey1> <pubkey2> ... <pubkeyN> <N> CHECKMULTISIG
        """
        script = bytearray()
        script.append(self.required)  # M

        for pubkey_hex in self.public_keys:
            pubkey_bytes = bytes.fromhex(pubkey_hex)
            script.append(len(pubkey_bytes))
            script.extend(pubkey_bytes)

        script.append(self.total_keys)  # N
        script.extend(b'\xae')  # CHECKMULTISIG opcode

        return bytes(script)

    def create_transaction(self, recipient: str, amount: float,
                           fee: float = 0.001) -> Dict:
        """
        Create a multi-signature transaction.
        Returns a transaction dict that requires M signatures.
        """
        # Create unsigned transaction
        tx_data = {
            "type": "multisig",
            "sender": self.address,
            "recipient": recipient,
            "amount": amount,
            "fee": fee,
            "required_sigs": self.required,
            "total_sigs": self.total_keys,
            "public_keys": self.public_keys,
            "signatures": [],
            "redeem_script": self.create_redeem_script().hex()
        }

        # Compute transaction hash
        tx_json = json.dumps(tx_data, sort_keys=True).encode()
        tx_data["hash"] = hashlib.sha256(tx_json).hexdigest()

        return tx_data

    def add_signature(self, tx_data: dict, signer_private_key: str,
                      signer_public_key: str) -> dict:
        """
        Add a signature to a multi-signature transaction.
        
        Args:
            tx_data: Transaction dict from create_transaction
            signer_private_key: Private key hex of the signer
            signer_public_key: Public key hex of the signer
            
        Returns:
            Updated transaction dict
        """
        # Verify the signer is authorized
        if signer_public_key not in self.public_keys:
            raise ValueError("Signer is not authorized for this wallet")

        # Check if already signed by this key
        for sig in tx_data["signatures"]:
            if sig["public_key"] == signer_public_key:
                raise ValueError("Already signed by this key")

        # Sign the transaction
        private_key = ecdsa.SigningKey.from_string(
            bytes.fromhex(signer_private_key), curve=ecdsa.SECP256k1
        )
        msg_bytes = bytes.fromhex(tx_data["hash"])
        signature = private_key.sign(msg_bytes)

        tx_data["signatures"].append({
            "public_key": signer_public_key,
            "signature": signature.hex()
        })

        return tx_data

    def verify_transaction(self, tx_data: dict) -> Tuple[bool, str]:
        """
        Verify a multi-signature transaction.
        Returns (is_valid, message).
        """
        # Check if we have enough signatures
        if len(tx_data["signatures"]) < self.required:
            return False, f"Need {self.required} signatures, have {len(tx_data['signatures'])}"

        # Verify each signature
        for sig_data in tx_data["signatures"]:
            pubkey_hex = sig_data["public_key"]
            signature_hex = sig_data["signature"]

            # Verify the public key is authorized
            if pubkey_hex not in self.public_keys:
                return False, f"Unauthorized key: {pubkey_hex[:16]}..."

            # Verify the signature
            try:
                vk = ecdsa.VerifyingKey.from_string(
                    bytes.fromhex(pubkey_hex), curve=ecdsa.SECP256k1
                )
                msg_bytes = bytes.fromhex(tx_data["hash"])
                vk.verify(bytes.fromhex(signature_hex), msg_bytes)
            except Exception:
                return False, f"Invalid signature from {pubkey_hex[:16]}..."

        return True, "Valid"

    def is_signed(self, tx_data: dict) -> bool:
        """Check if transaction has enough signatures to execute."""
        return len(tx_data["signatures"]) >= self.required

    def save(self, filepath: str):
        """Save multi-sig wallet to file."""
        data = {
            "required": self.required,
            "total_keys": self.total_keys,
            "public_keys": self.public_keys,
            "address": self.address,
            "redeem_script": self.create_redeem_script().hex()
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> 'MultiSigWallet':
        """Load multi-sig wallet from file."""
        with open(filepath) as f:
            data = json.load(f)
        return cls(
            required_signatures=data["required"],
            public_keys=data["public_keys"],
            address=data["address"]
        )

    def __repr__(self):
        return f"MultiSig({self.required}/{self.total_keys}:{self.address[:16]}...)"


def create_multisig_wallet(required: int, num_keys: int) -> Tuple[MultiSigWallet, List[Wallet]]:
    """
    Create a new multi-signature wallet with generated keys.
    
    Args:
        required: Number of required signatures (M)
        num_keys: Total number of keys (N)
        
    Returns:
        Tuple of (MultiSigWallet, list of individual Wallets)
    """
    wallets = []
    public_keys = []

    for _ in range(num_keys):
        w = Wallet.create()
        wallets.append(w)
        public_keys.append(w.pubkey_hex())

    multisig = MultiSigWallet(required, public_keys)
    return multisig, wallets
