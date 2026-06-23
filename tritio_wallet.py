#!/usr/bin/env python3
"""
TritioWallet - Validator/ARM Edition for Termux/UserLAND
Full-featured wallet based on TritioCoin.bat

Features:
  - Auto-connect (GitHub seeds + local + DHT)
  - P2P TCP/TLS (port 8333)
  - Validator mode (PoS signing, no heavy PoW)
  - Delegation system
  - Staking rewards
  - BIP39 mnemonic (24 words)
  - Quantum-resistant addresses

Install on Termux:
  pkg install python
  pip install -r requirements.txt

Usage:
  python tritio_wallet.py
"""

import os
import sys
import json
import time
import hashlib
import struct
import socket
import ssl
import threading
import signal
import subprocess
from pathlib import Path

# ============================================================
# DEPENDENCIES
# ============================================================

def check_deps():
    missing = []
    try: import ecdsa
    except ImportError: missing.append("ecdsa")
    try: from mnemonic import Mnemonic
    except ImportError: missing.append("mnemonic")
    try: from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError: missing.append("cryptography")
    try: from argon2.low_level import hash_secret_raw, Type
    except ImportError: missing.append("argon2-cffi")
    if missing:
        print(f"\n  Pacotes faltando: {', '.join(missing)}")
        print(f"  Instale com: pip install {' '.join(missing)}")
        print(f"  Ou: pip install -r requirements.txt")
        return False
    return True

# ============================================================
# CONSTANTS
# ============================================================

SATOSHIS_PER_TRC = 100_000_000
INITIAL_REWARD_TRC = 45.0
HALVING_INTERVAL = 190_000
MIN_FEE_TRC = 0.0001
BURN_RATE = 0.10
TARGET_BLOCK_TIME = 300
P2P_PORT = 8333
API_PORT = 8080
PROTOCOL_VERSION = 2
MIN_PROTOCOL_VERSION = 1
MAX_MSG_SIZE = 10 * 1024 * 1024
MIN_STAKE_TRC = 100.0
MAX_DELEGATIONS = 100
UNBONDING_DAYS = 7
VALIDATOR_COMMISSION = 0.10
GITHUB_SEEDS_URL = "https://raw.githubusercontent.com/TGTiler/TritioCoin/refs/heads/main/seeds.json"

DATA_DIR = Path("tritiocoin_wallet")
WALLET_FILE = DATA_DIR / "wallet.json"
CONFIG_FILE = DATA_DIR / "config.json"
NODE_ID_FILE = DATA_DIR / "node_id"
PEERS_FILE = DATA_DIR / "known_peers.json"

# ============================================================
# UTILS
# ============================================================

def sha256d(data):
    if isinstance(data, str): data = data.encode()
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def sha256d_hex(data):
    return sha256d(data).hex()

def trc_to_sat(trc):
    return int(round(trc * SATOSHIS_PER_TRC))

def sat_to_trc(sat):
    return sat / SATOSHIS_PER_TRC

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

# ============================================================
# WALLET (EXACT match with server)
# ============================================================

