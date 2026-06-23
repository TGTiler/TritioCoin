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
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("DHT")

K = 20
ALPHA = 3
ID_SIZE = 160
KEY_SIZE = 20


def generate_node_id() -> bytes:
    return os.urandom(KEY_SIZE)


def distance(id1: bytes, id2: bytes) -> int:
    return int.from_bytes(id1, 'big') ^ int.from_bytes(id2, 'big')


def common_prefix_length(id1: bytes, id2: bytes) -> int:
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
    node_id: bytes
    ip: str
    port: int
    last_seen: float = field(default_factory=time.time)

    @property
    def address(self) -> str:
        return f"{self.ip}:{self.port}"

    def to_dict(self) -> dict:
        return {"node_id": self.node_id.hex(), "ip": self.ip, "port": self.port}

    @classmethod
    def from_dict(cls, data: dict) -> 'NodeInfo':
        return cls(node_id=bytes.fromhex(data["node_id"]), ip=data["ip"], port=data["port"])


class KBucket:
    def __init__(self, range_min: int, range_max: int):
        self.range_min = range_min
        self.range_max = range_max
        self.nodes: List[NodeInfo] = []

    def add_node(self, node: NodeInfo) -> bool:
        for i, existing in enumerate(self.nodes):
            if existing.node_id == node.node_id:
                self.nodes[i].last_seen = time.time()
                return True
        if len(self.nodes) < K:
            self.nodes.append(node)
            return True
        return False

    def remove_node(self, node_id: bytes):
        self.nodes = [n for n in self.nodes if n.node_id != node_id]

    def get_closest(self, target: bytes, count: int = K) -> List[NodeInfo]:
        sorted_nodes = sorted(self.nodes, key=lambda n: distance(n.node_id, target))
        return sorted_nodes[:count]


class RoutingTable:
    def __init__(self, node_id: bytes):
        self.node_id = node_id
        self.buckets: List[KBucket] = []
        for i in range(ID_SIZE):
            self.buckets.append(KBucket(2**i, 2**(i+1)))

    def _get_bucket_index(self, node_id: bytes) -> int:
        common = common_prefix_length(self.node_id, node_id)
        return min(common, ID_SIZE - 1)

    def add_node(self, node: NodeInfo) -> bool:
        if node.node_id == self.node_id:
            return False
        idx = self._get_bucket_index(node.node_id)
        return self.buckets[idx].add_node(node)

    def remove_node(self, node_id: bytes):
        idx = self._get_bucket_index(node_id)
        self.buckets[idx].remove_node(node_id)

    def get_closest_nodes(self, target: bytes, count: int = K) -> List[NodeInfo]:
        all_nodes = []
        for bucket in self.buckets:
            all_nodes.extend(bucket.nodes)
        sorted_nodes = sorted(all_nodes, key=lambda n: distance(n.node_id, target))
        return sorted_nodes[:count]

    def get_all_nodes(self) -> List[NodeInfo]:
        nodes = []
        for bucket in self.buckets:
            nodes.extend(bucket.nodes)
        return nodes

    def size(self) -> int:
        return sum(len(b.nodes) for b in self.buckets)


