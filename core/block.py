import struct
import hashlib
import time
import json
from typing import List, Dict


class BlockHeader:
    """Fixed-size 86-byte binary header. Network byte order (Big-Endian)."""

    __slots__ = ('version', 'index', 'timestamp', 'previous_hash',
                 'merkle_root', 'difficulty', 'nonce')

    def __init__(self, index: int, previous_hash: bytes, merkle_root: bytes,
                 difficulty: int, nonce: int = 0, timestamp: int = None):
        self.version = 1
        self.index = index
        self.timestamp = int(timestamp or time.time())
        self.previous_hash = previous_hash
        self.merkle_root = merkle_root
        self.difficulty = difficulty
        self.nonce = nonce

    def to_bytes(self) -> bytes:
        return struct.pack(
            '>H I Q 32s 32s I I',
            self.version, self.index, self.timestamp,
            self.previous_hash, self.merkle_root,
            self.difficulty, self.nonce
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> 'BlockHeader':
        if len(data) != 86:
            raise ValueError(f"Invalid header size: expected 86, got {len(data)}")
        v, idx, ts, prev, merk, diff, nonc = struct.unpack('>H I Q 32s 32s I I', data)
        h = cls(idx, prev, merk, diff, nonc, ts)
        h.version = v
        return h


class Block:
    __slots__ = ('header', 'transactions', 'validator_signatures', 'hash', 'pow_hash')

    def __init__(self, index: int, previous_hash_hex: str,
                 transactions: List[Dict], difficulty: int):
        prev_bytes = bytes.fromhex(previous_hash_hex.zfill(64))
        merkle_bytes = self._merkle_root(transactions)
        self.header = BlockHeader(index, prev_bytes, merkle_bytes, difficulty)
        self.transactions = transactions
        self.validator_signatures: List[Dict] = []
        self.hash: str = None
        self.pow_hash: str = None

    @staticmethod
    def _merkle_root(transactions: List[Dict]) -> bytes:
        if not transactions:
            return hashlib.sha256(b"GENESIS").digest()
        data = b"".join(
            json.dumps(tx, sort_keys=True).encode() for tx in transactions
        )
        return hashlib.sha256(hashlib.sha256(data).digest()).digest()

    def pow_data(self) -> bytes:
        return self.header.to_bytes()

    def content_hash(self) -> str:
        payload = {
            "header": {
                "version": self.header.version,
                "index": self.header.index,
                "timestamp": self.header.timestamp,
                "previous_hash": self.header.previous_hash.hex(),
                "merkle_root": self.header.merkle_root.hex(),
                "difficulty": self.header.difficulty,
                "nonce": self.header.nonce
            },
            "transactions": self.transactions
        }
        raw = json.dumps(payload, sort_keys=True).encode()
        return hashlib.sha256(hashlib.sha256(raw).digest()).hexdigest()

    def serialize(self) -> dict:
        return {
            "header": {
                "version": self.header.version,
                "index": self.header.index,
                "timestamp": self.header.timestamp,
                "previous_hash": self.header.previous_hash.hex(),
                "merkle_root": self.header.merkle_root.hex(),
                "difficulty": self.header.difficulty,
                "nonce": self.header.nonce
            },
            "transactions": self.transactions,
            "validator_signatures": self.validator_signatures,
            "hash": self.hash,
            "pow_hash": self.pow_hash
        }

    @classmethod
    def deserialize(cls, data: dict) -> 'Block':
        h = data["header"]
        b = cls(h["index"], h["previous_hash"], data["transactions"], h["difficulty"])
        b.header.timestamp = h["timestamp"]
        b.header.nonce = h["nonce"]
        b.hash = data["hash"]
        b.pow_hash = data.get("pow_hash")
        b.validator_signatures = data.get("validator_signatures", [])
        return b