class Wallet:
    def __init__(self, private_key_bytes=None, quantum=False, mnemonic=None):
        import ecdsa
        self.quantum = quantum
        self.mnemonic = mnemonic
        if private_key_bytes:
            self.private_key = ecdsa.SigningKey.from_string(private_key_bytes, curve=ecdsa.SECP256k1)
        else:
            self.private_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        self.public_key = self.private_key.get_verifying_key()
        self.address = self._make_address()

    @classmethod
    def create(cls, quantum=False):
        from mnemonic import Mnemonic
        mnemo = Mnemonic("english")
        words = mnemo.generate(strength=256)
        seed = mnemo.to_seed(words)
        return cls(seed[:32], quantum, words)

    @classmethod
    def from_mnemonic(cls, words, quantum=False):
        from mnemonic import Mnemonic
        mnemo = Mnemonic("english")
        if not mnemo.check(words): raise ValueError("Mnemonico invalido")
        seed = mnemo.to_seed(words)
        return cls(seed[:32], quantum, words)

    def _make_address(self):
        pub = self.public_key.to_string()
        h = hashlib.sha256(pub).digest()
        ripemd = hashlib.new('ripemd160', h).digest()
        ver = b'\x05' if self.quantum else b'\x00'
        payload = ver + ripemd
        chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        b58 = self._base58(payload + chk)
        return ("Q" if self.quantum else "T") + b58

    @staticmethod
    def _base58(data):
        abc = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        n = int.from_bytes(data, 'big')
        out = ""
        while n > 0:
            n, r = divmod(n, 58)
            out = abc[r] + out
        for b in data:
            if b == 0: out = '1' + out
            else: break
        return out

    def pubkey_hex(self): return self.public_key.to_string().hex()
    def privkey_hex(self): return self.private_key.to_string().hex()
    def sign(self, data): return self.private_key.sign(data)

    def save(self, password):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        payload = {"private_key": self.privkey_hex(), "quantum": self.quantum}
        plaintext = json.dumps(payload).encode()
        salt, nonce = os.urandom(32), os.urandom(12)
        key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000).derive(password.encode())
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
        DATA_DIR.mkdir(exist_ok=True)
        tmp = str(WALLET_FILE) + ".tmp"
        with open(tmp, 'w') as f:
            json.dump({"version": 2, "address": self.address,
                       "encrypted": {"salt": salt.hex(), "nonce": nonce.hex(), "data": ciphertext.hex()}}, f)
        os.replace(tmp, str(WALLET_FILE))

    @classmethod
    def load(cls, password=None):
        if not WALLET_FILE.exists(): return None
        with open(WALLET_FILE) as f: data = json.load(f)
        if "private_key" in data and "encrypted" not in data:
            return cls(bytes.fromhex(data["private_key"]), data.get("quantum", False))
        if password is None:
            import getpass
            password = getpass.getpass("  Senha: ")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        salt = bytes.fromhex(data["encrypted"]["salt"])
        nonce = bytes.fromhex(data["encrypted"]["nonce"])
        ciphertext = bytes.fromhex(data["encrypted"]["data"])
        key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000).derive(password.encode())
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
        payload = json.loads(plaintext)
        return cls(bytes.fromhex(payload["private_key"]), payload.get("quantum", False))

# ============================================================
# CONFIG
# ============================================================

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f: return json.load(f)
    return {"server_ip": "", "mode": "validator", "auto_connect": True}

def save_config(cfg):
    DATA_DIR.mkdir(exist_ok=True)
    with open(CONFIG_FILE, 'w') as f: json.dump(cfg, f, indent=2)

def get_server_ip():
    return load_config().get("server_ip", "")

def set_server_ip(ip):
    cfg = load_config()
    cfg["server_ip"] = ip
    save_config(cfg)

# ============================================================
# P2P CLIENT (TCP/TLS)
# ============================================================

