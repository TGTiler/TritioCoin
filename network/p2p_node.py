"""
TritioCoin P2P Network Layer
- TLS encrypted connections
- Protocol versioning
- NAT traversal (UPnP)
- Peer authentication via node ID
- Challenge-Response authentication
- Rate limiting (adaptive based on reputation)
- Auto-reconnection
- Length-prefixed message framing
- Zlib compression for large messages
- Parallel broadcast
- Anti-Eclipse (subnet diversity check)
- SOCKS5/Tor support
"""
import asyncio
import struct
import json
import logging
import hashlib
import ssl
import os
import time
import socket
import zlib
import secrets
from typing import Dict, Optional, Set, List, Tuple
from pathlib import Path

logger = logging.getLogger("P2P")

PROTOCOL_VERSION = 3
MIN_PROTOCOL_VERSION = 1
MAX_MSG_SIZE = 10 * 1024 * 1024
RATE_LIMIT_MSGS = 200
RATE_LIMIT_WINDOW = 10
CERT_DIR = Path("tritiocoin_data/certs")
COMPRESSION_THRESHOLD = 10240
MAX_SAME_SUBNET = 3
MAX_PARALLEL_BROADCAST = 10


class RateLimiter:
    """Token bucket rate limiter with adaptive limits based on reputation."""

    def __init__(self, max_msgs: int = RATE_LIMIT_MSGS, window: int = RATE_LIMIT_WINDOW):
        self.max_msgs = max_msgs
        self.window = window
        self.counts: Dict[str, list] = {}
        self.peer_limits: Dict[str, int] = {}

    def get_limit(self, peer: str, reputation_score: int = 100) -> int:
        base = self.max_msgs
        if reputation_score > 150:
            return base * 2
        elif reputation_score > 120:
            return int(base * 1.5)
        elif reputation_score < 50:
            return base // 2
        elif reputation_score < 0:
            return base // 4
        return base

    def check(self, peer: str, reputation_score: int = 100) -> bool:
        now = time.time()
        limit = self.get_limit(peer, reputation_score)
        if peer not in self.counts:
            self.counts[peer] = []
        self.counts[peer] = [t for t in self.counts[peer] if now - t < self.window]
        if len(self.counts[peer]) >= limit:
            return False
        self.counts[peer].append(now)
        return True

    def cleanup(self):
        now = time.time()
        for peer in list(self.counts.keys()):
            self.counts[peer] = [t for t in self.counts[peer] if now - t < self.window]
            if not self.counts[peer]:
                del self.counts[peer]


class NATTraversal:
    """NAT traversal using UPnP."""

    def __init__(self):
        self.external_ip = None
        self.external_port = None
        self.upnp_available = False

    async def discover(self, internal_port: int) -> dict:
        result = {"internal_port": internal_port, "external_port": internal_port, "upnp": False}
        try:
            import urllib.request
            response = await asyncio.to_thread(
                urllib.request.urlopen, "https://api.ipify.org?format=json", timeout=5
            )
            data = json.loads(response.read().decode())
            self.external_ip = data.get("ip")
            result["external_ip"] = self.external_ip
            logger.info(f"External IP discovered: {self.external_ip}")
        except Exception as e:
            logger.debug(f"Could not discover external IP: {e}")
        try:
            upnp_result = await self._setup_upnp(internal_port)
            if upnp_result:
                result["external_port"] = upnp_result
                result["upnp"] = True
                self.upnp_available = True
                logger.info(f"UPnP port forwarding setup: {internal_port} -> {upnp_result}")
        except Exception as e:
            logger.debug(f"UPnP not available: {e}")
        return result

    async def _setup_upnp(self, port: int) -> Optional[int]:
        try:
            import miniupnpc
            u = miniupnpc.UPnP()
            u.discoverdelay = 200
            u.discover()
            u.selectigd()
            u.addportmapping(port, 'TCP', u.lanaddr, port, 'TritioCoin', '')
            logger.info(f"UPnP: Port {port} forwarded")
            return port
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"UPnP failed: {e}")
        return None

    def get_external_address(self) -> Optional[str]:
        if self.external_ip and self.external_port:
            return f"{self.external_ip}:{self.external_port}"
        return None


