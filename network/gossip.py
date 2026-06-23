"""
TritioCoin Gossip Protocol
Efficient propagation of blocks and transactions across the network.

Features:
- Block announcement with inventory (avoid sending full blocks)
- Transaction relay with deduplication
- Compact block relay
- Block header sync (fast initial sync)
- Batch block download with adaptive batch sizing
- Transaction cache for deduplication
"""
import hashlib
import time
import logging
import asyncio
from typing import Dict, Set, List, Optional, Tuple
from collections import OrderedDict

logger = logging.getLogger("Gossip")


class InventoryItem:
    """Represents an item in the inventory (block or tx)."""

    def __init__(self, inv_type: str, inv_hash: str, height: int = 0):
        self.type = inv_type
        self.hash = inv_hash
        self.height = height
        self.time_seen = time.time()

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "hash": self.hash,
            "height": self.height
        }


class GossipProtocol:
    """
    Efficient gossip protocol for block and transaction propagation.

    Flow for new block:
    1. Miner finds block
    2. Sends BLOCK_ANNOUNCE to peers (just hash + height)
    3. Peers check if they need it
    4. If yes, request full block via GET_BLOCK
    5. Miner sends full block

    Flow for new transaction:
    1. User creates transaction
    2. Sends TX_ANNOUNCE to peers (just hash)
    3. Peers check mempool
    4. If missing, request via GET_TX
    5. User sends full tx
    """

    MAX_INVENTORY_SIZE = 5000
    INV_EXPIRY_TIME = 3600
    MIN_BATCH_SIZE = 10
    MAX_BATCH_SIZE = 100
    DEFAULT_BATCH_SIZE = 50
    SYNC_TIMEOUT = 10

    def __init__(self):
        self.inventory: OrderedDict[str, InventoryItem] = OrderedDict()
        self.known_txs: Set[str] = set()
        self.known_blocks: Set[str] = set()
        self.sent_announcements: Set[str] = set()
        self._last_cleanup = time.time()
        self.peer_latencies: Dict[str, float] = {}

    def _cleanup_inventory(self):
        now = time.time()
        if now - self._last_cleanup < 60:
            return
        expired = [
            h for h, item in self.inventory.items()
            if now - item.time_seen > self.INV_EXPIRY_TIME
        ]
        for h in expired:
            del self.inventory[h]
            self.known_blocks.discard(h)
            self.known_txs.discard(h)
        self._last_cleanup = now

    def _track_item(self, item: InventoryItem):
        self.inventory[item.hash] = item
        if item.type == "block":
            self.known_blocks.add(item.hash)
        elif item.type == "tx":
            self.known_txs.add(item.hash)
        while len(self.inventory) > self.MAX_INVENTORY_SIZE:
            oldest_hash, _ = self.inventory.popitem(last=False)
            self.known_blocks.discard(oldest_hash)
            self.known_txs.discard(oldest_hash)

    def has_block(self, block_hash: str) -> bool:
        return block_hash in self.known_blocks

    def has_tx(self, tx_hash: str) -> bool:
        return tx_hash in self.known_txs

    def announce_block(self, block_hash: str, height: int) -> dict:
        self._track_item(InventoryItem("block", block_hash, height))
        self._cleanup_inventory()
        return {
            "type": "BLOCK_ANNOUNCE",
            "hash": block_hash,
            "height": height
        }

    def announce_tx(self, tx_hash: str) -> dict:
        self._track_item(InventoryItem("tx", tx_hash))
        self._cleanup_inventory()
        return {
            "type": "TX_ANNOUNCE",
            "hash": tx_hash
        }

    def should_request_block(self, block_hash: str, my_height: int, announced_height: int) -> bool:
        if block_hash in self.known_blocks:
            return False
        if announced_height <= my_height:
            return False
        return True

    def should_request_tx(self, tx_hash: str) -> bool:
        return tx_hash not in self.known_txs

    def update_peer_latency(self, peer: str, latency_ms: float):
        """Update measured latency for a peer."""
        self.peer_latencies[peer] = latency_ms

    def get_adaptive_batch_size(self, peer: str) -> int:
        """Calculate adaptive batch size based on peer latency."""
        latency = self.peer_latencies.get(peer, 500)
        if latency < 50:
            return self.MAX_BATCH_SIZE
        elif latency < 100:
            return 80
        elif latency < 200:
            return self.DEFAULT_BATCH_SIZE
        elif latency < 500:
            return 30
        elif latency < 1000:
            return 20
        else:
            return self.MIN_BATCH_SIZE

    def get_sync_ranges(self, my_height: int, peer_height: int, peer: str = None) -> List[Tuple[int, int]]:
        if peer_height <= my_height:
            return []
        batch_size = self.get_adaptive_batch_size(peer) if peer else self.DEFAULT_BATCH_SIZE
        ranges = []
        start = my_height + 1
        while start <= peer_height:
            end = min(start + batch_size - 1, peer_height)
            ranges.append((start, end))
            start = end + 1
        return ranges

    def create_sync_request(self, my_height: int, peer_height: int, peer: str = None) -> dict:
        ranges = self.get_sync_ranges(my_height, peer_height, peer)
        if not ranges:
            return None
        first_range = ranges[0]
        return {
            "type": "SYNC_REQUEST",
            "start_height": first_range[0],
            "end_height": first_range[1],
            "my_height": my_height,
            "batch_size": self.get_adaptive_batch_size(peer) if peer else self.DEFAULT_BATCH_SIZE
        }

    def create_block_batch(self, start_height: int, end_height: int, blocks_data: List[dict]) -> dict:
        return {
            "type": "SYNC_BLOCK_BATCH",
            "start_height": start_height,
            "end_height": end_height,
            "blocks": blocks_data,
            "count": len(blocks_data)
        }

    def create_get_blocks(self, heights: List[int], peer: str = None) -> dict:
        batch = self.get_adaptive_batch_size(peer) if peer else self.DEFAULT_BATCH_SIZE
        return {
            "type": "GET_BLOCKS",
            "heights": heights[:batch]
        }

    def get_stats(self) -> dict:
        return {
            "inventory_size": len(self.inventory),
            "known_blocks": len(self.known_blocks),
            "known_txs": len(self.known_txs),
            "announcements_sent": len(self.sent_announcements),
            "avg_latency_ms": round(
                sum(self.peer_latencies.values()) / max(len(self.peer_latencies), 1), 1
            )
        }


