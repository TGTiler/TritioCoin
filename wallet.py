"""
TritioCoin CLI Wallet
Commands: create, balance, send, history, info, list, peers, mine
"""
import sys
import os
import json
import time
import getpass
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.wallet import Wallet
from core.blockchain import Blockchain
from core.transaction import Transaction
from core.mempool import Mempool
from core.database import Database
from core.network_config import MAINNET

DATA_DIR = Path("tritiocoin_data")


def prompt_password(confirm=False) -> str:
    pw = getpass.getpass("Password: ")
    if confirm:
        pw2 = getpass.getpass("Confirm password: ")
        if pw != pw2:
            print("Passwords don't match!")
            sys.exit(1)
    return pw


def get_wallet(quantum=False, password=None) -> Wallet:
    name = "wallet_quantum.json" if quantum else "wallet.json"
    path = DATA_DIR / name
    if path.exists():
        try:
            return Wallet.load(str(path), password)
        except Exception as e:
            from cryptography.exceptions import InvalidTag
            if isinstance(e, InvalidTag):
                print("ERRO: Senha incorreta!")
                print("A carteira esta criptografada com outra senha.")
                sys.exit(1)
            raise
    print("ERRO: Carteira nao encontrada!")
    print(f"Arquivo esperado: {path}")
    print("Crie uma carteira primeiro: python wallet.py create")
    sys.exit(1)


def load_chain() -> Blockchain:
    db = Database(DATA_DIR / "mainnet.db")
    return Blockchain(MAINNET, db)


def connect_to_seed():
    """Connect to seed using full discovery system (GitHub + DHT + local)."""
    import socket
    import urllib.request

    all_peers = []

    # 1. Fetch from GitHub (updated seed list)
    try:
        response = urllib.request.urlopen(
            "https://raw.githubusercontent.com/TGTiler/TritioCoin/refs/heads/main/seeds.json",
            timeout=5
        )
        data = json.loads(response.read().decode())
        if isinstance(data, dict):
            github_seeds = data.get("seeds", [])
        else:
            github_seeds = data if isinstance(data, list) else []
        if github_seeds:
            all_peers.extend(github_seeds)
            print(f"  GitHub: {len(github_seeds)} seeds encontrados")
    except:
        pass

    # 2. Load local seeds.json
    seeds_file = DATA_DIR / "seeds.json"
    if seeds_file.exists():
        try:
            with open(seeds_file) as f:
                data = json.load(f)
                local_seeds = data.get("seeds", []) if isinstance(data, dict) else data
                if local_seeds:
                    all_peers.extend(local_seeds)
                    print(f"  Local: {len(local_seeds)} seeds")
        except:
            pass

    # 3. Check node status for running nodes
    status_file = DATA_DIR / "status.json"
    if status_file.exists():
        try:
            with open(status_file) as f:
                status = json.load(f)
                port = status.get("port", 8333)
                local_seed = f"127.0.0.1:{port}"
                if local_seed not in all_peers:
                    all_peers.append(local_seed)
                    print(f"  Local: node rodando na porta {port}")
        except:
            pass

    # Remove duplicates
    all_peers = list(dict.fromkeys(all_peers))

    if not all_peers:
        print("  Nenhum seed encontrado. Usando dados locais.")
        return False

    # Try to connect (keep trying until connected)
    print(f"  Buscando peers... ({len(all_peers)} candidatos)")
    connected = False
    attempts = 0
    max_attempts = 3

    while not connected and attempts < max_attempts:
        attempts += 1
        for seed in all_peers:
            try:
                host, port_str = seed.rsplit(":", 1)
                port = int(port_str)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((host, port))
                sock.close()
                if result == 0:
                    print(f"  Seed {seed} conectado!")
                    connected = True
                    # Save connected peer for future use
                    try:
                        save_connected_peer(seed)
                    except:
                        pass
                    break
            except:
                continue

        if not connected and attempts < max_attempts:
            print(f"  Tentativa {attempts}/{max_attempts}... tentando novamente em 2s")
            import time
            time.sleep(2)

    if not connected:
        print("  Nenhum seed disponivel. Usando dados locais.")
    return connected


