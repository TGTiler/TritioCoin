"""
Tests for P2P and Reputation modules.
"""
import pytest
import asyncio
from network.reputation import PeerReputation
from network.p2p_node import P2PNode, RateLimiter


class TestRateLimiter:
    """Test rate limiter functionality."""

    def test_rate_limit(self):
        """Test rate limiting."""
        rl = RateLimiter(max_msgs=5, window=1)
        for i in range(5):
            assert rl.check("peer1")
        assert not rl.check("peer1")

    def test_rate_limit_reset(self):
        """Test rate limit resets after window."""
        import time
        rl = RateLimiter(max_msgs=2, window=0.1)
        assert rl.check("peer1")
        assert rl.check("peer1")
        assert not rl.check("peer1")
        time.sleep(0.15)
        assert rl.check("peer1")


class TestPeerReputation:
    """Test peer reputation system."""

    def test_initial_score(self):
        """Test initial peer score."""
        rep = PeerReputation(persist=False)
        score = rep.get_peer("192.168.1.1:8333")
        assert score.score == 100

    def test_valid_message(self):
        """Test valid message increases score."""
        rep = PeerReputation(persist=False)
        rep.on_valid_message("192.168.1.1:8333", "NEW_BLOCK")
        assert rep.get_score("192.168.1.1:8333") > 100

    def test_invalid_message(self):
        """Test invalid message decreases score."""
        rep = PeerReputation(persist=False)
        for _ in range(15):
            rep.on_invalid_message("192.168.1.1:8333", "spam")
        assert rep.is_banned("192.168.1.1:8333")

    def test_manual_ban(self):
        """Test manual peer banning."""
        rep = PeerReputation(persist=False)
        rep.ban_peer("192.168.1.1:8333", "DDoS", 300)
        assert rep.is_banned("192.168.1.1:8333")

    def test_unban(self):
        """Test peer unbanning."""
        rep = PeerReputation(persist=False)
        rep.ban_peer("192.168.1.1:8333", "test", 300)
        rep.unban_peer("192.168.1.1:8333")
        assert not rep.is_banned("192.168.1.1:8333")

    def test_stats(self):
        """Test reputation statistics."""
        rep = PeerReputation(persist=False)
        rep.on_connect("peer1")
        rep.on_valid_message("peer1")
        stats = rep.get_stats()
        assert stats["total_peers"] >= 1

    def test_get_top_peers(self):
        """Test top peers retrieval."""
        rep = PeerReputation(persist=False)
        for i in range(5):
            rep.on_valid_message(f"peer{i}")
        top = rep.get_top_peers(3)
        assert len(top) == 3

    def test_cleanup(self):
        """Test old peer cleanup."""
        rep = PeerReputation(persist=False)
        rep.on_connect("old_peer")
        rep.peers["old_peer"].last_seen = 0
        rep.cleanup()
        assert "old_peer" not in rep.peers


class TestP2PNode:
    """Test P2P node functionality."""

    def test_generate_node_id(self, tmp_dir):
        """Test node ID generation."""
        import os
        os.chdir(tmp_dir)
        node = P2PNode("127.0.0.1", 19333)
        assert len(node.node_id) == 32

    def test_tls_setup(self, tmp_dir):
        """Test TLS certificate generation."""
        import os
        os.chdir(tmp_dir)
        node = P2PNode("127.0.0.1", 19334)
        assert node.ssl_context is not None
        assert node.ssl_client_context is not None

    @pytest.mark.asyncio
    async def test_connect(self, tmp_dir):
        """Test P2P connection."""
        import os
        os.chdir(tmp_dir)

        n1 = P2PNode("127.0.0.1", 19335)
        asyncio.create_task(n1.start())
        await asyncio.sleep(0.3)

        n2 = P2PNode("127.0.0.1", 19336)
        ok = await n2.connect("127.0.0.1", 19335)
        assert ok

        # Cleanup
        n1.server.close()
        n2.server.close() if n2.server else None
