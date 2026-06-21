"""
TritioCoin HD Wallet (BIP32/BIP44)
Hierarchical Deterministic wallet for deriving multiple addresses from one seed.
"""
import hashlib
import hmac
import struct
import os
from typing import Tuple, List, Optional
from mnemonic import Mnemonic
import ecdsa


class HDKey:
    """BIP32 HD Key."""

    def __init__(self, private_key: bytes, chain_code: bytes, depth: int = 0,
                 parent_fingerprint: bytes = b'\x00' * 4, child_number: int = 0):
        self.private_key = private_key
        self.chain_code = chain_code
        self.depth = depth
        self.parent_fingerprint = parent_fingerprint
        self.child_number = child_number

        # Derive public key
        sk = ecdsa.SigningKey.from_string(private_key, curve=ecdsa.SECP256k1)
        self.public_key = sk.get_verifying_key().to_string()

    @classmethod
    def from_seed(cls, seed: bytes) -> 'HDKey':
        """Create master key from seed."""
        # BIP32 master key derivation
        I = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
        master_key = I[:32]
        master_chain = I[32:]
        return cls(master_key, master_chain)

    def derive_child(self, index: int, hardened: bool = False) -> 'HDKey':
        """Derive child key at index."""
        if hardened:
            index += 0x80000000
            data = b'\x00' + self.private_key + struct.pack('>I', index)
        else:
            data = self.public_key + struct.pack('>I', index)

        I = hmac.new(self.chain_code, data, hashlib.sha512).digest()
        child_key = (int.from_bytes(I[:32], 'big') +
                     int.from_bytes(self.private_key, 'big')) % ecdsa.SECP256k1.order
        child_key = child_key.to_bytes(32, 'big')

        child_chain = I[32:]

        fingerprint = hashlib.sha1(self.public_key).digest()[:4]

        return HDKey(child_key, child_chain, self.depth + 1, fingerprint, index)

    def derive_path(self, path: str) -> 'HDKey':
        """
        Derive key from path like "m/44'/0'/0'/0/0"
        """
        parts = path.split('/')
        if parts[0] != 'm':
            raise ValueError("Path must start with 'm'")

        current = self
        for part in parts[1:]:
            if part.endswith("'"):
                hardened = True
                index = int(part[:-1])
            else:
                hardened = False
                index = int(part)
            current = current.derive_child(index, hardened)

        return current

    def get_address(self) -> str:
        """Get TritioCoin address from this key."""
        h = hashlib.sha256(self.public_key).digest()
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

    def sign(self, message: bytes) -> bytes:
        """Sign a message with this key."""
        sk = ecdsa.SigningKey.from_string(self.private_key, curve=ecdsa.SECP256k1)
        return sk.sign(message)

    def verify(self, message: bytes, signature: bytes) -> bool:
        """Verify a signature."""
        try:
            vk = ecdsa.VerifyingKey.from_string(self.public_key, curve=ecdsa.SECP256k1)
            return vk.verify(signature, message)
        except Exception:
            return False

    def serialize_private(self) -> str:
        """Serialize private key as hex."""
        return self.private_key.hex()

    def serialize_public(self) -> str:
        """Serialize public key as hex."""
        return self.public_key.hex()

    def __repr__(self):
        return f"HDKey(depth={self.depth}, addr={self.get_address()[:16]}...)"


class HDWallet:
    """
    BIP44 HD Wallet for TritioCoin.
    
    Path: m / 44' / coin_type' / account' / change / address_index
    
    Coin type for TritioCoin: 9999 (registered)
    """

    COIN_TYPE = 9999  # TritioCoin coin type

    def __init__(self, mnemonic: str = None):
        self.mnemonic = mnemonic or self._generate_mnemonic()
        self.seed = Mnemonic("english").to_seed(self.mnemonic)
        self.master_key = HDKey.from_seed(self.seed)
        self.accounts: Dict[int, HDKey] = {}

    @staticmethod
    def _generate_mnemonic() -> str:
        """Generate a new 24-word mnemonic."""
        return Mnemonic("english").generate(strength=256)

    def get_account(self, account_index: int = 0) -> HDKey:
        """Get or create an account key."""
        if account_index not in self.accounts:
            path = f"m/44'/{self.COIN_TYPE}'/{account_index}'"
            self.accounts[account_index] = self.master_key.derive_path(path)
        return self.accounts[account_index]

    def get_address(self, account_index: int = 0, change: int = 0,
                    address_index: int = 0) -> str:
        """
        Get a specific address.
        
        Args:
            account_index: Account number (0, 1, 2, ...)
            change: 0 = external (receiving), 1 = internal (change)
            address_index: Address index within the account
        """
        path = f"m/44'/{self.COIN_TYPE}'/{account_index}'/{change}/{address_index}"
        key = self.master_key.derive_path(path)
        return key.get_address()

    def get_private_key(self, account_index: int = 0, change: int = 0,
                        address_index: int = 0) -> HDKey:
        """Get the HDKey object for a specific address."""
        path = f"m/44'/{self.COIN_TYPE}'/{account_index}'/{change}/{address_index}"
        return self.master_key.derive_path(path)

    def generate_addresses(self, count: int = 10, account_index: int = 0,
                           change: int = 0) -> List[Tuple[str, str]]:
        """
        Generate multiple addresses.
        Returns list of (address, path) tuples.
        """
        addresses = []
        for i in range(count):
            path = f"m/44'/{self.COIN_TYPE}'/{account_index}'/{change}/{i}"
            key = self.master_key.derive_path(path)
            addresses.append((key.get_address(), path))
        return addresses

    def sign_transaction(self, tx_data: bytes, account_index: int = 0,
                         change: int = 0, address_index: int = 0) -> bytes:
        """Sign transaction data with derived key."""
        key = self.get_private_key(account_index, change, address_index)
        return key.sign(tx_data)

    def export_xpub(self, account_index: int = 0) -> str:
        """Export extended public key for watch-only wallets."""
        account = self.get_account(account_index)
        return account.serialize_public()

    def export_xprv(self, account_index: int = 0) -> str:
        """Export extended private key (KEEP SECRET)."""
        account = self.get_account(account_index)
        return account.serialize_private()

    def save(self, filepath: str, password: str = None):
        """Save HD wallet to file."""
        import json
        data = {
            "version": 1,
            "mnemonic": self.mnemonic,
            "coin_type": self.COIN_TYPE
        }
        if password:
            from core.wallet import Wallet
            plaintext = json.dumps(data).encode()
            encrypted = Wallet._encrypt(plaintext, password)
            data = {"version": 1, "encrypted": encrypted}

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, filepath: str, password: str = None) -> 'HDWallet':
        """Load HD wallet from file."""
        import json
        with open(filepath) as f:
            data = json.load(f)

        if "encrypted" in data and password:
            from core.wallet import Wallet
            plaintext = Wallet._decrypt(data["encrypted"], password)
            data = json.loads(plaintext)

        return cls(mnemonic=data["mnemonic"])

    def __repr__(self):
        return f"HDWallet({self.mnemonic[:20]}...)"


def create_hd_wallet(password: str = None) -> HDWallet:
    """Create a new HD wallet."""
    hd = HDWallet()
    return hd
