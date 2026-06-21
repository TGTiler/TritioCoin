"""
TritioCoin Light Client (SPV - Simplified Payment Verification)
Allows lightweight clients to verify transactions without full blockchain.
"""
import hashlib
import json
import logging
import asyncio
from typing import Optional, List, Dict
from pathlib import Path

logger = logging.getLogger("LightClient")


class SPVNode:
    """
    Simplified Payment Verification (SPV) node.
    
    Instead of downloading the full blockchain, SPV nodes:
    1. Download only block headers
    2. Verify Merkle proofs for transactions
    3. Trust the longest chain
    """

    HEADER_SIZE = 86  # Fixed header size in bytes

    def __init__(self):
        self.headers: Dict[int, dict] = {}  # height -> header
        self.peer_headers: Dict[str, int] = {}  # peer -> height
        self.best_height = 0
        self.best_hash = "0" * 64
        self.connected = False
        self.on_header = None
        self.on_transaction = None

    async def connect(self, host: str, port: int) -> bool:
        """Connect to a full node."""
        try:
            import ssl
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            reader, writer = await asyncio.open_connection(
                host, port, ssl=ssl_context
            )

            # Send handshake
            await self._send(writer, {
                "type": "LIGHT_HANDSHAKE",
                "client_type": "spv",
                "best_height": self.best_height
            })

            # Wait for response
            resp = await self._recv(reader)
            if resp and resp.get("type") == "LIGHT_HANDSHAKE_ACK":
                self.connected = True
                logger.info(f"Connected to full node {host}:{port}")
                asyncio.create_task(self._read_loop(reader, writer))
                return True

            return False
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    async def request_headers(self, start_height: int, count: int = 2000):
        """Request block headers from full node."""
        await self.p2p.broadcast({
            "type": "GET_HEADERS",
            "start_height": start_height,
            "count": count
        })

    async def verify_transaction(self, tx_hash: str, merkle_proof: List[str],
                                  block_hash: str, merkle_root: str) -> bool:
        """
        Verify a transaction using Merkle proof.
        
        Args:
            tx_hash: Transaction hash to verify
            merkle_proof: List of sibling hashes in Merkle path
            block_hash: Block hash containing the transaction
            merkle_root: Expected Merkle root from block header
            
        Returns:
            True if transaction is verified in the block
        """
        current = bytes.fromhex(tx_hash)

        for sibling_hex in merkle_proof:
            sibling = bytes.fromhex(sibling_hex)
            # Sort to ensure consistent ordering
            if current < sibling:
                combined = current + sibling
            else:
                combined = sibling + current
            current = hashlib.sha256(hashlib.sha256(combined).digest()).digest()

        return current.hex() == merkle_root

    async def _read_loop(self, reader, writer):
        """Read messages from full node."""
        try:
            while True:
                msg = await self._recv(reader)
                if msg is None:
                    break

                msg_type = msg.get("type")

                if msg_type == "HEADER":
                    await self._handle_header(msg)
                elif msg_type == "HEADERS":
                    for header in msg.get("headers", []):
                        await self._handle_header(header)
                elif msg_type == "MERKLE_PROOF":
                    await self._handle_merkle_proof(msg)

        except Exception as e:
            logger.error(f"Read error: {e}")
        finally:
            self.connected = False
            writer.close()

    async def _handle_header(self, header: dict):
        """Process a block header."""
        height = header.get("index", 0)
        block_hash = header.get("hash", "")

        # Store header
        self.headers[height] = header

        # Update best chain
        if height > self.best_height:
            self.best_height = height
            self.best_hash = block_hash
            logger.debug(f"New best header: height={height}")

        # Notify listener
        if self.on_header:
            await self.on_header(header)

    async def _handle_merkle_proof(self, msg: dict):
        """Process a Merkle proof response."""
        tx_hash = msg.get("tx_hash")
        proof = msg.get("proof", [])
        block_hash = msg.get("block_hash")
        merkle_root = msg.get("merkle_root")

        if self.on_transaction:
            await self.on_transaction(tx_hash, proof, block_hash, merkle_root)

    async def _send(self, writer, msg: dict):
        """Send a message."""
        raw = json.dumps(msg).encode('utf-8')
        writer.write(struct.pack('>I', len(raw)) + raw)
        await writer.drain()

    async def _recv(self, reader) -> Optional[dict]:
        """Receive a message."""
        try:
            hdr = await reader.readexactly(4)
            length = struct.unpack('>I', hdr)[0]
            if length > 10 * 1024 * 1024:
                return None
            data = await reader.readexactly(length)
            return json.loads(data.decode('utf-8'))
        except Exception:
            return None

    def get_header(self, height: int) -> Optional[dict]:
        """Get a block header by height."""
        return self.headers.get(height)

    def get_best_height(self) -> int:
        """Get the best known block height."""
        return self.best_height

    def get_stats(self) -> dict:
        """Get SPV node statistics."""
        return {
            "connected": self.connected,
            "best_height": self.best_height,
            "headers_stored": len(self.headers),
            "peers": len(self.peer_headers)
        }


class MerkleProof:
    """Utility for generating and verifying Merkle proofs."""

    @staticmethod
    def compute_root(tx_hashes: List[str]) -> str:
        """Compute Merkle root from transaction hashes."""
        if not tx_hashes:
            return hashlib.sha256(b"EMPTY").hexdigest()

        nodes = [bytes.fromhex(h) for h in tx_hashes]

        while len(nodes) > 1:
            next_level = []
            for i in range(0, len(nodes), 2):
                left = nodes[i]
                right = nodes[i + 1] if i + 1 < len(nodes) else left
                if left < right:
                    combined = left + right
                else:
                    combined = right + left
                parent = hashlib.sha256(hashlib.sha256(combined).digest()).digest()
                next_level.append(parent)
            nodes = next_level

        return nodes[0].hex()

    @staticmethod
    def generate_proof(tx_hashes: List[str], tx_index: int) -> List[str]:
        """Generate Merkle proof for a transaction."""
        if tx_index >= len(tx_hashes):
            return []

        nodes = [bytes.fromhex(h) for h in tx_hashes]
        proof = []
        idx = tx_index

        while len(nodes) > 1:
            next_level = []
            for i in range(0, len(nodes), 2):
                left = nodes[i]
                right = nodes[i + 1] if i + 1 < len(nodes) else left
                # Same sorting as compute_root
                if left < right:
                    combined = left + right
                else:
                    combined = right + left
                parent = hashlib.sha256(hashlib.sha256(combined).digest()).digest()
                next_level.append(parent)

            # Add sibling to proof (must match sorting in compute_root)
            if idx % 2 == 0:
                sibling_idx = idx + 1
            else:
                sibling_idx = idx - 1

            if 0 <= sibling_idx < len(nodes):
                sibling = nodes[sibling_idx]
                # Ensure consistent ordering in proof
                current_node = nodes[idx]
                if current_node < sibling:
                    proof.append(sibling.hex())
                else:
                    proof.append(sibling.hex())

            nodes = next_level
            idx //= 2

        return proof

    @staticmethod
    def verify_proof(tx_hash: str, proof: List[str], root: str, index: int) -> bool:
        """Verify a Merkle proof."""
        current = bytes.fromhex(tx_hash)

        for i, sibling_hex in enumerate(proof):
            sibling = bytes.fromhex(sibling_hex)
            # Same sorting as compute_root
            if current < sibling:
                combined = current + sibling
            else:
                combined = sibling + current
            current = hashlib.sha256(hashlib.sha256(combined).digest()).digest()
            index //= 2

        return current.hex() == root

        return current.hex() == root
