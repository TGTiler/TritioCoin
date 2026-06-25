"""
TritioCoin Wallet
ECDSA secp256k1 with AES-256-GCM encryption.
BIP39 mnemonic for key recovery.
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
    __slots__ = ('private_key', 'public_key', 'address', 'mnemonic')

    KDF_ITERATIONS = 600_000
    SALT_SIZE = 32
    NONCE_SIZE = 12

    def __init__(self, private_key_bytes: bytes = None, mnemonic: str = None):
        self.mnemonic = mnemonic

        if private_key_bytes:
            self.private_key = ecdsa.SigningKey.from_string(private_key_bytes, curve=ecdsa.SECP256k1)
        else:
            self.private_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)

        self.public_key = self.private_key.get_verifying_key()
        self.address = self._make_address()

    @classmethod
    def create(cls) -> 'Wallet':
        """Create new wallet with BIP39 mnemonic."""
        mnemo = Mnemonic("english")
        words = mnemo.generate(strength=256)
        seed = mnemo.to_seed(words)
        private_key_bytes = seed[:32]
        w = cls(private_key_bytes, words)
        return w

    @classmethod
    def from_mnemonic(cls, words: str) -> 'Wallet':
        """Recover wallet from BIP39 mnemonic."""
        mnemo = Mnemonic("english")
        if not mnemo.check(words):
            raise ValueError("Invalid mnemonic words")
        seed = mnemo.to_seed(words)
        private_key_bytes = seed[:32]
        return cls(private_key_bytes, words)

    def _make_address(self) -> str:
        pub = self.public_key.to_string()
        h = hashlib.sha256(pub).digest()
        ripemd = hashlib.new('ripemd160', h).digest()
        payload = b'\x00' + ripemd
        chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        return "T" + self._b58(payload + chk)

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
        return {
            "signature_mode": "ecdsa",
            "ecdsa_signature": self.private_key.sign(data)
        }

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
        import stat
        payload = {"private_key": self.privkey_hex()}

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
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        if os.path.exists(path):
            os.replace(tmp, path)
        else:
            os.rename(tmp, path)

    @classmethod
    def load(cls, path: str, password: str = None) -> 'Wallet':
        """Load wallet, decrypting with password if needed."""
        with open(path, 'r') as f:
            wallet_data = json.load(f)

        if "private_key" in wallet_data and "encrypted" not in wallet_data:
            return cls(bytes.fromhex(wallet_data["private_key"]))

        if password is None:
            password = getpass.getpass("Password: ")

        plaintext = cls._decrypt(wallet_data["encrypted"], password)
        payload = json.loads(plaintext)

        return cls(bytes.fromhex(payload["private_key"]))

    def __repr__(self):
        return f"Wallet(TRC:{self.address})"
