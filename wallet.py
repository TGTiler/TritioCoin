"""
TritioCoin CLI Wallet
Commands: create, balance, send, history, info, list, peers
"""
import sys
import os
import json
import time
import getpass
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
    """Prompt user for password."""
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
            error_str = str(e)
            if "InvalidTag" in error_str or "decrypt" in error_str.lower():
                print("ERRO: Senha incorreta!")
                print("A carteira esta criptografada com outra senha.")
                print("Tente novamente com a senha correta.")
                sys.exit(1)
            raise
    w = Wallet.create(quantum)
    DATA_DIR.mkdir(exist_ok=True)
    return w


def load_chain() -> Blockchain:
    db = Database(DATA_DIR / "mainnet.db")
    return Blockchain(MAINNET, db)


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
    return w


def cmd_recover(args):
    """Recover wallet from mnemonic."""
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
    bc = load_chain()
    bal = bc.balance(w.pubkey_hex()) + bc.balance(w.address)
    print(f"Address: {w.address}")
    print(f"Balance: {bal:.8f} TRC")
    print(f"Chain:   {bc.height()} blocks")


def cmd_send(args):
    if len(args) < 2:
        print("Usage: wallet.py send <recipient> <amount> [fee]")
        return
    recipient = args[0]
    amount = float(args[1])
    fee = float(args[2]) if len(args) > 2 else 0.001

    quantum = '--quantum' in sys.argv
    password = prompt_password()
    w = get_wallet(quantum, password)
    bc = load_chain()
    mempool = Mempool()

    bal = bc.balance(w.pubkey_hex())
    if bal < amount + fee:
        print(f"Insufficient funds: {bal:.8f} < {amount + fee:.8f}")
        return

    tx = Transaction(w.pubkey_hex(), recipient, amount, fee)
    tx_data = bytes.fromhex(tx.compute_hash())
    sigs = w.sign_tx(tx_data)
    tx.signature = sigs["ecdsa_signature"]
    tx.quantum_signature = sigs.get("quantum_signature")
    tx.signature_mode = sigs["signature_mode"]
    tx.tx_hash = tx.compute_hash()

    if not tx.is_valid():
        print("Transaction validation failed")
        return

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

    print(f"Transaction created: {tx}")
    print(f"  From:     {w.address}")
    print(f"  To:       {recipient}")
    print(f"  Amount:   {amount} TRC")
    print(f"  Fee:      {fee} TRC")
    print(f"  Mode:     {tx.signature_mode}")
    print(f"  Hash:     {tx.tx_hash[:32]}...")


def cmd_history(args):
    quantum = '--quantum' in sys.argv
    password = prompt_password()
    w = get_wallet(quantum, password)
    bc = load_chain()
    hist = bc.history(w.pubkey_hex()) + bc.history(w.address)
    if not hist:
        print("No transactions found")
        return
    print(f"Transaction history for {w.address[:24]}...")
    print(f"{'Block':<8} {'From':<20} {'To':<20} {'Amount':<12} {'Fee':<8}")
    print("-" * 68)
    for h in sorted(hist, key=lambda x: x['block']):
        print(f"{h['block']:<8} {h['from']:<20} {h['to']:<20} "
              f"{h['amount']:<12.4f} {h['fee']:<8.6f}")


def cmd_info(args):
    bc = load_chain()
    s = bc.stats()
    mined_pct = (s['circulating_satoshis'] / s['max_supply_satoshis']) * 100 if s['max_supply_satoshis'] > 0 else 0
    print("TritioCoin Network Info")
    print(f"  Height:              {s['height']}")
    print(f"  Transactions:        {s['transactions']}")
    print(f"  Difficulty:          {s['difficulty']}")
    print(f"  Reward:              {s['reward_trc']:.8f} TRC ({s['reward_satoshis']:,} sat)")
    print(f"  Block Time:          ~5 minutes")
    print(f"  Total Mined:         {s['total_mined_trc']:.2f} / {s['max_supply_trc']:,.0f} TRC")
    print(f"  Total Burned:        {s['total_burned_trc']:.2f} TRC")
    print(f"  Circulating Supply:  {s['circulating_trc']:.2f} TRC ({mined_pct:.4f}%)")
    print(f"  Supply Remaining:    {s['supply_remaining_trc']:.2f} TRC")
    print(f"  Burn Rate:           {s['burn_rate']*100:.0f}% of fees")
    print(f"  Next Halving:        Block {s['next_halving']:,}")
    print(f"  Halving Interval:    190,000 blocks")
    print(f"  Addresses:           {s['addresses']}")
    print(f"  Valid:               {'Yes' if s['valid'] else 'No'}")


def cmd_list(args):
    for name in ["wallet.json", "wallet_quantum.json"]:
        path = DATA_DIR / name
        if path.exists():
            print(f"[{'QR' if 'quantum' in name else 'TRC'}] {name}")


def cmd_mine(args):
    quantum = '--quantum' in sys.argv
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
    miner = Miner(bc, mempool)

    print(f"Mining with address: {w.address}")
    print(f"Chain height: {bc.height()}")
    print(f"Mempool: {mempool.size()} transactions")
    print("Mining... (Ctrl+C to stop)")

    import hashlib
    try:
        while True:
            block = miner.mine(w.pubkey_hex())
            if block:
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
                    print(f"Block #{block.header.index} mined! Hash: {block.hash[:32]}...")
                    print(f"Balance: {bc.balance(w.pubkey_hex()):.8f} TRC")
    except KeyboardInterrupt:
        print("\nMining stopped")


def atomic_write(path, data):
    tmp = str(path) + ".tmp"
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, str(path))


def cmd_peers(args):
    """Show connected peers in real-time."""
    status_path = DATA_DIR / "status.json"
    if not status_path.exists():
        print("No node running. Start with: python main.py")
        return

    with open(status_path) as f:
        status = json.load(f)

    print("TritioCoin Node Status")
    print(f"  Port:     {status.get('port', '?')}")
    print(f"  Mode:     {status.get('mode', '?')}")
    print(f"  Role:     {status.get('role', 'peer')}")
    print(f"  Address:  {status.get('address', '?')}")
    print(f"  Height:   {status.get('height', '?')} blocks")
    print(f"  Difficulty: {status.get('difficulty', '?')}")
    print(f"  Mempool:  {status.get('mempool', 0)} txs")
    print(f"  Mining:   {'Yes' if status.get('is_mining') else 'No'}")
    print()

    peers = status.get('peers', [])
    count = status.get('peers_count', 0)
    print(f"  Connected Peers: {count}")
    if peers:
        for p in peers:
            print(f"    - {p}")
    else:
        print("    (none)")


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
        print("  send <to> <amt> [fee]  Send TRC to address")
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
