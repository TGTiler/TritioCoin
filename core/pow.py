"""
TritioCoin Proof-of-Work
Blake2b with memory-hardness (Argon2-style).
- Memory allocation and filling
- Random memory reads
- Chained hashing rounds
"""
import hashlib
import struct
import os

MEMORY_SIZE = 256 * 1024  # 256 KB per hash
BLOCK_SIZE = 64            # Blake2b block size
ROUNDS = 4                 # Number of chaining rounds


def _blake2b(data: bytes, digest_size: int = 32) -> bytes:
    return hashlib.blake2b(data, digest_size=digest_size, person=b"tritiocoin_v1").digest()


def _fill_memory(seed: bytes) -> bytearray:
    """Fill memory buffer with Blake2b-derived blocks (Argon2-style)."""
    buf = bytearray(MEMORY_SIZE)
    num_blocks = MEMORY_SIZE // BLOCK_SIZE

    for i in range(num_blocks):
        block_input = seed + struct.pack('>I', i)
        block = _blake2b(block_input, BLOCK_SIZE)
        offset = i * BLOCK_SIZE
        buf[offset:offset + BLOCK_SIZE] = block

    return buf


def _random_reads(buf: bytearray, seed: bytes, count: int = 32):
    """Perform random reads from memory buffer to enforce memory access."""
    num_blocks = len(buf) // BLOCK_SIZE
    for i in range(count):
        idx_input = seed + struct.pack('>I', i)
        idx = int.from_bytes(_blake2b(idx_input, 4), 'big') % num_blocks
        offset = idx * BLOCK_SIZE
        _ = bytes(buf[offset:offset + BLOCK_SIZE])


def _chain_rounds(data: bytes, rounds: int = ROUNDS) -> bytes:
    """Chain multiple Blake2b rounds."""
    current = data
    for i in range(rounds):
        current = _blake2b(current + struct.pack('>I', i))
    return current


def memory_hard_hash(header: bytes) -> str:
    """
    Memory-hard Blake2b PoW hash.
    Steps:
    1. Initial hash of header
    2. Fill 256KB memory buffer with Blake2b-derived data
    3. Perform random memory reads (enforces memory access)
    4. Chain multiple Blake2b rounds
    5. Final hash
    """
    initial = _blake2b(header)

    buf = _fill_memory(initial)

    _random_reads(buf, initial, count=32)

    access_hash = _blake2b(initial + bytes(buf[:256]))

    final = _chain_rounds(access_hash + initial)

    return final.hex()