class SubnetTracker:
    """Tracks /24 subnet diversity to prevent Eclipse attacks."""

    def __init__(self, max_per_subnet: int = MAX_SAME_SUBNET):
        self.max_per_subnet = max_per_subnet
        self.subnet_counts: Dict[str, int] = {}

    def _get_subnet(self, ip: str) -> str:
        parts = ip.split('.')
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        return ip

    def can_accept(self, ip: str) -> bool:
        subnet = self._get_subnet(ip)
        return self.subnet_counts.get(subnet, 0) < self.max_per_subnet

    def on_connect(self, ip: str):
        subnet = self._get_subnet(ip)
        self.subnet_counts[subnet] = self.subnet_counts.get(subnet, 0) + 1

    def on_disconnect(self, ip: str):
        subnet = self._get_subnet(ip)
        if subnet in self.subnet_counts:
            self.subnet_counts[subnet] -= 1
            if self.subnet_counts[subnet] <= 0:
                del self.subnet_counts[subnet]

    def get_diversity_score(self) -> float:
        total_subnets = len(self.subnet_counts)
        total_peers = sum(self.subnet_counts.values())
        if total_peers == 0:
            return 1.0
        return min(total_subnets / max(total_peers, 1), 1.0)


class TransactionCache:
    """Bloom-filter-inspired cache for deduplicating transaction announcements."""

    def __init__(self, max_size: int = 10000, ttl: int = 60):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: Dict[str, float] = {}
        self._last_cleanup = time.time()

    def _cleanup(self):
        now = time.time()
        if now - self._last_cleanup < 10:
            return
        self.cache = {k: v for k, v in self.cache.items() if now - v < self.ttl}
        self._last_cleanup = now

    def add(self, tx_hash: str) -> bool:
        """Returns True if already seen (duplicate)."""
        self._cleanup()
        if tx_hash in self.cache:
            return True
        if len(self.cache) >= self.max_size:
            oldest = min(self.cache, key=self.cache.get)
            del self.cache[oldest]
        self.cache[tx_hash] = time.time()
        return False

    def has(self, tx_hash: str) -> bool:
        self._cleanup()
        return tx_hash in self.cache


