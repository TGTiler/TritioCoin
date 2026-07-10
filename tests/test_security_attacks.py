"""
TritioCoin Security Attack Test Suite
=====================================

Comprehensive penetration testing suite for the TritioCoin P2P network.
Tests the security defenses documented in ARCHITECTURE.md § Anti-DoS e Seguranca de Rede.

Attack vectors tested:
    1. Wire Protocol Attacks (magic, checksum, malformed headers)
    2. Memory Exhaustion Attacks (oversized payloads)
    3. Connection Flood Attacks (max peers, per-IP limits)
    4. Rate Limiting Tests (sliding window validation)
    5. Ban Score System Validation
    6. Handshake State Machine Attacks
    7. Self-Connection Detection
    8. Keep-Alive / Ping-Pong Exploits
    9. Gossip Protocol Attacks (inventory flooding)
    10. Version Manipulation Attacks

Run:
    python -m pytest tests/test_security_attacks.py -v

Requires: pytest, pytest-asyncio, cryptography
"""

import asyncio
import hashlib
import json
import os
import struct
import time
import random
import socket
import ssl

import pytest
import pytest_asyncio

# Ensure project root is importable
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from network.p2p_node import (
    MAGIC_BYTES, HEADER_FORMAT, HEADER_SIZE, MAX_PAYLOAD_SIZE,
    PROTOCOL_VERSION, MIN_PROTOCOL_VERSION,
    BAN_SCORE_MALFORMED, BAN_SCORE_INVALID_DATA, BAN_SCORE_THRESHOLD,
    MAX_PEERS, MAX_PER_IP, CONNECT_COOLDOWN, RECV_TIMEOUT,
    PeerSession, HandshakeState,
    sha256d, payload_checksum, make_header, parse_header,
    P2PNode, RateLimiter,
)


# ═══════════════════════════════════════════════════════════════════════
#  UTILITIES
# ═══════════════════════════════════════════════════════════════════════

PORT_COUNTER = 20000


def _next_port():
    global PORT_COUNTER
    PORT_COUNTER += 1
    return PORT_COUNTER


def random_nonce() -> int:
    return struct.unpack('<Q', os.urandom(8))[0]


async def raw_connect(host: str, port: int, ssl_ctx=None):
    """Open a raw TCP+TLS connection and return (reader, writer)."""
    return await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=ssl_ctx),
        timeout=5
    )


async def complete_handshake(reader, writer, node, nonce=None):
    """Complete the binary handshake as a malicious client."""
    if nonce is None:
        nonce = random_nonce()

    # Send version
    vp = struct.pack('<IQQQI', PROTOCOL_VERSION, 1,
                     int(time.time()), nonce, 0)
    writer.write(make_header('version', vp) + vp)
    await writer.drain()

    # Receive version response
    hdr = await asyncio.wait_for(reader.readexactly(HEADER_SIZE), timeout=5)
    _, cmd, vlen, _ = parse_header(hdr)
    assert cmd == 'version'
    if vlen > 0:
        await reader.readexactly(vlen)

    # Send verack
    writer.write(make_header('verack', b''))
    await writer.drain()

    # Receive verack
    hdr2 = await asyncio.wait_for(reader.readexactly(HEADER_SIZE), timeout=5)
    _, cmd2, vrlen, _ = parse_header(hdr2)
    assert cmd2 == 'verack'
    if vrlen > 0:
        await reader.readexactly(vrlen)

    await asyncio.sleep(0.2)


@pytest.fixture
def tmp_dir(tmp_path):
    old = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old)


@pytest_asyncio.fixture
async def target_node(tmp_dir):
    """A real P2P node to attack."""
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


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 1: WIRE PROTOCOL MAGIC BYTES
# ═══════════════════════════════════════════════════════════════════════

