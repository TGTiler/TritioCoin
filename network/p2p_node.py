"""
TritioCoin P2P Network Layer — Production-Grade Implementation
================================================================

Wire Protocol (binary, Little-Endian):
    ┌──────────────┬──────────────┬───────────────┬──────────────┐
    │ Magic (4B)   │ Cmd (12B)    │ Length (4B)   │ Checksum(4B) │  24 bytes total
    └──────────────┴──────────────┴───────────────┴──────────────┘
    │                        Payload (Length bytes)                     │
    └──────────────────────────────────────────────────────────────────┘

Header struct: ``<4s12sII`` (Little-Endian)
- Magic:   b'\\xF9\\xBE\\xB4\\xD9' (4 bytes, reject if mismatch)
- Command: ASCII string, null-padded right to 12 bytes
- Length:  uint32 payload size in bytes
- Checksum: first 4 bytes of SHA256d(payload)

Handshake state machine (per peer):
    TCP connected → send version → receive version → validate →
    send verack → receive verack → CONEXAO_ESTABELECIDA

Keep-alive: ping every 30 s of inactivity; pong must echo nonce within 10 s.
Anti-DoS:   ban_score ≥ 100 → disconnect + blacklist in memory.
Memory cap: payload > 2 MB → immediate disconnect (no read).

Author: TritioCoin Core Team
"""

import asyncio
import hashlib
import json
import logging
import os
import random
import ssl
import struct
import time
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("P2P")

# ═══════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

# Binary wire protocol magic bytes — Bitcoin-derived, unique to TritioCoin.
MAGIC_BYTES: bytes = b'\xF9\xBE\xB4\xD9'

# Header layout: 4s (magic) + 12s (command) + I (payload length) + I (checksum)
# Total: 4 + 12 + 4 + 4 = 24 bytes, Little-Endian.
HEADER_FORMAT: str = '<4s12sII'
HEADER_SIZE: int = struct.calcsize(HEADER_FORMAT)  # 24

# Maximum payload size (2 MiB) — hard cap to prevent memory exhaustion DoS.
MAX_PAYLOAD_SIZE: int = 2 * 1024 * 1024

# Protocol version and minimum supported version.
PROTOCOL_VERSION: int = 70015
MIN_PROTOCOL_VERSION: int = 70001

# Keep-alive: send ping after 30 s of inactivity.
KEEPALIVE_INTERVAL: int = 30
# Pong must arrive within 10 s or the peer is considered dead.
PONG_TIMEOUT: int = 10

# Ban score thresholds (spec §5).
BAN_SCORE_MALFORMED: int = 10   # bad checksum, unknown command, malformed
BAN_SCORE_INVALID_DATA: int = 50  # corrupted block/tx data
BAN_SCORE_THRESHOLD: int = 100   # disconnect + blacklist

# Connection limits.
MAX_PEERS: int = 50
MAX_OUTBOUND: int = 8
MAX_INBOUND: int = 42
MAX_PER_IP: int = 3
CONNECT_COOLDOWN: int = 60      # seconds between reconnection attempts
CONNECT_TIMEOUT: int = 10        # seconds for TCP+TLS connect

# Recv/send timeouts per message.
RECV_TIMEOUT: int = 30

# ═══════════════════════════════════════════════════════════════════════
#  CRYPTO HELPERS
# ═══════════════════════════════════════════════════════════════════════

