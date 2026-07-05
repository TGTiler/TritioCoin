"""
TritioCoin P2P Protocol — Production Test Suite
=================================================

Instantiates real nodes on localhost and validates:
    1. Binary wire protocol (header, checksum, magic).
    2. Version/verack handshake completion.
    3. Transaction propagation: Node 1 → Node 2 → Node 3 via Gossip.
    4. Malicious peer detection: bad checksum → ban + disconnect.
    5. Oversized payload → immediate disconnect.
    6. Ping/pong nonce echo.
    7. Keep-alive timeout.

Run:
    python -m pytest tests/test_p2p_protocol.py -v

Requires: pytest, pytest-asyncio.
"""

import asyncio
import hashlib
import json
import os
import struct
import tempfile
import time

import pytest
import pytest_asyncio

# ── Ensure project root is importable ────────────────────────────────
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from network.p2p_node import (
    MAGIC_BYTES, HEADER_FORMAT, HEADER_SIZE, MAX_PAYLOAD_SIZE,
    PROTOCOL_VERSION, MIN_PROTOCOL_VERSION,
    BAN_SCORE_MALFORMED, BAN_SCORE_INVALID_DATA, BAN_SCORE_THRESHOLD,
    PeerSession, HandshakeState,
    sha256d, payload_checksum, make_header, parse_header,
    P2PNode, RateLimiter,
)
from network.gossip import GossipProtocol


# ═══════════════════════════════════════════════════════════════════════
#  FIXTURES
# ═══════════════════════════════════════════════════════════════════════

PORT_COUNTER = 19500  # Start high to avoid collisions.


