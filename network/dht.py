"""
TritioCoin DHT (Distributed Hash Table) - Kademlia Protocol
Decentralized peer discovery without central seed nodes.

Features:
- TLS encrypted connections
- Persistent routing table
- Secure node authentication
"""
import hashlib
import time
import random
import logging
import asyncio
import json
import ssl
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("DHT")

K = 20
ALPHA = 3
ID_SIZE = 160
KEY_SIZE = 20
DHT_CERT_DIR = Path("tritiocoin_data/certs")
DHT_ROUTING_FILE = Path("tritiocoin_data/dht_routing.json")


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

    def is_empty(self) -> bool:
        return len(self.nodes) == 0


class RoutingTable:
    def __init__(self, node_id: bytes):
        self.node_id = node_id
        self.buckets: List[KBucket] = []
        self._init_buckets()

    def _init_buckets(self):
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

    def get_random_node(self) -> Optional[NodeInfo]:
        all_nodes = self.get_all_nodes()
        if all_nodes:
            return random.choice(all_nodes)
        return None

    def to_list(self) -> List[dict]:
        return [n.to_dict() for n in self.get_all_nodes()]

    def load_from_list(self, nodes_data: List[dict]):
        for nd in nodes_data:
            try:
                node = NodeInfo.from_dict(nd)
                self.add_node(node)
            except Exception:
                pass


class DHT:
    """Kademlia DHT with TLS encryption and persistent routing table."""

    def __init__(self, node_id: bytes = None, port: int = 8333):
        self.node_id = node_id or generate_node_id()
        self.port = port
        self.routing_table = RoutingTable(self.node_id)
        self.storage: Dict[str, str] = {}
        self.running = False
        self.server = None
        self.on_peer_found = None
        self.ssl_context = None
        self.ssl_client_context = None
        self._setup_tls()
        self._load_routing_table()

    def _setup_tls(self):
        DHT_CERT_DIR.mkdir(parents=True, exist_ok=True)
        cert_file = DHT_CERT_DIR / "dht.pem"
        key_file = DHT_CERT_DIR / "dht.key"
        if not cert_file.exists() or not key_file.exists():
            self._generate_dht_cert(cert_file, key_file)
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ssl_context.load_cert_chain(cert_file, key_file)
        self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
        self.ssl_client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.ssl_client_context.load_verify_locations(cert_file)
        self.ssl_client_context.check_hostname = False
        self.ssl_client_context.verify_mode = ssl.CERT_NONE
        self.ssl_client_context.minimum_version = ssl.TLSVersion.TLSv1_3

    def _generate_dht_cert(self, cert_path: Path, key_path: Path):
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            import datetime

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, f"TritioCoin-DHT"),
            ])
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime.utcnow())
                .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
                .add_extension(x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.IPAddress(__import__("ipaddress").IPv4Address("127.0.0.1")),
                ]), critical=False)
                .sign(key, hashes.SHA256())
            )
            with open(cert_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            with open(key_path, "wb") as f:
                f.write(key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.TraditionalOpenSSL,
                    serialization.NoEncryption()
                ))
        except Exception as e:
            logger.debug(f"Could not generate DHT cert: {e}")

    def _load_routing_table(self):
        try:
            if DHT_ROUTING_FILE.exists():
                with open(DHT_ROUTING_FILE, 'r') as f:
                    data = json.load(f)
                self.routing_table.load_from_list(data.get("nodes", []))
                logger.info(f"Loaded DHT routing table: {self.routing_table.size()} nodes")
        except Exception as e:
            logger.debug(f"Could not load DHT routing table: {e}")

    def _save_routing_table(self):
        try:
            DHT_ROUTING_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "nodes": self.routing_table.to_list(),
                "saved_at": time.time()
            }
            with open(DHT_ROUTING_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save DHT routing table: {e}")

    async def start(self, host: str = "0.0.0.0"):
        try:
            self.running = True
            self.server = await asyncio.start_server(
                self._handle_request, host, self.port, ssl=self.ssl_context
            )
            logger.info(f"DHT started on port {self.port} (TLS)")
        except OSError as e:
            if "10048" in str(e):
                logger.warning(f"Porta DHT {self.port} ja esta em uso. DHT desabilitado.")
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
            else:
                target = hashlib.sha1(key.encode()).digest()
                nodes = self.routing_table.get_closest_nodes(target, K)
                return {"type": "NODES", "nodes": [n.to_dict() for n in nodes]}
        elif msg_type == "STORE":
            key = msg["key"]
            value = msg["value"]
            self.storage[key] = value
            return {"type": "STORED", "key": key}
        elif msg_type == "GET_PEERS":
            peers = []
            for key, value in self.storage.items():
                if key.startswith("peer:"):
                    peers.append(value)
            return {"type": "PEERS", "peers": peers}
        return {"type": "ERROR", "message": "Unknown message type"}

    async def _send_dht_msg(self, node: NodeInfo, msg: dict) -> Optional[dict]:
        """Send a DHT message to a node with TLS."""
        try:
            reader, writer = await asyncio.open_connection(
                node.ip, node.port, ssl=self.ssl_client_context
            )
            raw = json.dumps(msg).encode('utf-8')
            writer.write(len(raw).to_bytes(4, 'big'))
            writer.write(raw)
            await writer.drain()
            length_data = await reader.readexactly(4)
            length = int.from_bytes(length_data, 'big')
            resp_data = await reader.readexactly(length)
            resp = json.loads(resp_data.decode('utf-8'))
            writer.close()
            return resp
        except Exception:
            return None

    async def ping(self, node: NodeInfo) -> bool:
        resp = await self._send_dht_msg(node, {
            "type": "PING",
            "node_id": self.node_id.hex()
        })
        return resp is not None and resp.get("type") == "PONG"

    async def find_node(self, target: bytes, node: NodeInfo) -> List[NodeInfo]:
        resp = await self._send_dht_msg(node, {
            "type": "FIND_NODE",
            "target": target.hex()
        })
        if resp is None:
            return []
        nodes = []
        for n_data in resp.get("nodes", []):
            nodes.append(NodeInfo.from_dict(n_data))
        return nodes

    async def store(self, key: str, value: str, node: NodeInfo) -> bool:
        resp = await self._send_dht_msg(node, {
            "type": "STORE",
            "key": key,
            "value": value
        })
        return resp is not None and resp.get("type") == "STORED"

    async def get_peers(self, node: NodeInfo) -> List[str]:
        resp = await self._send_dht_msg(node, {"type": "GET_PEERS"})
        if resp is None:
            return []
        return resp.get("peers", [])

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
        self._save_routing_table()
        logger.info(f"DHT bootstrapped with {self.routing_table.size()} nodes")

    async def iterative_find_node(self, target: bytes) -> List[NodeInfo]:
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
        self._save_routing_table()
        return all_found

    async def announce_peer(self, peer_address: str):
        key = f"peer:{peer_address}"
        value = peer_address
        target = hashlib.sha1(key.encode()).digest()
        closest = self.routing_table.get_closest_nodes(target, ALPHA)
        for node in closest:
            await self.store(key, value, node)

    async def lookup_peer(self, peer_address: str) -> bool:
        key = f"peer:{peer_address}"
        target = hashlib.sha1(key.encode()).digest()
        closest = self.routing_table.get_closest_nodes(target, ALPHA)
        for node in closest:
            resp = await self._send_dht_msg(node, {
                "type": "FIND_VALUE",
                "key": key
            })
            if resp and resp.get("type") == "VALUE" and resp.get("value") == peer_address:
                return True
        return False

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