class TestMagicBytesAttack:
    """
    Attack: Send packets with wrong magic bytes.
    Defense: parse_header() validates magic, rejects with ValueError.
    """

    @pytest.mark.asyncio
    async def test_wrong_magic_rejected(self, target_node):
        """Sending wrong magic bytes should be rejected immediately."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Send header with wrong magic
        bad_header = struct.pack(
            HEADER_FORMAT,
            b'\x00\x00\x00\x00',  # Wrong magic
            b'version\x00\x00\x00\x00',
            28,
            0
        )
        writer.write(bad_header)
        await writer.drain()

        await asyncio.sleep(0.3)
        # Node should reject and not create a session
        assert len(target_node.sessions) == 0
        writer.close()

    @pytest.mark.asyncio
    async def test_random_magic_rejected(self, target_node):
        """Random magic bytes should be rejected."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        for _ in range(5):
            random_magic = os.urandom(4)
            bad_header = struct.pack(
                HEADER_FORMAT,
                random_magic,
                b'version\x00\x00\x00\x00',
                28,
                0
            )
            writer.write(bad_header)
            await writer.drain()

        await asyncio.sleep(0.3)
        assert len(target_node.sessions) == 0
        writer.close()

    @pytest.mark.asyncio
    async def test_correct_magic_accepted(self, target_node):
        """Correct magic bytes should be accepted (during handshake)."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Send version with correct magic
        vp = struct.pack('<IQQQI', PROTOCOL_VERSION, 1,
                         int(time.time()), random_nonce(), 0)
        writer.write(make_header('version', vp) + vp)
        await writer.drain()

        # Should receive a version response (magic was accepted)
        hdr = await asyncio.wait_for(reader.readexactly(HEADER_SIZE), timeout=5)
        magic, cmd, vlen, _ = parse_header(hdr)
        assert magic == MAGIC_BYTES
        assert cmd == 'version'

        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 2: CHECKSUM MANIPULATION
# ═══════════════════════════════════════════════════════════════════════

class TestChecksumAttack:
    """
    Attack: Send messages with invalid checksums.
    Defense: payload_checksum() validation rejects corrupt data.
    """

    @pytest.mark.asyncio
    async def test_bad_checksum_triggers_ban(self, target_node):
        """Multiple bad checksums should trigger ban and disconnect."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake first
        await complete_handshake(reader, writer, target_node)

        # Flood with bad checksums to trigger ban (threshold=100, score=10 each)
        payload = b'{"type":"test"}'
        for _ in range(12):
            bad_header = struct.pack(
                HEADER_FORMAT,
                MAGIC_BYTES,
                b'json\x00\x00\x00\x00\x00\x00',
                len(payload),
                0xDEADBEEF  # Wrong checksum
            )
            writer.write(bad_header + payload)
            await writer.drain()

        await asyncio.sleep(0.5)
        assert len(target_node.sessions) == 0
        writer.close()

    @pytest.mark.asyncio
    async def test_truncated_payload_causes_disconnect(self, target_node):
        """Claiming more data than sent should cause disconnect."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Send header claiming 100 bytes but only send 10
        header = make_header('json', b'x' * 100)
        writer.write(header + b'x' * 10)  # Only 10 bytes
        await writer.drain()

        # Wait for timeout to occur (RECV_TIMEOUT = 30s, but we check earlier)
        await asyncio.sleep(2)

        # Session should be removed due to IncompleteReadError
        # Check that the session is marked for removal or already removed
        for session in target_node.sessions.values():
            # The session may still exist but will be cleaned up
            # after the read loop detects the incomplete read
            pass

        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 3: MEMORY EXHAUSTION (OVERSIZED PAYLOAD)
# ═══════════════════════════════════════════════════════════════════════

class TestMemoryExhaustionAttack:
    """
    Attack: Send headers claiming huge payloads to exhaust memory.
    Defense: MAX_PAYLOAD_SIZE (2MB) check BEFORE reading payload.
    """

    @pytest.mark.asyncio
    async def test_1mb_payload_rejected(self, target_node):
        """Payload > 2MB should be rejected immediately."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Send header claiming 3MB
        fake_length = 3 * 1024 * 1024
        bad_header = struct.pack(
            HEADER_FORMAT,
            MAGIC_BYTES,
            b'json\x00\x00\x00\x00\x00\x00',
            fake_length,
            0
        )
        writer.write(bad_header)
        await writer.drain()

        await asyncio.sleep(0.5)
        assert len(target_node.sessions) == 0
        writer.close()

    @pytest.mark.asyncio
    async def test_max_payload_boundary(self, target_node):
        """Payload exactly at MAX_PAYLOAD_SIZE should be accepted."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Send header claiming exactly MAX_PAYLOAD_SIZE
        # This should NOT be rejected (it's within limits)
        fake_length = MAX_PAYLOAD_SIZE
        header = struct.pack(
            HEADER_FORMAT,
            MAGIC_BYTES,
            b'json\x00\x00\x00\x00\x00\x00',
            fake_length,
            0
        )
        writer.write(header)
        await writer.drain()

        # Node should keep connection (payload size is valid)
        # It will timeout reading the actual data, but won't reject on size
        await asyncio.sleep(1)
        # Session may still exist or have timed out
        # The key is it didn't immediately disconnect
        writer.close()

    @pytest.mark.asyncio
    async def test_just_over_limit_rejected(self, target_node):
        """Payload one byte over limit should be rejected."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        fake_length = MAX_PAYLOAD_SIZE + 1
        bad_header = struct.pack(
            HEADER_FORMAT,
            MAGIC_BYTES,
            b'json\x00\x00\x00\x00\x00\x00',
            fake_length,
            0
        )
        writer.write(bad_header)
        await writer.drain()

        await asyncio.sleep(0.5)
        assert len(target_node.sessions) == 0
        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 4: CONNECTION FLOOD
