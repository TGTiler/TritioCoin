"""
TritioCoin Gossip Protocol — Production-Grade Implementation
=============================================================

Gossip propagation of blocks and transactions across the P2P network.

Wire-level inventory messages (binary, Little-Endian):
    ``inv``    / ``getdata``   —  payload ``<I32s`` (type 4B + SHA-256 hash 32B)
    Inventory types: 1 = TX, 2 = Block

Application-level announcements (JSON, backward-compatible):
    BLOCK_ANNOUNCE / TX_ANNOUNCE — legacy text-based announcements
    GET_BLOCK / GET_TX            — fetch full data

Flow for a new block:
    1. Miner node produces a valid block.
    2. Sends ``inv`` (type=2, hash) to all connected peers.
    3. Each receiving peer checks its local chain/mempool.
    4. If the block is unknown, the receiver replies with ``getdata``.
    5. The original node responds with the full block payload (JSON).

Flow for a new transaction:
    1. User broadcasts a signed TX.
    2. Node sends ``inv`` (type=1, hash) to all peers.
    3. Receiving peer checks its mempool.
    4. If unknown, replies with ``getdata``.
    5. Full TX JSON is sent back.

Each PeerSession keeps a ``known_inventory`` set to prevent redundant
re-announcement of the same hash to the same peer.
"""

import hashlib
import time
import logging
import asyncio
from typing import Dict, Set, List, Optional, Tuple
from collections import OrderedDict

logger = logging.getLogger("Gossip")


class InventoryItem:
    """An entry in the local inventory cache."""

    def __init__(self, inv_type: str, inv_hash: str, height: int = 0):
        self.type = inv_type          # "block" or "tx"
        self.hash = inv_hash          # hex-encoded SHA-256
        self.height = height
        self.time_seen = time.time()

    def to_dict(self) -> dict:
        return {"type": self.type, "hash": self.hash,
                "height": self.height}