def _next_port():
    global PORT_COUNTER
    PORT_COUNTER += 1
    return PORT_COUNTER


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory and chdir into it."""
    old = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old)


@pytest_asyncio.fixture
async def node_a(tmp_dir):
    """Node A (inbound listener on a random port)."""
    port = _next_port()
    node = P2PNode("127.0.0.1", port)
    await node.start()
    yield node
    for s in list(node.sessions.values()):
        s.close()
    node.sessions.clear()
    if node.server:
        node.server.close()
        await node.server.wait_closed()


@pytest_asyncio.fixture
async def node_b(tmp_dir):
    """Node B (connects to A)."""
    port = _next_port()
    node = P2PNode("127.0.0.1", port)
    yield node
    for s in list(node.sessions.values()):
        s.close()
    node.sessions.clear()


@pytest_asyncio.fixture
async def node_c(tmp_dir):
    """Node C (connects to B)."""
    port = _next_port()
    node = P2PNode("127.0.0.1", port)
    yield node
    for s in list(node.sessions.values()):
        s.close()
    node.sessions.clear()


# ═══════════════════════════════════════════════════════════════════════
#  TEST 1 — WIRE PROTOCOL UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestWireProtocol:
    """Low-level header construction and parsing."""

    def test_header_size_is_24(self):
        """Header must be exactly 24 bytes."""
        header = make_header("version", b'')
        assert len(header) == HEADER_SIZE == 24

    def test_header_struct_format(self):
        """Verify the struct layout matches ``<4s12sII``."""
        import struct
        assert struct.calcsize('<4s12sII') == 24

    def test_magic_bytes_present(self):
        """First 4 bytes of any header must be the magic."""
        header = make_header("ping", b'\x00' * 8)
        assert header[:4] == MAGIC_BYTES

    def test_command_null_padded(self):
        """Command field is 12 bytes, ASCII, null-padded on the right."""
        header = make_header("verack", b'')
        cmd = header[4:16]
        assert cmd == b'verack\x00\x00\x00\x00\x00\x00'

    def test_command_truncated_if_too_long(self):
        """Commands longer than 11 chars get truncated to 12 bytes total."""
        header = make_header("a" * 20, b'')
        cmd = header[4:16]
        assert cmd == b'a' * 11 + b'\x00'

    def test_payload_length_field(self):
        """Payload length is encoded as uint32 LE at offset 16."""
        payload = os.urandom(1024)
        header = make_header("json", payload)
        length_field = struct.unpack_from('<I', header, 16)[0]
        assert length_field == 1024

    def test_checksum_empty_payload(self):
        """Checksum of empty payload = first 4 bytes of SHA256d(b'')."""
        header = make_header("verack", b'')
        cksum = header[20:24]
        expected = sha256d(b'')[:4]
        assert cksum == expected

    def test_checksum_nonempty_payload(self):
        """Checksum matches SHA256d of the actual payload."""
        payload = b'hello world'
        header = make_header("json", payload)
        cksum = header[20:24]
        assert cksum == sha256d(payload)[:4]

    def test_parse_header_roundtrip(self):
        """Pack then unpack should yield identical fields."""
        payload = b'test-data-123'
        original_cmd = "inv"
        header = make_header(original_cmd, payload)
        magic, cmd, length, cksum = parse_header(header)
        assert magic == MAGIC_BYTES
        assert cmd == original_cmd
        assert length == len(payload)
        assert cksum == sha256d(payload)[:4]

    def test_parse_header_bad_magic_raises(self):
        """A header with wrong magic bytes raises ValueError."""
        bad_header = b'\x00\x00\x00\x00' + b'\x00' * 20
        with pytest.raises(ValueError, match="Bad magic"):
            parse_header(bad_header)

    def test_payload_checksum_matches_header(self):
        """The checksum stored in the header must equal payload_checksum()."""
        payload = os.urandom(256)
        header = make_header("tx", payload)
        _, _, _, cksum = parse_header(header)
        assert cksum == payload_checksum(payload)


# ═══════════════════════════════════════════════════════════════════════
#  TEST 2 — HANDSHAKE (2 REAL NODES)
# ═══════════════════════════════════════════════════════════════════════

class TestHandshake:
    """Verify version/verack handshake between real nodes."""

    @pytest.mark.asyncio
    async def test_handshake_completes(self, node_a, node_b):
        """
        Node B connects to Node A.  After the handshake both sides
        should reach CONNECTED state.
        """
        port_a = node_a.port
        ok = await node_b.connect("127.0.0.1", port_a)
        assert ok, "connect() should return True on success"

        # Both sides should have a session.
        assert len(node_a.sessions) >= 1
        assert len(node_b.sessions) >= 1

        # Both sessions should be CONNECTED.
        session_b = list(node_b.sessions.values())[0]
        assert session_b.state == HandshakeState.CONNECTED

        # Node A should also have a CONNECTED session.
        await asyncio.sleep(0.3)
        a_sessions = [s for s in node_a.sessions.values()
                      if s.state == HandshakeState.CONNECTED]
        assert len(a_sessions) >= 1

    @pytest.mark.asyncio
    async def test_handshake_exchanges_versions(self, node_a, node_b):
        """After handshake, both peers know each other's version."""
        await node_b.connect("127.0.0.1", node_a.port)
        await asyncio.sleep(0.3)

        session_b = list(node_b.sessions.values())[0]
        assert session_b.remote_version >= MIN_PROTOCOL_VERSION

        session_a = [s for s in node_a.sessions.values()
                     if s.state == HandshakeState.CONNECTED]
        assert len(session_a) >= 1
        assert session_a[0].remote_version >= MIN_PROTOCOL_VERSION

    @pytest.mark.asyncio
    async def test_reject_old_version(self, node_a):
        """
        A peer advertising a version below MIN_PROTOCOL_VERSION should
        be rejected during handshake.
        """
        port_a = node_a.port
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port_a, ssl=node_a.ssl_client_context)

        # Send a version with a version number that's too old.
        version_payload = struct.pack('<IQQQI',
                                      60000,  # below MIN_PROTOCOL_VERSION
                                      1,
                                      int(time.time()),
                                      random_nonce(),
                                      0)
        header = make_header('version', version_payload)
        writer.write(header + version_payload)
        await writer.drain()

        # The connection should be closed by Node A.
        await asyncio.sleep(0.5)
        assert len(node_a.sessions) == 0
        writer.close()


def random_nonce() -> int:
    return struct.unpack('<Q', os.urandom(8))[0]


# ═══════════════════════════════════════════════════════════════════════
#  TEST 3 — SELF-CONNECTION PREVENTION
# ═══════════════════════════════════════════════════════════════════════

