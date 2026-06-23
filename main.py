import asyncio
import argparse
import hashlib
import json
import logging
import random
import signal
import sys
import os
import ecdsa
from pathlib import Path

from core.blockchain import Blockchain
from core.mempool import Mempool
from core.miner import Miner
from core.wallet import Wallet
from core.transaction import Transaction
from core.database import Database
from core.network_config import get_network, MAINNET, TESTNET
from core.consensus import ConsensusEngine
from network.p2p_node import P2PNode
from network.api import TritioAPI
from network.dht import DHT, get_dht
from network.discovery import PeerDiscovery
from network.gossip import GossipNode, GossipProtocol
from core.delegation import DelegationPool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tritiocoin.log")
    ]
)
logger = logging.getLogger("Tritio")

DATA_DIR = Path("tritiocoin_data")
SEEDS_FILE = Path("seeds.json")
STATUS_FILE = DATA_DIR / "status.json"


def atomic_write(path: Path, data):
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(str(tmp), str(path))


def load_seeds_config() -> dict:
    """Load seeds config as dict with 'seeds' list and optional 'my_role'."""
    config = {"seeds": [], "my_role": "peer"}
    if SEEDS_FILE.exists():
        try:
            with open(SEEDS_FILE) as f:
                data = json.load(f)
                if isinstance(data, dict):
                    config["seeds"] = data.get("seeds", [])
                    config["my_role"] = data.get("my_role", "peer")
                elif isinstance(data, list):
                    config["seeds"] = data
        except Exception:
            pass
    return config