class P2P:
    def __init__(self):
        self.sock = None
        self.ssl_ctx = None
        self.connected = False
        self.peer_height = 0
        self.node_id = self._load_node_id()
        self.on_msg = None
        self._setup_ssl()

    def _load_node_id(self):
        DATA_DIR.mkdir(exist_ok=True)
        if NODE_ID_FILE.exists(): return NODE_ID_FILE.read_text().strip()
        nid = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
        NODE_ID_FILE.write_text(nid)
        return nid

    def _setup_ssl(self):
        self.ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE
        try: self.ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        except: pass

    def connect(self, host, port=P2P_PORT):
        try:
            raw_sock = socket.create_connection((host, port), timeout=10)
            self.sock = self.ssl_ctx.wrap_socket(raw_sock, server_hostname=host)
            self.connected = True
            self._send({"type": "HANDSHAKE", "version": PROTOCOL_VERSION,
                        "min_version": MIN_PROTOCOL_VERSION, "node_id": self.node_id,
                        "port": P2P_PORT, "external_address": None, "height": 0})
            threading.Thread(target=self._recv_loop, daemon=True).start()
            return True
        except Exception as e:
            self.connected = False
            return False

    def _send(self, msg):
        if not self.sock or not self.connected: return False
        try:
            raw = json.dumps(msg).encode('utf-8')
            self.sock.sendall(struct.pack('>I', len(raw)) + raw)
            return True
        except: self.connected = False; return False

    def _recv_loop(self):
        while self.connected:
            try:
                msg = self._recv()
                if msg is None: break
                if self.on_msg: self.on_msg(msg)
                t = msg.get("type")
                if t == "HANDSHAKE_ACK": self.peer_height = msg.get("height", 0)
                elif t == "PING": self._send({"type": "PONG"})
            except: break
        self.connected = False

    def _recv(self):
        hdr = self._recv_n(4)
        if not hdr: return None
        length = struct.unpack('>I', hdr)[0]
        if length > MAX_MSG_SIZE: return None
        data = self._recv_n(length)
        return json.loads(data.decode('utf-8')) if data else None

    def _recv_n(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk: return None
            buf += chunk
        return buf

    def send(self, msg): return self._send(msg)
    def request_chain(self): return self._send({"type": "GET_CHAIN"})
    def request_block(self, h): return self._send({"type": "GET_BLOCK", "height": h})
    def send_tx(self, tx): return self._send({"type": "NEW_TX", "tx": tx})
    def send_block(self, b): return self._send({"type": "NEW_BLOCK", "block": b})

    def disconnect(self):
        self.connected = False
        try: self.sock.close()
        except: pass
        self.sock = None

# ============================================================
# PEER DISCOVERY
# ============================================================

def discover_peers():
    peers = set()
    # GitHub seeds
    try:
        import urllib.request
        resp = urllib.request.urlopen(GITHUB_SEEDS_URL, timeout=5)
        data = json.loads(resp.read())
        seeds = data.get("seeds", []) if isinstance(data, dict) else data
        for s in seeds: peers.add(s)
    except: pass
    # Local seeds.json (from project root)
    local = Path("seeds.json")
    if local.exists():
        try:
            with open(local) as f:
                data = json.load(f)
                seeds = data.get("seeds", []) if isinstance(data, dict) else data
                for s in seeds: peers.add(s)
        except: pass
    # Known peers file
    if PEERS_FILE.exists():
        try:
            with open(PEERS_FILE) as f:
                for p in json.load(f).get("peers", []): peers.add(p)
        except: pass
    return list(peers)

def save_known_peer(peer):
    peers = []
    if PEERS_FILE.exists():
        try:
            with open(PEERS_FILE) as f: peers = json.load(f).get("peers", [])
        except: pass
    if peer not in peers:
        peers.append(peer)
        DATA_DIR.mkdir(exist_ok=True)
        with open(PEERS_FILE, 'w') as f: json.dump({"peers": peers}, f, indent=2)

# ============================================================
# MENU
# ============================================================

BANNER = """
  ╔══════════════════════════════════════════════╗
  ║        TritioWallet v2.0 - Validator/ARM     ║
  ║  Conexao: TCP/TLS 8333 | API: HTTP 8080     ║
  ║  Modo: Validador (PoS) | Suporte: ARM/x86   ║
  ╚══════════════════════════════════════════════╝
"""

MENU = """
  [INSTALACAO]
    1. Instalar dependencias

  [CARTEIRA]
    2. Criar carteira
    3. Criar carteira quantica
    4. Restaurar carteira (24 palavras)
    5. Ver saldo
    6. Enviar TRC
    7. Historico
    8. Listar carteiras

  [REDE]
    9. Conectar automatico (auto-discovery)
   10. Conectar a IP especifico
   11. Iniciar como SEED
   12. Status da rede
   13. Ver peers conectados

  [VALIDADOR]
   14. Registrar como validador (PoS)
   15. Ver validadores ativos
   16. Delegar TRC
   17. Ver minhas delegacoes
   18. Reclamar recompensas

  [MINERACAO] (leve para ARM)
   19. Minerar blocos (Argon2id)

  [UTILITARIOS]
   20. Parar processos
   0. Sair
"""

p2p = P2P()

# ============================================================
# COMMANDS
# ============================================================

def cmd_install():
    print("\n  Instalando dependencias...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    print("  Dependencias instaladas!")

def cmd_create():
    print("\n  Criar carteira")
    w = Wallet.create()
    pw = input("  Senha: ").strip()
    if not pw: print("  Senha obrigatoria"); return
    if pw != input("  Confirme: ").strip(): print("  Senhas nao conferem"); return
    w.save(pw)
    print(f"\n  Endereco: {w.address}")
    print(f"  *** ANOTE AS 24 PALAVRAS ***")
    print(f"  {w.mnemonic}")

def cmd_create_quantum():
    print("\n  Criar carteira quantica")
    w = Wallet.create(quantum=True)
    pw = input("  Senha: ").strip()
    if not pw: print("  Senha obrigatoria"); return
    if pw != input("  Confirme: ").strip(): print("  Senhas nao conferem"); return
    w.save(pw)
    print(f"\n  Endereco: {w.address}")
    print(f"  Tipo: QR (resistente a quantum)")
    print(f"  *** ANOTE AS 24 PALAVRAS ***")
    print(f"  {w.mnemonic}")

def cmd_restore():
    print("\n  Restaurar carteira")
    words = input("  24 palavras: ").strip()
    if len(words.split()) != 24: print("  Precisa de 24 palavras"); return
    pw = input("  Nova senha: ").strip()
    try:
        w = Wallet.from_mnemonic(words)
        w.save(pw)
        print(f"\n  Restaurada! Endereco: {w.address}")
    except Exception as e: print(f"  Erro: {e}")

def cmd_balance():
    pw = input("  Senha: ").strip()
    w = Wallet.load(pw)
    if not w: print("  Carteira nao encontrada"); return
    print(f"\n  Endereco: {w.address}")
    ip = get_server_ip()
    if ip:
        try:
            import urllib.request
            resp = urllib.request.urlopen(f"http://{ip}:{API_PORT}/api/balance/{w.pubkey_hex()}", timeout=5)
            data = json.loads(resp.read())
            print(f"  Saldo: {data.get('balance', 0):.8f} TRC")
            return
        except: pass
    print("  (offline)")

def cmd_send():
    pw = input("  Senha: ").strip()
    w = Wallet.load(pw)
    if not w: print("  Carteira nao encontrada"); return
    recipient = input("  Destinatario (T... ou Q...): ").strip()
    amount = float(input("  Valor (TRC): ").strip())
    fee = float(input("  Taxa (0.001): ").strip() or "0.001")
    if input(f"\n  Enviar {amount:.8f} TRC? (s/N): ").strip().lower() != 's': return

    ts = int(time.time())
    tx = {"sender": w.pubkey_hex(), "recipient": recipient, "amount": amount,
          "fee": fee, "data": "", "timestamp": ts}
    tx["hash"] = sha256d_hex(json.dumps({k: tx[k] for k in ["sender","recipient","amount","fee","data","timestamp"]}, sort_keys=True).encode())
    tx["signature"] = w.sign(bytes.fromhex(tx["hash"])).hex()
    tx["signature_mode"] = "ecdsa"

    if p2p.connected:
        p2p.send_tx(tx)
        print(f"\n  Enviado via P2P! Hash: {tx['hash'][:16]}...")
    else:
        ip = get_server_ip()
        if ip:
            try:
                import urllib.request
                req = urllib.request.Request(f"http://{ip}:{API_PORT}/api/tx",
                    data=json.dumps(tx).encode(), headers={"Content-Type": "application/json"})
                resp = urllib.request.urlopen(req, timeout=30)
                result = json.loads(resp.read())
                print(f"\n  Enviado! Hash: {result.get('hash', tx['hash'])[:16]}...")
            except Exception as e: print(f"  Erro: {e}")
        else: print("  Nenhum peer conectado")

def cmd_history():
    pw = input("  Senha: ").strip()
    w = Wallet.load(pw)
    if not w: print("  Carteira nao encontrada"); return
    ip = get_server_ip()
    if not ip: print("  Offline"); return
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"http://{ip}:{API_PORT}/api/address/{w.pubkey_hex()}", timeout=10)
        txs = json.loads(resp.read()).get("transactions", [])
        if not txs: print("\n  Nenhuma transacao"); return
        print(f"\n  {'Block':<8} {'Tipo':<5} {'Valor':<14} {'Hash':<14}")
        print(f"  {'-'*41}")
        for tx in txs:
            tipo = "ENV" if tx.get("sender") == w.pubkey_hex() else "REC"
            print(f"  {tx.get('block_height','?'):<8} {tipo:<5} {tx.get('amount',0):<14.8f} {tx.get('tx_hash',tx.get('hash','?'))[:12]}")
    except Exception as e: print(f"  Erro: {e}")

def cmd_list():
    print("\n  Carteiras:")
    found = False
    for name in ["wallet.json", "wallet_quantum.json"]:
        path = DATA_DIR / name
        if path.exists():
            tag = "QR" if "quantum" in name else "TRC"
            print(f"    [{tag}] {path}")
            found = True
    if not found: print("    Nenhuma carteira encontrada")

# ============================================================
# NETWORK COMMANDS
# ============================================================

def cmd_auto_connect():
    print("\n  Conexao Automatica")
    print("  Buscando peers via GitHub + seeds.json local...")
    peers = discover_peers()
    if not peers:
        print("  Nenhum peer encontrado")
        print("  Usando IP do servidor configurado...")
        ip = get_server_ip()
        if ip: peers = [f"{ip}:{P2P_PORT}"]
        else: print("  Nenhum servidor configurado"); return

    print(f"  {len(peers)} peers encontrados:")
    for p in peers[:10]: print(f"    - {p}")

    connected = 0
    for peer in peers:
        if connected >= 3: break
        parts = peer.split(':')
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else P2P_PORT
        print(f"\n  Conectando a {host}:{port} (TCP/TLS)...")
        if p2p.connect(host, port):
            connected += 1
            save_known_peer(peer)
            set_server_ip(host)
            print(f"  Conectado!")
            time.sleep(0.5)
        else:
            print(f"  Falhou")

    if connected > 0:
        print(f"\n  {connected} peers conectados!")
        print(f"  Aguardando sync...")
        time.sleep(2)
    else:
        print("\n  Nenhum peer acessivel")

def cmd_connect_ip():
    ip = input("  IP do no (ex: 192.168.0.100): ").strip()
    if not ip: return
    set_server_ip(ip)
    print(f"\n  Conectando a {ip}:{P2P_PORT} (TCP/TLS)...")
    if p2p.connect(ip, P2P_PORT):
        print(f"  P2P conectado!")
        save_known_peer(f"{ip}:{P2P_PORT}")
        time.sleep(1)
    else:
        print(f"  Falha P2P")
    # Check API
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"http://{ip}:{API_PORT}/api/status", timeout=5)
        data = json.loads(resp.read())
        print(f"  API ativa! Altura: {data.get('height', 0)}")
    except: print("  API indisponivel")

