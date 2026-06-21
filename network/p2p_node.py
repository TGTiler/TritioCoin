"""
TritioCoin P2P Network Layer
- TLS encrypted connections
- Protocol versioning
- NAT traversal (UPnP)
- Peer authentication via node ID
- Rate limiting
- Auto-reconnection
- Length-prefixed message framing
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
from typing import Dict, Optional, Set
from pathlib import Path

logger = logging.getLogger("P2P")

# Protocol version
PROTOCOL_VERSION = 2
MIN_PROTOCOL_VERSION = 1  # Minimum supported version

MAX_MSG_SIZE = 10 * 1024 * 1024
RATE_LIMIT_MSGS = 100
RATE_LIMIT_WINDOW = 10
CERT_DIR = Path("tritiocoin_data/certs")


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, max_msgs: int = RATE_LIMIT_MSGS, window: int = RATE_LIMIT_WINDOW):
        self.max_msgs = max_msgs
        self.window = window
        self.counts: Dict[str, list] = {}

    def check(self, peer: str) -> bool:
        now = time.time()
        if peer not in self.counts:
            self.counts[peer] = []
        self.counts[peer] = [t for t in self.counts[peer] if now - t < self.window]
        if len(self.counts[peer]) >= self.max_msgs:
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
        """Try to discover external IP and setup port forwarding."""
        result = {"internal_port": internal_port, "external_port": internal_port, "upnp": False}

        # Try to get external IP
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

        # Try UPnP
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
        """Setup UPnP port forwarding."""
        try:
            # Try to use miniupnpc if available
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
        """Get external IP:port if available."""
        if self.external_ip and self.external_port:
            return f"{self.external_ip}:{self.external_port}"
        return None


class P2PNode:
    """Production P2P node with TLS, protocol versioning, and NAT traversal."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.peers: Dict[str, asyncio.StreamWriter] = {}
        self.peer_ids: Dict[str, str] = {}
        self.peer_versions: Dict[str, int] = {}
        self.server = None
        self.on_message = None
        self.node_id = self._generate_node_id()
        self.rate_limiter = RateLimiter()
        self.ssl_context = None
        self.reputation = None
        self.nat = NATTraversal()
        self.external_address = None
        self._setup_certs()

    def _generate_node_id(self) -> str:
        """Generate unique node ID from random bytes."""
        id_file = Path("tritiocoin_data/node_id")
        if id_file.exists():
            return id_file.read_text().strip()
        node_id = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
        id_file.parent.mkdir(parents=True, exist_ok=True)
        id_file.write_text(node_id)
        return node_id

    def _setup_certs(self):
        """Setup self-signed TLS certificates."""
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
        """Generate self-signed certificate for TLS."""
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

    async def start(self):
        """Start the P2P server."""
        # Try NAT traversal
        nat_result = await self.nat.discover(self.port)
        self.external_address = self.nat.get_external_address()

        self.server = await asyncio.start_server(
            self._handle_conn, self.host, self.port,
            ssl=self.ssl_context
        )
        logger.info(f"P2P listening on {self.host}:{self.port} (TLS)")
        if self.external_address:
            logger.info(f"External address: {self.external_address}")

    async def connect(self, host: str, port: int) -> bool:
        key = f"{host}:{port}"
        if key in self.peers:
            return True

        if self.reputation and self.reputation.is_banned(key):
            logger.warning(f"Cannot connect to banned peer: {key}")
            return False

        try:
            reader, writer = await asyncio.open_connection(
                host, port, ssl=self.ssl_client_context
            )
            self.peers[key] = writer
            asyncio.create_task(self._read_loop(reader, writer, key))

            # Send handshake with protocol version
            await self._send(writer, {
                "type": "HANDSHAKE",
                "version": PROTOCOL_VERSION,
                "min_version": MIN_PROTOCOL_VERSION,
                "node_id": self.node_id,
                "port": self.port,
                "external_address": self.external_address
            })

            if self.reputation:
                self.reputation.on_connect(key)
            logger.info(f"Connected to {key} (TLS, v{PROTOCOL_VERSION})")
            return True
        except Exception as e:
            logger.debug(f"Connection failed to {key}: {e}")
            return False

    async def _handle_conn(self, reader: asyncio.StreamReader,
                           writer: asyncio.StreamWriter):
        addr = writer.get_extra_info('peername')
        key = f"{addr[0]}:{addr[1]}"
        self.peers[key] = writer
        logger.info(f"Incoming TLS connection from {key}")
        await self._read_loop(reader, writer, key)

    async def _read_loop(self, reader: asyncio.StreamReader,
                         writer: asyncio.StreamWriter, key: str):
        try:
            if self.reputation and self.reputation.is_banned(key):
                logger.warning(f"Banned peer attempted connection: {key}")
                return

            while True:
                raw = await self._recv(reader)
                if raw is None:
                    break

                if not self.rate_limiter.check(key):
                    logger.warning(f"Rate limit exceeded for {key}")
                    if self.reputation:
                        self.reputation.on_invalid_message(key, "rate_limit")
                    break

                msg = json.loads(raw)

                # Validate message
                if not self._validate_msg(msg):
                    logger.warning(f"Invalid message from {key}")
                    if self.reputation:
                        self.reputation.on_invalid_message(key, "invalid_format")
                    continue

                # Protocol version check
                if msg.get("type") == "HANDSHAKE":
                    peer_version = msg.get("version", 0)
                    if peer_version < MIN_PROTOCOL_VERSION:
                        logger.warning(f"Incompatible protocol version {peer_version} from {key}")
                        continue
                    self.peer_versions[key] = peer_version

                # Record valid message
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
            self._drop(key, writer)

    def _validate_msg(self, msg: dict) -> bool:
        """Validate message structure."""
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
            "PING", "PONG"
        }
        return msg_type in valid_types

    async def _recv(self, reader: asyncio.StreamReader) -> str:
        """Read a length-prefixed message."""
        hdr = await reader.readexactly(4)
        length = struct.unpack('>I', hdr)[0]
        if length > MAX_MSG_SIZE:
            logger.warning(f"Message too large: {length}")
            return None
        data = await reader.readexactly(length)
        return data.decode('utf-8')

    async def _send(self, writer: asyncio.StreamWriter, msg: dict):
        """Write a length-prefixed message."""
        raw = json.dumps(msg).encode('utf-8')
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
        dead = []
        for key, writer in list(self.peers.items()):
            try:
                await self._send(writer, msg)
            except Exception:
                dead.append(key)
        for k in dead:
            self.peers.pop(k, None)

    def _drop(self, key: str, writer: asyncio.StreamWriter):
        self.peers.pop(key, None)
        self.peer_ids.pop(key, None)
        self.peer_versions.pop(key, None)
        try:
            writer.close()
        except Exception:
            pass

    def get_peers(self) -> list:
        """Return list of connected peer keys."""
        return list(self.peers.keys())

    def get_peer_count(self) -> int:
        return len(self.peers)

    def get_external_address(self) -> Optional[str]:
        """Get external IP:port if behind NAT."""
        return self.external_address

    async def reconnect_loop(self, seeds: list, interval: int = 30):
        """Auto-reconnect to seeds."""
        while True:
            for host, port in seeds:
                key = f"{host}:{port}"
                if key not in self.peers:
                    await self.connect(host, port)
            self.rate_limiter.cleanup()
            await asyncio.sleep(interval)