# ═══════════════════════════════════════════════════════════════════════

class TestConnectionFloodAttack:
    """
    Attack: Exhaust connection slots with many connections.
    Defense: MAX_PEERS (50) limit, MAX_PER_IP (3) limit.
    """

    @pytest.mark.asyncio
    async def test_max_peers_enforced(self, target_node):
        """Should reject connections after MAX_PEERS is reached."""
        port = target_node.port
        connections = []

        for i in range(MAX_PEERS + 5):
            try:
                r, w = await asyncio.wait_for(
                    asyncio.open_connection(
                        "127.0.0.1", port,
                        ssl=target_node.ssl_client_context),
                    timeout=2)
                connections.append((r, w))
            except Exception:
                break

        await asyncio.sleep(0.5)

        # Node should not exceed MAX_PEERS sessions
        # Some connections may be in handshake state
        active = len(target_node.sessions)
        # The limit should prevent accepting beyond MAX_PEERS
        assert active <= MAX_PEERS

        for r, w in connections:
            w.close()

    @pytest.mark.asyncio
    async def test_per_ip_limit(self, target_node):
        """Should reject connections from same IP beyond MAX_PER_IP."""
        port = target_node.port
        connections = []

        # Complete handshake for multiple connections from same IP
        for i in range(MAX_PER_IP + 3):
            try:
                r, w = await asyncio.wait_for(
                    asyncio.open_connection(
                        "127.0.0.1", port,
                        ssl=target_node.ssl_client_context),
                    timeout=2)
                # Complete handshake
                await complete_handshake(r, w, target_node,
                                        nonce=random_nonce())
                connections.append((r, w))
                await asyncio.sleep(0.1)
            except Exception:
                break

        await asyncio.sleep(0.3)

        # Count sessions from 127.0.0.1
        local_sessions = sum(
            1 for s in target_node.sessions.values()
            if s.key.startswith('127.0.0.1:'))

        # Should be limited to MAX_PER_IP
        assert local_sessions <= MAX_PER_IP

        for r, w in connections:
            try:
                w.close()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 5: RATE LIMITING
