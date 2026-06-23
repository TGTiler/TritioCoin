"""
TritioCoin Peer Reputation System
Tracks peer behavior and bans malicious peers.
Persists reputation data to disk for survival across restarts.
"""
import time
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger("Reputation")

REPUTATION_FILE = Path("tritiocoin_data/peer_reputation.json")


@dataclass
class PeerScore:
    """Tracks reputation score for a peer."""
    address: str
    score: int = 100
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

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "score": self.score,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "invalid_messages": self.invalid_messages,
            "blocks_received": self.blocks_received,
            "txs_received": self.txs_received,
            "connects": self.connects,
            "disconnects": self.disconnects,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "banned": self.banned,
            "ban_reason": self.ban_reason,
            "ban_until": self.ban_until
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'PeerScore':
        return cls(
            address=data.get("address", ""),
            score=data.get("score", 100),
            messages_sent=data.get("messages_sent", 0),
            messages_received=data.get("messages_received", 0),
            invalid_messages=data.get("invalid_messages", 0),
            blocks_received=data.get("blocks_received", 0),
            txs_received=data.get("txs_received", 0),
            connects=data.get("connects", 0),
            disconnects=data.get("disconnects", 0),
            first_seen=data.get("first_seen", time.time()),
            last_seen=data.get("last_seen", time.time()),
            banned=data.get("banned", False),
            ban_reason=data.get("ban_reason", ""),
            ban_until=data.get("ban_until", 0)
        )


class PeerReputation:
    """Manages peer reputation and banning with disk persistence."""

    SCORE_VALID_MSG = 1
    SCORE_INVALID_MSG = -10
    SCORE_VALID_BLOCK = 5
    SCORE_VALID_TX = 2
    SCORE_DISCONNECT = -5
    SCORE_CONNECT = 2
    BAN_THRESHOLD = -50
    BAN_DURATION = 3600
    BAN_DURATION_SEVERE = 86400
    SEVERE_PENALTY = -100

    def __init__(self, persist_path: Path = REPUTATION_FILE, persist: bool = True):
        self.peers: Dict[str, PeerScore] = {}
        self.banned_ips: Dict[str, float] = {}
        self.persist_path = persist_path
        self.persist = persist
        self._last_save = time.time()
        if persist:
            self._load()

    def _load(self):
        """Load reputation data from disk."""
        try:
            if self.persist_path.exists():
                with open(self.persist_path, 'r') as f:
                    data = json.load(f)
                for peer_data in data.get("peers", []):
                    ps = PeerScore.from_dict(peer_data)
                    self.peers[ps.address] = ps
                    if ps.is_banned():
                        self.banned_ips[ps.address] = ps.ban_until
                logger.info(f"Loaded reputation data: {len(self.peers)} peers")
        except Exception as e:
            logger.debug(f"Could not load reputation data: {e}")

    def _save(self):
        """Save reputation data to disk."""
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "peers": [p.to_dict() for p in self.peers.values()],
                "saved_at": time.time()
            }
            with open(self.persist_path, 'w') as f:
                json.dump(data, f, indent=2)
            self._last_save = time.time()
        except Exception as e:
            logger.debug(f"Could not save reputation data: {e}")

    def _maybe_save(self):
        """Save periodically (every 5 minutes)."""
        now = time.time()
        if now - self._last_save >= 300:
            self._save()

    def get_peer(self, address: str) -> PeerScore:
        if address not in self.peers:
            self.peers[address] = PeerScore(address=address)
        return self.peers[address]

    def on_connect(self, address: str):
        peer = self.get_peer(address)
        peer.connects += 1
        peer.last_seen = time.time()
        if peer.is_banned():
            logger.warning(f"Banned peer attempted connection: {address}")
            return False
        peer.score += self.SCORE_CONNECT
        self._maybe_save()
        return True

    def on_disconnect(self, address: str):
        peer = self.get_peer(address)
        peer.disconnects += 1
        peer.score += self.SCORE_DISCONNECT
        self._maybe_save()

    def on_valid_message(self, address: str, msg_type: str = ""):
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
        self._maybe_save()

    def on_invalid_message(self, address: str, reason: str = ""):
        peer = self.get_peer(address)
        peer.invalid_messages += 1
        peer.score += self.SCORE_INVALID_MSG
        logger.warning(f"Invalid message from {address}: {reason}")
        if peer.score <= self.BAN_THRESHOLD:
            self.ban_peer(address, "Repeated invalid messages")
        self._maybe_save()

    def ban_peer(self, address: str, reason: str, duration: int = None):
        if duration is None:
            duration = self.BAN_DURATION
        peer = self.get_peer(address)
        peer.banned = True
        peer.ban_reason = reason
        peer.ban_until = time.time() + duration
        peer.score += self.SEVERE_PENALTY
        self.banned_ips[address] = peer.ban_until
        logger.warning(f"Peer banned: {address} for {duration}s - {reason}")
        self._save()

    def unban_peer(self, address: str):
        peer = self.get_peer(address)
        peer.banned = False
        peer.ban_reason = ""
        peer.ban_until = 0
        peer.score = max(0, peer.score)
        self.banned_ips.pop(address, None)
        logger.info(f"Peer unbanned: {address}")
        self._save()

    def is_banned(self, address: str) -> bool:
        if address in self.banned_ips:
            if time.time() > self.banned_ips[address]:
                self.banned_ips.pop(address)
                return False
            return True
        peer = self.peers.get(address)
        return peer.is_banned() if peer else False

    def get_score(self, address: str) -> int:
        return self.get_peer(address).score

    def get_top_peers(self, limit: int = 10) -> List[Dict]:
        peers = sorted(self.peers.values(), key=lambda p: p.score, reverse=True)
        return [self._peer_to_dict(p) for p in peers[:limit]]

    def get_worst_peers(self, limit: int = 10) -> List[Dict]:
        peers = sorted(self.peers.values(), key=lambda p: p.score)
        return [self._peer_to_dict(p) for p in peers[:limit]]

    def get_banned_peers(self) -> List[Dict]:
        banned = []
        for addr, peer in self.peers.items():
            if peer.is_banned():
                banned.append(self._peer_to_dict(peer))
        return banned

    def get_stats(self) -> dict:
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
        cutoff = time.time() - 86400
        to_remove = [
            addr for addr, peer in self.peers.items()
            if peer.last_seen < cutoff and not peer.is_banned()
        ]
        for addr in to_remove:
            del self.peers[addr]
        expired = [addr for addr, expiry in self.banned_ips.items()
                   if time.time() > expiry]
        for addr in expired:
            self.banned_ips.pop(addr)
            if addr in self.peers:
                self.peers[addr].banned = False
        self._save()
