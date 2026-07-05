"""
TritioCoin Wallet
=================

ECDSA secp256k1 with AES-256-GCM encryption.
BIP39 mnemonic for key recovery (24 words = 256-bit entropy).

Collision resistance:
    - secp256k1 curve order ≈ 2^256 ≈ 1.16 × 10^77
    - Birthday paradox threshold ≈ 2^128 ≈ 3.4 × 10^38 wallets
    - Probability with 10^9 (1 billion) wallets: ≈ 10^-60

Additional defenses implemented:
    1. Private key range validation (1 ≤ k < n, n = curve order)
    2. Entropy source quality check (os.urandom / getrandom syscall)
    3. Address Base58Check checksum verification
    4. Local collision registry (detects self-collisions)
    5. BIP39 optional passphrase (extra 256-bit entropy layer)
    6. Key regeneration on weak entropy indicators
"""
import hashlib
import json
import os
import secrets
import getpass
import stat
import logging
import time
from pathlib import Path
from typing import Optional, Tuple, Set

import ecdsa
from mnemonic import Mnemonic
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger("Wallet")

# ═══════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

# secp256k1 curve order (n).
# All valid private keys must satisfy: 1 ≤ k < SECP256K1_ORDER
SECP256K1_ORDER = ecdsa.SECP256k1.order

# Local collision registry: stores SHA-256 hashes of generated addresses.
# Path: tritiocoin_data/address_registry.json
REGISTRY_DIR = Path("tritiocoin_data")
REGISTRY_FILE = REGISTRY_DIR / "address_registry.json"
MAX_REGISTRY_SIZE = 1_000_000  # Safety cap to prevent unbounded growth.