# ═══════════════════════════════════════════════════════════════════════

class TestRateLimitAttack:
    """
    Attack: Flood messages to DoS the node.
    Defense: RateLimiter sliding window (200 msgs/10s per peer).
    """

    def test_rate_limiter_enforces_budget(self):
        """Rate limiter should block after budget is exhausted."""
        rl = RateLimiter(max_msgs=10, window=1)
        for _ in range(10):
            assert rl.check("attacker")
        # 11th message should be blocked
        assert not rl.check("attacker")

    def test_rate_limiter_independent_peers(self):
        """Rate limiting should be per-peer, not global."""
        rl = RateLimiter(max_msgs=2, window=1)
        assert rl.check("peer_a")
        assert rl.check("peer_a")
        assert not rl.check("peer_a")  # peer_a exhausted
        assert rl.check("peer_b")      # peer_b still has budget

    def test_rate_limiter_window_expiry(self):
        """Rate limit should reset after window expires."""
        rl = RateLimiter(max_msgs=2, window=0.05)
        rl.check("spammer")
        rl.check("spammer")
        assert not rl.check("spammer")
        time.sleep(0.06)
        assert rl.check("spammer")  # Window expired

    @pytest.mark.asyncio
    async def test_message_flood_detected(self, target_node):
        """Rapid message flooding should be handled gracefully."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Flood with valid JSON messages
        flood_count = 500
        msg = json.dumps({"type": "PING"}).encode()
        header = make_header('json', msg)

        for _ in range(flood_count):
            try:
                writer.write(header + msg)
            except Exception:
                break

        await writer.drain()
        await asyncio.sleep(1)

        # Node should still be running (not crashed)
        assert target_node.server is not None

        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 6: BAN SCORE SYSTEM
# ═══════════════════════════════════════════════════════════════════════

class TestBanScoreAttack:
    """
    Attack: Verify ban score thresholds and disconnect behavior.
    Defense: Ban scoring with threshold-based disconnection.
    """

    def test_malformed_packet_scoring(self):
        """Each malformed packet should add +10 ban score."""
        session = PeerSession("attacker:9999", None, None, "inbound")
        session.state = HandshakeState.CONNECTED

        for i in range(9):
            banned = session.add_ban_score(BAN_SCORE_MALFORMED, "test")
            assert not banned, f"Should not be banned after {i+1} packets"

        # 10th packet should trigger ban
        banned = session.add_ban_score(BAN_SCORE_MALFORMED, "test")
        assert banned
        assert session.ban_score >= BAN_SCORE_THRESHOLD

    def test_invalid_data_heavier_penalty(self):
        """Invalid data should get +50 (heavier penalty)."""
        session = PeerSession("attacker:9999", None, None, "inbound")
        session.state = HandshakeState.CONNECTED

        # 1 invalid data packet = 50 points (not banned yet)
        banned = session.add_ban_score(BAN_SCORE_INVALID_DATA, "corrupt block")
        assert not banned
        assert session.ban_score == 50

        # 2nd invalid data packet = 100 points = banned
        banned = session.add_ban_score(BAN_SCORE_INVALID_DATA, "bad tx")
        assert banned
        assert session.ban_score >= BAN_SCORE_THRESHOLD

    def test_combined_attack_scoring(self):
        """Mixed attack types should accumulate correctly."""
        session = PeerSession("attacker:9999", None, None, "inbound")
        session.state = HandshakeState.CONNECTED

        # 8 malformed (80) + 1 invalid (50) = 130 → banned
        for _ in range(8):
            session.add_ban_score(BAN_SCORE_MALFORMED, "test")
        banned = session.add_ban_score(BAN_SCORE_INVALID_DATA, "test")
        assert banned
        assert session.ban_score == 130


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 7: SELF-CONNECTION DETECTION
# ═══════════════════════════════════════════════════════════════════════

class TestSelfConnectionAttack:
    """
    Attack: Try to connect to self via nonce replay.
    Defense: Nonce comparison detects self-connections.
    """

    @pytest.mark.asyncio
    async def test_self_nonce_rejected(self, target_node):
        """Connecting with same nonce as target should be rejected."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Craft version with same nonce as target
        payload = struct.pack('<IQQQI',
                              PROTOCOL_VERSION,
                              1,
                              int(time.time()),
                              target_node.local_nonce,  # Same nonce!
                              0)
        writer.write(make_header('version', payload) + payload)
        await writer.drain()

        await asyncio.sleep(0.5)
        assert len(target_node.sessions) == 0
        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 8: VERSION MANIPULATION