def save_connected_peer(peer: str):
    """Save a connected peer to seeds.json for future use."""
    seeds_file = DATA_DIR / "seeds.json"
    seeds = []
    if seeds_file.exists():
        try:
            with open(seeds_file) as f:
                data = json.load(f)
                seeds = data.get("seeds", []) if isinstance(data, dict) else data
        except:
            pass

    if peer not in seeds:
        seeds.append(peer)
        DATA_DIR.mkdir(exist_ok=True)
        with open(seeds_file, "w") as f:
            json.dump({"seeds": seeds}, f, indent=2)


def atomic_write(path, data):
    tmp = str(path) + ".tmp"
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, str(path))


def cmd_create(args):
    quantum = '--quantum' in sys.argv
    print("Create a password to encrypt your wallet.")
    print("This protects your funds if someone steals the file.")
    print()
    password = prompt_password(confirm=True)

    w = Wallet.create(quantum)
    DATA_DIR.mkdir(exist_ok=True)
    name = "wallet_quantum.json" if quantum else "wallet.json"
    w.save(str(DATA_DIR / name), password)

    tag = "QR (quantum-resistant)" if quantum else "TRC (standard)"
    print()
    print(f"Wallet created [{tag}]")
    print(f"  Address:  {w.address}")
    print()
    print("  IMPORTANT: Save your recovery phrase!")
    print("  If you lose it, you lose your funds forever.")
    print()
    print(f"  Recovery phrase:")
    print(f"  {w.mnemonic}")
    print()
    print(f"  Saved to: {DATA_DIR / name}")
    print(f"  Encrypted: AES-256-GCM")


def cmd_recover(args):
    quantum = '--quantum' in sys.argv
    print("Recover wallet from recovery phrase.")
    print()
    words = input("Enter 24-word recovery phrase: ").strip()
    if len(words.split()) != 24:
        print("Error: Recovery phrase must be 24 words")
        return

    try:
        w = Wallet.from_mnemonic(words, quantum)
    except ValueError as e:
        print(f"Error: {e}")
        return

    print()
    print("Set a password to encrypt your wallet.")
    password = prompt_password(confirm=True)

    DATA_DIR.mkdir(exist_ok=True)
    name = "wallet_quantum.json" if quantum else "wallet.json"
    w.save(str(DATA_DIR / name), password)

    tag = "QR (quantum-resistant)" if quantum else "TRC (standard)"
    print()
    print(f"Wallet recovered [{tag}]")
    print(f"  Address:  {w.address}")
    print(f"  Saved to: {DATA_DIR / name}")


def cmd_balance(args):
    quantum = '--quantum' in sys.argv
    password = prompt_password()
    w = get_wallet(quantum, password)

    print("  Conectando para obter dados atualizados...")
    connect_to_seed()

    bc = load_chain()
    bal = bc.balance(w.pubkey_hex()) + bc.balance(w.address)
    print()
    print(f"  Address: {w.address}")
    print(f"  Balance: {bal:.8f} TRC")
    print(f"  Chain:   {bc.height()} blocks (local)")
    print()
    print("  Nota: Para dados em tempo real, inicie um node (opcao 8 ou 12)")