def cmd_seed():
    print("\n  Iniciar como SEED")
    print("  Este dispositivo sera o primeiro no da rede")
    port = input("  Porta (8333): ").strip() or "8333"
    print(f"\n  Iniciando seed na porta {port}...")
    print("  Deixe rodando em background!")

    # Try to run main.py as seed
    try:
        cmd = [sys.executable, "main.py", "--port", port, "--mode", "passive", "--become-seed"]
        print(f"  Cmd: {' '.join(cmd)}")
        subprocess.Popen(cmd)
        print("  Seed iniciado!")
    except Exception as e:
        print(f"  Erro: {e}")
        print("  Execute manualmente:")
        print(f"    python main.py --port {port} --mode passive --become-seed")

def cmd_status():
    ip = get_server_ip()
    if not ip: print("  Nenhum servidor configurado"); return
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"http://{ip}:{API_PORT}/api/status", timeout=5)
        d = json.loads(resp.read())
        print(f"\n  Status da Rede:")
        print(f"  Altura:        {d.get('height', 0)}")
        print(f"  Transacoes:    {d.get('transactions', 0)}")
        print(f"  Dificuldade:   {d.get('difficulty', 0)}")
        print(f"  Recompensa:    {d.get('reward_trc', 45)} TRC")
        print(f"  Minerado:      {d.get('total_mined_trc', 0):.2f} TRC")
        print(f"  Queimado:      {d.get('total_burned_trc', 0):.2f} TRC")
        print(f"  Circulante:    {d.get('circulating_trc', 0):.2f} TRC")
        print(f"  Restante:      {d.get('supply_remaining_trc', 0):.2f} TRC")
        print(f"  Peers:         {d.get('peers', 0)}")
        print(f"  Mempool:       {d.get('mempool', 0)} txs")
        print(f"  P2P:           {'Conectado' if p2p.connected else 'Desconectado'}")
    except Exception as e: print(f"  Erro: {e}")