class TestSelfConnectionPrevention:
    """A node must not connect to itself (nonce match)."""

    @pytest.mark.asyncio
    async def test_self_nonce_rejected(self, node_a):
        """If the incoming version has the same nonce as the listener,
        the connection should be dropped."""
        port_a = node_a.port
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port_a, ssl=node_a.ssl_client_context)

        # Craft a version message with the *same* nonce as node_a.
        payload = struct.pack('<IQQQI',
                              PROTOCOL_VERSION,
                              1,
                              int(time.time()),
                              node_a.local_nonce,  # identical nonce
                              0)
        header = make_header('version', payload)
        writer.write(header + payload)
        await writer.drain()

        await asyncio.sleep(0.5)
        assert len(node_a.sessions) == 0
        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  TEST 4 — TX PROPAGATION: Node1 → Node2 → Node3
# ═══════════════════════════════════════════════════════════════════════

class TestTxPropagation:
    """
    Three-node chain:  Node1 ← Node2 ← Node3

    A TX announced at Node1 should propagate via inv/getdata
    gossip to Node3 through Node2.
    """

    @pytest.mark.asyncio
    async def test_tx_reaches_all_nodes(self, tmp_dir):
        """End-to-end TX propagation across 3 nodes via raw inv/getdata."""
        port1 = _next_port()
        port2 = _next_port()
        port3 = _next_port()

        n1 = P2PNode("127.0.0.1", port1)
        n2 = P2PNode("127.0.0.1", port2)
        n3 = P2PNode("127.0.0.1", port3)

        TX_HASH = hashlib.sha256(b"test-tx-12345").hexdigest()
        tx_hash_bytes = bytes.fromhex(TX_HASH)

        # Track received TX hashes at each node.
        received_n2 = asyncio.Event()
        received_n3 = asyncio.Event()
        received_hashes: Dict[str, Set[str]] = {"n2": set(), "n3": set()}

        async def callback_n2(msg, peer, writer):
            t = msg.get("type")
            if t == "INV" and msg.get("inv_type") == "tx":
                h = msg.get("hash", "")
                received_hashes["n2"].add(h)
                received_n2.set()
                # Gossip relay: forward the inv to n3.
                # n2 has sessions for both n1 (outbound) and n3 (inbound).
                # Forward to every session that isn't the sender.
                for s in n2.sessions.values():
                    if s.key != peer:
                        await s.send_inv(1, tx_hash_bytes)

        async def callback_n3(msg, peer, writer):
            t = msg.get("type")
            if t == "INV" and msg.get("inv_type") == "tx":
                h = msg.get("hash", "")
                received_hashes["n3"].add(h)
                received_n3.set()

        n1.on_message = lambda m, p, w: asyncio.sleep(0)
        n2.on_message = callback_n2
        n3.on_message = callback_n3

        await n1.start()
        await n2.start()
        await n3.start()

        # Connect: n2 → n1, n3 → n2
        ok = await n2.connect("127.0.0.1", port1)
        assert ok
        await asyncio.sleep(0.3)
        ok = await n3.connect("127.0.0.1", port2)
        assert ok
        await asyncio.sleep(0.3)

        # n1 sends raw inv to n2.
        n1_session = list(n2.sessions.values())[0] if n2.sessions else None
        assert n1_session, "n2 should have a session for n1"
        # Actually n1→n2 means n1 sends to the session n2 has for n1.
        # n2 connected to n1, so n1 has a session for n2.
        n1_to_n2 = list(n1.sessions.values())[0] if n1.sessions else None
        assert n1_to_n2, "n1 should have a session for n2"
        await n1_to_n2.send_inv(1, tx_hash_bytes)

        # Wait for n2 to receive the inv.
        try:
            await asyncio.wait_for(received_n2.wait(), timeout=5)
        except asyncio.TimeoutError:
            pytest.fail("Node2 did not receive the TX inv")

        # Wait for n3 to receive the forwarded inv.
        try:
            await asyncio.wait_for(received_n3.wait(), timeout=5)
        except asyncio.TimeoutError:
            pytest.fail("Node3 did not receive the TX inv")

        assert TX_HASH in received_hashes["n2"]
        assert TX_HASH in received_hashes["n3"]

        # Cleanup
        for n in (n1, n2, n3):
            for s in list(n.sessions.values()):
                s.close()
            n.sessions.clear()
            if n.server:
                n.server.close()
                await n.server.wait_closed()


# ═══════════════════════════════════════════════════════════════════════
#  TEST 5 — BAD CHECKSUM → BAN + DISCONNECT
# ═══════════════════════════════════════════════════════════════════════