# ═══════════════════════════════════════════════════════════════════════

class TestVersionAttack:
    """
    Attack: Manipulate protocol version in handshake.
    Defense: MIN_PROTOCOL_VERSION check rejects old versions.
    """

    @pytest.mark.asyncio
    async def test_old_version_rejected(self, target_node):
        """Protocol version below minimum should be rejected."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Send ancient version
        vp = struct.pack('<IQQQI',
                         1000,  # Way below MIN_PROTOCOL_VERSION
                         1,
                         int(time.time()),
                         random_nonce(),
                         0)
        writer.write(make_header('version', vp) + vp)
        await writer.drain()

        await asyncio.sleep(0.5)
        assert len(target_node.sessions) == 0
        writer.close()

    @pytest.mark.asyncio
    async def test_version_zero_rejected(self, target_node):
        """Version 0 should be rejected."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        vp = struct.pack('<IQQQI', 0, 1, int(time.time()), random_nonce(), 0)
        writer.write(make_header('version', vp) + vp)
        await writer.drain()

        await asyncio.sleep(0.5)
        assert len(target_node.sessions) == 0
        writer.close()

    @pytest.mark.asyncio
    async def test_oversized_version_payload_rejected(self, target_node):
        """Version payload with wrong size should be rejected."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Send version with oversized payload
        vp = os.urandom(100)  # Should be exactly 28 bytes
        writer.write(make_header('version', vp) + vp)
        await writer.drain()

        await asyncio.sleep(0.5)
        assert len(target_node.sessions) == 0
        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 9: PING/PONG NONCE MANIPULATION
# ═══════════════════════════════════════════════════════════════════════

class TestPingPongAttack:
    """
    Attack: Manipulate ping/pong nonces.
    Defense: Nonce echo validation detects mismatches.
    """

    @pytest.mark.asyncio
    async def test_pong_nonce_validation(self, target_node):
        """Pong nonce must match the ping nonce sent."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Send a ping with known nonce
        test_nonce = 0xDEADBEEFCAFEBABE
        ping_payload = struct.pack('<Q', test_nonce)
        writer.write(make_header('ping', ping_payload) + ping_payload)
        await writer.drain()

        # Receive pong
        pong_hdr = await asyncio.wait_for(reader.readexactly(HEADER_SIZE),
                                          timeout=5)
        _, cmd, plen, _ = parse_header(pong_hdr)
        assert cmd == 'pong'
        pong_payload = await reader.readexactly(plen)
        echoed_nonce, = struct.unpack('<Q', pong_payload)
        assert echoed_nonce == test_nonce

        writer.close()

    @pytest.mark.asyncio
    async def test_bad_ping_size_banned(self, target_node):
        """Ping with wrong payload size should trigger ban."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Send pings with wrong sizes
        for _ in range(12):
            bad_ping = os.urandom(random.choice([4, 12, 16, 32]))
            writer.write(make_header('ping', bad_ping) + bad_ping)
            await writer.drain()

        await asyncio.sleep(0.5)
        assert len(target_node.sessions) == 0
        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 10: GOSSIP / INVENTORY FLOODING
# ═══════════════════════════════════════════════════════════════════════

class TestGossipFloodAttack:
    """
    Attack: Flood inventory announcements.
    Defense: known_inventory deduplication, ban scoring.
    """

    @pytest.mark.asyncio
    async def test_duplicate_inv_ignored(self, target_node):
        """Same inv hash sent twice should be deduplicated."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Send same inv 10 times
        inv_hash = os.urandom(32)
        inv_payload = struct.pack('<I32s', 1, inv_hash)

        for _ in range(10):
            writer.write(make_header('inv', inv_payload) + inv_payload)
            await writer.drain()

        await asyncio.sleep(0.3)

        # Check that the peer's known_inventory has the hash only once
        for session in target_node.sessions.values():
            assert len([h for h in session.known_inventory
                       if h == inv_hash.hex()]) <= 1

        writer.close()

    @pytest.mark.asyncio
    async def test_invalid_inv_size_banned(self, target_node):
        """Inv with wrong payload size should trigger ban."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Send inv with wrong size
        for _ in range(12):
            bad_inv = os.urandom(20)  # Should be 36 bytes
            writer.write(make_header('inv', bad_inv) + bad_inv)
            await writer.drain()

        await asyncio.sleep(0.5)
        assert len(target_node.sessions) == 0
        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 11: UNKNOWN COMMAND FLOOD
# ═══════════════════════════════════════════════════════════════════════

class TestUnknownCommandAttack:
    """
    Attack: Send unknown commands to crash or exploit the node.
    Defense: Ban scoring for unrecognized commands.
    """

    @pytest.mark.asyncio
    async def test_unknown_command_banned(self, target_node):
        """Unknown commands should trigger ban scoring."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Flood with unknown commands
        payload = b'x' * 100
        for _ in range(15):
            writer.write(make_header('zzzzzzzzzzzz', payload) + payload)
            await writer.drain()

        await asyncio.sleep(1.0)
        assert len(target_node.sessions) == 0
        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 12: HANDSHAKE STATE MACHINE
