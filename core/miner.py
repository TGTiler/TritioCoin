"""
TritioCoin Mining System
Proof-of-Work with Argon2id (ASIC-resistant).
Multi-threaded, async, with real-time progress.
"""
import hashlib
import json
import time
import logging
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict
from core.block import Block
from core.blockchain import Blockchain
from core.mempool import Mempool
from core.transaction import Transaction, TransactionBuilder
from core.constants import SATOSHIS_PER_TRC, format_trc

logger = logging.getLogger("Miner")

try:
    from argon2.low_level import hash_secret_raw, Type
    HAS_ARGON2 = True
except ImportError:
    HAS_ARGON2 = False
    logger.warning("argon2-cffi not installed, using SHA256 fallback")


class MiningStats:
    """Tracks mining statistics."""

    def __init__(self):
        self.reset()
        self._lock = threading.Lock()

    def reset(self):
        self.mining = False
        self.nonce = 0
        self.hashes = 0
        self.start_time = 0.0
        self.blocks_found = 0
        self.total_hashes = 0
        self.best_hash_rate = 0.0
        self.found = False

    def start_mining(self):
        with self._lock:
            self.mining = True
            self.found = False
            self.nonce = 0
            self.hashes = 0
            self.start_time = time.time()

    def stop_mining(self):
        with self._lock:
            self.mining = False
            elapsed = time.time() - self.start_time
            if elapsed > 0:
                rate = self.hashes / elapsed
                self.best_hash_rate = max(self.best_hash_rate, rate)
            self.total_hashes += self.hashes

    def increment(self, count=1):
        with self._lock:
            self.nonce += count
            self.hashes += count
            self.total_hashes += count

    def get_hash_rate(self) -> float:
        elapsed = time.time() - self.start_time
        if elapsed <= 0:
            return 0.0
        return self.hashes / elapsed

    def get_elapsed(self) -> float:
        return time.time() - self.start_time

    def to_dict(self) -> dict:
        elapsed = time.time() - self.start_time if self.start_time else 0
        rate = self.hashes / elapsed if elapsed > 0 else 0
        return {
            "mining": self.mining,
            "nonce": self.nonce,
            "hashes_session": self.hashes,
            "hashes_total": self.total_hashes,
            "hash_rate": f"{rate:.0f} H/s",
            "best_hash_rate": f"{self.best_hash_rate:.0f} H/s",
            "blocks_found": self.blocks_found,
            "elapsed": f"{elapsed:.1f}s",
            "threads": self.threads if hasattr(self, 'threads') else 1
        }


