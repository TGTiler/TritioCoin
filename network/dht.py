"""
TritioCoin DHT (Distributed Hash Table) - Kademlia Protocol
Decentralized peer discovery without central seed nodes.
"""
import hashlib
import time
import random
import logging
import asyncio
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("DHT")

# Kademlia constants
K = 20  # Bucket size
ALPHA = 3  # Concurrency parameter
ID_SIZE = 160  # Bit length of node IDs
KEY_SIZE = 20  # Byte length of node IDs


def generate_node_id() -> bytes:
    """Generate a random 160-bit node ID."""
    return os.urandom(KEY_SIZE)


def distance(id1: bytes, id2: bytes) -> int:
    """Calculate XOR distance between two node IDs."""
    return int.from_bytes(id1, 'big') ^ int.from_bytes(id2, 'big')


def common_prefix_length(id1: bytes, id2: bytes) -> int:
    """Calculate the length of common prefix between two IDs."""
    xor = distance(id1, id2)
    if xor == 0:
        return ID_SIZE
    length = 0
    while xor > 0:
        length += 1
        xor >>= 1
    return ID_SIZE - length


@dataclass
class NodeInfo:
    """Information about a DHT node."""
    node_id: bytes
    ip: str
    port: int
    last_seen: float = field(default_factory=time.time)

    @property
    def address(self) -> str:
        return f"{self.ip}:{self.port}"

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id.hex(),
            "ip": self.ip,
            "port": self.port
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'NodeInfo':
        return cls(
            node_id=bytes.fromhex(data["node_id"]),
            ip=data["ip"],
            port=data["port"]
        )


class KBucket:
    """K-bucket for storing nodes in the DHT routing table."""

    def __init__(self, range_min: int, range_max: int):
        self.range_min = range_min
        self.range_max = range_max
        self.nodes: List[NodeInfo] = []

    def add_node(self, node: NodeInfo) -> bool:
        """Add a node to the bucket. Returns True if added."""
        # Check if node already exists
        for i, existing in enumerate(self.nodes):
            if existing.node_id == node.node_id:
                # Update last_seen
                self.nodes[i].last_seen = time.time()
                return True

        if len(self.nodes) < K:
            self.nodes.append(node)
            return True

        # Bucket is full, check if we should replace
        # (In real implementation, we'd ping the oldest node)
        return False

    def remove_node(self, node_id: bytes):
        """Remove a node from the bucket."""
        self.nodes = [n for n in self.nodes if n.node_id != node_id]

    def get_closest(self, target: bytes, count: int = K) -> List[NodeInfo]:
        """Get the closest nodes to a target ID."""
        sorted_nodes = sorted(self.nodes, key=lambda n: distance(n.node_id, target))
        return sorted_nodes[:count]

    def is_empty(self) -> bool:
        return len(self.nodes) == 0


class RoutingTable:
    """Kademlia routing table with k-buckets."""

    def __init__(self, node_id: bytes):
        self.node_id = node_id
        self.buckets: List[KBucket] = []
        self._init_buckets()

    def _init_buckets(self):
        """Initialize 160 k-buckets."""
        for i in range(ID_SIZE):
            self.buckets.append(KBucket(2**i, 2**(i+1)))

    def _get_bucket_index(self, node_id: bytes) -> int:
        """Get the bucket index for a node ID."""
        common = common_prefix_length(self.node_id, node_id)
        return min(common, ID_SIZE - 1)

    def add_node(self, node: NodeInfo) -> bool:
        """Add a node to the routing table."""
        if node.node_id == self.node_id:
            return False  # Don't add ourselves

        idx = self._get_bucket_index(node.node_id)
        return self.buckets[idx].add_node(node)

    def remove_node(self, node_id: bytes):
        """Remove a node from the routing table."""
        idx = self._get_bucket_index(node_id)
        self.buckets[idx].remove_node(node_id)

    def get_closest_nodes(self, target: bytes, count: int = K) -> List[NodeInfo]:
        """Get the closest nodes to a target ID."""
        all_nodes = []
        for bucket in self.buckets:
            all_nodes.extend(bucket.nodes)

        sorted_nodes = sorted(all_nodes, key=lambda n: distance(n.node_id, target))
        return sorted_nodes[:count]

    def get_all_nodes(self) -> List[NodeInfo]:
        """Get all known nodes."""
        nodes = []
        for bucket in self.buckets:
            nodes.extend(bucket.nodes)
        return nodes

    def size(self) -> int:
        """Get total number of nodes in routing table."""
        return sum(len(b.nodes) for b in self.buckets)

    def get_random_node(self) -> Optional[NodeInfo]:
        """Get a random node from the routing table."""
        all_nodes = self.get_all_nodes()
        if all_nodes:
            return random.choice(all_nodes)
        return None