class GossipNode:
    """Node mixin that adds gossip protocol to P2PNode."""

    def __init__(self):
        self.gossip = GossipProtocol()
        self._sync_in_progress = False
        self._sync_peer = None
        self._pending_blocks: Dict[int, dict] = {}
        self._tx_cache = None

    def _get_tx_cache(self):
        if self._tx_cache is None:
            from network.p2p_node import TransactionCache
            self._tx_cache = TransactionCache()
        return self._tx_cache

    async def gossip_handle_message(self, msg: dict, peer: str, writer):
        msg_type = msg.get("type")
        if msg_type == "BLOCK_ANNOUNCE":
            await self._gossip_handle_block_announce(msg, peer)
            return True
        elif msg_type == "TX_ANNOUNCE":
            await self._gossip_handle_tx_announce(msg, peer)
            return True
        elif msg_type == "SYNC_REQUEST":
            await self._gossip_handle_sync_request(msg, peer)
            return True
        elif msg_type == "SYNC_BLOCK_BATCH":
            await self._gossip_handle_sync_batch(msg)
            return True
        elif msg_type == "GET_BLOCKS":
            await self._gossip_handle_get_blocks(msg, peer)
            return True
        return False

    async def gossip_announce_block(self, block_hash: str, height: int):
        msg = self.gossip.announce_block(block_hash, height)
        await self.p2p.broadcast(msg)
        logger.debug(f"Announced block #{height}: {block_hash[:16]}...")

    async def gossip_announce_tx(self, tx_hash: str):
        tx_cache = self._get_tx_cache()
        if tx_cache.has(tx_hash):
            return
        tx_cache.add(tx_hash)
        msg = self.gossip.announce_tx(tx_hash)
        await self.p2p.broadcast(msg)
        logger.debug(f"Announced tx: {tx_hash[:16]}...")

    async def gossip_request_block(self, peer: str, height: int):
        await self.p2p.send(peer, {"type": "GET_BLOCK", "height": height})

    async def gossip_request_blocks(self, peer: str, heights: List[int]):
        msg = self.gossip.create_get_blocks(heights, peer)
        await self.p2p.send(peer, msg)

    async def start_sync(self, peer: str, peer_height: int):
        if self._sync_in_progress:
            logger.debug("Sync already in progress")
            return
        self._sync_in_progress = True
        self._sync_peer = peer
        my_height = self.blockchain.height()
        logger.info(f"Starting sync: {my_height} -> {peer_height} from {peer}")
        batch_size = self.gossip.get_adaptive_batch_size(peer)
        logger.info(f"Adaptive batch size: {batch_size}")
        ranges = self.gossip.get_sync_ranges(my_height, peer_height, peer)
        for start, end in ranges:
            logger.info(f"Requesting blocks {start}-{end}")
            await self.p2p.send(peer, {
                "type": "SYNC_REQUEST",
                "start_height": start,
                "end_height": end,
                "my_height": my_height,
                "batch_size": batch_size
            })
            await asyncio.sleep(0.5)
        self._sync_in_progress = False
        self._sync_peer = None

    async def _gossip_handle_block_announce(self, msg: dict, peer: str):
        block_hash = msg.get("hash")
        height = msg.get("height", 0)
        if not block_hash:
            return
        my_height = self.blockchain.height()
        if self.gossip.should_request_block(block_hash, my_height, height):
            logger.info(f"New block announced: #{height} from {peer}")
            await self.gossip_request_block(peer, height)
        else:
            logger.debug(f"Ignoring announced block #{height} (already have or behind)")

    async def _gossip_handle_tx_announce(self, msg: dict, peer: str):
        tx_hash = msg.get("hash")
        if not tx_hash:
            return
        tx_cache = self._get_tx_cache()
        if tx_cache.has(tx_hash):
            return
        if self.gossip.should_request_tx(tx_hash):
            logger.debug(f"New tx announced: {tx_hash[:16]}...")
            await self.p2p.send(peer, {"type": "GET_TX", "tx_hash": tx_hash})

    async def _gossip_handle_sync_request(self, msg: dict, peer: str):
        start_height = msg.get("start_height", 0)
        end_height = msg.get("end_height", 0)
        blocks_data = []
        for h in range(start_height, end_height + 1):
            block_data = self.blockchain.db.get_block(h)
            if block_data:
                blocks_data.append(block_data)
        if blocks_data:
            response = self.gossip.create_block_batch(start_height, end_height, blocks_data)
            await self.p2p.send(peer, response)
            logger.debug(f"Sent {len(blocks_data)} blocks ({start_height}-{end_height})")

    async def _gossip_handle_sync_batch(self, msg: dict):
        blocks = msg.get("blocks", [])
        count = msg.get("count", 0)
        if not blocks:
            return
        accepted = 0
        for block_data in blocks:
            from core.block import Block
            block = Block.deserialize(block_data)
            if self.blockchain.add_block(block):
                accepted += 1
                self.mempool.remove_many(
                    [tx.get("hash") for tx in block.transactions if tx.get("hash")]
                )
        logger.info(f"Sync batch: {accepted}/{count} blocks accepted")

    async def _gossip_handle_get_blocks(self, msg: dict, peer: str):
        heights = msg.get("heights", [])
        blocks_data = []
        for h in heights:
            block_data = self.blockchain.db.get_block(h)
            if block_data:
                blocks_data.append(block_data)
        if blocks_data:
            await self.p2p.send(peer, {
                "type": "SYNC_BLOCK_BATCH",
                "blocks": blocks_data,
                "count": len(blocks_data)
            })
