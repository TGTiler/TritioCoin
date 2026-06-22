"""
TritioCoin REST + WebSocket API
Real-time updates for blocks, transactions, and network status.
"""
import json
import asyncio
import logging
from aiohttp import web
from pathlib import Path
from core.constants import SATOSHIS_PER_TRC

logger = logging.getLogger("API")


class TritioAPI:
    def __init__(self, node, host: str = "0.0.0.0", port: int = 8080):
        self.node = node
        self.host = host
        self.port = port
        self.app = web.Application()
        self.ws_clients: list = []
        self._setup_routes()

    def _setup_routes(self):
        # Static files
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/explorer", self.handle_explorer)

        # REST endpoints
        self.app.router.add_get("/api/status", self.handle_status)
        self.app.router.add_get("/api/block/{height}", self.handle_block)
        self.app.router.add_get("/api/blocks", self.handle_blocks)
        self.app.router.add_get("/api/balance/{address}", self.handle_balance)
        self.app.router.add_get("/api/tx/{tx_hash}", self.handle_tx)
        self.app.router.add_get("/api/address/{address}", self.handle_address)
        self.app.router.add_get("/api/mempool", self.handle_mempool)
        self.app.router.add_get("/api/peers", self.handle_peers)
        self.app.router.add_get("/api/validators", self.handle_validators)
        self.app.router.add_post("/api/tx", self.handle_send_tx)
        self.app.router.add_post("/api/validator/register", self.handle_register_validator)

        # WebSocket endpoint
        self.app.router.add_get("/ws", self.handle_websocket)

    # ========== WebSocket ==========

    async def handle_websocket(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.ws_clients.append(ws)
        client_id = id(ws)
        logger.info(f"WebSocket client connected: {client_id}")

        try:
            # Send initial state
            await ws.send_json({
                "type": "connected",
                "height": self.node.blockchain.height(),
                "peers": self.node.p2p.get_peer_count()
            })

            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_ws_message(ws, data)
                    except json.JSONDecodeError:
                        pass
                elif msg.type == web.WSMsgType.ERROR:
                    break
        finally:
            self.ws_clients.remove(ws)
            logger.info(f"WebSocket client disconnected: {client_id}")

        return ws

    async def _handle_ws_message(self, ws, data: dict):
        """Handle incoming WebSocket messages."""
        msg_type = data.get("type")

        if msg_type == "subscribe":
            # Client subscribes to specific channels
            await ws.send_json({"type": "subscribed", "channels": data.get("channels", [])})

        elif msg_type == "get_status":
            stats = self.node.blockchain.stats()
            stats["peers"] = self.node.p2p.get_peer_count()
            await ws.send_json({"type": "status", "data": stats})

        elif msg_type == "get_block":
            height = data.get("height")
            block = self.node.blockchain.db.get_block(height)
            await ws.send_json({"type": "block", "data": block})

        elif msg_type == "get_balance":
            address = data.get("address")
            balance = self.node.blockchain.balance(address)
            await ws.send_json({"type": "balance", "address": address, "balance": balance})

        elif msg_type == "ping":
            await ws.send_json({"type": "pong"})

    async def broadcast_ws(self, event: dict):
        """Broadcast event to all WebSocket clients."""
        if not self.ws_clients:
            return

        dead = []
        for ws in self.ws_clients:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)

        for ws in dead:
            if ws in self.ws_clients:
                self.ws_clients.remove(ws)

    # ========== REST Endpoints ==========

    async def handle_status(self, request):
        stats = self.node.blockchain.stats()
        stats["peers"] = self.node.p2p.get_peer_count()
        stats["version"] = "1.0.0"
        stats["websocket_clients"] = len(self.ws_clients)
        stats["dht"] = self.node.dht.get_stats() if hasattr(self.node, 'dht') else {}
        stats["external_address"] = self.node.p2p.get_external_address()

        # Add validator stats
        if hasattr(self.node, 'consensus'):
            validator_stats = self.node.consensus.get_validator_stats()
            stats["active_validators"] = validator_stats.get("active_validators", 0)
            stats["total_stake"] = validator_stats.get("total_stake", 0)
        else:
            stats["active_validators"] = 0
            stats["total_stake"] = 0

        return web.json_response(stats)

    async def handle_block(self, request):
        height = int(request.match_info["height"])
        block = self.node.blockchain.db.get_block(height)
        if block:
            return web.json_response(block)
        return web.json_response({"error": "Block not found"}, status=404)

    async def handle_blocks(self, request):
        limit = int(request.query.get("limit", 10))
        offset = int(request.query.get("offset", 0))
        blocks = []
        height = self.node.blockchain.height()
        for i in range(min(height, offset + limit) - 1, max(-1, offset - 1), -1):
            block = self.node.blockchain.db.get_block(i)
            if block:
                blocks.append(block)
        return web.json_response({"blocks": blocks, "total": height})

    async def handle_balance(self, request):
        address = request.match_info["address"]
        balance = self.node.blockchain.balance(address)
        return web.json_response({"address": address, "balance": balance})

    async def handle_tx(self, request):
        tx_hash = request.match_info["tx_hash"]
        tx = self.node.blockchain.db.get_tx_by_hash(tx_hash)
        if tx:
            return web.json_response(tx)
        return web.json_response({"error": "Transaction not found"}, status=404)

    async def handle_address(self, request):
        address = request.match_info["address"]
        balance = self.node.blockchain.balance(address)
        txs = self.node.blockchain.db.get_address_txs(address)
        return web.json_response({
            "address": address,
            "balance": balance,
            "transactions": txs
        })

    async def handle_mempool(self, request):
        txs = self.node.mempool.get()
        return web.json_response({"mempool": txs, "count": len(txs)})

    async def handle_peers(self, request):
        peers = self.node.p2p.get_peers()
        return web.json_response({"peers": peers, "count": len(peers)})

    async def handle_validators(self, request):
        validators = self.node.consensus.get_active_validators()
        stats = self.node.consensus.get_validator_stats()
        return web.json_response({"validators": validators, "stats": stats})

    async def handle_send_tx(self, request):
        try:
            data = await request.json()
            from core.transaction import Transaction
            tx = Transaction(
                data["sender"], data["recipient"],
                data["amount"], data.get("fee", 0.001),
                data.get("data", "")
            )
            if "private_key" in data:
                from core.wallet import Wallet
                w = Wallet(bytes.fromhex(data["private_key"]))
                sigs = w.sign_tx(bytes.fromhex(tx.compute_hash()))
                tx.signature = sigs["ecdsa_signature"]
                tx.quantum_signature = sigs.get("quantum_signature")
                tx.signature_mode = sigs["signature_mode"]
                tx.tx_hash = tx.compute_hash()

            if self.node.mempool.add(tx, self.node.blockchain.balance):
                await self.node.p2p.broadcast({"type": "NEW_TX", "tx": tx.to_dict()})
                # Broadcast to WebSocket clients
                await self.broadcast_ws({
                    "type": "new_tx",
                    "tx": tx.to_dict()
                })
                return web.json_response({"status": "ok", "hash": tx.tx_hash})
            return web.json_response({"error": "Invalid transaction"}, status=400)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_register_validator(self, request):
        try:
            data = await request.json()
            address = data.get("address")
            stake = data.get("stake", 0)
            pubkey = data.get("pubkey")

            if not address:
                return web.json_response({"error": "Address required"}, status=400)

            if stake < self.node.consensus.min_stake:
                return web.json_response({"error": f"Minimum stake: {self.node.consensus.min_stake} TRC"}, status=400)

            # Check balance
            from core.constants import trc_to_satoshis
            balance = self.node.blockchain.balance_satoshis(address)
            needed = trc_to_satoshis(stake)
            if balance < needed:
                return web.json_response({
                    "error": f"Insufficient balance: {balance/SATOSHIS_PER_TRC:.8f} < {stake}"
                }, status=400)

            # Deduct stake from balance
            self.node.blockchain._debit_satoshis(address, needed)

            # Register locally
            from core.wallet import Wallet
            if pubkey:
                import ecdsa
                vk = ecdsa.VerifyingKey.from_string(bytes.fromhex(pubkey), curve=ecdsa.SECP256k1)
                w = Wallet.__new__(Wallet)
                w.private_key = None
                w.public_key = vk
                w.address = address
                w.quantum_mode = False
                w.hybrid_keys = None
                w.mnemonic = None
                self.node.consensus.register_validator(w, stake)

            # Broadcast registration
            await self.node.p2p.broadcast({
                "type": "REGISTER_VALIDATOR",
                "address": address,
                "stake": stake,
                "pubkey": pubkey
            })
            return web.json_response({
                "status": "ok",
                "address": address,
                "stake": stake,
                "remaining_balance": (balance - needed) / SATOSHIS_PER_TRC
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_index(self, request):
        return web.Response(
            text="TritioCoin API v1.0.0\n\nEndpoints:\n"
                 "  GET  /api/status\n"
                 "  GET  /api/block/{height}\n"
                 "  GET  /api/blocks\n"
                 "  GET  /api/balance/{address}\n"
                 "  GET  /api/tx/{tx_hash}\n"
                 "  GET  /api/address/{address}\n"
                 "  GET  /api/mempool\n"
                 "  GET  /api/peers\n"
                 "  GET  /api/validators\n"
                 "  POST /api/tx\n"
                 "  POST /api/validator/register\n"
                 "  WS   /ws\n"
                 "  WEB  /explorer",
            content_type="text/plain"
        )

    async def handle_explorer(self, request):
        explorer_path = Path(__file__).parent.parent / "explorer.html"
        if explorer_path.exists():
            return web.FileResponse(explorer_path)
        return web.Response(text="Explorer not found", status=404)

    async def start(self):
        try:
            runner = web.AppRunner(self.app)
            await runner.setup()
            site = web.TCPSite(runner, self.host, self.port)
            await site.start()
            logger.info(f"API listening on http://{self.host}:{self.port}")
        except OSError as e:
            if "10048" in str(e):
                logger.warning(f"Porta {self.port} ja esta em uso. API desabilitada.")
            else:
                logger.error(f"API error: {e}")