class Miner:
    """
    TritioCoin Miner with Argon2id Proof-of-Work.

    Features:
    - Argon2id hashing (ASIC-resistant)
    - SHA256 fallback if argon2 not available
    - Multi-threaded mining (all CPU cores)
    - Async mining (non-blocking)
    - Auto-restart after block found
    - Real-time progress display
    - Dynamic difficulty adjustment
    """

    ARGON_TIME_COST = 1
    ARGON_MEMORY_COST = 65536  # 64 MB
    ARGON_PARALLELISM = 1
    ARGON_HASH_LEN = 32
    ARGON_SALT = b"tritiocoin_v1"

    def __init__(self, blockchain: Blockchain, mempool: Mempool, threads: int = None):
        self.blockchain = blockchain
        self.mempool = mempool
        self.stats = MiningStats()
        self.current_block: Optional[Block] = None
        self.threads = threads or self._get_cpu_count()
        self.stats.threads = self.threads
        self._stop_event = threading.Event()
        self._on_block_found = None
        self._progress_callback = None

    def _get_cpu_count(self) -> int:
        try:
            import os
            return os.cpu_count() or 4
        except:
            return 4

    def _pow_hash(self, data: bytes) -> str:
        if HAS_ARGON2:
            return hash_secret_raw(
                secret=data,
                salt=self.ARGON_SALT,
                time_cost=self.ARGON_TIME_COST,
                memory_cost=self.ARGON_MEMORY_COST,
                parallelism=self.ARGON_PARALLELISM,
                hash_len=self.ARGON_HASH_LEN,
                type=Type.ID
            ).hex()
        return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()

    def create_block_template(self, address: str) -> Block:
        prev = self.blockchain.latest()
        diff = self.blockchain.adjust_difficulty()
        pending = self.mempool.get(500)

        coinbase = TransactionBuilder.create_coinbase(
            address,
            self.blockchain.reward_at_satoshis(),
            self.blockchain.height()
        )

        txs = [coinbase.to_dict()] + [t.to_dict() for t in pending]
        block = Block(prev.header.index + 1, prev.hash, txs, diff)

        return block

    def _mine_worker(self, block: Block, target: str,
                     start_nonce: int, step: int) -> Optional[Dict]:
        """Single thread mining worker. Returns result dict if found."""
        header_bytes = block.header.to_bytes()
        nonce = start_nonce

        while not self._stop_event.is_set():
            block.header.nonce = nonce
            data = block.header.to_bytes()
            pow_hash = self._pow_hash(data)

            if pow_hash.startswith(target):
                return {"nonce": nonce, "pow_hash": pow_hash}

            nonce += step
            self.stats.increment(1)

            if nonce % 50000 == 0 and self._progress_callback:
                self._progress_callback(self.stats)

        return None

    def _print_progress(self, stats: MiningStats):
        rate = stats.get_hash_rate()
        elapsed = stats.get_elapsed()
        nonce = stats.nonce
        difficulty = self.current_block.header.difficulty if self.current_block else 0

        target_zeros = "0" * difficulty
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        print(f"\r  Nonce: {nonce:>12,} | "
              f"Hashrate: {rate:>8,.0f} H/s | "
              f"Dificuldade: {difficulty} | "
              f"Tempo: {minutes}m{seconds:02d}s | "
              f"Threads: {self.threads}   ",
              end="", flush=True)

    def mine(self, address: str) -> Optional[Block]:
        self.stats.start_mining()
        self._stop_event.clear()
        self.current_block = self.create_block_template(address)
        self._progress_callback = self._print_progress

        target = "0" * self.current_block.header.difficulty
        logger.info(f"Mining block #{self.current_block.header.index} "
                    f"(difficulty={self.current_block.header.difficulty}, "
                    f"threads={self.threads})")

        print(f"\n  Minerando bloco #{self.current_block.header.index}...")
        print(f"  Dificuldade: {target} ({self.current_block.header.difficulty} zeros)")
        print(f"  Recompensa: {self.blockchain.reward_at():.8f} TRC")
        print(f"  Threads: {self.threads}")
        print()

        from concurrent.futures import as_completed

        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = []
            for i in range(self.threads):
                future = executor.submit(
                    self._mine_worker,
                    self.current_block,
                    target,
                    i,
                    self.threads
                )
                futures.append(future)

            result = None
            try:
                for future in as_completed(futures, timeout=None):
                    try:
                        res = future.result(timeout=1)
                        if res:
                            result = res
                            self._stop_event.set()
                            break
                    except Exception as e:
                        logger.debug(f"Thread finished: {type(e).__name__}")
            except Exception as e:
                logger.error(f"Mining error: {type(e).__name__}: {e}")

        if result:
            self.current_block.header.nonce = result["nonce"]
            self.current_block.hash = self.current_block.content_hash()
            self.current_block.pow_hash = result["pow_hash"]

            pending = self.mempool.get(500)
            self.mempool.remove_many([t.tx_hash for t in pending])

            self.stats.stop_mining()
            self.stats.blocks_found += 1

            print(f"\n  Bloco #{self.current_block.header.index} minerado!")
            print(f"  Nonce: {result['nonce']:,}")
            print(f"  Hash: {self.current_block.hash[:32]}...")
            print(f"  Hashtotal: {self.stats.get_hash_rate():,.0f} H/s")

            logger.info(f"Block #{self.current_block.header.index} mined! "
                        f"Nonce={result['nonce']} "
                        f"Hash={self.current_block.hash[:16]}... "
                        f"Rate={self.stats.get_hash_rate():.0f} H/s")

            return self.current_block

        self.stats.stop_mining()
        print()
        return None

    def stop(self):
        self._stop_event.set()
        self.stats.stop_mining()
        print("\n  Mineracao interrompida.")
        logger.info("Mining stopped")

    async def mine_async(self, address: str) -> Optional[Block]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.mine, address)

    async def mine_continuous(self, address: str, callback=None):
        """Mine continuously. Auto-restart after each block found."""
        print("\n  Mineracao continua iniciada (Ctrl+C para parar)")
        print(f"  Endereco: {address[:32]}...")
        print()

        blocks_total = 0

        while not self._stop_event.is_set():
            block = await self.mine_async(address)

            if block:
                blocks_total += 1
                print(f"\n  Total de blocos minerados: {blocks_total}")
                print(f"  Reiniciando mineracao...")

                if callback:
                    await callback(block)

                await asyncio.sleep(0.5)
            else:
                if self._stop_event.is_set():
                    break
                await asyncio.sleep(1)

        print(f"\n  Mineracao finalizada. {blocks_total} blocos minerados.")

    def get_stats(self) -> dict:
        stats = self.stats.to_dict()
        stats["difficulty"] = self.blockchain.difficulty
        stats["reward"] = self.blockchain.reward_at()
        stats["reward_satoshis"] = self.blockchain.reward_at_satoshis()
        stats["threads"] = self.threads
        stats["argon2"] = HAS_ARGON2
        return stats

    def get_block_template_info(self) -> dict:
        pending = self.mempool.get(10)
        return {
            "height": self.blockchain.height() + 1,
            "difficulty": self.blockchain.difficulty,
            "reward": self.blockchain.reward_at(),
            "pending_txs": len(pending),
            "estimated_fee": sum(t.get("fee", 0) for t in pending)
        }