class DHT:
    def __init__(self, node_id: bytes = None, port: int = 8333):
        self.node_id = node_id or generate_node_id()
        self.port = port
        self.routing_table = RoutingTable(self.node_id)
        self.storage: Dict[str, str] = {}
        self.running = False
        self.server = None
        self.on_peer_found = None

    async def start(self, host: str = "0.0.0.0"):
        try:
            self.running = True
            self.server = await asyncio.start_server(
                self._handle_request, host, self.port
            )
            logger.info(f"DHT started on port {self.port}")
        except OSError as e:
            if "10048" in str(e) or "address already in use" in str(e).lower():
                logger.warning(f"Porta DHT {self.port} ja esta em uso.")
            else:
                logger.error(f"DHT error: {e}")

    async def _handle_request(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            while True:
                length_data = await reader.readexactly(4)
                length = int.from_bytes(length_data, 'big')
                if length > 1024 * 1024:
                    break
                msg_data = await reader.readexactly(length)
                msg = json.loads(msg_data.decode('utf-8'))
                response = await self._process_request(msg)
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
        msg_type = msg.get("type")
        if msg_type == "PING":
            return {"type": "PONG", "node_id": self.node_id.hex()}
        elif msg_type == "FIND_NODE":
            target = bytes.fromhex(msg["target"])
            nodes = self.routing_table.get_closest_nodes(target, K)
            return {"type": "NODES", "nodes": [n.to_dict() for n in nodes]}
        elif msg_type == "FIND_VALUE":
            key = msg["key"]
            value = self.storage.get(key)
            if value:
                return {"type": "VALUE", "value": value}
            target = hashlib.sha1(key.encode()).digest()
            nodes = self.routing_table.get_closest_nodes(target, K)
            return {"type": "NODES", "nodes": [n.to_dict() for n in nodes]}
        elif msg_type == "STORE":
            self.storage[msg["key"]] = msg["value"]
            return {"type": "STORED", "key": msg["key"]}
        elif msg_type == "GET_PEERS":
            peers = [v for k, v in self.storage.items() if k.startswith("peer:")]
            return {"type": "PEERS", "peers": peers}
        return {"type": "ERROR", "message": "Unknown"}

    async def ping(self, node: NodeInfo) -> bool:
        try:
            reader, writer = await asyncio.open_connection(node.ip, node.port)
            msg = json.dumps({"type": "PING", "node_id": self.node_id.hex()}).encode('utf-8')
            writer.write(len(msg).to_bytes(4, 'big'))
            writer.write(msg)
            await writer.drain()
            length_data = await reader.readexactly(4)
            length = int.from_bytes(length_data, 'big')
            resp_data = await reader.readexactly(length)
            resp = json.loads(resp_data.decode('utf-8'))
            writer.close()
            return resp.get("type") == "PONG"
        except Exception:
            return False

    async def find_node(self, target: bytes, node: NodeInfo) -> List[NodeInfo]:
        try:
            reader, writer = await asyncio.open_connection(node.ip, node.port)
            msg = json.dumps({"type": "FIND_NODE", "target": target.hex()}).encode('utf-8')
            writer.write(len(msg).to_bytes(4, 'big'))
            writer.write(msg)
            await writer.drain()
            length_data = await reader.readexactly(4)
            length = int.from_bytes(length_data, 'big')
            resp_data = await reader.readexactly(length)
            resp = json.loads(resp_data.decode('utf-8'))
            writer.close()
            return [NodeInfo.from_dict(n) for n in resp.get("nodes", [])]
        except Exception:
            return []

    async def store(self, key: str, value: str, node: NodeInfo) -> bool:
        try:
            reader, writer = await asyncio.open_connection(node.ip, node.port)
            msg = json.dumps({"type": "STORE", "key": key, "value": value}).encode('utf-8')
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
        for node in known_nodes:
            self.routing_table.add_node(node)
            nodes = await self.find_node(self.node_id, node)
            for n in nodes:
                self.routing_table.add_node(n)
            peers = await self.get_peers(node)
            for peer_addr in peers:
                if self.on_peer_found:
                    self.on_peer_found(peer_addr)
        logger.info(f"DHT bootstrapped with {self.routing_table.size()} nodes")

    async def announce_peer(self, peer_address: str):
        key = f"peer:{peer_address}"
        target = hashlib.sha1(key.encode()).digest()
        closest = self.routing_table.get_closest_nodes(target, ALPHA)
        for node in closest:
            await self.store(key, peer_address, node)

    def get_stats(self) -> dict:
        return {
            "node_id": self.node_id.hex()[:16] + "...",
            "routing_table_size": self.routing_table.size(),
            "storage_size": len(self.storage),
            "known_peers": len([k for k in self.storage if k.startswith("peer:")])
        }


_dht: Optional[DHT] = None


def get_dht() -> DHT:
    global _dht
    if _dht is None:
        _dht = DHT()
    return _dht