class GossipProtocol:
    """
    Inventory tracking, announcement scheduling, and sync range calculation.

    This class is *stateless with respect to the network* — it manages the
    local inventory cache and decides *what* to announce/request.  The
    actual wire-level send/receive is handled by GossipNode (mixin).
    """

    MAX_INVENTORY_SIZE = 5000
    INV_EXPIRY_TIME = 3600          # 1 hour
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

    # ── Inventory housekeeping ────────────────────────────────────────

    def _cleanup_inventory(self):
        """Drop expired inventory entries."""
        now = time.time()
        if now - self._last_cleanup < 60:
            return
        expired = [h for h, item in self.inventory.items()
                   if now - item.time_seen > self.INV_EXPIRY_TIME]
        for h in expired:
            del self.inventory[h]
            self.known_blocks.discard(h)
            self.known_txs.discard(h)
        self._last_cleanup = now

    def _track_item(self, item: InventoryItem):
        """Insert an item into the inventory cache, evicting oldest if full."""
        self.inventory[item.hash] = item
        if item.type == "block":
            self.known_blocks.add(item.hash)
        elif item.type == "tx":
            self.known_txs.add(item.hash)
        while len(self.inventory) > self.MAX_INVENTORY_SIZE:
            oldest_hash, _ = self.inventory.popitem(last=False)
            self.known_blocks.discard(oldest_hash)
            self.known_txs.discard(oldest_hash)

    # ── Query helpers ─────────────────────────────────────────────────

    def has_block(self, block_hash: str) -> bool:
        return block_hash in self.known_blocks

    def has_tx(self, tx_hash: str) -> bool:
        return tx_hash in self.known_txs

    def should_request_block(self, block_hash: str, my_height: int,
                             announced_height: int) -> bool:
        if block_hash in self.known_blocks:
            return False
        if announced_height <= my_height:
            return False
        return True

    def should_request_tx(self, tx_hash: str) -> bool:
        return tx_hash not in self.known_txs

    # ── Announcement builders ─────────────────────────────────────────

    def announce_block(self, block_hash: str, height: int) -> dict:
        """Register a block in the local cache and return an inv message dict."""
        self._track_item(InventoryItem("block", block_hash, height))
        self._cleanup_inventory()
        return {"type": "BLOCK_ANNOUNCE", "hash": block_hash,
                "height": height}

    def announce_tx(self, tx_hash: str) -> dict:
        """Register a TX in the local cache and return an inv message dict."""
        self._track_item(InventoryItem("tx", tx_hash))
        self._cleanup_inventory()
        return {"type": "TX_ANNOUNCE", "hash": tx_hash}

    # ── Sync helpers ──────────────────────────────────────────────────

    def update_peer_latency(self, peer: str, latency_ms: float):
        self.peer_latencies[peer] = latency_ms

    def get_adaptive_batch_size(self, peer: str = None) -> int:
        """Scale batch size inversely with measured peer latency."""
        if peer is None:
            return self.DEFAULT_BATCH_SIZE
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
        return self.MIN_BATCH_SIZE

    def get_sync_ranges(self, my_height: int, peer_height: int,
                        peer: str = None) -> List[Tuple[int, int]]:
        if peer_height <= my_height:
            return []
        batch = self.get_adaptive_batch_size(peer)
        ranges = []
        start = my_height + 1
        while start <= peer_height:
            end = min(start + batch - 1, peer_height)
            ranges.append((start, end))
            start = end + 1
        return ranges

    def create_sync_request(self, my_height: int, peer_height: int,
                            peer: str = None) -> Optional[dict]:
        ranges = self.get_sync_ranges(my_height, peer_height, peer)
        if not ranges:
            return None
        first = ranges[0]
        return {"type": "SYNC_REQUEST",
                "start_height": first[0], "end_height": first[1],
                "my_height": my_height,
                "batch_size": self.get_adaptive_batch_size(peer)}

    def create_block_batch(self, start_height: int, end_height: int,
                           blocks_data: List[dict]) -> dict:
        return {"type": "SYNC_BLOCK_BATCH",
                "start_height": start_height, "end_height": end_height,
                "blocks": blocks_data, "count": len(blocks_data)}

    def create_get_blocks(self, heights: List[int],
                          peer: str = None) -> dict:
        batch = self.get_adaptive_batch_size(peer)
        return {"type": "GET_BLOCKS", "heights": heights[:batch]}

    def get_stats(self) -> dict:
        return {
            "inventory_size": len(self.inventory),
            "known_blocks": len(self.known_blocks),
            "known_txs": len(self.known_txs),
            "announcements_sent": len(self.sent_announcements),
            "avg_latency_ms": round(
                sum(self.peer_latencies.values())
                / max(len(self.peer_latencies), 1), 1)
        }