def sha256d(data: bytes) -> bytes:
    """Double SHA-256: SHA256(SHA256(data)). Used for checksums and PoW."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def payload_checksum(payload: bytes) -> bytes:
    """
    Compute the 4-byte checksum stored in the wire header.

    The checksum is the *first 4 bytes* of SHA256d(payload).
    For messages without payload the checksum is computed over b''.
    """
    return sha256d(payload)[:4]


def make_header(command: str, payload: bytes) -> bytes:
    """
    Build a 24-byte binary header.

    :param command: ASCII command name (max 11 chars, null-padded to 12).
    :param payload: raw payload bytes.
    :returns: 24 bytes ``<4s12sII``.

    The struct format ``<4s12sII`` encodes:
        - ``4s``: 4-byte magic ``b'\\xF9\\xBE\\xB4\\xD9'``
        - ``12s``: null-padded ASCII command string
        - ``I``:  uint32 payload length (Little-Endian)
        - ``I``:  uint32 checksum — first 4 bytes of SHA256d(payload),
                  stored as an unsigned 32-bit integer (Little-Endian).
    """
    cmd_bytes = command.encode('ascii')[:11].ljust(12, b'\x00')
    # Convert 4-byte checksum to uint32 for struct.pack 'I' format.
    cksum_int = int.from_bytes(payload_checksum(payload), 'little')
    return struct.pack(HEADER_FORMAT,
                       MAGIC_BYTES,
                       cmd_bytes,
                       len(payload),
                       cksum_int)


def parse_header(header_bytes: bytes) -> Tuple[bytes, str, int, bytes]:
    """
    Parse a 24-byte header into its four fields.

    :param header_bytes: exactly 24 bytes.
    :returns: (magic, command_str, payload_length, checksum_bytes).
              checksum_bytes is a 4-byte ``bytes`` object for easy
              comparison with ``payload_checksum()``.
    :raises ValueError: if magic bytes don't match.
    """
    magic, cmd_raw, length, cksum_int = struct.unpack(HEADER_FORMAT, header_bytes)
    if magic != MAGIC_BYTES:
        raise ValueError(f"Bad magic: expected {MAGIC_BYTES!r}, got {magic!r}")
    command = cmd_raw.rstrip(b'\x00').decode('ascii')
    # Convert uint32 back to 4-byte bytes for comparison.
    cksum_bytes = cksum_int.to_bytes(4, 'little')
    return magic, command, length, cksum_bytes


# ═══════════════════════════════════════════════════════════════════════
#  RATE LIMITER
# ═══════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Sliding-window per-peer rate limiter."""

    def __init__(self, max_msgs: int = 200, window: int = 10):
        self.max_msgs = max_msgs
        self.window = window
        self._counts: Dict[str, List[float]] = {}

    def check(self, peer: str) -> bool:
        """Return True if the peer is within its message budget."""
        now = time.time()
        timestamps = self._counts.setdefault(peer, [])
        # Prune entries outside the window.
        timestamps[:] = [t for t in timestamps if now - t < self.window]
        if len(timestamps) >= self.max_msgs:
            return False
        timestamps.append(now)
        return True

    def cleanup(self):
        """Drop entries for peers that have been idle beyond the window."""
        now = time.time()
        expired = [p for p, ts in self._counts.items()
                   if all(now - t >= self.window for t in ts)]
        for p in expired:
            del self._counts[p]


# ═══════════════════════════════════════════════════════════════════════
#  HANDSHAKE STATE MACHINE
# ═══════════════════════════════════════════════════════════════════════

class HandshakeState(Enum):
    """
    Per-peer connection state machine.

    For an *outbound* connection the initiator:
        CONNECTING → VERSION_SENT → VERSION_RECEIVED → VERACK_SENT → CONNECTED

    For an *inbound* connection the receiver:
        VERSION_RECEIVED → VERSION_SENT → VERACK_SENT → VERACK_RECEIVED → CONNECTED

    The ``CONNECTED`` state is reached only after both verack messages
    have been exchanged.
    """
    CONNECTING = auto()
    VERSION_SENT = auto()
    VERSION_RECEIVED = auto()
    VERACK_SENT = auto()
    VERACK_RECEIVED = auto()
    CONNECTED = auto()


# ═══════════════════════════════════════════════════════════════════════
#  INVENTORY HELPERS
# ═══════════════════════════════════════════════════════════════════════

# Inventory types for the ``inv`` / ``getdata`` messages.
INV_TX: int = 1
INV_BLOCK: int = 2


# ═══════════════════════════════════════════════════════════════════════
#  PEER SESSION
# ═══════════════════════════════════════════════════════════════════════