def broadcast_transaction(tx: Transaction) -> bool:
    """Broadcast transaction to the network. Tries local API, then seeds, then P2P."""
    import socket
    import ssl
    import struct

    tx_dict = tx.to_dict()

    # 1. Try local API (HTTP POST to 127.0.0.1:8080)
    try:
        import urllib.request
        import urllib.error
        data = json.dumps(tx_dict).encode('utf-8')
        req = urllib.request.Request(
            "http://127.0.0.1:8080/api/tx",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=3)
        result = json.loads(resp.read().decode())
        if result.get("status") == "ok":
            print(f"  Transacao enviada via node local!")
            return True
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        pass
    except Exception as e:
        logger.debug(f"Local API failed: {e}")

    # 2. Try to broadcast via P2P to each seed
    seeds = []
    try:
        response = urllib.request.urlopen(
            "https://raw.githubusercontent.com/TGTiler/TritioCoin/refs/heads/main/seeds.json",
            timeout=3
        )
        data = json.loads(response.read().decode())
        seeds = data.get("seeds", []) if isinstance(data, dict) else data if isinstance(data, list) else []
    except:
        pass

    seeds_file = DATA_DIR / "seeds.json"
    if seeds_file.exists():
        try:
            with open(seeds_file) as f:
                data = json.load(f)
                local_seeds = data.get("seeds", []) if isinstance(data, dict) else data
                for s in local_seeds:
                    if s not in seeds:
                        seeds.append(s)
        except:
            pass

    for seed in seeds:
        try:
            host, port_str = seed.rsplit(":", 1)
            port = int(port_str)

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            reader, writer = asyncio.run(_p2p_broadcast(host, port, tx_dict, ctx))
            if writer:
                print(f"  Transacao enviada via P2P para {seed}!")
                return True
        except Exception as e:
            logger.debug(f"P2P broadcast to {seed} failed: {e}")
            continue

    return False


async def _p2p_broadcast(host: str, port: int, tx_dict: dict, ssl_ctx):
    """Connect to a peer via P2P and broadcast a transaction."""
    import hashlib
    import struct

    node_id = hashlib.sha256(os.urandom(32)).hexdigest()[:32]

    reader, writer = await asyncio.open_connection(host, port, ssl=ssl_ctx)

    # Send handshake
    handshake = json.dumps({
        "type": "HANDSHAKE",
        "version": 2,
        "min_version": 1,
        "node_id": node_id,
        "port": 0,
        "external_address": None,
        "height": 0
    }).encode('utf-8')
    writer.write(struct.pack('>I', len(handshake)) + handshake)
    await writer.drain()

    # Read handshake response (with timeout)
    try:
        raw_len = await asyncio.wait_for(reader.readexactly(4), timeout=3)
        msg_len = struct.unpack('>I', raw_len)[0]
        raw_msg = await asyncio.wait_for(reader.readexactly(msg_len), timeout=3)
    except (asyncio.TimeoutError, asyncio.IncompleteReadError):
        writer.close()
        return reader, None

    # Send NEW_TX
    tx_msg = json.dumps({"type": "NEW_TX", "tx": tx_dict}).encode('utf-8')
    writer.write(struct.pack('>I', len(tx_msg)) + tx_msg)
    await writer.drain()

    writer.close()
    return reader, writer


def cmd_send(args):
    quantum = '--quantum' in sys.argv
    password = prompt_password()
    w = get_wallet(quantum, password)

    # Valores interativos
    recipient = input("  Endereco do destinatario: ").strip()
    if not recipient:
        print("  Cancelado.")
        return

    amount_str = input("  Valor (TRC): ").strip()
    if not amount_str:
        print("  Cancelado.")
        return
    try:
        amount = float(amount_str)
    except ValueError:
        print("  ERRO: Valor invalido!")
        return

    fee_str = input("  Taxa (padrao 0.001): ").strip()
    fee = float(fee_str) if fee_str else 0.001

    print("  Conectando a rede...")
    connect_to_seed()

    bc = load_chain()
    mempool = Mempool()

    bal = bc.balance(w.pubkey_hex()) + bc.balance(w.address)
    if bal < amount + fee:
        print(f"  ERRO: Saldo insuficiente! ({bal:.8f} < {amount + fee:.8f})")
        return

    tx = Transaction(w.pubkey_hex(), recipient, amount, fee)
    tx_data = bytes.fromhex(tx.compute_hash())
    sigs = w.sign_tx(tx_data)
    tx.signature = sigs["ecdsa_signature"]
    tx.quantum_signature = sigs.get("quantum_signature")
    tx.signature_mode = sigs["signature_mode"]
    tx.tx_hash = tx.compute_hash()

    if not tx.is_valid():
        print("  ERRO: Transacao invalida!")
        return

    # Save locally
    mempool.add(tx)

    DATA_DIR.mkdir(exist_ok=True)
    mempool_path = DATA_DIR / "mempool.json"
    existing = []
    if mempool_path.exists():
        with open(mempool_path) as f:
            existing = json.load(f)
    existing.append(tx.to_dict())
    with open(mempool_path, 'w') as f:
        json.dump(existing, f)

    # Broadcast to network
    print("  Enviando transacao para a rede...")
    sent = broadcast_transaction(tx)

    print()
    print(f"  Transacao criada com sucesso!")
    print(f"  De:       {w.address}")
    print(f"  Para:     {recipient}")
    print(f"  Valor:    {amount} TRC")
    print(f"  Taxa:     {fee} TRC")
    print(f"  Hash:     {tx.tx_hash[:32]}...")

    if sent:
        print(f"  Status:   Enviada para a rede!")
    else:
        print(f"  Status:   Salva localmente (nenhum node disponivel)")
        print(f"  Para confirmar, inicie um node: python main.py --mode passive")


