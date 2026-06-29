"""
TritioCoin Network Test
Creates 2 nodes (seed + miner), wallet, and mines for 2 minutes.
"""
import asyncio
import sys
import os
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.blockchain import Blockchain
from core.mempool import Mempool
from core.wallet import Wallet
from core.database import Database
from core.network_config import MAINNET

DATA_DIR = Path("tritiocoin_data")


async def run_test():
    print("=" * 60)
    print("  TRITIOCOIN NETWORK TEST")
    print("  2 Nodes + Carteira + Mineracao (2 minutos)")
    print("=" * 60)
    print()

    import shutil
    test_dir = DATA_DIR / "test_network"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)

    os.environ["TRC_PASSWORD"] = "TestPassword123"

    from main import TritioNode

    # 1. Create wallet
    print("[1/5] Criando carteira...")
    w = Wallet.create()
    password = "TestPassword123"
    wallet_path = test_dir / "wallet.json"
    w.save(str(wallet_path), password)
    print(f"  Endereco: {w.address}")
    print()

    # 2. Start seed node
    print("[2/5] Iniciando seed node (porta 18333)...")
    seed_config = {
        'host': '127.0.0.1',
        'port': 18333,
        'mode': 'passive',
        'difficulty': 2,
        'network': 'mainnet',
        'api': True,
        'api_port': 18080
    }
    seed_node = TritioNode(seed_config)
    seed_task = asyncio.create_task(seed_node.start())
    await asyncio.sleep(2)
    print("  Seed node rodando!")
    print()

    # 3. Start miner node (connects to seed)
    print("[3/5] Iniciando miner node (porta 18334)...")
    miner_config = {
        'host': '127.0.0.1',
        'port': 18334,
        'seed': '127.0.0.1:18333',
        'mode': 'miner',
        'difficulty': 2,
        'network': 'mainnet',
        'api': True,
        'api_port': 18081
    }
    miner_node = TritioNode(miner_config)
    miner_task = asyncio.create_task(miner_node.start())
    await asyncio.sleep(3)
    print("  Miner node rodando e conectado ao seed!")
    print()

    # 4. Mine for 2 minutes
    print("[4/5] Minerando por 2 minutos com TritioHash...")
    print(f"  Recompensa: 50 TRC (70% minerador = 35 TRC)")
    print(f"  Dificuldade: 2")
    print()

    from core.miner import Miner
    miner = Miner(miner_node.blockchain, miner_node.mempool)

    start_time = time.time()
    blocks_mined = 0

    def on_block(block):
        nonlocal blocks_mined
        block_data = f"{block.header.index}{block.hash}".encode()
        import hashlib
        sig = w.sign_tx(hashlib.sha256(block_data).digest())
        block.validator_signatures.append({
            "address": w.address,
            "signature": sig["ecdsa_signature"].hex(),
            "signature_mode": sig["signature_mode"]
        })
        if miner_node.blockchain.add_block(block):
            blocks_mined += 1
            elapsed = time.time() - start_time
            print(f"  Bloco #{block.header.index} minerado! "
                  f"Nonce={block.header.nonce} "
                  f"Hash={block.pow_hash[:16]}... "
                  f"({blocks_mined} blocos em {elapsed:.0f}s)")

    try:
        async def async_on_block(block):
            on_block(block)

        mining_task = asyncio.create_task(
            miner.mine_continuous(w.address, callback=async_on_block)
        )

        await asyncio.sleep(90)

        miner.stop()
        mining_task.cancel()
        try:
            await mining_task
        except asyncio.CancelledError:
            pass

    except KeyboardInterrupt:
        pass

    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print("  RESULTADO DO TESTE")
    print("=" * 60)
    print(f"  Blocos minerados: {blocks_mined}")
    print(f"  Tempo total: {elapsed:.0f} segundos")
    print(f"  Altura da chain: {miner_node.blockchain.height()}")
    print(f"  Saldo: {miner_node.blockchain.balance(w.address):.8f} TRC")
    print(f"  Algoritmo: TritioHash (Blake2b + 32MB memory-hard)")
    print("=" * 60)

    seed_task.cancel()
    miner_task.cancel()
    try:
        await seed_task
    except asyncio.CancelledError:
        pass
    try:
        await miner_task
    except asyncio.CancelledError:
        pass

    print()
    print("Limpando arquivos de teste...")
    shutil.rmtree(test_dir, ignore_errors=True)
    print("Concluido!")


if __name__ == "__main__":
    asyncio.run(run_test())