class PeerSession:
    """
    Encapsulates a single TCP connection to a peer.

    Manages concurrently:
    - A read loop (packet dispatch).
    - An async write queue with ``writer.drain()``.
    - A keep-alive (ping) task that fires every KEEPALIVE_INTERVAL s.

    Attributes:
        key:             ``"host:port"`` identifier.
        reader:          asyncio.StreamReader for this socket.
        writer:          asyncio.StreamWriter for this socket.
        direction:       ``"outbound"`` or ``"inbound"``.
        state:           Current handshake state.
        remote_version:  Protocol version advertised by the peer.
        remote_nonce:    Nonce from the peer's version message (loopback detection).
        remote_height:   Block height advertised by the peer.
        ban_score:       Accumulated misbehaviour score.
        known_inventory: Set of inventory hashes already announced to this peer.
        last_activity:   Timestamp of the last received message.
        ping_nonce:      Nonce we last sent in a ``ping``; None if no outstanding ping.
    """

    def __init__(self, key: str, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter, direction: str):
        self.key: str = key
        self.reader: asyncio.StreamReader = reader
        self.writer: asyncio.StreamWriter = writer
        self.direction: str = direction  # "outbound" or "inbound"

        # Handshake
        self.state: HandshakeState = (
            HandshakeState.CONNECTING if direction == "outbound"
            else HandshakeState.VERSION_RECEIVED  # inbound waits for remote version first
        )
        self.remote_version: int = 0
        self.remote_nonce: int = 0
        self.remote_height: int = 0
        self.remote_services: int = 0

        # Security
        self.ban_score: int = 0

        # Gossip deduplication
        self.known_inventory: Set[str] = set()

        # Keep-alive
        self.last_activity: float = time.time()
        self.ping_nonce: Optional[int] = None

        # Write queue — serialises concurrent writes.
        self._write_lock: asyncio.Lock = asyncio.Lock()
        self._closed: bool = False

    # ── Low-level I/O ─────────────────────────────────────────────────

    async def send_raw(self, command: str, payload: bytes) -> bool:
        """
        Write a complete framed message (header + payload) to the socket.

        Serialises writes via ``_write_lock`` so concurrent callers never
        interleave their bytes on the wire.

        :returns: True on success, False on I/O error.
        """
        if self._closed:
            return False
        header = make_header(command, payload)
        async with self._write_lock:
            try:
                self.writer.write(header + payload)
                await self.writer.drain()
                return True
            except (ConnectionResetError, BrokenPipeError,
                    asyncio.IncompleteReadError, OSError) as exc:
                logger.debug(f"send_raw failed to {self.key}: {exc}")
                return False

    async def send_version(self, local_height: int, local_nonce: int,
                           local_services: int = 1):
        """
        Pack and send a ``version`` message.

        Payload layout (Little-Endian ``<IQQQI``):
            Protocol Version  (4 bytes, uint32)
            Services          (8 bytes, uint64 bitmask)
            Timestamp         (8 bytes, uint64 Unix epoch)
            Nonce             (8 bytes, uint64 random)
            Block Height      (4 bytes, uint32)
        """
        payload = struct.pack('<IQQQI',
                              PROTOCOL_VERSION,
                              local_services,
                              int(time.time()),
                              local_nonce,
                              local_height)
        return await self.send_raw('version', payload)

    async def send_verack(self):
        """Send a ``verack`` acknowledgement (empty payload)."""
        return await self.send_raw('verack', b'')

    async def send_ping(self, nonce: Optional[int] = None) -> Optional[int]:
        """
        Send a ``ping`` with an 8-byte random nonce (``<Q``).

        Returns the nonce so the caller can match it against the ``pong``.
        """
        if nonce is None:
            nonce = random.getrandbits(64)
        payload = struct.pack('<Q', nonce)
        ok = await self.send_raw('ping', payload)
        return nonce if ok else None

    async def send_pong(self, nonce: int):
        """Echo a ``pong`` with the exact nonce received in the ``ping``."""
        payload = struct.pack('<Q', nonce)
        return await self.send_raw('pong', payload)

    async def send_inv(self, inv_type: int, inv_hash: bytes):
        """
        Send an ``inv`` announcement.

        Payload (``<I32s``):
            Inventory Type  (4 bytes: 1=TX, 2=Block)
            Hash            (32 bytes, SHA-256)
        """
        payload = struct.pack('<I32s', inv_type, inv_hash)
        return await self.send_raw('inv', payload)

    async def send_getdata(self, inv_type: int, inv_hash: bytes):
        """
        Send a ``getdata`` request (same layout as ``inv``).
        """
        payload = struct.pack('<I32s', inv_type, inv_hash)
        return await self.send_raw('getdata', payload)

    async def send_json(self, command: str, data: dict) -> bool:
        """
        Send a message whose payload is a JSON object (UTF-8 encoded).

        Used for complex structures (blocks, transactions, etc.) that don't
        fit neatly into fixed-size binary structs.
        """
        payload = json.dumps(data, separators=(',', ':')).encode('utf-8')
        return await self.send_raw(command, payload)

    # ── Ban scoring ───────────────────────────────────────────────────

    def add_ban_score(self, points: int, reason: str = "") -> bool:
        """
        Add misbehaviour points. Returns True if the peer should be banned
        (score ≥ threshold).
        """
        self.ban_score += points
        if self.ban_score >= BAN_SCORE_THRESHOLD:
            logger.warning(
                f"Banned peer {self.key}: score {self.ban_score} "
                f"(+{points} {reason})")
            return True
        return False

    # ── Activity tracking ─────────────────────────────────────────────

    def touch(self):
        """Update last_activity to now."""
        self.last_activity = time.time()

    def is_inactive(self) -> bool:
        """True if no message received for more than KEEPALIVE_INTERVAL."""
        return (time.time() - self.last_activity) > KEEPALIVE_INTERVAL

    # ── Cleanup ───────────────────────────────────────────────────────

    def close(self):
        """Mark the session as closed and close the writer."""
        if self._closed:
            return
        self._closed = True
        try:
            self.writer.close()
        except Exception:
            pass

    def __repr__(self):
        return (f"PeerSession({self.key!r} dir={self.direction} "
                f"state={self.state.name} ban={self.ban_score})")


# ═══════════════════════════════════════════════════════════════════════
#  NAT TRAVERSAL (unchanged — already production-quality)
# ═══════════════════════════════════════════════════════════════════════

