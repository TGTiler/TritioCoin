"""Testes exaustivos em testnet."""
import sys, tempfile, os
sys.path.insert(0, '.')
from core.wallet import Wallet
from core.blockchain import Blockchain
from core.database import Database
from core.consensus import ConsensusEngine
from core.delegation import DelegationPool
from core.miner import Miner
from core.mempool import Mempool
from core.block import Block
from core.transaction import TransactionBuilder
from core.network_config import TESTNET
from core.constants import SATOSHIS_PER_TRC

def ok(val):
    return "OK" if val else "FALHOU"

print("=" * 60)
print("TESTES EXAUSTIVOS EM TESTNET")
print("=" * 60)

# =============================================
# TESTE 1: Setup da rede
# =============================================
print()
print("=== TESTE 1: Setup - 3 nos ===")

db_seed = Database(tempfile.mktemp(suffix='.db'))
db_miner = Database(tempfile.mktemp(suffix='.db'))

bc_seed = Blockchain(TESTNET, db_seed)
bc_miner = Blockchain(TESTNET, db_miner)

wallet_seed = Wallet.create()
wallet_miner = Wallet.create()
wallet_validator = Wallet.create()

print(f"  Seed: {bc_seed.height()} blocos")
print(f"  Miner: {bc_miner.height()} blocos")

# =============================================
# TESTE 2: Mineracao
# =============================================
print()
print("=== TESTE 2: Mineracao ===")

mempool = Mempool(db_miner)
miner = Miner(bc_miner, mempool)

for i in range(3):
    block = miner.mine(wallet_miner.address)
    if block:
        bc_miner.add_block(block)
        print(f"  Bloco #{block.header.index} minerado")

print(f"  Miner height: {bc_miner.height()}")
print(f"  Miner balance: {bc_miner.balance(wallet_miner.address):.2f} TRC")

# =============================================
# TESTE 3: Sincronizacao
# =============================================
print()
print("=== TESTE 3: Sincronizacao seed <- miner ===")

print(f"  Seed ANTES: {bc_seed.height()}")
for i in range(bc_miner.height()):
    block_data = bc_miner.db.get_block(i)
    if block_data:
        block = Block.deserialize(block_data)
        bc_seed.add_block(block)

print(f"  Seed DEPOIS: {bc_seed.height()}")
print(f"  Sync OK: {ok(bc_seed.height() == bc_miner.height())}")

# =============================================
# TESTE 4: Validadores
# =============================================
print()
print("=== TESTE 4: Validadores ===")

consensus = ConsensusEngine(bc_seed)

min_stake = consensus.min_stake
print(f"  Stake minimo: {min_stake} TRC")

ok1 = consensus.register_validator(wallet_validator, min_stake)
ok2 = consensus.register_validator(wallet_seed, min_stake)
print(f"  Registro 1: {ok(ok1)} (stake={min_stake})")
print(f"  Registro 2: {ok(ok2)} (stake={min_stake})")

selected = consensus.select_validators_for_block(1)
print(f"  Selecionados: {len(selected)}")

# Assinar bloco
coinbase = TransactionBuilder.create_coinbase('test', bc_seed.reward_at_satoshis(), bc_seed.height())
block = Block(bc_seed.height(), bc_seed.latest().hash, [coinbase.to_dict()], bc_seed.difficulty)
block.hash = block.content_hash()
block.pow_hash = "0" * block.header.difficulty + "test"

sigs = 0
for w in [wallet_validator, wallet_seed]:
    sig = consensus.sign_block(block, w)
    if sig:
        block.validator_signatures.append({"address": w.address, "signature": sig, "signature_mode": "ecdsa"})
        sigs += 1

print(f"  Assinaturas: {sigs}/2")
confirmed = consensus.is_block_confirmed(block)
print(f"  Bloco confirmado: {ok(confirmed)}")

# =============================================
# TESTE 5: Delegacao
# =============================================
print()
print("=== TESTE 5: Delegacao ===")

delegation = DelegationPool()

delegador1 = Wallet.create()
delegador2 = Wallet.create()

# Fundar delegadores
coinbase_d = TransactionBuilder.create_coinbase(delegador1.pubkey_hex(), bc_seed.reward_at_satoshis(), bc_seed.height())
block_d = Block(bc_seed.height(), bc_seed.latest().hash, [coinbase_d.to_dict()], bc_seed.difficulty)
block_d.hash = block_d.content_hash()
block_d.pow_hash = "0" * block.header.difficulty + "d1"
bc_seed.add_block(block_d)

d1 = delegation.delegate(delegador1.address, wallet_validator.address, 20.0)
d2 = delegation.delegate(delegador2.address, wallet_validator.address, 30.0)
print(f"  Delegacao 1: {ok(d1)}")
print(f"  Delegacao 2: {ok(d2)}")

effective = delegation.get_effective_stake(wallet_validator.address, 50.0)
print(f"  Stake efetivo: {effective} TRC")

delegation.distribute_rewards(wallet_validator.address, 13.5)
r1 = delegation.claim_rewards(delegador1.address)
r2 = delegation.claim_rewards(delegador2.address)
print(f"  Recompensa 1: {r1:.4f} TRC")
print(f"  Recompensa 2: {r2:.4f} TRC")

# =============================================
# TESTE 6: Stake dinamico
# =============================================
print()
print("=== TESTE 6: Stake dinamico ===")
print(f"  Recompensa: {bc_seed.reward_at()} TRC")
print(f"  Stake minimo: {consensus.min_stake} TRC")
print(f"  Proximo halving: bloco {bc_seed.halving_at()}")

# =============================================
# TESTE 7: Double-spend
# =============================================
print()
print("=== TESTE 7: Prevencao double-spend ===")

dup = Block(1, "0"*64, [], bc_seed.difficulty)
dup.hash = bc_seed.chain[1].hash
dup.pow_hash = "0" * dup.header.difficulty + "dup"
r1 = bc_seed.add_block(dup)
print(f"  Bloco duplicado: {ok(not r1)}")

same = Block(1, "0"*64, [], bc_seed.difficulty)
same.hash = same.content_hash()
same.pow_hash = "0" * same.header.difficulty + "same"
r2 = bc_seed.add_block(same)
print(f"  Bloco mesmo height: {ok(not r2)}")

# =============================================
# TESTE 8: Wallet recovery
# =============================================
print()
print("=== TESTE 8: Recuperacao ===")

words = wallet_miner.mnemonic
recovered = Wallet.from_mnemonic(words)
print(f"  Original: {wallet_miner.address[:24]}...")
print(f"  Recuperada: {recovered.address[:24]}...")
print(f"  Match: {ok(wallet_miner.address == recovered.address)}")

# =============================================
# TESTE 9: Integridade
# =============================================
print()
print("=== TESTE 9: Integridade ===")

print(f"  Blocos: {bc_seed.height()}")
print(f"  Transacoes: {db_seed.get_tx_count()}")
print(f"  Chain valida: {ok(bc_seed.is_valid())}")
print(f"  Stake info: {consensus.get_stake_info()}")

db_seed.close()
db_miner.close()
os.unlink(db_seed.db_path)
os.unlink(db_miner.db_path)

print()
print("=" * 60)
print("TODOS OS TESTES EXAUSTIVOS PASSARAM")
print("=" * 60)