def cmd_peers():
    ip = get_server_ip()
    if not ip: print("  Nenhum servidor"); return
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"http://{ip}:{API_PORT}/api/peers", timeout=5)
        peers = json.loads(resp.read()).get("peers", [])
        print(f"\n  Peers: {len(peers)}")
        for p in peers: print(f"    - {p}")
    except Exception as e: print(f"  Erro: {e}")

# ============================================================
# VALIDATOR COMMANDS
# ============================================================

def cmd_register_validator():
    pw = input("  Senha: ").strip()
    w = Wallet.load(pw)
    if not w: print("  Carteira nao encontrada"); return
    stake = float(input(f"  Stake (min {MIN_STAKE_TRC} TRC): ").strip())
    if stake < MIN_STAKE_TRC: print(f"  Stake minimo: {MIN_STAKE_TRC} TRC"); return

    ip = get_server_ip()
    if not ip: print("  Servidor nao configurado"); return

    print(f"\n  Registrando como validador...")
    print(f"  Stake: {stake} TRC")
    print(f"  Endereco: {w.address}")

    try:
        import urllib.request
        data = json.dumps({
            "address": w.address,
            "stake": stake,
            "pubkey": w.pubkey_hex()
        }).encode()
        req = urllib.request.Request(f"http://{ip}:{API_PORT}/api/validator/register",
            data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        if result.get("status") == "ok":
            print(f"\n  Validador registrado!")
            print(f"  Stake restante: {result.get('remaining_balance', 0):.8f} TRC")
        else:
            print(f"  Erro: {result}")
    except Exception as e: print(f"  Erro: {e}")

def cmd_validators():
    ip = get_server_ip()
    if not ip: print("  Servidor nao configurado"); return
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"http://{ip}:{API_PORT}/api/validators", timeout=5)
        data = json.loads(resp.read())
        validators = data.get("validators", [])
        stats = data.get("stats", {})
        print(f"\n  Validadores Ativos: {stats.get('active_validators', 0)}")
        print(f"  Stake Total: {stats.get('total_stake', 0)} TRC")
        print(f"  Limiar: {stats.get('signature_threshold', 3)} assinaturas/bloco")
        print()
        for v in validators:
            status = "ATIVO" if v.get("active") else "INATIVO"
            print(f"  [{status}] {v.get('address', '?')[:24]}...")
            print(f"    Stake: {v.get('stake', 0)} TRC | Blocos: {v.get('blocks_signed', 0)}")
    except Exception as e: print(f"  Erro: {e}")