class NATTraversal:
    """UPnP + external IP discovery with fallback."""

    def __init__(self):
        self.external_ip: Optional[str] = None
        self.external_port: Optional[int] = None
        self.upnp_device = None

    async def discover(self, internal_port: int) -> dict:
        result = {"internal_port": internal_port,
                  "external_port": internal_port, "upnp": False}
        try:
            import miniupnpc
            u = miniupnpc.UPnP()
            u.discoverdelay = 200
            u.discover()
            u.selectigd()
            external_ip = u.externalip()
            if external_ip:
                self.external_ip = external_ip
                result["external_ip"] = external_ip
                if u.addportmapping(internal_port, 'TCP',
                                    internal_port, 'UDP', 'TritioCoin P2P'):
                    self.external_port = internal_port
                    self.upnp_device = u
                    result["upnp"] = True
                    return result
        except ImportError:
            pass
        except Exception as exc:
            logger.debug(f"UPnP failed: {exc}")
        try:
            import urllib.request
            response = await asyncio.to_thread(
                urllib.request.urlopen,
                "https://api.ipify.org?format=json", timeout=5)
            import json as _json
            data = _json.loads(response.read().decode())
            self.external_ip = data.get("ip")
            result["external_ip"] = self.external_ip
        except Exception:
            pass
        return result

    def cleanup(self):
        if self.upnp_device:
            try:
                self.upnp_device.deleteportmapping(self.external_port, 'TCP')
            except Exception:
                pass

    def get_external_address(self) -> Optional[str]:
        if self.external_ip and self.external_port:
            return f"{self.external_ip}:{self.external_port}"
        return None


# ═══════════════════════════════════════════════════════════════════════
#  P2P NODE
# ═══════════════════════════════════════════════════════════════════════

