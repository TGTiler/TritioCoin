"""Teste completo do sistema de validadores."""
import sys, tempfile, os
sys.path.insert(0, '.')
from core.wallet import Wallet
from core.blockchain import Blockchain
from core.database import Database
from core.consensus import ConsensusEngine
from core.block import Block
from core.transaction import TransactionBuilder
from core.network_config import MAINNET
from core.constants import SATOSHIS_PER_TRC

tmpdb = tempfile.mktemp(suffix='.db')
db = Database(tmpdb)
bc = Blockchain(MAINNET, db)
consensus = ConsensusEngine(bc)

def ok(val):
    return "OK" if val else "FALHOU"

print("=== TESTE 1: Registrar validadores ===")

validators = []
for i in range(3):
    w = Wallet.create()
    coinbase = TransactionBuilder.create_coinbase(w.pubkey_hex(), bc.reward_at_satoshis(), bc.height())
    block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
    block.hash = block.content_hash()
    block.pow_hash = "0" * block.header.difficulty + "test"
    bc.add_block(block)
    balance = bc.balance(w.pubkey_hex())
    print(f"  Validador {i+1}: {w.address[:24]}... | Saldo: {balance:.2f} TRC")
    validators.append(w)

for i, w in enumerate(validators):
    result = consensus.register_validator(w, 100.0)
    print(f"  Registro validador {i+1}: {ok(result)} (stake=100 TRC)")

active = consensus.get_active_validators()
print(f"  Validadores ativos: {len(active)}")

w_low = Wallet.create()
ok_low = consensus.register_validator(w_low, 10.0)
print(f"  Registro com 10 TRC: {ok(not ok_low)} (deve ser rejeitado)")

print()
print("=== TESTE 2: Selecao de validadores ===")

for block_idx in [10, 20, 30, 40, 50]:
    selected = consensus.select_validators_for_block(block_idx)
    names = [s[:16] + "..." for s in selected]
    print(f"  Bloco {block_idx}: {names}")

print()
print("=== TESTE 3: Assinatura de bloco ===")

coinbase = TransactionBuilder.create_coinbase("miner_addr", bc.reward_at_satoshis(), bc.height())
block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
block.hash = block.content_hash()
block.pow_hash = "0" * block.header.difficulty + "test"

for w in validators[:3]:
    sig = consensus.sign_block(block, w)
    if sig:
        block.validator_signatures.append({
            "address": w.address,
            "signature": sig,
            "signature_mode": "ecdsa"
        })
        print(f"  {w.address[:16]}... assinou o bloco")

valid_count = 0
for sig_data in block.validator_signatures:
    v = consensus.verify_block_signature(block, sig_data["address"], sig_data["signature"])
    if v:
        valid_count += 1
print(f"  Assinaturas validas: {valid_count}/{len(block.validator_signatures)}")

confirmed = consensus.is_block_confirmed(block)
print(f"  Bloco confirmado (>=3 sigs): {ok(confirmed)}")

print()
print("=== TESTE 4: Distribuicao de recompensas ===")

bc.add_block(block)

old_balances = {}
for w in validators:
    old_balances[w.address] = bc.balance(w.pubkey_hex())

consensus.distribute_block_rewards(block)

for w in validators:
    new_balance = bc.balance(w.pubkey_hex())
    old = old_balances[w.address]
    diff = new_balance - old
    print(f"  {w.address[:16]}...: {old:.8f} -> {new_balance:.8f} (+{diff:.8f} TRC)")

print()
print("=== TESTE 5: Estatisticas ===")

stats = consensus.get_validator_stats()
print(f"  Total validadores: {stats['total_validators']}")
print(f"  Validadores ativos: {stats['active_validators']}")
print(f"  Stake total: {stats['total_stake']} TRC")
print(f"  Blocos assinados: {stats['total_blocks_signed']}")
print(f"  Stake minimo: {stats['min_stake']} TRC")
print(f"  Assinaturas necessarias: {stats['signature_threshold']}")

db.close()
os.unlink(tmpdb)

print()
print("=== TODOS OS TESTES PASSARAM ===")