def cmd_history(args):
    quantum = '--quantum' in sys.argv
    password = prompt_password()
    w = get_wallet(quantum, password)
    bc = load_chain()
    hist = bc.history(w.pubkey_hex()) + bc.history(w.address)
    if not hist:
        print("  Nenhuma transacao encontrada")
        return
    print(f"  Historico para {w.address[:24]}...")
    print(f"  {'Bloco':<8} {'De':<20} {'Para':<20} {'Valor':<12} {'Taxa':<8}")
    print("  " + "-" * 68)
    for h in sorted(hist, key=lambda x: x['block']):
        print(f"  {h['block']:<8} {h['from']:<20} {h['to']:<20} "
              f"{h['amount']:<12.4f} {h['fee']:<8.6f}")


def cmd_info(args):
    print("  Conectando a rede...")
    connect_to_seed()

    bc = load_chain()
    s = bc.stats()
    mined_pct = (s['circulating_satoshis'] / s['max_supply_satoshis']) * 100 if s['max_supply_satoshis'] > 0 else 0
    print()
    print("  TritioCoin Network Info")
    print(f"  Height:              {s['height']}")
    print(f"  Transactions:        {s['transactions']}")
    print(f"  Difficulty:          {s['difficulty']}")
    print(f"  Reward:              {s['reward_trc']:.8f} TRC")
    print(f"  Block Time:          ~5 minutes")
    print(f"  Total Mined:         {s['total_mined_trc']:.2f} / {s['max_supply_trc']:,.0f} TRC")
    print(f"  Total Burned:        {s['total_burned_trc']:.2f} TRC")
    print(f"  Circulating Supply:  {s['circulating_trc']:.2f} TRC ({mined_pct:.4f}%)")
    print(f"  Supply Remaining:    {s['supply_remaining_trc']:.2f} TRC")
    print(f"  Burn Rate:           {s['burn_rate']*100:.0f}% of fees")
    print(f"  Next Halving:        Block {s['next_halving']:,}")
    print(f"  Addresses:           {s['addresses']}")
    print(f"  Valid:               {'Yes' if s['valid'] else 'No'}")


def cmd_list(args):
    print("  Carteiras encontradas:")
    print()
    found = False
    for name in ["wallet.json", "wallet_quantum.json"]:
        path = DATA_DIR / name
        if path.exists():
            found = True
            tag = "QR (quantica)" if "quantum" in name else "TRC (padrao)"
            try:
                with open(path) as f:
                    data = json.load(f)
                addr = data.get("address", "?")
                print(f"  [{tag}]")
                print(f"    Arquivo: {name}")
                print(f"    Endereco: {addr}")
                print()
            except:
                print(f"  [{tag}] {name} (erro ao ler)")
                print()

    if not found:
        print("  Nenhuma carteira encontrada.")
        print("  Crie uma com: python wallet.py create")