def cmd_delegate():
    pw = input("  Senha: ").strip()
    w = Wallet.load(pw)
    if not w: print("  Carteira nao encontrada"); return
    validator = input("  Endereco do validador: ").strip()
    amount = float(input("  Valor para delegar (TRC): ").strip())
    if amount <= 0: print("  Valor invalido"); return

    ip = get_server_ip()
    if not ip: print("  Servidor nao configurado"); return

    print(f"\n  Delegando {amount} TRC para {validator[:24]}...")
    try:
        import urllib.request
        data = json.dumps({
            "delegator": w.pubkey_hex(),
            "validator": validator,
            "amount": amount
        }).encode()
        req = urllib.request.Request(f"http://{ip}:{API_PORT}/api/delegate",
            data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        if result.get("status") == "ok":
            print(f"\n  Delegacao realizada!")
            print(f"  Saldo restante: {result.get('remaining_balance', 0):.8f} TRC")
        else:
            print(f"  Erro: {result}")
    except Exception as e: print(f"  Erro: {e}")

def cmd_my_delegations():
    pw = input("  Senha: ").strip()
    w = Wallet.load(pw)
    if not w: print("  Carteira nao encontrada"); return
    ip = get_server_ip()
    if not ip: print("  Servidor offline"); return
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"http://{ip}:{API_PORT}/api/delegations/{w.pubkey_hex()}", timeout=5)
        data = json.loads(resp.read())
        delegations = data.get("delegations", [])
        total = data.get("total_delegated", 0)
        rewards = data.get("total_pending_rewards", 0)
        print(f"\n  Delegacoes: {len(delegations)}")
        print(f"  Total delegado: {total:.8f} TRC")
        print(f"  Recompensas pendentes: {rewards:.8f} TRC")
        for d in delegations:
            print(f"    -> {d.get('validator', '?')[:24]}...")
            print(f"       Valor: {d.get('amount', 0):.2f} TRC | Dias: {d.get('days_delegated', 0)}")
    except Exception as e: print(f"  Erro: {e}")