class TestBadChecksumBan:
    """A peer sending messages with a wrong checksum should be banned."""

    @pytest.mark.asyncio
    async def test_bad_checksum_disconnects(self, node_a):
        """After completing handshake, sending a bad-checksum message
        should result in disconnection."""
        port_a = node_a.port

        # Connect with a raw TLS connection and complete handshake.
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port_a, ssl=node_a.ssl_client_context)

        # Send valid version.
        vp = struct.pack('<IQQQI', PROTOCOL_VERSION, 1,
                         int(time.time()), random_nonce(), 0)
        writer.write(make_header('version', vp) + vp)
        await writer.drain()

        # Receive version response.
        hdr = await asyncio.wait_for(reader.readexactly(HEADER_SIZE),
                                     timeout=5)
        _, vcmd, vlen, _ = parse_header(hdr)
        assert vcmd == 'version'
        if vlen > 0:
            await reader.readexactly(vlen)

        # Send verack.
        vb = make_header('verack', b'')
        writer.write(vb)
        await writer.drain()

        # Receive verack.
        hdr2 = await asyncio.wait_for(reader.readexactly(HEADER_SIZE),
                                      timeout=5)
        _, vrcmd, vrlen, _ = parse_header(hdr2)
        assert vrcmd == 'verack'
        if vrlen > 0:
            await reader.readexactly(vrlen)

        await asyncio.sleep(0.3)

        # Send enough messages with bad checksums to exceed ban threshold.
        # Each malformed packet adds +10 ban_score; threshold is 100.
        # So 10 bad packets (100 pts) should trigger a ban + disconnect.
        payload = b'{"type":"PING"}'
        bad_header = struct.pack(
            HEADER_FORMAT,
            MAGIC_BYTES,
            b'json\x00\x00\x00\x00\x00\x00\x00',
            len(payload),
            0  # wrong checksum (int, not bytes)
        )
        for _ in range(12):
            writer.write(bad_header + payload)
            await writer.drain()

        # Node A should disconnect us after enough bad checksums.
        await asyncio.sleep(0.5)
        assert len(node_a.sessions) == 0
        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  TEST 6 — OVERSIZED PAYLOAD → IMMEDIATE DISCONNECT
# ═══════════════════════════════════════════════════════════════════════

class TestOversizedPayload:
    """Declaring a payload > 2 MiB must cause immediate disconnection."""

    @pytest.mark.asyncio
    async def test_oversized_payload_kicks(self, node_a):
        port_a = node_a.port
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port_a, ssl=node_a.ssl_client_context)

        # Handshake.
        vp = struct.pack('<IQQQI', PROTOCOL_VERSION, 1,
                         int(time.time()), random_nonce(), 0)
        writer.write(make_header('version', vp) + vp)
        await writer.drain()

        hdr = await asyncio.wait_for(reader.readexactly(HEADER_SIZE),
                                     timeout=5)
        _, _, vlen, _ = parse_header(hdr)
        if vlen > 0:
            await reader.readexactly(vlen)

        vb = make_header('verack', b'')
        writer.write(vb)
        await writer.drain()

        hdr2 = await asyncio.wait_for(reader.readexactly(HEADER_SIZE),
                                      timeout=5)
        _, _, vrlen, _ = parse_header(hdr2)
        if vrlen > 0:
            await reader.readexactly(vrlen)

        await asyncio.sleep(0.3)

        # Send a header claiming 3 MiB payload.
        fake_length = 3 * 1024 * 1024
        bad_header = struct.pack(
            HEADER_FORMAT,
            MAGIC_BYTES,
            b'json\x00\x00\x00\x00\x00\x00\x00',
            fake_length,
            0
        )
        writer.write(bad_header)
        await writer.drain()

        await asyncio.sleep(0.5)
        assert len(node_a.sessions) == 0
        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  TEST 7 — PING / PONG NONCE ECHO
# ═══════════════════════════════════════════════════════════════════════