class DHT:
    """
    Kademlia DHT for decentralized peer discovery.

    Nodes store and retrieve peer addresses without central authority.
    """

    def __init__(self, node_id: bytes = None, port: int = 8333):
        self.node_id = node_id or generate_node_id()
        self.port = port
        self.routing_table = RoutingTable(self.node_id)
        self.storage: Dict[str, str] = {}  # key -> value (peer addresses)
        self.running = False
        self.server = None
        self.on_peer_found = None  # Callback when new peer discovered

    async def start(self, host: str = "0.0.0.0"):
        """Start the DHT server."""
        self.running = True
        self.server = await asyncio.start_server(
            self._handle_request, host, self.port
        )
        logger.info(f"DHT started on port {self.port}")

    async def _handle_request(self, reader: asyncio.StreamReader,
                               writer: asyncio.StreamWriter):
        """Handle incoming DHT requests."""
        try:
            while True:
                # Read message length
                length_data = await reader.readexactly(4)
                length = int.from_bytes(length_data, 'big')

                if length > 1024 * 1024:  # 1MB max
                    break

                # Read message
                msg_data = await reader.readexactly(length)
                msg = json.loads(msg_data.decode('utf-8'))

                # Process request
                response = await self._process_request(msg)

                # Send response
                resp_json = json.dumps(response).encode('utf-8')
                writer.write(len(resp_json).to_bytes(4, 'big'))
                writer.write(resp_json)
                await writer.drain()

        except (ConnectionResetError, asyncio.IncompleteReadError):
            pass
        except Exception as e:
            logger.error(f"DHT request error: {e}")
        finally:
            writer.close()

    async def _process_request(self, msg: dict) -> dict:
        """Process a DHT request and return response."""
        msg_type = msg.get("type")

        if msg_type == "PING":
            return {"type": "PONG", "node_id": self.node_id.hex()}

        elif msg_type == "FIND_NODE":
            target = bytes.fromhex(msg["target"])
            nodes = self.routing_table.get_closest_nodes(target, K)
            return {
                "type": "NODES",
                "nodes": [n.to_dict() for n in nodes]
            }

        elif msg_type == "FIND_VALUE":
            key = msg["key"]
            value = self.storage.get(key)
            if value:
                return {"type": "VALUE", "value": value}
            else:
                # Return closest nodes
                target = hashlib.sha1(key.encode()).digest()
                nodes = self.routing_table.get_closest_nodes(target, K)
                return {
                    "type": "NODES",
                    "nodes": [n.to_dict() for n in nodes]
                }

        elif msg_type == "STORE":
            key = msg["key"]
            value = msg["value"]
            self.storage[key] = value
            return {"type": "STORED", "key": key}

        elif msg_type == "GET_PEERS":
            # Return all known peer addresses
            peers = []
            for key, value in self.storage.items():
                if key.startswith("peer:"):
                    peers.append(value)
            return {"type": "PEERS", "peers": peers}

        return {"type": "ERROR", "message": "Unknown message type"}

    async def ping(self, node: NodeInfo) -> bool:
        """Ping a node to check if it's alive."""
        try:
            reader, writer = await asyncio.open_connection(node.ip, node.port)
            msg = json.dumps({
                "type": "PING",
                "node_id": self.node_id.hex()
            }).encode('utf-8')

            writer.write(len(msg).to_bytes(4, 'big'))
            writer.write(msg)
            await writer.drain()

            # Read response
            length_data = await reader.readexactly(4)
            length = int.from_bytes(length_data, 'big')
            resp_data = await reader.readexactly(length)
            resp = json.loads(resp_data.decode('utf-8'))

            writer.close()
            return resp.get("type") == "PONG"

        except Exception:
            return False

    async def find_node(self, target: bytes, node: NodeInfo) -> List[NodeInfo]:
        """Ask a node to find nodes close to target."""
        try:
            reader, writer = await asyncio.open_connection(node.ip, node.port)
            msg = json.dumps({
                "type": "FIND_NODE",
                "target": target.hex()
            }).encode('utf-8')

            writer.write(len(msg).to_bytes(4, 'big'))
            writer.write(msg)
            await writer.drain()

            length_data = await reader.readexactly(4)
            length = int.from_bytes(length_data, 'big')
            resp_data = await reader.readexactly(length)
            resp = json.loads(resp_data.decode('utf-8'))

            writer.close()

            nodes = []
            for n_data in resp.get("nodes", []):
                nodes.append(NodeInfo.from_dict(n_data))
            return nodes

        except Exception:
            return []

    async def store(self, key: str, value: str, node: NodeInfo) -> bool:
        """Store a key-value pair on a node."""
        try:
            reader, writer = await asyncio.open_connection(node.ip, node.port)
            msg = json.dumps({
                "type": "STORE",
                "key": key,
                "value": value
            }).encode('utf-8')

            writer.write(len(msg).to_bytes(4, 'big'))
            writer.write(msg)
            await writer.drain()

            length_data = await reader.readexactly(4)
            length = int.from_bytes(length_data, 'big')
            resp_data = await reader.readexactly(length)
            resp = json.loads(resp_data.decode('utf-8'))

            writer.close()
            return resp.get("type") == "STORED"

        except Exception:
            return False

    async def get_peers(self, node: NodeInfo) -> List[str]:
        """Get peer list from a node."""
        try:
            reader, writer = await asyncio.open_connection(node.ip, node.port)
            msg = json.dumps({"type": "GET_PEERS"}).encode('utf-8')

            writer.write(len(msg).to_bytes(4, 'big'))
            writer.write(msg)
            await writer.drain()

            length_data = await reader.readexactly(4)
            length = int.from_bytes(length_data, 'big')
            resp_data = await reader.readexactly(length)
            resp = json.loads(resp_data.decode('utf-8'))

            writer.close()
            return resp.get("peers", [])

        except Exception:
            return []

    async def bootstrap(self, known_nodes: List[NodeInfo]):
        """Bootstrap the DHT by querying known nodes."""
        for node in known_nodes:
            # Add to routing table
            self.routing_table.add_node(node)

            # Find ourselves
            nodes = await self.find_node(self.node_id, node)
            for n in nodes:
                self.routing_table.add_node(n)

            # Get peers
            peers = await self.get_peers(node)
            for peer_addr in peers:
                if self.on_peer_found:
                    self.on_peer_found(peer_addr)

        logger.info(f"DHT bootstrapped with {self.routing_table.size()} nodes")

    async def iterative_find_node(self, target: bytes) -> List[NodeInfo]:
        """Iterative find node operation."""
        closest = self.routing_table.get_closest_nodes(target, ALPHA)
        queried = set()
        all_found = []

        while closest:
            next_closest = []

            for node in closest:
                if node.node_id in queried:
                    continue

                queried.add(node.node_id)
                nodes = await self.find_node(target, node)

                for n in nodes:
                    self.routing_table.add_node(n)
                    if n.node_id not in queried:
                        next_closest.append(n)
                        all_found.append(n)

            closest = sorted(next_closest, key=lambda n: distance(n.node_id, target))[:K]

        return all_found

    async def announce_peer(self, peer_address: str):
        """Announce a peer address to the DHT."""
        key = f"peer:{peer_address}"
        value = peer_address

        # Store on closest nodes to the key
        target = hashlib.sha1(key.encode()).digest()
        closest = self.routing_table.get_closest_nodes(target, ALPHA)

        for node in closest:
            await self.store(key, value, node)

    async def lookup_peer(self, peer_address: str) -> bool:
        """Look up if a peer exists in the DHT."""
        key = f"peer:{peer_address}"
        target = hashlib.sha1(key.encode()).digest()

        closest = self.routing_table.get_closest_nodes(target, ALPHA)

        for node in closest:
            try:
                reader, writer = await asyncio.open_connection(node.ip, node.port)
                msg = json.dumps({
                    "type": "FIND_VALUE",
                    "key": key
                }).encode('utf-8')

                writer.write(len(msg).to_bytes(4, 'big'))
                writer.write(msg)
                await writer.drain()

                length_data = await reader.readexactly(4)
                length = int.from_bytes(length_data, 'big')
                resp_data = await reader.readexactly(length)
                resp = json.loads(resp_data.decode('utf-8'))

                writer.close()

                if resp.get("type") == "VALUE" and resp.get("value") == peer_address:
                    return True

            except Exception:
                continue

        return False

    def get_stats(self) -> dict:
        """Get DHT statistics."""
        return {
            "node_id": self.node_id.hex()[:16] + "...",
            "routing_table_size": self.routing_table.size(),
            "storage_size": len(self.storage),
            "known_peers": len([k for k in self.storage if k.startswith("peer:")])
        }


# Global DHT instance
_dht: Optional[DHT] = None


def get_dht() -> DHT:
    """Get the global DHT instance."""
    global _dht
    if _dht is None:
        _dht = DHT()
    return _dht


import os