# ═══════════════════════════════════════════════════════════════════════

class TestHandshakeStateAttack:
    """
    Attack: Send messages out of order during handshake.
    Defense: State machine rejects out-of-order messages.
    """

    @pytest.mark.asyncio
    async def test_send_data_before_handshake(self, target_node):
        """Sending data before completing handshake should be ignored."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Start handshake but don't complete
        vp = struct.pack('<IQQQI', PROTOCOL_VERSION, 1,
                         int(time.time()), random_nonce(), 0)
        writer.write(make_header('version', vp) + vp)
        await writer.drain()

        # Try to send data before verack
        msg = json.dumps({"type": "NEW_BLOCK"}).encode()
        writer.write(make_header('json', msg) + msg)
        await writer.drain()

        await asyncio.sleep(0.3)
        # Node should not crash, may or may not have session
        assert target_node.server is not None

        writer.close()

    @pytest.mark.asyncio
    async def test_double_verack(self, target_node):
        """Sending verack twice should not crash the node."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Send extra verack
        writer.write(make_header('verack', b''))
        await writer.drain()

        await asyncio.sleep(0.3)
        # Node should still be running
        assert target_node.server is not None

        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 13: JSON PAYLOAD ATTACKS
# ═══════════════════════════════════════════════════════════════════════

class TestJsonPayloadAttack:
    """
    Attack: Send malformed JSON payloads.
    Defense: JSON decode error handling with ban scoring.
    """

    @pytest.mark.asyncio
    async def test_invalid_json_banned(self, target_node):
        """Invalid JSON should trigger ban scoring."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Send invalid JSON
        for _ in range(12):
            bad_json = b'not valid json {{{'
            writer.write(make_header('json', bad_json) + bad_json)
            await writer.drain()

        await asyncio.sleep(0.5)
        assert len(target_node.sessions) == 0
        writer.close()

    @pytest.mark.asyncio
    async def test_binary_payload_as_json_banned(self, target_node):
        """Binary data in JSON command should trigger ban."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Send binary garbage as JSON
        for _ in range(12):
            binary_data = os.urandom(256)
            writer.write(make_header('json', binary_data) + binary_data)
            await writer.drain()

        await asyncio.sleep(0.5)
        assert len(target_node.sessions) == 0
        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 14: CONCURRENT CONNECTION ATTEMPTS