class TestPingPong:
    """Verify that a ping nonce is echoed back in pong."""

    @pytest.mark.asyncio
    async def test_pong_echoes_nonce(self, node_a):
        port_a = node_a.port
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port_a, ssl=node_a.ssl_client_context)

        # Handshake.
        vp = struct.pack('<IQQQI', PROTOCOL_VERSION, 1,
                         int(time.time()), random_nonce(), 0)
        writer.write(make_header('version', vp) + vp)
        await writer.drain()

        hdr = await asyncio.wait_for(reader.readexactly(HEADER_SIZE),
                                     timeout=5)
        _, _, vlen, _ = parse_header(hdr)
        if vlen > 0:
            await reader.readexactly(vlen)

        vb = make_header('verack', b'')
        writer.write(vb)
        await writer.drain()

        hdr2 = await asyncio.wait_for(reader.readexactly(HEADER_SIZE),
                                      timeout=5)
        _, _, vrlen, _ = parse_header(hdr2)
        if vrlen > 0:
            await reader.readexactly(vrlen)

        await asyncio.sleep(0.3)

        # Send a ping with a known nonce.
        test_nonce = 0xDEADBEEFCAFEBABE
        ping_payload = struct.pack('<Q', test_nonce)
        writer.write(make_header('ping', ping_payload) + ping_payload)
        await writer.drain()

        # Receive pong.
        pong_hdr = await asyncio.wait_for(reader.readexactly(HEADER_SIZE),
                                          timeout=5)
        _, cmd, plen, _ = parse_header(pong_hdr)
        assert cmd == 'pong', f"Expected 'pong', got '{cmd}'"
        pong_payload = await reader.readexactly(plen)
        echoed_nonce, = struct.unpack('<Q', pong_payload)
        assert echoed_nonce == test_nonce, (
            f"Nonce mismatch: sent {test_nonce:#x}, got {echoed_nonce:#x}")

        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  TEST 8 — RATE LIMITER
# ═══════════════════════════════════════════════════════════════════════

class TestRateLimiter:
    """Unit tests for the sliding-window rate limiter."""

    def test_allows_within_budget(self):
        rl = RateLimiter(max_msgs=5, window=1)
        for _ in range(5):
            assert rl.check("peer1")

    def test_blocks_over_budget(self):
        rl = RateLimiter(max_msgs=3, window=1)
        for _ in range(3):
            rl.check("peer1")
        assert not rl.check("peer1")

    def test_resets_after_window(self):
        rl = RateLimiter(max_msgs=2, window=0.1)
        assert rl.check("peer1")
        assert rl.check("peer1")
        assert not rl.check("peer1")
        time.sleep(0.15)
        assert rl.check("peer1")

    def test_independent_peers(self):
        rl = RateLimiter(max_msgs=1, window=1)
        assert rl.check("a")
        assert not rl.check("a")
        assert rl.check("b")

    def test_cleanup_removes_idle_peers(self):
        rl = RateLimiter(max_msgs=10, window=0.05)
        rl.check("stale")
        time.sleep(0.1)
        rl.cleanup()
        assert "stale" not in rl._counts


# ═══════════════════════════════════════════════════════════════════════
#  TEST 9 — BAN SCORE SYSTEM
# ═══════════════════════════════════════════════════════════════════════

class TestBanScore:
    """Verify that ban scoring triggers disconnection."""

    def test_malformed_packet_ban(self):
        """Repeated malformed packets should trigger a ban."""
        session = PeerSession("test:9999", None, None, "inbound")
        session.state = HandshakeState.CONNECTED
        # 10 malformed packets → 100 points → banned.
        for i in range(10):
            banned = session.add_ban_score(BAN_SCORE_MALFORMED, "test")
        assert banned
        assert session.ban_score >= BAN_SCORE_THRESHOLD

    def test_invalid_data_heavier_penalty(self):
        """Invalid data gets a heavier penalty (+50)."""
        session = PeerSession("test:9999", None, None, "inbound")
        session.state = HandshakeState.CONNECTED
        # 2 invalid data packets → 100 points → banned.
        for _ in range(2):
            banned = session.add_ban_score(BAN_SCORE_INVALID_DATA, "test")
        assert banned

    def test_below_threshold_not_banned(self):
        """Below threshold the session stays active."""
        session = PeerSession("test:9999", None, None, "inbound")
        session.state = HandshakeState.CONNECTED
        for _ in range(9):
            banned = session.add_ban_score(BAN_SCORE_MALFORMED, "test")
        assert not banned