def cmd_peers(args):
    print("  Conectando a rede...")
    connected = connect_to_seed()

    status_path = DATA_DIR / "status.json"
    if status_path.exists():
        with open(status_path) as f:
            status = json.load(f)

        print()
        print("  TritioCoin Node Status")
        print(f"  Port:      {status.get('port', '?')}")
        print(f"  Mode:      {status.get('mode', '?')}")
        print(f"  Role:      {status.get('role', 'peer')}")
        print(f"  Address:   {status.get('address', '?')}")
        print(f"  Height:    {status.get('height', '?')} blocks")
        print(f"  Difficulty: {status.get('difficulty', '?')}")
        print(f"  Mempool:   {status.get('mempool', 0)} txs")
        print(f"  Mining:    {'Yes' if status.get('is_mining') else 'No'}")
        print()

        peers = status.get('peers', [])
        count = status.get('peers_count', 0)
        print(f"  Connected Peers: {count}")
        if peers:
            for p in peers:
                print(f"    - {p}")
        else:
            print("    (nenhum)")
    else:
        print()
        print("  Nenhum node rodando.")
        print("  Inicie com: python main.py --mode passive")


def cmd_mine(args):
    quantum = '--quantum' in sys.argv
    threads = 1
    for arg in args:
        if arg.startswith('--threads='):
            threads = int(arg.split('=')[1])

    password = prompt_password()
    w = get_wallet(quantum, password)
    bc = load_chain()
    mempool = Mempool()

    mempool_path = DATA_DIR / "mempool.json"
    if mempool_path.exists():
        with open(mempool_path) as f:
            for tx_data in json.load(f):
                tx = Transaction.from_dict(tx_data)
                mempool.add(tx)

    from core.miner import Miner
    miner = Miner(bc, mempool, threads=threads)

    import hashlib

    def on_block_found(block):
        block_data = f"{block.header.index}{block.hash}".encode()
        sig = w.sign_tx(hashlib.sha256(block_data).digest())
        block.validator_signatures.append({
            "address": w.address,
            "signature": sig["ecdsa_signature"].hex(),
            "signature_mode": sig["signature_mode"]
        })
        if bc.add_block(block):
            DATA_DIR.mkdir(exist_ok=True)
            atomic_write(DATA_DIR / "blockchain.json", bc.serialize())
            print(f"\n  Saldo: {bc.balance(w.address):.8f} TRC")

    print(f"\n  Endereco: {w.address}")
    print(f"  Altura da chain: {bc.height()}")
    print(f"  Transacoes pendentes: {mempool.size()}")
    print(f"  Threads: {threads}")

    try:
        async def async_on_block(block):
            on_block_found(block)

        asyncio.run(miner.mine_continuous(w.address, callback=async_on_block))
    except KeyboardInterrupt:
        miner.stop()


CMDS = {
    'create': cmd_create,
    'recover': cmd_recover,
    'balance': cmd_balance,
    'send': cmd_send,
    'history': cmd_history,
    'info': cmd_info,
    'list': cmd_list,
    'mine': cmd_mine,
    'peers': cmd_peers,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print("TritioCoin Wallet CLI")
        print()
        print("Usage: python wallet.py <command> [args] [--quantum]")
        print()
        print("Commands:")
        print("  create              Create a new wallet (shows mnemonic)")
        print("  recover             Recover wallet from mnemonic")
        print("  balance             Show wallet balance")
        print("  send                Send TRC to address")
        print("  history             Show transaction history")
        print("  info                Show network info")
        print("  list                List all wallets")
        print("  mine                Mine blocks")
        print("  peers               Show connected peers")
        print()
        print("Options:")
        print("  --quantum           Use quantum-resistant mode (QR)")
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]
    filtered = [a for a in args if a != '--quantum']
    CMDS[cmd](filtered)


if __name__ == "__main__":
    main()