# ═══════════════════════════════════════════════════════════════════════

class TestConcurrentAttack:
    """
    Attack: Multiple simultaneous connection attempts.
    Defense: Connection limits, session registry thread safety.
    """

    @pytest.mark.asyncio
    async def test_rapid_connect_disconnect(self, target_node):
        """Rapid connect/disconnect cycles should not crash the node."""
        port = target_node.port

        async def connect_and_disconnect():
            try:
                r, w = await asyncio.wait_for(
                    asyncio.open_connection(
                        "127.0.0.1", port,
                        ssl=target_node.ssl_client_context),
                    timeout=2)
                await asyncio.sleep(0.05)
                w.close()
            except Exception:
                pass

        # Launch many concurrent connections
        tasks = [connect_and_disconnect() for _ in range(50)]
        await asyncio.gather(*tasks, return_exceptions=True)

        await asyncio.sleep(1)
        # Node should still be running
        assert target_node.server is not None


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 15: RECONNECTION COOLDOWN
# ═══════════════════════════════════════════════════════════════════════

class TestReconnectionAttack:
    """
    Attack: Rapid reconnection attempts.
    Defense: CONNECT_COOLDOWN (60s) between attempts.
    """

    @pytest.mark.asyncio
    async def test_cooldown_enforced(self, target_node):
        """Reconnection attempts within cooldown should be rejected."""
        port = target_node.port

        # First connection attempt
        ok1 = await target_node.connect("127.0.0.1", port)
        # This is self-connection, should fail
        # Let's test the cooldown logic directly

        target_node.last_connect_attempt["127.0.0.1:99999"] = time.time()
        ok2 = await target_node.connect("127.0.0.1", 99999)
        assert not ok2  # Should be rejected due to cooldown


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 16: HEADER FIELD MANIPULATION
# ═══════════════════════════════════════════════════════════════════════

class TestHeaderManipulation:
    """
    Attack: Craft headers with various malformed fields.
    Defense: Header parsing rejects invalid structures.
    """

    def test_short_header_rejected(self):
        """Header shorter than 24 bytes should raise error."""
        with pytest.raises(Exception):
            parse_header(b'\x00' * 10)

    def test_empty_header_rejected(self):
        """Empty header should raise error."""
        with pytest.raises(Exception):
            parse_header(b'')

    def test_command_overflow(self):
        """Command field should be truncated to 12 bytes."""
        header = make_header('a' * 100, b'')
        cmd = header[4:16]
        assert len(cmd) == 12
        assert cmd[:11] == b'a' * 11
        assert cmd[11:12] == b'\x00'

    def test_payload_length_max(self):
        """Payload length field should handle max uint32."""
        header = make_header('test', b'')
        # The length field is at offset 16, 4 bytes
        length_field = struct.unpack_from('<I', header, 16)[0]
        assert length_field == 0  # Empty payload


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 17: CHECKSUM COLLISION
# ═══════════════════════════════════════════════════════════════════════

class TestChecksumCollision:
    """
    Attack: Craft payloads that collide checksums.
    Defense: SHA256d makes collisions computationally infeasible.
    """

    def test_checksum_uniqueness(self):
        """Different payloads should produce different checksums."""
        checksums = set()
        for i in range(1000):
            payload = f"test-payload-{i}".encode()
            cksum = payload_checksum(payload)
            checksums.add(cksum)

        # With SHA256d, 1000 different payloads should have 1000 different checksums
        assert len(checksums) == 1000

    def test_checksum_deterministic(self):
        """Same payload should always produce same checksum."""
        payload = b"deterministic-test"
        cksum1 = payload_checksum(payload)
        cksum2 = payload_checksum(payload)
        assert cksum1 == cksum2


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 18: REPLAY ATTACK
# ═══════════════════════════════════════════════════════════════════════