def save_seeds_config(config: dict):
    """Save seeds config to file."""
    try:
        with open(SEEDS_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save seeds config: {e}")


def get_random_seed(seeds: list) -> str:
    """Pick a random seed from the list."""
    if not seeds:
        return None
    return random.choice(seeds)


class TritioNode(GossipNode):
    def __init__(self, config: dict):
        GossipNode.__init__(self)
        self.config = config
        self.running = False
        self.quantum = config.get('quantum', False)
        self.mode = config.get('mode', 'passive')
        self.network = config.get('network', 'mainnet')

        DATA_DIR.mkdir(exist_ok=True)

        # Network configuration
        self.net_config = get_network(self.network)
        if self.network == "testnet":
            self.db = Database(DATA_DIR / "testnet.db")
        else:
            self.db = Database(DATA_DIR / "mainnet.db")

        self.seeds_config = load_seeds_config()
        self.wallet = self._load_wallet()
        self.blockchain = Blockchain(self.net_config, self.db)
        self.mempool = Mempool(self.db, self.net_config.mempool_max, self.net_config.min_fee_satoshis)
        self.miner = Miner(self.blockchain, self.mempool)
        self.consensus = ConsensusEngine(self.blockchain)
        self.delegation_pool = DelegationPool()
        self.p2p = P2PNode(config['host'], config['port'])
        self.p2p.on_message = self._on_msg

        # DHT for decentralized peer discovery
        dht_port = config.get('dht_port', config['port'] + 1)
        self.dht = DHT(port=dht_port)
        self.dht.on_peer_found = self._on_peer_found

        # Peer discovery (GitHub seeds + local + bootstrap)
        self.discovery = PeerDiscovery()

        self.mining_task = None
        self.is_seed = config.get('become_seed', False)
        self.api = None
        self.orphan_pool: dict = {}
        self.max_orphans = 50
        self._pending_signatures: dict = {}

        # Update P2P height after blockchain loads
        self.p2p.blockchain_height = self.blockchain.height()

        logger.info(f"Node started | Network: {self.network} | Mode: {self.mode} | "
                    f"Quantum: {'ON' if self.quantum else 'OFF'} | "
                    f"Address: {self.wallet.address} | "
                    f"DHT port: {dht_port}")

    def _wallet_path(self) -> Path:
        name = "wallet_quantum.json" if self.quantum else "wallet.json"
        return DATA_DIR / name

    def _chain_path(self) -> Path:
        return DATA_DIR / "blockchain.json"

    def _load_wallet(self) -> Wallet:
        path = self._wallet_path()
        if path.exists():
            try:
                password = os.environ.get("TRC_PASSWORD", "")
                if not password:
                    # Try to load without password (unencrypted)
                    try:
                        return Wallet.load(str(path))
                    except:
                        logger.error("Carteira existe mas precisa de senha. "
                                    "Defina a variavel de ambiente TRC_PASSWORD.")
                        logger.error(f"Arquivo: {path}")
                        logger.error("Exemplo: set TRC_PASSWORD=sua_senha")
                        sys.exit(1)
                else:
                    return Wallet.load(str(path), password)
            except Exception as e:
                logger.error(f"Erro ao carregar carteira: {e}")
                logger.error("A carteira NAO sera substituida. "
                            "Verifique a senha em TRC_PASSWORD.")
                sys.exit(1)

        # Only create new wallet if file doesn't exist
        logger.info("Nenhuma carteira encontrada. Criando nova carteira...")
        w = Wallet.create(self.quantum)
        DATA_DIR.mkdir(exist_ok=True)
        password = os.environ.get("TRC_PASSWORD", "tritiocoin123")
        w.save(str(path), password)
        logger.info(f"Nova carteira criada: {w.address}")
        logger.info(f"Arquivo: {path}")
        logger.info(f"IMPORTANTE: Anote as 24 palavras de recuperacao!")
        return w

    def _load_chain(self) -> Blockchain:
        path = self._chain_path()
        if path.exists():
            try:
                with open(path) as f:
                    bc = Blockchain.deserialize(json.load(f), self.net_config, self.db)
                logger.info(f"Chain loaded: {bc.height()} blocks")
                return bc
            except Exception as e:
                logger.warning(f"Chain load error: {e}")
        return self.blockchain

    def _save_chain(self, bc: Blockchain = None):
        bc = bc or self.blockchain
        atomic_write(self._chain_path(), bc.serialize())

    async def _on_msg(self, msg: dict, peer: str, writer):
        # First try gossip protocol
        if await self.gossip_handle_message(msg, peer, writer):
            return

        t = msg.get("type")
        if t == "HANDSHAKE":
            peer_height = msg.get("height", 0)
            await self.p2p.send(peer, {"type": "HANDSHAKE_ACK",
                                        "version": 2,
                                        "height": self.blockchain.height(),
                                        "role": self.seeds_config.get("my_role", "peer"),
                                        "seeds": self.seeds_config.get("seeds", []),
                                        "gossip": True})
            # If peer has more blocks, request sync
            if isinstance(peer_height, int) and peer_height > self.blockchain.height():
                logger.info(f"Peer {peer} has more blocks ({peer_height} > {self.blockchain.height()}), requesting sync")
                await self.p2p.send(peer, {"type": "GET_CHAIN", "my_height": self.blockchain.height()})
            else:
                # Peer might be behind - send our chain info
                logger.info(f"Handshake from {peer} (peer_height={peer_height}, my_height={self.blockchain.height()})")
            remote_seeds = msg.get("seeds", [])
            await self._merge_seeds(remote_seeds)

        elif t == "HANDSHAKE_ACK":
            role = msg.get("role", "peer")
            height = msg.get("height", "?")
            logger.info(f"Connected to {peer} (height={height}, role={role})")
            if isinstance(height, int) and height > self.blockchain.height():
                logger.info(f"Remote has more blocks, syncing from {peer}")
                await self.start_sync(peer, height)
            elif isinstance(height, int) and height < self.blockchain.height():
                logger.info(f"I have more blocks ({self.blockchain.height()} > {height}), should broadcast")
            remote_seeds = msg.get("seeds", [])
            await self._merge_seeds(remote_seeds)

        elif t == "NEW_BLOCK":
            await self._handle_block(msg.get("block"))

        elif t == "COMPACT_BLOCK":
            await self._handle_compact_block(msg)

        elif t == "GET_BLOCK":
            await self._handle_get_block(msg, peer)

        elif t == "NEW_TX":
            await self._handle_tx(msg.get("tx"))

        elif t == "GET_TX":
            await self._handle_get_tx(msg, peer)

        elif t == "GET_CHAIN":
            # Send only blocks the peer needs
            peer_height = msg.get("my_height", 0)
            if isinstance(peer_height, int) and peer_height > 0:
                # Send only blocks from peer_height to end
                blocks = []
                for i in range(peer_height, self.blockchain.height()):
                    block_data = self.blockchain.db.get_block(i)
                    if block_data:
                        blocks.append(block_data)
                await self.p2p.send(peer, {"type": "CHAIN",
                                            "chain": {"blocks": blocks, "difficulty": self.blockchain.difficulty}})
                logger.info(f"Sent {len(blocks)} blocks to peer (from height {peer_height})")
            else:
                # Send full chain (fallback)
                await self.p2p.send(peer, {"type": "CHAIN",
                                            "chain": self.blockchain.serialize()})

        elif t == "CHAIN":
            await self._handle_chain(msg.get("chain"))

        elif t == "SEED_ANNOUNCE":
            await self._handle_seed_announce(msg)

        elif t == "SEED_REMOVE":
            await self._handle_seed_remove(msg)

        elif t == "SEED_SYNC":
            await self._handle_seed_sync(msg, peer)

        elif t == "REQUEST_SIGNATURE":
            await self._handle_request_signature(msg, peer)

        elif t == "BLOCK_SIGNATURE":
            await self._handle_block_signature(msg)

        elif t == "REGISTER_VALIDATOR":
            await self._handle_register_validator(msg)

        elif t == "DELEGATE":
            await self._handle_delegate(msg)

        elif t == "PING":
            await self.p2p.send(peer, {"type": "PONG"})

    async def _handle_get_tx(self, msg: dict, peer: str):
        """Respond to GET_TX request with full transaction."""
        tx_hash = msg.get("tx_hash")
        if not tx_hash:
            return

        for tx_data in self.mempool.get():
            if tx_data.get("tx_hash") == tx_hash:
                await self.p2p.send(peer, {"type": "NEW_TX", "tx": tx_data})
                return

    async def _handle_block(self, block_data: dict):
        if not block_data:
            return
        from core.block import Block
        block = Block.deserialize(block_data)

        # Check if parent exists
        if block.header.previous_hash.hex() != self.blockchain.latest().hash:
            # Parent missing - store as orphan
            orphan_hash = block.hash or block.content_hash()
            if len(self.orphan_pool) < self.max_orphans:
                self.orphan_pool[orphan_hash] = block_data
                logger.info(f"Orphan block stored: #{block.header.index} "
                           f"(waiting for parent {block.header.previous_hash.hex()[:16]}...)")
            return

        if self.blockchain.add_block(block):
            self.p2p.blockchain_height = self.blockchain.height()
            self.mempool.remove_many(
                [tx.get("hash") for tx in block.transactions if tx.get("hash")]
            )
            logger.info(f"Block #{block.header.index} accepted (height={self.blockchain.height()})")

            # Announce block via gossip
            await self.gossip_announce_block(block.hash, block.header.index)

            # Broadcast to WebSocket clients
            if self.api:
                await self.api.broadcast_ws({
                    "type": "new_block",
                    "height": block.header.index,
                    "hash": block.hash,
                    "tx_count": len(block.transactions)
                })

            # Try to connect orphans
            await self._connect_orphans()
        else:
            logger.info(f"Block #{block.header.index} rejected (duplicate or invalid)")
            if self.api:
                await self.api.broadcast_ws({
                    "type": "new_block",
                    "height": block.header.index,
                    "hash": block.hash,
                    "tx_count": len(block.transactions)
                })
            # Try to connect orphans
            await self._connect_orphans()

    async def _handle_compact_block(self, msg: dict):
        """Handle compact block (header + tx hashes, reconstruct from mempool)."""
        from core.block import Block
        header_data = msg.get("header")
        tx_hashes = msg.get("tx_hashes", [])
        pow_hash = msg.get("pow_hash")

        if not header_data:
            return

        # Reconstruct transactions from mempool
        mempool_txs = self.mempool.get_hashes()
        transactions = []
        missing = []

        for tx_hash in tx_hashes:
            if tx_hash in mempool_txs:
                # Found in mempool - get full tx
                for tx in self.mempool.get():
                    if tx["tx_hash"] == tx_hash:
                        transactions.append(tx)
                        break
            else:
                missing.append(tx_hash)

        if missing:
            # Request missing transactions
            await self.p2p.broadcast({
                "type": "GET_TX",
                "tx_hashes": missing
            })
            logger.debug(f"Compact block: {len(missing)} txs missing, requesting")
            return

        # Reconstruct full block
        block_data = {
            "header": header_data,
            "transactions": transactions,
            "pow_hash": pow_hash,
            "hash": msg.get("hash"),
            "validator_signatures": msg.get("validator_signatures", [])
        }

        await self._handle_block(block_data)

    async def _handle_get_block(self, msg: dict, peer: str):
        """Respond to GET_BLOCK request."""
        height = msg.get("height")
        if height is not None:
            block_data = self.blockchain.db.get_block(height)
            if block_data:
                await self.p2p.send(peer, {"type": "NEW_BLOCK", "block": block_data})

    async def _connect_orphans(self):
        """Try to connect orphan blocks to the chain."""
        connected = True
        while connected:
            connected = False
            for orphan_hash in list(self.orphan_pool.keys()):
                orphan_data = self.orphan_pool[orphan_hash]
                from core.block import Block
                orphan = Block.deserialize(orphan_data)

                if orphan.header.previous_hash.hex() == self.blockchain.latest().hash:
                    if self.blockchain.add_block(orphan):
                        self.p2p.blockchain_height = self.blockchain.height()
                        self.mempool.remove_many(
                            [tx.get("hash") for tx in orphan.transactions if tx.get("hash")]
                        )
                        del self.orphan_pool[orphan_hash]
                        logger.info(f"Orphan connected: #{orphan.header.index}")
                        connected = True

    async def _handle_tx(self, tx_data: dict):
        if not tx_data:
            return
        tx = Transaction.from_dict(tx_data)
        if self.mempool.add(tx, self.blockchain.balance):
            logger.info(f"Tx accepted: {tx}")

            # Announce via gossip
            if tx.tx_hash:
                await self.gossip_announce_tx(tx.tx_hash)

            # Broadcast to WebSocket clients
            if self.api:
                await self.api.broadcast_ws({
                    "type": "new_tx",
                    "tx": tx_data
                })

    async def _handle_chain(self, chain_data: dict):
        if not chain_data:
            return
        old_height = self.blockchain.height()

        # Handle both full chain and partial sync
        if "blocks" in chain_data:
            # Partial sync - only new blocks
            blocks = chain_data.get("blocks", [])
            added = 0
            for block_data in blocks:
                from core.block import Block
                block = Block.deserialize(block_data)
                if self.blockchain.add_block(block):
                    added += 1
                    self.p2p.blockchain_height = self.blockchain.height()
            if added > 0:
                logger.info(f"Synced {added} blocks (height: {self.blockchain.height()})")
        else:
            # Full chain sync - replace local chain entirely
            remote = Blockchain.deserialize(chain_data, self.net_config, self.db)
            if remote.height() > old_height and remote.is_valid():
                # Replace local chain with remote chain
                self.blockchain = remote
                self.p2p.blockchain_height = self.blockchain.height()
                logger.info(f"Chain synced: {self.blockchain.height()} blocks (was {old_height})")
                # Save the new chain
                self._save_chain()
            elif remote.height() == old_height:
                logger.info("Chain already up to date")

    async def _handle_seed_announce(self, msg: dict):
        """Another node announced itself as seed. Add to seeds.json and gossip."""
        new_seed = msg.get("address")
        if new_seed and new_seed not in self.seeds_config.get("seeds", []):
            self.seeds_config.setdefault("seeds", []).append(new_seed)
            save_seeds_config(self.seeds_config)
            logger.info(f"New seed added: {new_seed}")
            # Gossip: forward to all other peers
            await self.p2p.broadcast({"type": "SEED_ANNOUNCE", "address": new_seed})

    async def _handle_seed_remove(self, msg: dict):
        """A seed was removed. Remove from seeds.json and gossip."""
        remove_seed = msg.get("address")
        seeds = self.seeds_config.get("seeds", [])
        if remove_seed in seeds:
            seeds.remove(remove_seed)
            save_seeds_config(self.seeds_config)
            logger.info(f"Seed removed: {remove_seed}")
            # Gossip: forward to all other peers
            await self.p2p.broadcast({"type": "SEED_REMOVE", "address": remove_seed})

    async def _handle_seed_sync(self, msg: dict, peer: str):
        """Respond to seed sync request with our seed list."""
        remote_seeds = msg.get("seeds", [])
        await self._merge_seeds(remote_seeds)
        await self.p2p.send(peer, {"type": "SEED_SYNC",
                                    "seeds": self.seeds_config.get("seeds", [])})

    async def _merge_seeds(self, remote_seeds: list):
        """Merge remote seeds into our seeds.json."""
        if not remote_seeds:
            return
        my_seeds = self.seeds_config.get("seeds", [])
        merged = False
        for s in remote_seeds:
            if s not in my_seeds:
                my_seeds.append(s)
                merged = True
        if merged:
            self.seeds_config["seeds"] = my_seeds
            save_seeds_config(self.seeds_config)
            logger.info(f"Seeds merged: now {len(my_seeds)} seeds")

    async def _handle_request_signature(self, msg: dict, peer: str):
        """Miner requested our signature on a block."""
        if self.mode != "validator":
            return
        block_data = msg.get("block")
        if not block_data:
            return
        from core.block import Block
        block = Block.deserialize(block_data)
        # Sign the block
        sig = self.consensus.sign_block(block, self.wallet)
        if sig:
            await self.p2p.send(peer, {
                "type": "BLOCK_SIGNATURE",
                "block_hash": block.hash,
                "block_index": block.header.index,
                "address": self.wallet.address,
                "signature": sig
            })

    async def _handle_block_signature(self, msg: dict):
        """Received a validator signature on a block."""
        block_hash = msg.get("block_hash")
        block_index = msg.get("block_index")
        address = msg.get("address")
        signature = msg.get("signature")

        if not all([block_hash, address, signature]):
            return

        logger.info(f"Validator signature received: {address[:16]}... on block #{block_index}")
        if block_hash not in self._pending_signatures:
            self._pending_signatures[block_hash] = []
        self._pending_signatures[block_hash].append({
            "address": address,
            "signature": signature
        })

    async def _handle_register_validator(self, msg: dict):
        """Register a new validator."""
        address = msg.get("address")
        stake = msg.get("stake", 0)
        pubkey = msg.get("pubkey")

        if not address or stake < self.consensus.min_stake:
            return

        if pubkey:
            try:
                from core.wallet import Wallet
                vk = ecdsa.VerifyingKey.from_string(bytes.fromhex(pubkey), curve=ecdsa.SECP256k1)
                w = Wallet.__new__(Wallet)
                w.private_key = None
                w.public_key = vk
                w.address = address
                w.quantum_mode = False
                w.hybrid_keys = None
                w.mnemonic = None

                if self.consensus.register_validator(w, stake):
                    logger.info(f"Validator registered: {address[:16]}... stake={stake} TRC")
                    # Broadcast to other peers
                    await self.p2p.broadcast(msg)
                else:
                    logger.warning(f"Validator registration rejected: {address[:16]}...")
            except Exception as e:
                logger.error(f"Validator registration error: {e}")

    async def _handle_delegate(self, msg: dict):
        """Handle delegation broadcast from other nodes."""
        delegator = msg.get("delegator")
        validator = msg.get("validator")
        amount = msg.get("amount", 0)

        if not delegator or not validator or amount <= 0:
            return

        # Register delegation locally
        self.delegation_pool.delegate(delegator, validator, amount)
        logger.info(f"Delegation received: {delegator[:16]}... -> {validator[:16]}... ({amount} TRC)")

    async def _auto_connect(self):
        """Auto-connect to network using peer discovery."""
        logger.info("Starting peer discovery...")

        # Discover peers from all sources
        peers = await self.discovery.discover()

        # Add CLI seed override
        cli_seed = self.config.get('seed')
        if cli_seed and cli_seed not in peers:
            peers.append(cli_seed)

        if not peers:
            logger.info("No peers found. Running standalone")
            return []

        # Try to connect to discovered peers
        connected = 0
        for peer in peers:
            if connected >= 3:  # Max 3 connections
                break
            try:
                parts = peer.split(':')
                host = parts[0]
                port = int(parts[1]) if len(parts) > 1 else 8333
                if await self.p2p.connect(host, port):
                    connected += 1
                    self.discovery.mark_connected(peer)
                    self.discovery.save_peer(peer)
            except Exception as e:
                logger.debug(f"Failed to connect to {peer}: {e}")

        logger.info(f"Connected to {connected} peers")
        return [(p.split(':')[0], int(p.split(':')[1])) for p in peers if ':' in p]

    async def become_seed(self):
        """Promote this node to seed status."""
        my_addr = f"{self.config['host']}:{self.config['port']}"
        self.is_seed = True

        # Announce to DHT
        await self.dht.announce_peer(my_addr)

        # Announce to all connected peers (gossip)
        await self.p2p.broadcast({
            "type": "SEED_ANNOUNCE",
            "address": my_addr,
            "height": self.blockchain.height()
        })
        logger.info(f"This node is now a SEED: {my_addr}")

    async def stop_being_seed(self):
        """Demote this node from seed status."""
        my_addr = f"{self.config['host']}:{self.config['port']}"
        self.is_seed = False
        logger.info(f"This node is no longer a SEED: {my_addr}")

        # Announce removal to all connected peers (gossip)
        await self.p2p.broadcast({
            "type": "SEED_REMOVE",
            "address": my_addr
        })

    async def _seed_sync_loop(self):
        """Periodically sync seeds with connected peers."""
        while self.running:
            await asyncio.sleep(30)  # Every 30 seconds
            if self.p2p.peers:
                # Pick a random peer and sync seeds
                peer = list(self.p2p.peers.keys())[0]
                await self.p2p.send(peer, {
                    "type": "SEED_SYNC",
                    "seeds": self.seeds_config.get("seeds", [])
                })

    async def _bootstrap_dht(self):
        """Bootstrap DHT with known nodes."""
        from network.dht import NodeInfo
        known_nodes = []

        # Add seeds from seeds_config
        for seed_addr in self.seeds_config.get("seeds", []):
            try:
                parts = seed_addr.split(':')
                if len(parts) == 2:
                    host, port = parts[0], int(parts[1])
                    node_id = hashlib.sha1(seed_addr.encode()).digest()
                    known_nodes.append(NodeInfo(node_id, host, port))
            except Exception:
                continue

        # Add connected peers
        for peer_key in self.p2p.peers.keys():
            try:
                parts = peer_key.split(':')
                if len(parts) == 2:
                    host, port = parts[0], int(parts[1])
                    node_id = hashlib.sha1(peer_key.encode()).digest()
                    known_nodes.append(NodeInfo(node_id, host, port))
            except Exception:
                continue

        if known_nodes:
            await self.dht.bootstrap(known_nodes)
            logger.info(f"DHT bootstrapped with {len(known_nodes)} nodes")

    async def _dht_discovery_loop(self):
        """Periodically discover peers via DHT."""
        while self.running:
            await asyncio.sleep(60)  # Every 60 seconds

            try:
                # Announce ourselves
                my_addr = f"{self.config['host']}:{self.config['port']}"
                await self.dht.announce_peer(my_addr)

                # Discover new peers
                all_nodes = self.dht.routing_table.get_all_nodes()
                for node in all_nodes[:5]:  # Check 5 nodes
                    peers = await self.dht.get_peers(node)
                    for peer_addr in peers:
                        if peer_addr not in self.p2p.peers:
                            logger.info(f"DHT discovered new peer: {peer_addr}")
                            await self._connect_to_peer_async(peer_addr)

            except Exception as e:
                logger.debug(f"DHT discovery error: {e}")

    def _save_status(self):
        """Save node status to file for wallet.py to read."""
        status = {
            "port": self.config['port'],
            "mode": self.mode,
            "role": "seed" if self.is_seed else "peer",
            "address": self.wallet.address,
            "height": self.blockchain.height(),
            "difficulty": self.blockchain.difficulty,
            "mempool": self.mempool.size(),
            "peers": list(self.p2p.peers.keys()),
            "peers_count": len(self.p2p.peers),
            "is_mining": self.miner.mining if hasattr(self.miner, 'mining') else False
        }
        atomic_write(STATUS_FILE, status)

    async def _status_loop(self):
        """Save status every 2 seconds."""
        while self.running:
            self._save_status()
            await asyncio.sleep(2)

    async def _mining_loop(self):
        while self.running:
            if self.mode == 'miner':
                block = await self.miner.mine_async(self.wallet.address)
                if block:
                    await self._process_mined_block(block)

            elif self.mode == 'validator':
                await asyncio.sleep(1)

            await asyncio.sleep(0.1)

    async def _process_mined_block(self, block):
        # Sign with miner key
        block_data = f"{block.header.index}{block.hash}".encode()
        sig = self.wallet.sign_tx(hashlib.sha256(block_data).digest())
        block.validator_signatures.append({
            "address": self.wallet.address,
            "signature": sig["ecdsa_signature"].hex(),
            "signature_mode": sig["signature_mode"]
        })

        # Request validator signatures
        await self.p2p.broadcast({
            "type": "REQUEST_SIGNATURE",
            "block": block.serialize()
        })

        # Wait briefly for signatures
        await asyncio.sleep(0.5)

        # Add any pending signatures
        if block.hash in self._pending_signatures:
            block.validator_signatures.extend(self._pending_signatures.pop(block.hash))

        if self.blockchain.add_block(block):
            self.p2p.blockchain_height = self.blockchain.height()
            self.blockchain.adjust_difficulty()

            # Broadcast FULL block (not compact - coinbase is not in mempool)
            await self.p2p.broadcast({
                "type": "NEW_BLOCK",
                "block": block.serialize()
            })
            logger.info(f"Block #{block.header.index} broadcast to all peers")

            # Distribute rewards
            self.consensus.distribute_block_rewards(block)

            # Broadcast to WebSocket
            if self.api:
                await self.api.broadcast_ws({
                    "type": "new_block",
                    "height": block.header.index,
                    "hash": block.hash,
                    "tx_count": len(block.transactions)
                })

    def _on_peer_found(self, peer_addr: str):
        """Callback when DHT discovers a new peer."""
        logger.info(f"DHT discovered peer: {peer_addr}")
        # Try to connect to discovered peer
        asyncio.create_task(self._connect_to_peer_async(peer_addr))

    async def _connect_to_peer_async(self, peer_addr: str):
        """Async connection to a peer."""
        try:
            parts = peer_addr.split(':')
            if len(parts) == 2:
                host, port = parts[0], int(parts[1])
                await self.p2p.connect(host, port)
        except Exception as e:
            logger.debug(f"Failed to connect to DHT peer {peer_addr}: {e}")

    async def start(self):
        self.running = True
        tasks = [asyncio.create_task(self.p2p.start())]

        # Start DHT
        dht_port = self.config.get('dht_port', self.config['port'] + 1)
        tasks.append(asyncio.create_task(self.dht.start()))
        logger.info(f"DHT started on port {dht_port}")

        # Bootstrap DHT with known nodes
        await self._bootstrap_dht()

        # Auto-connect to random seed (fallback)
        seed_pairs = await self._auto_connect()

        # Reconnect loop
        if seed_pairs:
            tasks.append(asyncio.create_task(
                self.p2p.reconnect_loop(seed_pairs)
            ))

        # DHT peer discovery loop
        tasks.append(asyncio.create_task(self._dht_discovery_loop()))

        # Mining
        if self.mode == 'miner':
            tasks.append(asyncio.create_task(self._mining_loop()))

        # Status loop (writes status.json for wallet.py)
        tasks.append(asyncio.create_task(self._status_loop()))

        # Seed sync loop (syncs seeds.json with peers)
        tasks.append(asyncio.create_task(self._seed_sync_loop()))

        # REST API
        if self.config.get('api', True):
            api_port = self.config.get('api_port', 8080)
            self.api = TritioAPI(self, port=api_port)
            await self.api.start()

        logger.info(f"Node running on port {self.config['port']} | "
                    f"API on port {self.config.get('api_port', 8080)}")

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass

    async def stop(self):
        self.running = False
        if self.mining_task:
            self.miner.stop()
            self.mining_task.cancel()
        self._save_chain()
        logger.info("Node stopped")


def parse_args():
    p = argparse.ArgumentParser(description="TritioCoin Node")
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('--port', type=int, default=8333)
    p.add_argument('--seed', default=None, help="ip:port override")
    p.add_argument('--mode', choices=['miner', 'validator', 'passive'], default='passive')
    p.add_argument('--network', choices=['mainnet', 'testnet'], default='mainnet')
    p.add_argument('--difficulty', type=int, default=4)
    p.add_argument('--quantum', action='store_true')
    p.add_argument('--become-seed', action='store_true', help="Promote to seed on startup")
    p.add_argument('--api', action='store_true', default=True)
    p.add_argument('--api-port', type=int, default=8080)
    p.add_argument('--no-api', action='store_true', help="Disable REST API")
    return p.parse_args()


async def main():
    args = parse_args()
    config = {
        'host': args.host, 'port': args.port, 'seed': args.seed,
        'mode': args.mode, 'difficulty': args.difficulty,
        'quantum': args.quantum, 'network': args.network,
        'api': not args.no_api, 'api_port': args.api_port
    }
    node = TritioNode(config)

    if args.become_seed:
        await node.become_seed()

    loop = asyncio.get_running_loop()
    if sys.platform != 'win32':
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(node.stop()))

    await node.start()


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