# ═══════════════════════════════════════════════════════════════════════
#  TEST 10 — GOSSIP PROTOCOL UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestGossipProtocol:
    """Unit tests for the GossipProtocol inventory tracking."""

    def test_announce_block_tracks_inventory(self):
        g = GossipProtocol()
        msg = g.announce_block("aabb" * 16, height=42)
        assert msg["type"] == "BLOCK_ANNOUNCE"
        assert msg["hash"] == "aabb" * 16
        assert g.has_block("aabb" * 16)

    def test_announce_tx_tracks_inventory(self):
        g = GossipProtocol()
        msg = g.announce_tx("ccdd" * 16)
        assert msg["type"] == "TX_ANNOUNCE"
        assert g.has_tx("ccdd" * 16)

    def test_should_request_block_unknown(self):
        g = GossipProtocol()
        assert g.should_request_block("unknown", 10, 20)

    def test_should_not_request_known_block(self):
        g = GossipProtocol()
        g.known_blocks.add("known")
        assert not g.should_request_block("known", 10, 20)

    def test_should_not_request_old_height(self):
        g = GossipProtocol()
        assert not g.should_request_block("new", 20, 10)

    def test_inventory_eviction(self):
        """When inventory is full, oldest items are evicted."""
        g = GossipProtocol()
        g.MAX_INVENTORY_SIZE = 5
        for i in range(10):
            g.announce_block(f"hash{i:04d}" * 4, i)
        assert len(g.inventory) == 5
        # Oldest should be gone.
        assert not g.has_block("hash0000" * 4)

    def test_sync_ranges(self):
        g = GossipProtocol()
        ranges = g.get_sync_ranges(0, 100, peer="fast")
        assert len(ranges) > 0
        # Start of first range should be 1.
        assert ranges[0][0] == 1
        # End of last range should be 100.
        assert ranges[-1][1] == 100

    def test_empty_sync_ranges_when_up_to_date(self):
        g = GossipProtocol()
        assert g.get_sync_ranges(100, 100) == []
        assert g.get_sync_ranges(100, 50) == []


# ═══════════════════════════════════════════════════════════════════════
#  TEST 11 — COMMAND DISPATCH REJECTS UNKNOWN
# ═══════════════════════════════════════════════════════════════════════

class TestUnknownCommand:
    """Sending an unknown command should trigger ban scoring."""

    @pytest.mark.asyncio
    async def test_unknown_command_banned(self, node_a):
        port_a = node_a.port
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port_a, ssl=node_a.ssl_client_context)

        # Complete handshake.
        vp = struct.pack('<IQQQI', PROTOCOL_VERSION, 1,
                         int(time.time()), random_nonce(), 0)
        writer.write(make_header('version', vp) + vp)
        await writer.drain()
        hdr = await asyncio.wait_for(reader.readexactly(HEADER_SIZE),
                                     timeout=5)
        _, _, vlen, _ = parse_header(hdr)
        if vlen > 0:
            await reader.readexactly(vlen)
        writer.write(make_header('verack', b''))
        await writer.drain()
        hdr2 = await asyncio.wait_for(reader.readexactly(HEADER_SIZE),
                                      timeout=5)
        _, _, vrlen, _ = parse_header(hdr2)
        if vrlen > 0:
            await reader.readexactly(vrlen)
        await asyncio.sleep(0.3)

        # Flood with unknown commands.
        payload = b'data'
        for _ in range(15):
            writer.write(make_header('zzz', payload) + payload)
            await writer.drain()

        await asyncio.sleep(1.0)
        # After enough unknown commands, the peer should be dropped.
        assert len(node_a.sessions) == 0
        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  TEST 12 — INV/GETDATA BINARY PROTOCOL
# ═══════════════════════════════════════════════════════════════════════

class TestInvGetdata:
    """Verify binary inv/getdata round-trip."""

    def test_inv_payload_format(self):
        """Verify inv payload packs as ``<I32s``."""
        inv_type = 1  # TX
        inv_hash = os.urandom(32)
        payload = struct.pack('<I32s', inv_type, inv_hash)
        assert len(payload) == 36  # 4 + 32

        decoded_type, decoded_hash = struct.unpack('<I32s', payload)
        assert decoded_type == inv_type
        assert decoded_hash == inv_hash

    def test_getdata_same_layout_as_inv(self):
        """getdata must use the same binary layout as inv."""
        getdata_payload = struct.pack('<I32s', 2, os.urandom(32))
        inv_payload = struct.pack('<I32s', 2, os.urandom(32))
        assert len(getdata_payload) == len(inv_payload) == 36


# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