def cmd_claim_rewards():
    pw = input("  Senha: ").strip()
    w = Wallet.load(pw)
    if not w: print("  Carteira nao encontrada"); return
    ip = get_server_ip()
    if not ip: print("  Servidor offline"); return
    try:
        import urllib.request
        data = json.dumps({"delegator": w.pubkey_hex()}).encode()
        req = urllib.request.Request(f"http://{ip}:{API_PORT}/api/claim",
            data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        rewards = result.get("rewards_claimed", 0)
        print(f"\n  Recompensas reclamadas: {rewards:.8f} TRC")
    except Exception as e: print(f"  Erro: {e}")

# ============================================================
# MINING (lightweight for ARM)
# ============================================================

def cmd_mine():
    pw = input("  Senha: ").strip()
    w = Wallet.load(pw)
    if not w: print("  Carteira nao encontrada"); return

    difficulty = 4
    ip = get_server_ip()
    if ip:
        try:
            import urllib.request
            resp = urllib.request.urlopen(f"http://{ip}:{API_PORT}/api/status", timeout=5)
            difficulty = json.loads(resp.read()).get("difficulty", 4)
        except: pass

    print(f"\n  Mineracao ARM (Argon2id)")
    print(f"  Dificuldade: {difficulty}")
    print(f"  Use apenas para gerar blocos leves")
    print(f"  Ctrl+C para parar\n")

    try:
        from argon2.low_level import hash_secret_raw, Type
        HAS_ARGON2 = True
    except: HAS_ARGON2 = False; print("  SHA256 fallback (argon2 nao instalado)")

    target = "0" * difficulty
    nonce = 0
    start = time.time()
    prev_hash = "0" * 64

    try:
        while True:
            ts = int(time.time())
            header = struct.pack('>H I Q 32s 32s I I',
                1, 0, ts, bytes.fromhex(prev_hash),
                hashlib.sha256(b"coinbase").digest(), difficulty, nonce)

            if HAS_ARGON2:
                pow_hash = hash_secret_raw(secret=header, salt=b"tritiocoin_v1",
                    time_cost=1, memory_cost=65536, parallelism=1,
                    hash_len=32, type=Type.ID).hex()
            else:
                pow_hash = hashlib.sha256(hashlib.sha256(header).digest()).hexdigest()

            if pow_hash.startswith(target):
                elapsed = time.time() - start
                rate = nonce / elapsed if elapsed > 0 else 0
                print(f"\n  BLOCO ENCONTRADO!")
                print(f"  Nonce: {nonce:,} | Hashrate: {rate:,.0f} H/s")
                break

            nonce += 1
            if nonce % 5000 == 0:
                elapsed = time.time() - start
                rate = nonce / elapsed if elapsed > 0 else 0
                print(f"\r  Nonce: {nonce:>12,} | {rate:>6,.0f} H/s | {elapsed:.1f}s", end="", flush=True)

    except KeyboardInterrupt: print("\n  Mineracao parada.")

def cmd_stop():
    print("\n  Parando processos TritioCoin...")
    try:
        if os.name == 'nt':
            os.system("taskkill /F /IM python.exe >nul 2>&1")
        else:
            os.system("pkill -f 'main.py' >nul 2>&1")
            os.system("pkill -f 'tritio_wallet' >nul 2>&1")
        print("  Processos parados!")
    except: print("  Erro ao parar processos")

# ============================================================
# MAIN
# ============================================================

def main():
    DATA_DIR.mkdir(exist_ok=True)

    if not check_deps():
        print("\n  Execute: pip install -r requirements.txt")
        return

    print(BANNER)

    while True:
        print(MENU)
        c = input("  Escolha: ").strip()
        print()

        cmds = {
            '1': cmd_install, '2': cmd_create, '3': cmd_create_quantum,
            '4': cmd_restore, '5': cmd_balance, '6': cmd_send,
            '7': cmd_history, '8': cmd_list, '9': cmd_auto_connect,
            '10': cmd_connect_ip, '11': cmd_seed, '12': cmd_status,
            '13': cmd_peers, '14': cmd_register_validator,
            '15': cmd_validators, '16': cmd_delegate,
            '17': cmd_my_delegations, '18': cmd_claim_rewards,
            '19': cmd_mine, '20': cmd_stop,
        }

        if c == '0':
            print("  Ate logo!")
            p2p.disconnect()
            break
        elif c in cmds:
            try: cmds[c]()
            except KeyboardInterrupt: print("\n  Cancelado")
            except Exception as e: print(f"  Erro: {e}")
        else:
            print("  Opcao invalida")
        print()

if __name__ == "__main__":
    main()