class GossipNode:
    """
    Mixin that adds gossip protocol handling to a P2P node.

    Provides:
    - ``gossip_handle_message()`` — routes inv / getdata / announce msgs.
    - ``gossip_announce_block()`` — broadcast block hash to all peers.
    - ``gossip_announce_tx()``    — broadcast TX hash to all peers.
    - ``start_sync()``            — initiate block sync from a peer.
    """

    def __init__(self):
        self.gossip = GossipProtocol()
        self._sync_in_progress = False
        self._sync_peer = None
        self._pending_blocks: Dict[int, dict] = {}
        self._tx_cache: Set[str] = set()

    def _get_tx_cache(self):
        return self._tx_cache

    # ── Message routing ───────────────────────────────────────────────

    async def gossip_handle_message(self, msg: dict, peer: str,
                                    writer) -> bool:
        """
        Route an incoming gossip message.  Returns True if handled.

        Handles both binary-level ``INV`` / ``GETDATA`` messages (from
        the P2P layer) and legacy JSON ``BLOCK_ANNOUNCE`` / ``TX_ANNOUNCE``.
        """
        msg_type = msg.get("type")

        # ── Binary inventory messages (from wire protocol) ───────
        if msg_type == "INV":
            return await self._handle_wire_inv(msg, peer)
        if msg_type == "GETDATA":
            return await self._handle_wire_getdata(msg, peer)

        # ── Legacy JSON announcements ────────────────────────────
        if msg_type == "BLOCK_ANNOUNCE":
            await self._gossip_handle_block_announce(msg, peer)
            return True
        if msg_type == "TX_ANNOUNCE":
            await self._gossip_handle_tx_announce(msg, peer)
            return True
        if msg_type == "SYNC_REQUEST":
            await self._gossip_handle_sync_request(msg, peer)
            return True
        if msg_type == "SYNC_BLOCK_BATCH":
            await self._gossip_handle_sync_batch(msg)
            return True
        if msg_type == "GET_BLOCKS":
            await self._gossip_handle_get_blocks(msg, peer)
            return True
        return False

    # ── Wire-level inventory handling ─────────────────────────────────

    async def _handle_wire_inv(self, msg: dict, peer: str) -> bool:
        """
        Process a wire-level ``inv`` message.

        If we don't have the announced item, send ``getdata`` back.
        """
        inv_type_int = msg.get("raw_inv_type", 0)
        inv_hash_hex = msg.get("hash", "")
        session = self.p2p.sessions.get(peer)

        # Skip if already known to this peer.
        if session and inv_hash_hex in session.known_inventory:
            return True

        if inv_type_int == 1:  # TX
            if not self.gossip.should_request_tx(inv_hash_hex):
                return True
            logger.debug(f"Requesting TX {inv_hash_hex[:16]}... from {peer}")
            if session:
                await session.send_getdata(1, bytes.fromhex(inv_hash_hex))
            return True

        if inv_type_int == 2:  # Block
            # We need to know our height to decide.
            my_height = 0
            if hasattr(self, 'blockchain') and self.blockchain:
                my_height = self.blockchain.height()
            if not self.gossip.should_request_block(
                    inv_hash_hex, my_height, my_height + 1):
                return True
            logger.info(f"Requesting block {inv_hash_hex[:16]}... from {peer}")
            if session:
                await session.send_getdata(2, bytes.fromhex(inv_hash_hex))
            return True

        return True

    async def _handle_wire_getdata(self, msg: dict, peer: str) -> bool:
        """
        Process a wire-level ``getdata`` request.

        Look up the requested hash in our mempool / blockchain and
        respond with the full data.
        """
        inv_type_int = msg.get("raw_inv_type", 0)
        inv_hash_hex = msg.get("hash", "")
        session = self.p2p.sessions.get(peer)
        if not session:
            return True

        if inv_type_int == 1:  # TX
            for tx_data in self.mempool.get():
                if tx_data.get("tx_hash") == inv_hash_hex:
                    await session.send_json('tx', tx_data)
                    return True
            return True

        if inv_type_int == 2:  # Block
            if hasattr(self, 'blockchain') and self.blockchain:
                for h in range(self.blockchain.height() + 1):
                    bd = self.blockchain.db.get_block(h)
                    if bd and bd.get("hash") == inv_hash_hex:
                        await session.send_json('block', bd)
                        return True
            return True

        return True

    # ── Public announcement API ───────────────────────────────────────

    async def gossip_announce_block(self, block_hash: str, height: int):
        """Announce a new block to all peers via inv messages."""
        msg = self.gossip.announce_block(block_hash, height)
        # Send binary inv to peers that support it, JSON fallback otherwise.
        inv_payload = struct.pack('<I32s', 2, bytes.fromhex(block_hash.zfill(64)))
        for key in list(self.p2p.sessions.keys()):
            session = self.p2p.sessions.get(key)
            if not session or session._closed:
                continue
            if block_hash in session.known_inventory:
                continue
            session.known_inventory.add(block_hash)
            await session.send_raw('inv', inv_payload)
        logger.debug(f"Announced block #{height}: {block_hash[:16]}...")

    async def gossip_announce_tx(self, tx_hash: str):
        """Announce a new TX to all peers via inv messages."""
        tx_cache = self._get_tx_cache()
        if tx_hash in tx_cache:
            return
        tx_cache.add(tx_hash)
        msg = self.gossip.announce_tx(tx_hash)
        inv_payload = struct.pack('<I32s', 1, bytes.fromhex(tx_hash.zfill(64)))
        for key in list(self.p2p.sessions.keys()):
            session = self.p2p.sessions.get(key)
            if not session or session._closed:
                continue
            if tx_hash in session.known_inventory:
                continue
            session.known_inventory.add(tx_hash)
            await session.send_raw('inv', inv_payload)
        logger.debug(f"Announced tx: {tx_hash[:16]}...")

    async def gossip_request_block(self, peer: str, height: int):
        await self.p2p.send(peer, {"type": "GET_BLOCK", "height": height})

    async def gossip_request_blocks(self, peer: str, heights: List[int]):
        msg = self.gossip.create_get_blocks(heights, peer)
        await self.p2p.send(peer, msg)

    async def start_sync(self, peer: str, peer_height: int):
        if self._sync_in_progress:
            return
        self._sync_in_progress = True
        self._sync_peer = peer
        my_height = self.blockchain.height()
        logger.info(f"Starting sync: {my_height} -> {peer_height} from {peer}")
        batch_size = self.gossip.get_adaptive_batch_size(peer)
        ranges = self.gossip.get_sync_ranges(my_height, peer_height, peer)
        for start, end in ranges:
            await self.p2p.send(peer, {
                "type": "SYNC_REQUEST",
                "start_height": start, "end_height": end,
                "my_height": my_height, "batch_size": batch_size})
            await asyncio.sleep(0.5)
        self._sync_in_progress = False
        self._sync_peer = None

    # ── Legacy JSON announce handlers ─────────────────────────────────

    async def _gossip_handle_block_announce(self, msg: dict, peer: str):
        block_hash = msg.get("hash")
        height = msg.get("height", 0)
        if not block_hash:
            return
        my_height = self.blockchain.height()
        if self.gossip.should_request_block(block_hash, my_height, height):
            logger.info(f"New block announced: #{height} from {peer}")
            await self.gossip_request_block(peer, height)

    async def _gossip_handle_tx_announce(self, msg: dict, peer: str):
        tx_hash = msg.get("hash")
        if not tx_hash:
            return
        tx_cache = self._get_tx_cache()
        if tx_hash in tx_cache:
            return
        if self.gossip.should_request_tx(tx_hash):
            await self.p2p.send(peer, {"type": "GET_TX",
                                       "tx_hash": tx_hash})

    async def _gossip_handle_sync_request(self, msg: dict, peer: str):
        start_h = msg.get("start_height", 0)
        end_h = msg.get("end_height", 0)
        blocks = []
        for h in range(start_h, end_h + 1):
            bd = self.blockchain.db.get_block(h)
            if bd:
                blocks.append(bd)
        if blocks:
            resp = self.gossip.create_block_batch(start_h, end_h, blocks)
            await self.p2p.send(peer, resp)

    async def _gossip_handle_sync_batch(self, msg: dict):
        blocks = msg.get("blocks", [])
        count = msg.get("count", 0)
        if not blocks:
            return
        accepted = 0
        rejected = 0
        from core.block import Block
        for bd in blocks:
            try:
                block = Block.deserialize(bd)
                if self.blockchain.add_block(block):
                    accepted += 1
                    self.mempool.remove_many(
                        [tx.get("hash") for tx in block.transactions
                         if tx.get("hash")])
                else:
                    rejected += 1
            except Exception as exc:
                rejected += 1
                logger.warning(f"Block deserialize failed: {exc}")
        logger.info(f"Sync batch: {accepted}/{count} accepted, {rejected} rejected")

    async def _gossip_handle_get_blocks(self, msg: dict, peer: str):
        heights = msg.get("heights", [])
        blocks = []
        for h in heights:
            bd = self.blockchain.db.get_block(h)
            if bd:
                blocks.append(bd)
        if blocks:
            await self.p2p.send(peer, {
                "type": "SYNC_BLOCK_BATCH",
                "blocks": blocks, "count": len(blocks)})


# Needed for gossip_announce_block / gossip_announce_tx binary packing.
import struct  # noqa: E402