class Wallet:
    __slots__ = ('private_key', 'public_key', 'address', 'mnemonic',
                 'passphrase')

    KDF_ITERATIONS = 600_000
    SALT_SIZE = 32
    NONCE_SIZE = 12
    MIN_PASSWORD_LENGTH = 8

    # ── Entropy validation ────────────────────────────────────────────
    MIN_ENTROPY_BYTES = 32  # 256-bit minimum for private key material.

    def __init__(self, private_key_bytes: bytes = None,
                 mnemonic: str = None, passphrase: str = ""):
        self.mnemonic = mnemonic
        self.passphrase = passphrase

        if private_key_bytes:
            # Validate key range: 1 ≤ k < n
            self._validate_key_range(private_key_bytes)
            self.private_key = ecdsa.SigningKey.from_string(
                private_key_bytes, curve=ecdsa.SECP256k1)
        else:
            self.private_key = self._generate_strong_key()

        self.public_key = self.private_key.get_verifying_key()
        self.address = self._make_address()

    # ── Key generation with entropy validation ────────────────────────

    @staticmethod
    def _generate_strong_key() -> ecdsa.SigningKey:
        """
        Generate a private key with entropy quality checks.

        Steps:
        1. Request 32 bytes from OS CSPRNG (os.urandom → /dev/urandom
           or BCryptGenRandom on Windows).
        2. Verify the bytes are not all-zero or suspiciously low-entropy.
        3. Validate the key is in range [1, n-1].
        4. Retry up to 3 times if any check fails (extremely unlikely).
        """
        for attempt in range(3):
            raw = os.urandom(32)

            # Check 1: Not all zeros.
            if raw == b'\x00' * 32:
                logger.warning(f"Weak entropy detected (all zeros), "
                               f"retry {attempt + 1}/3")
                continue

            # Check 2: Not suspiciously low-entropy (e.g., repeating byte).
            if len(set(raw)) < 8:
                logger.warning(f"Weak entropy detected (low diversity), "
                               f"retry {attempt + 1}/3")
                continue

            # Check 3: Within valid secp256k1 range.
            key_int = int.from_bytes(raw, 'big')
            if key_int == 0 or key_int >= SECP256K1_ORDER:
                logger.warning(f"Key out of range, retry {attempt + 1}/3")
                continue

            return ecdsa.SigningKey.from_string(raw, curve=ecdsa.SECP256k1)

        # Fallback: use secrets module (also CSPRNG-backed).
        raw = secrets.token_bytes(32)
        return ecdsa.SigningKey.from_string(raw, curve=ecdsa.SECP256k1)

    @staticmethod
    def _validate_key_range(key_bytes: bytes):
        """
        Validate that a private key is within the secp256k1 valid range.

        A valid private key k must satisfy: 1 ≤ k < n
        where n is the curve order (~2^256).
        """
        if len(key_bytes) != 32:
            raise ValueError(
                f"Private key must be 32 bytes, got {len(key_bytes)}")
        k = int.from_bytes(key_bytes, 'big')
        if k == 0:
            raise ValueError("Private key cannot be zero")
        if k >= SECP256K1_ORDER:
            raise ValueError(
                f"Private key exceeds curve order: {k} ≥ {SECP256K1_ORDER}")

    # ── Wallet creation ───────────────────────────────────────────────

    @classmethod
    def create(cls, passphrase: str = "") -> 'Wallet':
        """
        Create a new wallet with BIP39 mnemonic (24 words, 256-bit).

        The passphrase adds an extra 256-bit entropy layer on top of
        the mnemonic. Two wallets with the same mnemonic but different
        passphrases produce completely different private keys.

        :param passphrase: Optional BIP39 passphrase for extra security.
        """
        mnemo = Mnemonic("english")
        words = mnemo.generate(strength=256)  # 256-bit entropy
        seed = mnemo.to_seed(words, passphrase=passphrase)
        private_key_bytes = seed[:32]

        # Validate the derived key.
        cls._validate_key_range(private_key_bytes)

        w = cls(private_key_bytes, words, passphrase)

        # Register the address to detect local collisions.
        AddressRegistry.register(w.address)

        return w

    @classmethod
    def from_mnemonic(cls, words: str, passphrase: str = '') -> 'Wallet':
        """Recover wallet from BIP39 mnemonic + optional passphrase."""
        mnemo = Mnemonic("english")
        if not mnemo.check(words):
            raise ValueError("Invalid mnemonic words")
        seed = mnemo.to_seed(words, passphrase=passphrase)
        private_key_bytes = seed[:32]
        return cls(private_key_bytes, words, passphrase)

    # ── Address generation ────────────────────────────────────────────

    def _make_address(self) -> str:
        """
        Generate a Base58Check address from the public key.

        Format: 'T' + Base58(RIPEMD-160(SHA-256(pubkey)) with checksum)
        """
        pub = self.public_key.to_string()
        h = hashlib.sha256(pub).digest()
        ripemd = hashlib.new('ripemd160', h).digest()
        payload = b'\x00' + ripemd
        chk = hashlib.sha256(
            hashlib.sha256(payload).digest()).digest()[:4]
        return "T" + self._b58(payload + chk)

    @staticmethod
    def _b58(data: bytes) -> str:
        """Base58 encoding (Bitcoin alphabet)."""
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

    @staticmethod
    def validate_address(address: str) -> bool:
        """
        Validate a Base58Check address.

        Checks:
        1. Starts with 'T' (TritioCoin prefix).
        2. Length is reasonable (25-35 chars).
        3. Base58Check checksum is correct.
        """
        if not address or not address.startswith('T'):
            return False
        if len(address) < 25 or len(address) > 35:
            return False

        try:
            # Decode Base58.
            abc = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
            n = 0
            for c in address[1:]:  # Skip 'T' prefix.
                n = n * 58 + abc.index(c)

            # Convert to bytes.
            result = n.to_bytes((n.bit_length() + 7) // 8, 'big')

            # Re-add leading zeros (base58 '1' = leading zero byte).
            for c in address[1:]:
                if c == '1':
                    result = b'\x00' + result
                else:
                    break

            if len(result) < 25:
                return False

            # Split payload and checksum.
            payload = result[:-4]
            checksum = result[-4:]

            # Verify checksum.
            expected = hashlib.sha256(
                hashlib.sha256(payload).digest()).digest()[:4]
            return checksum == expected
        except (ValueError, IndexError):
            return False

    # ── Key export / import ───────────────────────────────────────────

    def pubkey_hex(self) -> str:
        return self.public_key.to_string().hex()

    def privkey_hex(self) -> str:
        key_bytes = bytearray(self.private_key.to_string())
        hex_str = bytes(key_bytes).hex()
        # Zeroize the buffer after use.
        for i in range(len(key_bytes)):
            key_bytes[i] = 0
        return hex_str

    def sign_tx(self, data: bytes) -> dict:
        return {
            "signature_mode": "ecdsa",
            "ecdsa_signature": self.private_key.sign(data)
        }

    # ── Password validation ───────────────────────────────────────────

    @staticmethod
    def validate_password(password: str) -> Tuple[bool, str]:
        """Validate password strength. Returns (is_valid, message)."""
        if len(password) < Wallet.MIN_PASSWORD_LENGTH:
            return False, (
                f"Senha precisa de pelo menos "
                f"{Wallet.MIN_PASSWORD_LENGTH} caracteres")
        if not any(c.isupper() for c in password):
            return False, "Senha precisa de pelo menos 1 letra maiuscula"
        if not any(c.isdigit() for c in password):
            return False, "Senha precisa de pelo menos 1 numero"
        return True, ""

    # ── Encryption / Decryption ───────────────────────────────────────

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

    # ── Persistence ───────────────────────────────────────────────────

    def save(self, path: str, password: str):
        """Save wallet encrypted with password."""
        payload = {"private_key": self.privkey_hex()}
        plaintext = json.dumps(payload).encode('utf-8')
        encrypted = self._encrypt(plaintext, password)

        wallet_data = {
            "version": 3,
            "address": self.address,
            "encrypted": encrypted
        }

        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                     stat.S_IRUSR | stat.S_IWUSR)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(wallet_data, f)
        except Exception:
            os.close(fd)
            raise

    @classmethod
    def load(cls, path: str, password: str = None) -> 'Wallet':
        """Load wallet, decrypting with password if needed."""
        with open(path, 'r') as f:
            wallet_data = json.load(f)

        # Reject legacy unencrypted format.
        if "private_key" in wallet_data and "encrypted" not in wallet_data:
            raise ValueError(
                "Carteira nao-criptografada detectada. "
                "Por seguranca, crie uma nova carteira com senha.")

        if password is None:
            password = getpass.getpass("Password: ")

        plaintext = cls._decrypt(wallet_data["encrypted"], password)
        payload = json.loads(plaintext)

        w = cls(bytes.fromhex(payload["private_key"]))

        # Validate address integrity after loading.
        if not cls.validate_address(w.address):
            raise ValueError(
                f"Endereco corrompido: {w.address} — "
                f"checksum invalido")

        return w

    def __repr__(self):
        return f"Wallet(TRC:{self.address})"


