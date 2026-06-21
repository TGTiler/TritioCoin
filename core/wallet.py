"""
TritioCoin Wallet
- ECDSA secp256k1
- AES-256-GCM encrypted storage
- BIP39 mnemonic backup
- Quantum-resistant hybrid mode
"""
import hashlib
import json
import os
import getpass
import ecdsa
from mnemonic import Mnemonic
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


class Wallet:
    __slots__ = ('private_key', 'public_key', 'address', 'quantum_mode',
                 'hybrid_keys', 'mnemonic')

    KDF_ITERATIONS = 600_000
    SALT_SIZE = 32
    NONCE_SIZE = 12

    def __init__(self, private_key_bytes: bytes = None, quantum_mode: bool = False,
                 mnemonic: str = None):
        self.quantum_mode = quantum_mode
        self.hybrid_keys = None
        self.mnemonic = mnemonic

        if private_key_bytes:
            self.private_key = ecdsa.SigningKey.from_string(private_key_bytes, curve=ecdsa.SECP256k1)
        else:
            self.private_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)

        self.public_key = self.private_key.get_verifying_key()

        if quantum_mode:
            self._gen_quantum_keys()

        self.address = self._make_address()

    @classmethod
    def create(cls, quantum: bool = False) -> 'Wallet':
        """Create new wallet with BIP39 mnemonic."""
        mnemo = Mnemonic("english")
        words = mnemo.generate(strength=256)
        seed = mnemo.to_seed(words)
        # Use first 32 bytes of seed as private key
        private_key_bytes = seed[:32]
        w = cls(private_key_bytes, quantum, words)
        return w

    @classmethod
    def from_mnemonic(cls, words: str, quantum: bool = False) -> 'Wallet':
        """Recover wallet from BIP39 mnemonic."""
        mnemo = Mnemonic("english")
        if not mnemo.check(words):
            raise ValueError("Invalid mnemonic words")
        seed = mnemo.to_seed(words)
        private_key_bytes = seed[:32]
        return cls(private_key_bytes, quantum, words)

    def _gen_quantum_keys(self):
        from core.quantum import HybridSignature
        self.hybrid_keys = HybridSignature().generate()

    def _make_address(self) -> str:
        pub = self.public_key.to_string()
        h = hashlib.sha256(pub).digest()
        ripemd = hashlib.new('ripemd160', h).digest()
        ver = b'\x05' if self.quantum_mode else b'\x00'
        prefix = "Q" if self.quantum_mode else "T"
        payload = ver + ripemd
        chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        return prefix + self._b58(payload + chk)

    @staticmethod
    def _b58(data: bytes) -> str:
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

    def pubkey_hex(self) -> str:
        return self.public_key.to_string().hex()

    def privkey_hex(self) -> str:
        return self.private_key.to_string().hex()

    def sign_tx(self, data: bytes) -> dict:
        result = {"signature_mode": "hybrid" if self.quantum_mode else "ecdsa"}
        result["ecdsa_signature"] = self.private_key.sign(data)
        if self.quantum_mode and self.hybrid_keys:
            from core.quantum import HybridSignature
            h = HybridSignature()
            h.ecdsa_key = self.private_key
            h.wots_priv = bytes.fromhex(self.hybrid_keys["wots_priv"])
            h.wots_pub = bytes.fromhex(self.hybrid_keys["wots_pub"])
            result["quantum_signature"] = h.sign(data)
        return result

    @staticmethod
    def _derive_key(password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=Wallet.KDF_ITERATIONS,
        )
        return kdf.derive(password.encode('utf-8'))

    @staticmethod
    def _encrypt(plaintext: bytes, password: str) -> dict:
        salt = os.urandom(Wallet.SALT_SIZE)
        nonce = os.urandom(Wallet.NONCE_SIZE)
        key = Wallet._derive_key(password, salt)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return {
            "salt": salt.hex(),
            "nonce": nonce.hex(),
            "data": ciphertext.hex()
        }

    @staticmethod
    def _decrypt(enc: dict, password: str) -> bytes:
        salt = bytes.fromhex(enc["salt"])
        nonce = bytes.fromhex(enc["nonce"])
        ciphertext = bytes.fromhex(enc["data"])
        key = Wallet._derive_key(password, salt)
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    def save(self, path: str, password: str):
        """Save wallet encrypted with password."""
        payload = {
            "private_key": self.privkey_hex(),
            "quantum_mode": self.quantum_mode
        }
        if self.hybrid_keys:
            payload["hybrid_keys"] = self.hybrid_keys

        plaintext = json.dumps(payload).encode('utf-8')
        encrypted = self._encrypt(plaintext, password)

        wallet_data = {
            "version": 2,
            "address": self.address,
            "encrypted": encrypted
        }

        tmp = path + ".tmp"
        with open(tmp, 'w') as f:
            json.dump(wallet_data, f)
        if os.path.exists(path):
            os.replace(tmp, path)
        else:
            os.rename(tmp, path)

    @classmethod
    def load(cls, path: str, password: str = None) -> 'Wallet':
        """Load wallet, decrypting with password if needed."""
        with open(path, 'r') as f:
            wallet_data = json.load(f)

        # Legacy unencrypted format
        if "private_key" in wallet_data and "encrypted" not in wallet_data:
            w = cls(bytes.fromhex(wallet_data["private_key"]),
                    wallet_data.get("quantum_mode", False))
            if wallet_data.get("hybrid_keys"):
                w.hybrid_keys = wallet_data["hybrid_keys"]
            return w

        # Encrypted format
        if password is None:
            password = getpass.getpass("Password: ")

        plaintext = cls._decrypt(wallet_data["encrypted"], password)
        payload = json.loads(plaintext)

        w = cls(bytes.fromhex(payload["private_key"]),
                payload.get("quantum_mode", False))
        if payload.get("hybrid_keys"):
            w.hybrid_keys = payload["hybrid_keys"]
        return w

    def __repr__(self):
        tag = "QR" if self.quantum_mode else "TRC"
        return f"Wallet({tag}:{self.address})"
