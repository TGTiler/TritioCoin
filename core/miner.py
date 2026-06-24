"""
TritioCoin Mining System
Proof-of-Work with blake2b (fast, ASIC-resistant).
Multi-process, async, with real-time progress.
"""
import hashlib
import json
import time
import logging
import struct
import multiprocessing
from typing import Optional, List, Dict
from core.block import Block
from core.blockchain import Blockchain
from core.mempool import Mempool
from core.transaction import Transaction, TransactionBuilder
from core.constants import SATOSHIS_PER_TRC, format_trc

logger = logging.getLogger("Miner")


class MiningStats:
    """Tracks mining statistics."""

    def __init__(self):
        self.reset()
        self._lock = multiprocessing.Lock() if hasattr(multiprocessing, 'Lock') else None

    def reset(self):
        self.mining = False
        self.nonce = 0
        self.hashes = 0
        self.start_time = 0.0
        self.blocks_found = 0
        self.total_hashes = 0
        self.best_hash_rate = 0.0
        self.found = False
        self.threads = 1

    def start_mining(self):
        self.mining = True
        self.found = False
        self.nonce = 0
        self.hashes = 0
        self.start_time = time.time()

    def stop_mining(self):
        self.mining = False
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            rate = self.hashes / elapsed
            self.best_hash_rate = max(self.best_hash_rate, rate)
        self.total_hashes += self.hashes

    def increment(self, count=1):
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
            "threads": self.threads
        }


def _mine_worker(header_base: bytes, target: str, start_nonce: int, step: int,
                 result_queue: multiprocessing.Queue, stop_event: multiprocessing.Event,
                 hashes_counter: multiprocessing.Value):
    """Process-based mining worker. Runs in a separate OS process."""
    nonce = start_nonce
    local_hashes = 0

    while not stop_event.is_set():
        data = header_base + struct.pack('>I', nonce)
        pow_hash = hashlib.blake2b(data, digest_size=32, person=b"tritiocoin_v1").hexdigest()

        if pow_hash.startswith(target):
            with hashes_counter.get_lock():
                hashes_counter.value += local_hashes
            result_queue.put({"nonce": nonce, "pow_hash": pow_hash})
            return

        nonce += step
        local_hashes += 1

        if local_hashes % 50000 == 0:
            with hashes_counter.get_lock():
                hashes_counter.value += 50000
            local_hashes = 0

    with hashes_counter.get_lock():
        hashes_counter.value += local_hashes


class Miner:
    """
    TritioCoin Miner with blake2b Proof-of-Work.

    Features:
    - blake2b hashing (ASIC-resistant, fast)
    - Multi-process mining (real parallelism across CPU cores)
    - Async mining (non-blocking)
    - Auto-restart after block found
    - Real-time progress display
    - Dynamic difficulty adjustment
    """

    def __init__(self, blockchain: Blockchain, mempool: Mempool, threads: int = None):
        self.blockchain = blockchain
        self.mempool = mempool
        self.stats = MiningStats()
        self.current_block: Optional[Block] = None
        self.threads = threads or self._get_cpu_count()
        self.stats.threads = self.threads
        self._stop_event = None
        self._on_block_found = None
        self._progress_callback = None

    def _get_cpu_count(self) -> int:
        try:
            import os
            return os.cpu_count() or 4
        except:
            return 4

    @staticmethod
    def _pow_hash(data: bytes) -> str:
        return hashlib.blake2b(data, digest_size=32, person=b"tritiocoin_v1").hexdigest()

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

    def _print_progress(self, hashes_counter, start_time, difficulty):
        elapsed = time.time() - start_time
        if elapsed <= 0:
            return
        with hashes_counter.get_lock():
            total = hashes_counter.value
        rate = total / elapsed
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        print(f"\r  Nonce: {total:>12,} | "
              f"Hashrate: {rate:>8,.0f} H/s | "
              f"Dificuldade: {difficulty} | "
              f"Tempo: {minutes}m{seconds:02d}s | "
              f"Threads: {self.threads}   ",
              end="", flush=True)

    def mine(self, address: str) -> Optional[Block]:
        self.stats.start_mining()
        self.current_block = self.create_block_template(address)

        target = "0" * self.current_block.header.difficulty
        header_base = self.current_block.header.to_bytes_base()

        logger.info(f"Mining block #{self.current_block.header.index} "
                    f"(difficulty={self.current_block.header.difficulty}, "
                    f"processes={self.threads})")

        print(f"\n  Minerando bloco #{self.current_block.header.index}...")
        print(f"  Dificuldade: {target} ({self.current_block.header.difficulty} zeros)")
        print(f"  Recompensa: {self.blockchain.reward_at():.8f} TRC")
        print(f"  Processos: {self.threads}")
        print()

        self._stop_event = multiprocessing.Event()
        result_queue = multiprocessing.Queue()
        hashes_counter = multiprocessing.Value('i', 0)

        processes = []
        for i in range(self.threads):
            p = multiprocessing.Process(
                target=_mine_worker,
                args=(header_base, target, i, self.threads,
                      result_queue, self._stop_event, hashes_counter)
            )
            processes.append(p)
            p.start()

        result = None
        start_time = time.time()

        try:
            while True:
                if not result_queue.empty():
                    result = result_queue.get_nowait()
                    self._stop_event.set()
                    break
                if all(not p.is_alive() for p in processes):
                    break
                time.sleep(0.01)

                elapsed = time.time() - start_time
                if elapsed > 0 and int(elapsed * 2) % 2 == 0:
                    self._print_progress(hashes_counter, start_time,
                                         self.current_block.header.difficulty)
        except KeyboardInterrupt:
            self._stop_event.set()

        for p in processes:
            p.join(timeout=2)
            if p.is_alive():
                p.terminate()

        with hashes_counter.get_lock():
            self.stats.hashes = hashes_counter.value
            self.stats.total_hashes += hashes_counter.value

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
            print(f"  Hashrate: {self.stats.get_hash_rate():,.0f} H/s")

            logger.info(f"Block #{self.current_block.header.index} mined! "
                        f"Nonce={result['nonce']} "
                        f"Hash={self.current_block.hash[:16]}... "
                        f"Rate={self.stats.get_hash_rate():.0f} H/s")

            return self.current_block

        self.stats.stop_mining()
        print()
        return None

    def stop(self):
        if self._stop_event:
            self._stop_event.set()
        self.stats.stop_mining()
        print("\n  Mineracao interrompida.")
        logger.info("Mining stopped")

    async def mine_async(self, address: str) -> Optional[Block]:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.mine, address)

    async def mine_continuous(self, address: str, callback=None):
        """Mine continuously. Auto-restart after each block found."""
        print("\n  Mineracao continua iniciada (Ctrl+C para parar)")
        print(f"  Endereco: {address[:32]}...")
        print()

        blocks_total = 0

        while True:
            block = await self.mine_async(address)

            if block:
                blocks_total += 1
                print(f"\n  Total de blocos minerados: {blocks_total}")
                print(f"  Reiniciando mineracao...")

                if callback:
                    await callback(block)

                import asyncio
                await asyncio.sleep(0.5)
            else:
                break

        print(f"\n  Mineracao finalizada. {blocks_total} blocos minerados.")

    def get_stats(self) -> dict:
        stats = self.stats.to_dict()
        stats["difficulty"] = self.blockchain.difficulty
        stats["reward"] = self.blockchain.reward_at()
        stats["reward_satoshis"] = self.blockchain.reward_at_satoshis()
        stats["threads"] = self.threads
        stats["algorithm"] = "blake2b"
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
