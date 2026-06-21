"""
TritioCoin Peer Discovery
Busca automatica de peers via:
1. GitHub (lista atualizada)
2. seeds.json local
3. Conexoes existentes
"""
import asyncio
import json
import logging
import random
from typing import List
from pathlib import Path

logger = logging.getLogger("Discovery")

# URL da lista de seeds no GitHub (atualizada automaticamente)
SEED_URL = "https://raw.githubusercontent.com/TritioCoin/seeds/main/seeds.json"

# Seeds fixas como fallback
FALLBACK_SEEDS = []


class PeerDiscovery:
    def __init__(self):
        self.peers = []
        self.connected = []

    async def discover(self) -> List[str]:
        """Busca peers automaticamente."""
        all_peers = []

        # 1. Tenta buscar do GitHub
        github_peers = await self._fetch_github()
        if github_peers:
            all_peers.extend(github_peers)
            logger.info(f"GitHub: {len(github_peers)} seeds encontrados")

        # 2. Busca do seeds.json local
        local_peers = self._load_local()
        if local_peers:
            all_peers.extend(local_peers)
            logger.info(f"Local: {len(local_peers)} seeds")

        # 3. Fallback
        if not all_peers:
            all_peers.extend(FALLBACK_SEEDS)
            logger.info("Usando seeds fixas")

        # Remove duplicatas
        all_peers = list(set(all_peers))

        # Remove ja conectados
        all_peers = [p for p in all_peers if p not in self.connected]

        self.peers = all_peers
        return all_peers

    async def _fetch_github(self) -> List[str]:
        """Busca lista de seeds do GitHub."""
        try:
            import urllib.request
            response = await asyncio.to_thread(
                urllib.request.urlopen, SEED_URL, timeout=5
            )
            data = json.loads(response.read().decode())
            if isinstance(data, dict):
                return data.get("seeds", [])
            return data if isinstance(data, list) else []
        except:
            return []

    def _load_local(self) -> List[str]:
        """Carrega seeds do arquivo local."""
        try:
            with open("seeds.json") as f:
                data = json.load(f)
                return data.get("seeds", [])
        except:
            return []

    def save_peer(self, peer: str):
        """Salva peer no arquivo local."""
        peers = self._load_local()
        if peer not in peers:
            peers.append(peer)
            with open("seeds.json", "w") as f:
                json.dump({"seeds": peers}, f, indent=2)

    def mark_connected(self, peer: str):
        """Marca peer como conectado."""
        if peer not in self.connected:
            self.connected.append(peer)

    def get_stats(self) -> dict:
        return {
            "discovered": len(self.peers),
            "connected": len(self.connected)
        }
