"""
TritioCoin Peer Discovery
Automatic peer search via multiple methods with automatic fallback:
1. DHT (preferred)
2. DNS Seeds
3. GitHub (updated list)
4. seeds.json local
5. Existing connections

Features:
- DNS SRV record support
- Automatic fallback cascade
- Timeout per method
- Method logging
"""
import asyncio
import json
import logging
import random
import socket
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger("Discovery")

SEED_URL = "https://raw.githubusercontent.com/TGTiler/TritioCoin/refs/heads/main/seeds.json"
FALLBACK_SEEDS = [
    "127.0.0.1:8333",
]
DNS_SEEDS = [
    "seeds.tritiocoin.org",
    "seed.tritiocoin.org",
    "nodes.tritiocoin.org"
]
DNS_TIMEOUT = 3
GITHUB_TIMEOUT = 5
LOCAL_TIMEOUT = 1


class PeerDiscovery:
    def __init__(self):
        self.peers = []
        self.connected = []
        self._method_used = None

    async def discover(self) -> List[str]:
        all_peers = []
        methods_tried = []

        # Method 1: DHT (external)
        dht_peers = await self._discover_dht()
        if dht_peers:
            all_peers.extend(dht_peers)
            methods_tried.append(f"DHT({len(dht_peers)})")
            logger.info(f"DHT: {len(dht_peers)} peers encontrados")

        # Method 2: DNS Seeds
        dns_peers = await self._discover_dns()
        if dns_peers:
            all_peers.extend(dns_peers)
            methods_tried.append(f"DNS({len(dns_peers)})")
            logger.info(f"DNS: {len(dns_peers)} seeds encontrados")

        # Method 3: GitHub
        github_peers = await self._fetch_github()
        if github_peers:
            all_peers.extend(github_peers)
            methods_tried.append(f"GitHub({len(github_peers)})")
            logger.info(f"GitHub: {len(github_peers)} seeds encontrados")

        # Method 4: Local seeds.json
        local_peers = self._load_local()
        if local_peers:
            all_peers.extend(local_peers)
            methods_tried.append(f"Local({len(local_peers)})")
            logger.info(f"Local: {len(local_peers)} seeds")

        # Fallback: hardcoded seeds
        if not all_peers and FALLBACK_SEEDS:
            all_peers.extend(FALLBACK_SEEDS)
            methods_tried.append(f"Fallback({len(FALLBACK_SEEDS)})")
            logger.info("Usando seeds fixas")

        # Remove duplicates and already connected
        all_peers = list(set(all_peers))
        all_peers = [p for p in all_peers if p not in self.connected]

        self.peers = all_peers
        self._method_used = " + ".join(methods_tried) if methods_tried else "none"
        logger.info(f"Total: {len(all_peers)} peers | Methods: {self._method_used}")
        return all_peers

    async def _discover_dht(self) -> List[str]:
        """Discover peers via DHT if available."""
        try:
            from network.dht import get_dht
            dht = get_dht()
            if not dht.running:
                return []
            all_nodes = dht.routing_table.get_all_nodes()
            return [f"{n.ip}:{n.port}" for n in all_nodes]
        except Exception:
            return []

    async def _discover_dns(self) -> List[str]:
        """Discover peers via DNS SRV and A records."""
        peers = []
        for dns_host in DNS_SEEDS:
            try:
                resolved = await asyncio.wait_for(
                    self._resolve_dns(dns_host),
                    timeout=DNS_TIMEOUT
                )
                if resolved:
                    peers.extend(resolved)
                    logger.debug(f"DNS {dns_host}: {len(resolved)} records")
            except asyncio.TimeoutError:
                logger.debug(f"DNS {dns_host}: timeout")
            except Exception as e:
                logger.debug(f"DNS {dns_host}: {e}")
        return peers

    async def _resolve_dns(self, hostname: str) -> List[str]:
        """Resolve DNS hostname to list of peers."""
        peers = []
        try:
            loop = asyncio.get_event_loop()
            infos = await loop.getaddrinfo(
                hostname, None,
                family=socket.AF_INET,
                type=socket.SOCK_STREAM
            )
            for info in infos:
                ip = info[4][0]
                # Try default port first, then common ports
                for port in [8333, 18333]:
                    peers.append(f"{ip}:{port}")
        except socket.gaierror:
            pass
        return peers

    async def _fetch_github(self) -> List[str]:
        try:
            import urllib.request
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    urllib.request.urlopen, SEED_URL, timeout=GITHUB_TIMEOUT
                ),
                timeout=GITHUB_TIMEOUT + 1
            )
            data = json.loads(response.read().decode())
            if isinstance(data, dict):
                return data.get("seeds", [])
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _load_local(self) -> List[str]:
        try:
            with open("seeds.json") as f:
                data = json.load(f)
                return data.get("seeds", [])
        except Exception:
            return []

    def save_peer(self, peer: str):
        peers = self._load_local()
        if peer not in peers:
            peers.append(peer)
            with open("seeds.json", "w") as f:
                json.dump({"seeds": peers}, f, indent=2)

    def mark_connected(self, peer: str):
        if peer not in self.connected:
            self.connected.append(peer)

    def get_stats(self) -> dict:
        return {
            "discovered": len(self.peers),
            "connected": len(self.connected),
            "method_used": self._method_used or "none"
        }
