"""
TritioCoin Peer Reputation System
Tracks peer behavior and bans malicious peers.
"""
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("Reputation")


@dataclass
class PeerScore:
    """Tracks reputation score for a peer."""
    address: str
    score: int = 100  # Start with neutral score
    messages_sent: int = 0
    messages_received: int = 0
    invalid_messages: int = 0
    blocks_received: int = 0
    txs_received: int = 0
    connects: int = 0
    disconnects: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    banned: bool = False
    ban_reason: str = ""
    ban_until: float = 0

    def is_banned(self) -> bool:
        if not self.banned:
            return False
        if time.time() > self.ban_until:
            self.banned = False
            self.ban_reason = ""
            return False
        return True


class PeerReputation:
    """Manages peer reputation and banning."""

    # Score changes
    SCORE_VALID_MSG = 1
    SCORE_INVALID_MSG = -10
    SCORE_VALID_BLOCK = 5
    SCORE_VALID_TX = 2
    SCORE_DISCONNECT = -5
    SCORE_CONNECT = 2

    # Ban thresholds
    BAN_THRESHOLD = -50
    BAN_DURATION = 3600  # 1 hour default
    BAN_DURATION_SEVERE = 86400  # 24 hours for severe offenses

    # Severe offense score penalties
    SEVERE_PENALTY = -100

    def __init__(self):
        self.peers: Dict[str, PeerScore] = {}
        self.banned_ips: Dict[str, float] = {}  # ip -> ban_expiry

    def get_peer(self, address: str) -> PeerScore:
        """Get or create peer score."""
        if address not in self.peers:
            self.peers[address] = PeerScore(address=address)
        return self.peers[address]

    def on_connect(self, address: str):
        """Record a peer connection."""
        peer = self.get_peer(address)
        peer.connects += 1
        peer.last_seen = time.time()
        if peer.is_banned():
            logger.warning(f"Banned peer attempted connection: {address}")
            return False
        peer.score += self.SCORE_CONNECT
        return True

    def on_disconnect(self, address: str):
        """Record a peer disconnection."""
        peer = self.get_peer(address)
        peer.disconnects += 1
        peer.score += self.SCORE_DISCONNECT

    def on_valid_message(self, address: str, msg_type: str = ""):
        """Record a valid message from peer."""
        peer = self.get_peer(address)
        peer.messages_received += 1
        peer.last_seen = time.time()
        peer.score += self.SCORE_VALID_MSG

        if msg_type == "NEW_BLOCK":
            peer.blocks_received += 1
            peer.score += self.SCORE_VALID_BLOCK
        elif msg_type == "NEW_TX":
            peer.txs_received += 1
            peer.score += self.SCORE_VALID_TX

    def on_invalid_message(self, address: str, reason: str = ""):
        """Record an invalid message from peer."""
        peer = self.get_peer(address)
        peer.invalid_messages += 1
        peer.score += self.SCORE_INVALID_MSG
        logger.warning(f"Invalid message from {address}: {reason}")

        if peer.score <= self.BAN_THRESHOLD:
            self.ban_peer(address, "Repeated invalid messages")

    def ban_peer(self, address: str, reason: str, duration: int = None):
        """Ban a peer for specified duration."""
        if duration is None:
            duration = self.BAN_DURATION

        peer = self.get_peer(address)
        peer.banned = True
        peer.ban_reason = reason
        peer.ban_until = time.time() + duration
        peer.score += self.SEVERE_PENALTY

        self.banned_ips[address] = peer.ban_until
        logger.warning(f"Peer banned: {address} for {duration}s - {reason}")

    def unban_peer(self, address: str):
        """Manually unban a peer."""
        peer = self.get_peer(address)
        peer.banned = False
        peer.ban_reason = ""
        peer.ban_until = 0
        peer.score = max(0, peer.score)
        self.banned_ips.pop(address, None)
        logger.info(f"Peer unbanned: {address}")

    def is_banned(self, address: str) -> bool:
        """Check if a peer is banned."""
        if address in self.banned_ips:
            if time.time() > self.banned_ips[address]:
                self.banned_ips.pop(address)
                return False
            return True
        peer = self.peers.get(address)
        return peer.is_banned() if peer else False

    def get_score(self, address: str) -> int:
        """Get peer's current score."""
        return self.get_peer(address).score

    def get_top_peers(self, limit: int = 10) -> List[Dict]:
        """Get top peers by score."""
        peers = sorted(self.peers.values(), key=lambda p: p.score, reverse=True)
        return [self._peer_to_dict(p) for p in peers[:limit]]

    def get_worst_peers(self, limit: int = 10) -> List[Dict]:
        """Get worst peers by score."""
        peers = sorted(self.peers.values(), key=lambda p: p.score)
        return [self._peer_to_dict(p) for p in peers[:limit]]

    def get_banned_peers(self) -> List[Dict]:
        """Get all currently banned peers."""
        banned = []
        for addr, peer in self.peers.items():
            if peer.is_banned():
                banned.append(self._peer_to_dict(peer))
        return banned

    def get_stats(self) -> dict:
        """Get reputation statistics."""
        total = len(self.peers)
        banned = sum(1 for p in self.peers.values() if p.is_banned())
        avg_score = sum(p.score for p in self.peers.values()) / total if total > 0 else 0

        return {
            "total_peers": total,
            "banned_peers": banned,
            "active_peers": total - banned,
            "average_score": round(avg_score, 1),
            "total_messages": sum(p.messages_received for p in self.peers.values()),
            "total_invalid": sum(p.invalid_messages for p in self.peers.values())
        }

    def _peer_to_dict(self, peer: PeerScore) -> dict:
        return {
            "address": peer.address,
            "score": peer.score,
            "messages": peer.messages_received,
            "invalid": peer.invalid_messages,
            "blocks": peer.blocks_received,
            "txs": peer.txs_received,
            "connects": peer.connects,
            "banned": peer.is_banned(),
            "ban_reason": peer.ban_reason if peer.is_banned() else "",
            "last_seen": int(peer.last_seen)
        }

    def cleanup(self):
        """Remove old peer records."""
        cutoff = time.time() - 86400  # 24 hours
        to_remove = [
            addr for addr, peer in self.peers.items()
            if peer.last_seen < cutoff and not peer.is_banned()
        ]
        for addr in to_remove:
            del self.peers[addr]

        # Clean expired bans
        expired = [addr for addr, expiry in self.banned_ips.items()
                   if time.time() > expiry]
        for addr in expired:
            self.banned_ips.pop(addr)
            if addr in self.peers:
                self.peers[addr].banned = False