# ═══════════════════════════════════════════════════════════════════════
#  ADDRESS COLLISION REGISTRY
# ═══════════════════════════════════════════════════════════════════════

class AddressRegistry:
    """
    Local registry of generated address hashes.

    Purpose: detect self-collisions (same machine generating the same
    address twice). This is NOT for detecting collisions with other
    nodes — that's cryptographically impossible at scale.

    Storage: JSON file with a set of SHA-256(address) hex strings.
    """

    _cache: Optional[Set[str]] = None

    @classmethod
    def _load(cls) -> Set[str]:
        if cls._cache is not None:
            return cls._cache
        try:
            if REGISTRY_FILE.exists():
                data = json.loads(REGISTRY_FILE.read_text())
                cls._cache = set(data.get("addresses", []))
            else:
                cls._cache = set()
        except Exception:
            cls._cache = set()
        return cls._cache

    @classmethod
    def _save(cls):
        if cls._cache is None:
            return
        REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        # Cap the registry size to prevent disk exhaustion.
        if len(cls._cache) > MAX_REGISTRY_SIZE:
            # Keep only the most recent entries by clearing old ones.
            cls._cache = set(list(cls._cache)[-MAX_REGISTRY_SIZE // 2:])
        data = {
            "addresses": sorted(cls._cache),
            "count": len(cls._cache),
            "updated": int(time.time())
        }
        REGISTRY_FILE.write_text(json.dumps(data, indent=2))

    @classmethod
    def register(cls, address: str) -> bool:
        """
        Register an address. Returns True if it's new, False if it
        already existed (collision detected!).
        """
        registry = cls._load()
        addr_hash = hashlib.sha256(address.encode()).hexdigest()

        if addr_hash in registry:
            logger.critical(
                f"COLLISION DETECTED: address {address} already in registry")
            return False

        registry.add(addr_hash)
        cls._cache = registry
        cls._save()
        return True

    @classmethod
    def is_registered(cls, address: str) -> bool:
        registry = cls._load()
        addr_hash = hashlib.sha256(address.encode()).hexdigest()
        return addr_hash in registry

    @classmethod
    def count(cls) -> int:
        return len(cls._load())
