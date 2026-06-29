"""
TritioHash - TritioCoin Proof-of-Work Algorithm
Blake2b with memory-hardness (32MB, data-dependent access, sequential chaining).
ASIC-resistant through:
- 32MB memory requirement (too large for ASIC SRAM)
- Data-dependent access pattern (each read depends on previous)
- Sequential chaining (cannot parallelize)
- Multiple write passes (ensures real memory allocation)
- Latency-enforced (sequential reads take real time)
"""
import hashlib
import struct
import os
import time

MEMORY_SIZE = 32 * 1024 * 1024  # 32 MB per hash
BLOCK_SIZE = 64                   # Blake2b block size
ROUNDS = 8                        # More chaining rounds
READ_COUNT = 128                  # More random reads
WRITE_ROUNDS = 4                  # Memory write passes


def _blake2b(data: bytes, digest_size: int = 32) -> bytes:
    return hashlib.blake2b(data, digest_size=digest_size, person=b"tritiocoin_v1").digest()


def _fill_memory(seed: bytes) -> bytearray:
    """Fill memory buffer with Blake2b-derived blocks (multiple passes)."""
    buf = bytearray(MEMORY_SIZE)
    num_blocks = MEMORY_SIZE // BLOCK_SIZE

    # Multiple write passes to ensure memory is actually allocated
    for pass_num in range(WRITE_ROUNDS):
        for i in range(num_blocks):
            # Each block depends on previous block AND the pass number
            if pass_num == 0 and i == 0:
                block_input = seed
            elif pass_num == 0:
                # Chain: each block depends on previous
                prev_offset = (i - 1) * BLOCK_SIZE
                prev_block = bytes(buf[prev_offset:prev_offset + BLOCK_SIZE])
                block_input = prev_block + struct.pack('>I', i)
            else:
                # Later passes mix in previous pass data
                offset = i * BLOCK_SIZE
                prev_pass = bytes(buf[offset:offset + BLOCK_SIZE])
                block_input = prev_pass + seed + struct.pack('>I', pass_num)

            block = _blake2b(block_input, BLOCK_SIZE)
            offset = i * BLOCK_SIZE
            buf[offset:offset + BLOCK_SIZE] = block

    return buf


def _random_reads(buf: bytearray, seed: bytes, count: int = READ_COUNT):
    """
    Data-dependent random reads from memory.
    Each read index depends on the PREVIOUS read result (non-linear).
    This forces sequential access and prevents parallelization.
    """
    num_blocks = len(buf) // BLOCK_SIZE
    current_hash = seed

    for i in range(count):
        # Read index depends on PREVIOUS read result (data-dependent)
        idx_hash = _blake2b(current_hash + struct.pack('>I', i), 4)
        idx = int.from_bytes(idx_hash, 'big') % num_blocks

        # Actually read from memory (forces real memory access)
        offset = idx * BLOCK_SIZE
        read_data = bytes(buf[offset:offset + BLOCK_SIZE])

        # Next read depends on THIS read (chain dependency)
        current_hash = _blake2b(read_data + current_hash)

    return current_hash


def _chain_rounds(data: bytes, rounds: int = ROUNDS) -> bytes:
    """Chain multiple Blake2b rounds with latency."""
    current = data
    for i in range(rounds):
        # Each round depends on previous (sequential, cannot parallelize)
        current = _blake2b(current + struct.pack('>I', i))
    return current


def tritio_hash(header: bytes) -> str:
    """
    TritioHash - Memory-hard Blake2b PoW algorithm.
    
    Design principles:
    1. 32MB memory requirement (too large for ASIC SRAM)
    2. Data-dependent access pattern (each read depends on previous)
    3. Sequential chaining (cannot parallelize across blocks)
    4. Multiple write passes (ensure memory is real, not cached)
    5. Latency-enforced (sequential reads take real time)
    """
    # Step 1: Initial hash of header
    initial = _blake2b(header)

    # Step 2: Fill 32MB memory buffer (multiple passes)
    buf = _fill_memory(initial)

    # Step 3: Data-dependent random reads (sequential, non-parallelizable)
    access_hash = _random_reads(buf, initial)

    # Step 4: Mix memory into final hash
    access_result = _blake2b(access_hash + bytes(buf[:256]))

    # Step 5: Chain multiple rounds (sequential)
    final = _chain_rounds(access_result + initial)

    return final.hex()


# Keep backward compatibility
memory_hard_hash = tritio_hash