class P2PNode:
    """
    Production-grade P2P node with binary wire protocol.

    Public API (backward-compatible with main.py):
        start()                         — bind and listen
        connect(host, port) -> bool     — outbound connection
        send(key, msg_dict)             — send JSON message to one peer
        broadcast(msg_dict)             — send JSON message to all peers
        get_peers() -> list
        get_peer_count() -> int
        get_external_address() -> str|None
        reconnect_loop(seeds, interval) — auto-reconnect coroutine
    """

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

        # Active sessions keyed by "host:port".
        self.sessions: Dict[str, PeerSession] = {}

        # Backward-compat alias — main.py accesses ``self.peers``.
        # Maps key → writer (kept in sync with sessions).
        self.peers: Dict[str, asyncio.StreamWriter] = {}

        # Per-peer metadata kept for compat (main.py reads these).
        self.peer_ids: Dict[str, str] = {}
        self.peer_versions: Dict[str, int] = {}
        self.last_connect_attempt: Dict[str, float] = {}

        self.server: Optional[asyncio.AbstractServer] = None
        self.on_message: Optional[Callable] = None  # async callback
        self.node_id: str = self._generate_node_id()
        self.local_nonce: int = random.getrandbits(64)
        self.blockchain_height: int = 0

        self.rate_limiter = RateLimiter()
        self.ssl_context = None
        self.ssl_client_context = None

        # Reputation (imports lazily to avoid circular deps).
        try:
            from network.reputation import PeerReputation
            self.reputation = PeerReputation(persist=False)
        except Exception:
            self.reputation = None

        self.nat = NATTraversal()
        self.external_address: Optional[str] = None

        # Background tasks.
        self._keepalive_tasks: Dict[str, asyncio.Task] = {}
        self._background_tasks: List[asyncio.Task] = []

        self._setup_certs()

    # ── Identity ──────────────────────────────────────────────────────

    def _generate_node_id(self) -> str:
        id_file = Path("tritiocoin_data/node_id")
        if id_file.exists():
            return id_file.read_text().strip()
        nid = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
        id_file.parent.mkdir(parents=True, exist_ok=True)
        id_file.write_text(nid)
        return nid

    # ── TLS ───────────────────────────────────────────────────────────

    def _setup_certs(self):
        import ssl
        cert_dir = Path("tritiocoin_data/certs")
        cert_dir.mkdir(parents=True, exist_ok=True)
        cert_file = cert_dir / "node.pem"
        key_file = cert_dir / "node.key"
        if not cert_file.exists() or not key_file.exists():
            self._generate_self_signed_cert(cert_file, key_file)

        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ssl_context.load_cert_chain(cert_file, key_file)
        try:
            self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
        except Exception:
            pass

        self.ssl_client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.ssl_client_context.load_verify_locations(cert_file)
        self.ssl_client_context.check_hostname = False
        self.ssl_client_context.verify_mode = ssl.CERT_NONE
        try:
            self.ssl_client_context.minimum_version = ssl.TLSVersion.TLSv1_3
        except Exception:
            pass

    def _generate_self_signed_cert(self, cert_path: Path, key_path: Path):
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME,
                               f"TritioCoin-{self.node_id[:16]}"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow()
                             + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(__import__("ipaddress").IPv4Address("127.0.0.1")),
            ]), critical=False)
            .sign(key, hashes.SHA256()))
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption()))

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self):
        """Bind the inbound listener and start background tasks."""
        try:
            await self.nat.discover(self.port)
            self.external_address = self.nat.get_external_address()
            self.server = await asyncio.start_server(
                self._handle_inbound, self.host, self.port,
                ssl=self.ssl_context)
            logger.info(f"P2P listening on {self.host}:{self.port} (TLS)")
        except OSError as exc:
            if "10048" in str(exc) or "address already in use" in str(exc).lower():
                logger.warning(f"Porta P2P {self.port} ja esta em uso.")
            else:
                logger.error(f"P2P error: {exc}")

    # ── Outbound connection ───────────────────────────────────────────

    async def connect(self, host: str, port: int) -> bool:
        """
        Open an outbound TCP+TLS connection, perform the binary handshake,
        and register a PeerSession on success.
        """
        key = f"{host}:{port}"
        if key in self.sessions:
            return True

        now = time.time()
        last = self.last_connect_attempt.get(key, 0)
        if now - last < CONNECT_COOLDOWN:
            return False
        self.last_connect_attempt[key] = now

        if self.reputation and self.reputation.is_banned(key):
            return False

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port,
                                        ssl=self.ssl_client_context),
                timeout=CONNECT_TIMEOUT)

            session = PeerSession(key, reader, writer, "outbound")
            self._register_session(session)

            # Step 1: send version.
            session.state = HandshakeState.VERSION_SENT
            ok = await session.send_version(self.blockchain_height,
                                            self.local_nonce)
            if not ok:
                self._remove_session(session)
                return False

            # Step 2: wait for remote version.
            version_payload = await self._recv_payload(reader, 'version')
            if version_payload is None:
                self._remove_session(session)
                return False
            if not self._handle_version_payload(session, version_payload):
                self._remove_session(session)
                return False

            # Step 3: send verack.
            session.state = HandshakeState.VERACK_SENT
            ok = await session.send_verack()
            if not ok:
                self._remove_session(session)
                return False

            # Step 4: wait for remote verack.
            await self._recv_payload(reader, 'verack')
            session.state = HandshakeState.CONNECTED
            session.touch()

            logger.info(
                f"[+] Conectado ao peer {key} v{session.remote_version} "
                f"h={session.remote_height} ({len(self.sessions)} ativos)")

            # Start read loop + keep-alive.
            self._start_read_loop(session)
            self._start_keepalive(session)

            if self.reputation:
                self.reputation.on_connect(key)
            return True

        except asyncio.TimeoutError:
            logger.debug(f"Connection timeout to {key}")
            return False
        except Exception as exc:
            logger.debug(f"Connection failed to {key}: {exc}")
            return False

    # ── Inbound connection ────────────────────────────────────────────

    async def _handle_inbound(self, reader: asyncio.StreamReader,
                              writer: asyncio.StreamWriter):
        addr = writer.get_extra_info('peername')
        key = f"{addr[0]}:{addr[1]}"

        if len(self.sessions) >= MAX_PEERS:
            logger.debug(f"Max peers reached, rejecting {key}")
            writer.close()
            return

        ip = addr[0]
        ip_count = sum(1 for s in self.sessions.values()
                       if s.key.split(':')[0] == ip)
        if ip_count >= MAX_PER_IP:
            logger.debug(f"Per-IP limit for {ip}, rejecting {key}")
            writer.close()
            return

        if key in self.sessions:
            writer.close()
            return

        session = PeerSession(key, reader, writer, "inbound")
        self._register_session(session)

        try:
            # Step 1: receive remote version.
            version_payload = await self._recv_payload(reader, 'version')
            if version_payload is None:
                self._remove_session(session)
                return
            if not self._handle_version_payload(session, version_payload):
                self._remove_session(session)
                return

            # Step 2: send our version.
            session.state = HandshakeState.VERSION_SENT
            ok = await session.send_version(self.blockchain_height,
                                            self.local_nonce)
            if not ok:
                self._remove_session(session)
                return

            # Step 3: wait for remote verack.
            await self._recv_payload(reader, 'verack')
            session.state = HandshakeState.VERACK_RECEIVED

            # Step 4: send verack.
            session.state = HandshakeState.VERACK_SENT
            ok = await session.send_verack()
            if not ok:
                self._remove_session(session)
                return

            session.state = HandshakeState.CONNECTED
            session.touch()
            logger.info(
                f"[+] Peer conectado: {key} v{session.remote_version} "
                f"h={session.remote_height} ({len(self.sessions)} ativos)")

            self._start_read_loop(session)
            self._start_keepalive(session)

            if self.reputation:
                self.reputation.on_connect(key)

        except (asyncio.TimeoutError, asyncio.IncompleteReadError,
                ConnectionResetError, OSError) as exc:
            logger.debug(f"Inbound handshake failed with {key}: {exc}")
            self._remove_session(session)
        except Exception as exc:
            logger.error(f"Inbound error for {key}: {exc}")
            self._remove_session(session)

    # ── Version handling ──────────────────────────────────────────────

    def _handle_version_payload(self, session: PeerSession,
                                payload: bytes) -> bool:
        """
        Parse the binary version payload and validate parameters.

        Layout ``<IQQQI``:
            Protocol Version  (4B)
            Services          (8B)
            Timestamp         (8B)
            Nonce             (8B)
            Block Height      (4B)

        Returns True if the version is acceptable.
        """
        if len(payload) != struct.calcsize('<IQQQI'):
            session.add_ban_score(BAN_SCORE_MALFORMED, "bad version size")
            return False

        version, services, timestamp, nonce, height = \
            struct.unpack('<IQQQI', payload)

        # Reject old protocol versions.
        if version < MIN_PROTOCOL_VERSION:
            logger.warning(
                f"Rejecting {session.key}: version {version} "
                f"< minimum {MIN_PROTOCOL_VERSION}")
            return False

        # Self-connection detection via nonce.
        if nonce == self.local_nonce:
            logger.warning(
                f"Self-connection detected with {session.key} (nonce match)")
            return False

        session.remote_version = version
        session.remote_services = services
        session.remote_nonce = nonce
        session.remote_height = height
        session.state = HandshakeState.VERSION_RECEIVED

        self.peer_versions[session.key] = version
        return True

    async def _recv_payload(self, reader: asyncio.StreamReader,
                            expected_cmd: str) -> Optional[bytes]:
        """
        Read one framed message from the socket, validate magic, command,
        and checksum.  Returns the payload bytes or None on error.

        Memory safety: if the declared payload length exceeds MAX_PAYLOAD_SIZE
        the connection is severed *immediately* without reading the payload.
        """
        try:
            header_data = await asyncio.wait_for(
                reader.readexactly(HEADER_SIZE), timeout=RECV_TIMEOUT)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            return None

        try:
            magic, command, length, expected_cksum = parse_header(header_data)
        except ValueError as exc:
            logger.warning(f"Bad header from {session_key(reader)}: {exc}")
            return None

        # Enforce 2 MiB payload limit BEFORE reading payload bytes.
        if length > MAX_PAYLOAD_SIZE:
            logger.warning(
                f"Payload too large ({length} bytes) from "
                f"{session_key(reader)} — disconnecting")
            return None

        if command != expected_cmd:
            logger.warning(
                f"Expected '{expected_cmd}', got '{command}' "
                f"from {session_key(reader)}")
            return None

        if length == 0:
            return b''

        try:
            payload = await asyncio.wait_for(
                reader.readexactly(length), timeout=RECV_TIMEOUT)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            return None

        # Verify checksum.
        actual_cksum = payload_checksum(payload)
        if actual_cksum != expected_cksum:
            logger.warning(
                f"Checksum mismatch from {session_key(reader)}")
            return None

        return payload

    # ── Session registry helpers ──────────────────────────────────────

    def _register_session(self, session: PeerSession):
        """Add a session to the active maps."""
        self.sessions[session.key] = session
        self.peers[session.key] = session.writer

    def _remove_session(self, session: PeerSession):
        """Remove and clean up a session."""
        session.close()
        self.sessions.pop(session.key, None)
        self.peers.pop(session.key, None)
        self.peer_ids.pop(session.key, None)
        self.peer_versions.pop(session.key, None)
        # Cancel keepalive task if any.
        task = self._keepalive_tasks.pop(session.key, None)
        if task and not task.done():
            task.cancel()
        if self.reputation:
            self.reputation.on_disconnect(session.key)

    # ── Read loop ─────────────────────────────────────────────────────

    def _start_read_loop(self, session: PeerSession):
        """Launch a background reader coroutine for the session."""
        task = asyncio.create_task(self._read_loop(session))
        self._background_tasks.append(task)

    async def _read_loop(self, session: PeerSession):
        """
        Continuously read framed messages from a peer and dispatch them.

        Handles the full lifecycle: read → validate checksum → dispatch
        callback → update ban score on errors.  Never raises; always
        cleans up the session in the ``finally`` block.
        """
        try:
            while not session._closed:
                header_data = await asyncio.wait_for(
                    session.reader.readexactly(HEADER_SIZE),
                    timeout=RECV_TIMEOUT)

                try:
                    magic, command, length, expected_cksum = \
                        parse_header(header_data)
                except ValueError:
                    banned = session.add_ban_score(
                        BAN_SCORE_MALFORMED, "bad magic")
                    if banned:
                        break
                    continue

                # Memory protection: disconnect before reading oversized payload.
                if length > MAX_PAYLOAD_SIZE:
                    logger.warning(
                        f"Oversized payload ({length}) from {session.key}")
                    session.add_ban_score(BAN_SCORE_MALFORMED,
                                          "oversized payload")
                    break

                # Read payload.
                payload = b''
                if length > 0:
                    try:
                        payload = await asyncio.wait_for(
                            session.reader.readexactly(length),
                            timeout=RECV_TIMEOUT)
                    except (asyncio.TimeoutError,
                            asyncio.IncompleteReadError):
                        break

                # Verify checksum.
                if payload_checksum(payload) != expected_cksum:
                    banned = session.add_ban_score(
                        BAN_SCORE_MALFORMED, "bad checksum")
                    if banned:
                        break
                    continue

                session.touch()

                # ── Command dispatch ──────────────────────────────
                handled = await self._dispatch(session, command, payload)
                if not handled:
                    banned = session.add_ban_score(
                        BAN_SCORE_MALFORMED,
                        f"unknown command '{command}'")
                    if banned:
                        break

                # Check if dispatch itself triggered a ban (e.g. bad JSON).
                if session.ban_score >= BAN_SCORE_THRESHOLD:
                    break

        except asyncio.CancelledError:
            pass
        except (ConnectionResetError, asyncio.IncompleteReadError,
                ssl.SSLError):
            pass
        except Exception as exc:
            logger.error(f"Read loop error for {session.key}: {exc}")
        finally:
            self._remove_session(session)

    # ── Command dispatch ──────────────────────────────────────────────

    async def _dispatch(self, session: PeerSession, command: str,
                        payload: bytes) -> bool:
        """
        Route an incoming message to the appropriate handler.

        Returns True if the command was recognised and handled.
        """
        # ── Handshake commands ───────────────────────────────────
        if command == 'version':
            return await self._on_version(session, payload)
        if command == 'verack':
            return await self._on_verack(session)
        if command == 'ping':
            return await self._on_ping(session, payload)
        if command == 'pong':
            return await self._on_pong(session, payload)

        # ── All other commands require a completed handshake ─────
        if session.state != HandshakeState.CONNECTED:
            logger.debug(
                f"Ignoring '{command}' from {session.key} "
                f"(handshake incomplete)")
            return True  # Don't ban — handshake in progress.

        # ── Inventory protocol ───────────────────────────────────
        if command == 'inv':
            return await self._on_inv(session, payload)
        if command == 'getdata':
            return await self._on_getdata(session, payload)

        # ── JSON-encoded commands (backward-compatible) ──────────
        try:
            msg = json.loads(payload.decode('utf-8')) if payload else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            session.add_ban_score(BAN_SCORE_MALFORMED, "bad JSON payload")
            return True

        # Delegate to the registered callback (main.py's _on_msg).
        if self.on_message:
            await self.on_message(msg, session.key, session.writer)

        if self.reputation:
            self.reputation.on_valid_message(session.key,
                                             msg.get("type", command))
        return True

    # ── Handshake command handlers ────────────────────────────────────

    async def _on_version(self, session: PeerSession,
                          payload: bytes) -> bool:
        """Handle an incoming ``version`` message."""
        if not self._handle_version_payload(session, payload):
            session.close()
            return True
        return True

    async def _on_verack(self, session: PeerSession) -> bool:
        """Handle an incoming ``verack`` message."""
        if session.state == HandshakeState.VERACK_SENT:
            session.state = HandshakeState.CONNECTED
            logger.debug(f"Handshake completed with {session.key}")
        elif session.state != HandshakeState.CONNECTED:
            session.state = HandshakeState.VERACK_RECEIVED
        return True

    async def _on_ping(self, session: PeerSession,
                       payload: bytes) -> bool:
        """
        Handle a ``ping``: extract the 8-byte nonce (``<Q``) and reply
        with an identical ``pong``.
        """
        if len(payload) != struct.calcsize('<Q'):
            session.add_ban_score(BAN_SCORE_MALFORMED, "bad ping size")
            return True
        nonce, = struct.unpack('<Q', payload)
        await session.send_pong(nonce)
        return True

    async def _on_pong(self, session: PeerSession,
                       payload: bytes) -> bool:
        """
        Handle a ``pong``: verify the echoed nonce matches our outstanding
        ``ping_nonce``.
        """
        if len(payload) != struct.calcsize('<Q'):
            session.add_ban_score(BAN_SCORE_MALFORMED, "bad pong size")
            return True
        nonce, = struct.unpack('<Q', payload)
        if session.ping_nonce is not None and nonce != session.ping_nonce:
            session.add_ban_score(BAN_SCORE_MALFORMED, "pong nonce mismatch")
            return True
        session.ping_nonce = None  # Mark ping as answered.
        return True

    # ── Inventory protocol handlers ───────────────────────────────────

    async def _on_inv(self, session: PeerSession,
                      payload: bytes) -> bool:
        """
        Handle an ``inv`` announcement.

        Payload ``<I32s``:  inventory type (4B) + hash (32B).
        If we don't have the item, reply with ``getdata``.
        """
        if len(payload) != struct.calcsize('<I32s'):
            session.add_ban_score(BAN_SCORE_MALFORMED, "bad inv size")
            return True
        inv_type, inv_hash = struct.unpack('<I32s', payload)
        inv_hash_hex = inv_hash.hex()

        if inv_hash_hex in session.known_inventory:
            return True  # Already announced — ignore.
        session.known_inventory.add(inv_hash_hex)

        # Delegate to gossip layer (if present) via JSON callback.
        if self.on_message:
            type_name = "tx" if inv_type == INV_TX else "block"
            msg = {"type": "INV", "inv_type": type_name,
                   "hash": inv_hash_hex, "raw_inv_type": inv_type,
                   "raw_hash": inv_hash}
            await self.on_message(msg, session.key, session.writer)
        return True

    async def _on_getdata(self, session: PeerSession,
                          payload: bytes) -> bool:
        """
        Handle a ``getdata`` request.  Same layout as ``inv``.
        Delegate to the on_message callback so the application layer
        can respond with the full block/tx.
        """
        if len(payload) != struct.calcsize('<I32s'):
            session.add_ban_score(BAN_SCORE_MALFORMED, "bad getdata size")
            return True
        inv_type, inv_hash = struct.unpack('<I32s', payload)
        inv_hash_hex = inv_hash.hex()

        if self.on_message:
            type_name = "tx" if inv_type == INV_TX else "block"
            msg = {"type": "GETDATA", "inv_type": type_name,
                   "hash": inv_hash_hex, "raw_inv_type": inv_type,
                   "raw_hash": inv_hash}
            await self.on_message(msg, session.key, session.writer)
        return True

    # ── Keep-alive ────────────────────────────────────────────────────

    def _start_keepalive(self, session: PeerSession):
        """Launch a periodic ping task for the session."""
        task = asyncio.create_task(self._keepalive_loop(session))
        self._keepalive_tasks[session.key] = task

    async def _keepalive_loop(self, session: PeerSession):
        """
        Every KEEPALIVE_INTERVAL seconds of inactivity, send a ``ping``.
        If the peer doesn't respond within PONG_TIMEOUT, disconnect.
        """
        try:
            while not session._closed:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                if session._closed:
                    break

                if session.is_inactive():
                    nonce = await session.send_ping()
                    if nonce is not None:
                        session.ping_nonce = nonce
                        # Wait for pong.
                        await asyncio.sleep(PONG_TIMEOUT)
                        if session.ping_nonce is not None:
                            logger.warning(
                                f"Pong timeout from {session.key}")
                            break
                else:
                    # Activity seen — send a proactive ping to confirm liveness.
                    nonce = await session.send_ping()
                    if nonce is not None:
                        session.ping_nonce = nonce
                        await asyncio.sleep(PONG_TIMEOUT)
                        if session.ping_nonce is not None:
                            logger.warning(
                                f"Pong timeout from {session.key}")
                            break
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug(f"Keepalive error for {session.key}: {exc}")
        finally:
            if not session._closed:
                self._remove_session(session)

    # ── Public send API (backward-compatible) ─────────────────────────

    async def send(self, key: str, msg: dict):
        """
        Send a JSON-encoded message to a specific peer.

        This is the primary interface used by main.py and gossip.py.
        The message dict is serialised as JSON and wrapped in the binary
        wire protocol with a ``json`` command.
        """
        session = self.sessions.get(key)
        if not session or session._closed:
            return
        ok = await session.send_json('json', msg)
        if not ok:
            self._remove_session(session)

    async def broadcast(self, msg: dict):
        """
        Send a JSON-encoded message to every connected peer.
        Failed sends silently remove the dead peer.
        """
        dead: List[str] = []
        for key in list(self.sessions.keys()):
            session = self.sessions.get(key)
            if not session or session._closed:
                dead.append(key)
                continue
            ok = await session.send_json('json', msg)
            if not ok:
                dead.append(key)
        for k in dead:
            session = self.sessions.get(k)
            if session:
                self._remove_session(session)

    # ── Backward-compatible helpers ───────────────────────────────────

    def get_peers(self) -> list:
        return list(self.sessions.keys())

    def get_peer_count(self) -> int:
        return len(self.sessions)

    def get_external_address(self) -> Optional[str]:
        return self.external_address

    async def reconnect_loop(self, seeds: list, interval: int = 60):
        """Periodically attempt to reconnect to known seeds."""
        while True:
            for host, port in seeds:
                key = f"{host}:{port}"
                if key not in self.sessions:
                    try:
                        await asyncio.wait_for(
                            self.connect(host, port), timeout=CONNECT_TIMEOUT)
                    except asyncio.TimeoutError:
                        pass
            self.rate_limiter.cleanup()
            await asyncio.sleep(interval)


# ═══════════════════════════════════════════════════════════════════════
#  UTILITY
# ═══════════════════════════════════════════════════════════════════════

def session_key(reader: asyncio.StreamReader) -> str:
    """Extract 'host:port' from a stream reader's transport."""
    sock = reader._transport.get_extra_info('peername')
    if sock:
        return f"{sock[0]}:{sock[1]}"
    return "unknown"