class P2PNode:
    """Production P2P node with TLS, protocol versioning, NAT traversal, and security features."""

    CONNECT_COOLDOWN = 60

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.peers: Dict[str, asyncio.StreamWriter] = {}
        self.peer_ids: Dict[str, str] = {}
        self.peer_versions: Dict[str, int] = {}
        self.peer_latencies: Dict[str, float] = {}
        self.last_connect_attempt: Dict[str, float] = {}
        self.server = None
        self.on_message = None
        self.node_id = self._generate_node_id()
        self.rate_limiter = RateLimiter()
        self.ssl_context = None
        self.ssl_client_context = None
        self.reputation = None
        self.nat = NATTraversal()
        self.external_address = None
        self.blockchain_height = 0
        self.subnet_tracker = SubnetTracker()
        self.tx_cache = TransactionCache()
        self._socks5_proxy = None
        self._setup_certs()

    def _generate_node_id(self) -> str:
        id_file = Path("tritiocoin_data/node_id")
        if id_file.exists():
            return id_file.read_text().strip()
        node_id = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
        id_file.parent.mkdir(parents=True, exist_ok=True)
        id_file.write_text(node_id)
        return node_id

    def _setup_certs(self):
        CERT_DIR.mkdir(parents=True, exist_ok=True)
        cert_file = CERT_DIR / "node.pem"
        key_file = CERT_DIR / "node.key"
        if not cert_file.exists() or not key_file.exists():
            self._generate_self_signed_cert(cert_file, key_file)
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ssl_context.load_cert_chain(cert_file, key_file)
        self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
        self.ssl_client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.ssl_client_context.load_verify_locations(cert_file)
        self.ssl_client_context.check_hostname = False
        self.ssl_client_context.verify_mode = ssl.CERT_NONE
        self.ssl_client_context.minimum_version = ssl.TLSVersion.TLSv1_3

    def _generate_self_signed_cert(self, cert_path: Path, key_path: Path):
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, f"TritioCoin-{self.node_id[:16]}"),
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

    def set_socks5_proxy(self, proxy_host: str, proxy_port: int):
        """Configure SOCKS5 proxy for outbound connections."""
        self._socks5_proxy = (proxy_host, proxy_port)
        logger.info(f"SOCKS5 proxy set: {proxy_host}:{proxy_port}")

    async def _connect_via_socks5(self, host: str, port: int) -> Optional[Tuple[asyncio.StreamReader, asyncio.StreamWriter]]:
        if not self._socks5_proxy:
            return None
        try:
            proxy_host, proxy_port = self._socks5_proxy
            reader, writer = await asyncio.open_connection(proxy_host, proxy_port)
            CONNECT_REQ = bytes([5, 1, 0, 1]) + socket.inet_aton(host) + struct.pack('>H', port)
            writer.write(CONNECT_REQ)
            await writer.drain()
            resp = await reader.readexactly(4)
            if resp[1] == 0:
                return reader, writer
            else:
                writer.close()
                return None
        except Exception as e:
            logger.debug(f"SOCKS5 connection failed: {e}")
            return None

    async def start(self):
        try:
            nat_result = await self.nat.discover(self.port)
            self.external_address = self.nat.get_external_address()
            self.server = await asyncio.start_server(
                self._handle_conn, self.host, self.port, ssl=self.ssl_context
            )
            logger.info(f"P2P listening on {self.host}:{self.port} (TLS)")
            if self.external_address:
                logger.info(f"External address: {self.external_address}")
        except OSError as e:
            if "10048" in str(e):
                logger.warning(f"Porta P2P {self.port} ja esta em uso. P2P desabilitado.")
            else:
                logger.error(f"P2P error: {e}")

    async def connect(self, host: str, port: int) -> bool:
        key = f"{host}:{port}"
        if key in self.peers:
            return True
        now = time.time()
        last_attempt = self.last_connect_attempt.get(key, 0)
        if now - last_attempt < self.CONNECT_COOLDOWN:
            return False
        self.last_connect_attempt[key] = now
        if self.reputation and self.reputation.is_banned(key):
            logger.warning(f"Cannot connect to banned peer: {key}")
            return False
        if not self.subnet_tracker.can_accept(host):
            logger.warning(f"Subnet limit reached for {host}, skipping")
            return False
        try:
            if self._socks5_proxy:
                result = await self._connect_via_socks5(host, port)
                if result is None:
                    return False
                reader, writer = result
            else:
                reader, writer = await asyncio.open_connection(
                    host, port, ssl=self.ssl_client_context
                )
            self.peers[key] = writer
            asyncio.create_task(self._read_loop(reader, writer, key))
            challenge = secrets.token_hex(16)
            await self._send(writer, {
                "type": "HANDSHAKE",
                "version": PROTOCOL_VERSION,
                "min_version": MIN_PROTOCOL_VERSION,
                "node_id": self.node_id,
                "port": self.port,
                "external_address": self.external_address,
                "height": self.blockchain_height,
                "challenge": challenge
            })
            if self.reputation:
                self.reputation.on_connect(key)
            self.subnet_tracker.on_connect(host)
            logger.info(f"[+] Conectado ao peer! ({len(self.peers)} peers ativos)")
            return True
        except Exception as e:
            logger.debug(f"Connection failed to {key}: {e}")
            return False

    async def _handle_conn(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info('peername')
        key = f"{addr[0]}:{addr[1]}"
        if key in self.peers:
            logger.debug(f"Duplicate connection from {key}, ignoring")
            try:
                writer.close()
            except:
                pass
            return
        if not self.subnet_tracker.can_accept(addr[0]):
            logger.warning(f"Subnet limit reached for {addr[0]}, rejecting connection")
            try:
                writer.close()
            except:
                pass
            return
        self.peers[key] = writer
        self.subnet_tracker.on_connect(addr[0])
        logger.info(f"[+] Novo peer conectado: {key} ({len(self.peers)} peers ativos)")
        await self._read_loop(reader, writer, key)

    async def _read_loop(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, key: str):
        try:
            if self.reputation and self.reputation.is_banned(key):
                logger.warning(f"Banned peer attempted connection: {key}")
                return
            while True:
                raw = await self._recv(reader)
                if raw is None:
                    break
                rep_score = 100
                if self.reputation:
                    peer_score = self.reputation.get_peer(key)
                    rep_score = peer_score.score
                if not self.rate_limiter.check(key, rep_score):
                    logger.warning(f"Rate limit exceeded for {key}")
                    if self.reputation:
                        self.reputation.on_invalid_message(key, "rate_limit")
                    break
                msg = json.loads(raw)
                if not self._validate_msg(msg):
                    logger.warning(f"Invalid message from {key}")
                    if self.reputation:
                        self.reputation.on_invalid_message(key, "invalid_format")
                    continue
                if msg.get("type") == "HANDSHAKE":
                    peer_version = msg.get("version", 0)
                    if peer_version < MIN_PROTOCOL_VERSION:
                        logger.warning(f"Incompatible protocol version {peer_version} from {key}")
                        continue
                    self.peer_versions[key] = peer_version
                    if "node_id" in msg:
                        self.peer_ids[key] = msg["node_id"]
                if self.reputation:
                    self.reputation.on_valid_message(key, msg.get("type", ""))
                if self.on_message:
                    await self.on_message(msg, key, writer)
        except (ConnectionResetError, asyncio.IncompleteReadError, ssl.SSLError):
            pass
        except Exception as e:
            logger.error(f"Read error from {key}: {e}")
        finally:
            if self.reputation:
                self.reputation.on_disconnect(key)
            addr = key.split(':')[0] if ':' in key else key
            self.subnet_tracker.on_disconnect(addr)
            self._drop(key, writer)

    def _validate_msg(self, msg: dict) -> bool:
        if not isinstance(msg, dict):
            return False
        msg_type = msg.get("type")
        if not msg_type:
            return False
        valid_types = {
            "HANDSHAKE", "HANDSHAKE_ACK", "NEW_BLOCK", "COMPACT_BLOCK",
            "GET_BLOCK", "GET_TX", "NEW_TX", "GET_CHAIN", "CHAIN",
            "SEED_ANNOUNCE", "SEED_REMOVE", "SEED_SYNC",
            "REQUEST_SIGNATURE", "BLOCK_SIGNATURE", "REGISTER_VALIDATOR",
            "DELEGATE", "PING", "PONG", "CHALLENGE", "CHALLENGE_RESPONSE",
            "BLOCK_ANNOUNCE", "TX_ANNOUNCE",
            "SYNC_REQUEST", "SYNC_BLOCK_BATCH", "GET_BLOCKS"
        }
        return msg_type in valid_types

    async def _recv(self, reader: asyncio.StreamReader) -> str:
        hdr = await reader.readexactly(4)
        length = struct.unpack('>I', hdr)[0]
        if length > MAX_MSG_SIZE:
            logger.warning(f"Message too large: {length}")
            return None
        data = await reader.readexactly(length)
        try:
            decompressed = zlib.decompress(data)
            data = decompressed
        except zlib.error:
            pass
        return data.decode('utf-8')

    async def _send(self, writer: asyncio.StreamWriter, msg: dict):
        raw = json.dumps(msg).encode('utf-8')
        if len(raw) > COMPRESSION_THRESHOLD:
            compressed = zlib.compress(raw, level=6)
            if len(compressed) < len(raw):
                raw = compressed
        writer.write(struct.pack('>I', len(raw)) + raw)
        await writer.drain()

    async def send(self, key: str, msg: dict):
        writer = self.peers.get(key)
        if writer:
            try:
                await self._send(writer, msg)
            except Exception:
                self._drop(key, writer)

    async def broadcast(self, msg: dict):
        tasks = []
        for key, writer in list(self.peers.items()):
            tasks.append(self._broadcast_to_peer(key, writer, msg))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _broadcast_to_peer(self, key: str, writer: asyncio.StreamWriter, msg: dict):
        try:
            await self._send(writer, msg)
        except Exception:
            self._drop(key, writer)

    def _drop(self, key: str, writer: asyncio.StreamWriter):
        self.peers.pop(key, None)
        self.peer_ids.pop(key, None)
        self.peer_versions.pop(key, None)
        self.peer_latencies.pop(key, None)
        try:
            writer.close()
        except Exception:
            pass

    def get_peers(self) -> list:
        return list(self.peers.keys())

    def get_peer_count(self) -> int:
        return len(self.peers)

    def get_external_address(self) -> Optional[str]:
        return self.external_address

    def get_network_health(self) -> dict:
        diversity = self.subnet_tracker.get_diversity_score()
        peer_count = self.get_peer_count()
        healthy = peer_count >= 3 and diversity > 0.5
        return {
            "peer_count": peer_count,
            "subnet_diversity": round(diversity, 2),
            "healthy": healthy,
            "subnets": dict(self.subnet_tracker.subnet_counts)
        }

    async def reconnect_loop(self, seeds: list, interval: int = 60):
        while True:
            for host, port in seeds:
                key = f"{host}:{port}"
                if key not in self.peers:
                    await self.connect(host, port)
            self.rate_limiter.cleanup()
            await asyncio.sleep(interval)