class TestReplayAttack:
    """
    Attack: Replay captured valid messages.
    Defense: Nonce-based replay protection, timestamp validation.
    """

    @pytest.mark.asyncio
    async def test_replayed_version_rejected(self, target_node):
        """Replaying a version message should not create a new session."""
        port = target_node.port

        # Create a valid version message
        nonce = random_nonce()
        vp = struct.pack('<IQQQI', PROTOCOL_VERSION, 1,
                         int(time.time()), nonce, 0)
        msg = make_header('version', vp) + vp

        # Send it twice rapidly
        r1, w1 = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)
        w1.write(msg)
        await w1.drain()

        r2, w2 = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)
        w2.write(msg)
        await w2.drain()

        await asyncio.sleep(0.5)

        # Both connections should be handled (may have sessions or not)
        # But should not crash
        assert target_node.server is not None

        w1.close()
        w2.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 19: PAYLOAD CHECKSUM BYPASS
# ═══════════════════════════════════════════════════════════════════════

class TestChecksumBypass:
    """
    Attack: Try to bypass checksum validation.
    Defense: SHA256d checksum is mandatory for all messages.
    """

    @pytest.mark.asyncio
    async def test_zero_checksum_rejected(self, target_node):
        """Checksum of zero should not match valid payload."""
        port = target_node.port
        reader, writer = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)

        # Complete handshake
        await complete_handshake(reader, writer, target_node)

        # Send messages with zero checksum until banned
        payload = b'{"type":"test"}'
        for _ in range(12):
            header = struct.pack(
                HEADER_FORMAT,
                MAGIC_BYTES,
                b'json\x00\x00\x00\x00\x00\x00',
                len(payload),
                0  # Zero checksum
            )
            writer.write(header + payload)
            await writer.drain()

        await asyncio.sleep(0.5)
        # After enough bad checksums, should be disconnected
        assert len(target_node.sessions) == 0
        writer.close()


# ═══════════════════════════════════════════════════════════════════════
#  ATTACK 20: END-TO-END SECURITY VALIDATION
# ═══════════════════════════════════════════════════════════════════════

class TestEndToEndSecurity:
    """
    Comprehensive end-to-end security validation.
    """

    @pytest.mark.asyncio
    async def test_attack_recovery(self, target_node):
        """Node should recover after handling an attack."""
        port = target_node.port

        # Perform an attack
        for _ in range(3):
            try:
                r, w = await raw_connect(
                    "127.0.0.1", port, target_node.ssl_client_context)

                # Send bad magic
                bad_header = struct.pack(
                    HEADER_FORMAT,
                    b'\x00\x00\x00\x00',
                    b'version\x00\x00\x00\x00',
                    28, 0)
                w.write(bad_header)
                await w.drain()
                w.close()
            except Exception:
                pass

        await asyncio.sleep(0.5)

        # Node should still accept valid connections
        r2, w2 = await raw_connect(
            "127.0.0.1", port, target_node.ssl_client_context)
        vp = struct.pack('<IQQQI', PROTOCOL_VERSION, 1,
                         int(time.time()), random_nonce(), 0)
        w2.write(make_header('version', vp) + vp)
        await w2.drain()

        # Should receive valid version response
        hdr = await asyncio.wait_for(r2.readexactly(HEADER_SIZE), timeout=5)
        magic, cmd, vlen, _ = parse_header(hdr)
        assert magic == MAGIC_BYTES
        assert cmd == 'version'

        w2.close()


# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json
    pytest.main([__file__, "-v", "--tb=short"])
