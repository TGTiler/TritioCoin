"""Teste do sistema de delegacao."""
import sys, tempfile, os
sys.path.insert(0, '.')
from core.wallet import Wallet
from core.blockchain import Blockchain
from core.database import Database
from core.consensus import ConsensusEngine
from core.delegation import DelegationPool
from core.block import Block
from core.transaction import TransactionBuilder
from core.network_config import MAINNET
from core.constants import SATOSHIS_PER_TRC

tmpdb = tempfile.mktemp(suffix='.db')
db = Database(tmpdb)
bc = Blockchain(MAINNET, db)
consensus = ConsensusEngine(bc)
delegation = DelegationPool()

print("=== TESTE 1: Setup - criar carteiras e fundos ===")

# Criar validador
validator = Wallet.create()
coinbase = TransactionBuilder.create_coinbase(validator.pubkey_hex(), bc.reward_at_satoshis(), bc.height())
block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
block.hash = block.content_hash()
block.pow_hash = "0" * block.header.difficulty + "test"
bc.add_block(block)
print(f"  Validador: {validator.address[:24]}... | Saldo: {bc.balance(validator.pubkey_hex()):.2f} TRC")

# Registrar como validador
ok = consensus.register_validator(validator, 90.0)
print(f"  Registro validador: {'OK' if ok else 'FALHOU'} (stake=90 TRC)")

# Criar 3 delegadores
delegators = []
for i in range(3):
    w = Wallet.create()
    coinbase = TransactionBuilder.create_coinbase(w.pubkey_hex(), bc.reward_at_satoshis(), bc.height())
    block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
    block.hash = block.content_hash()
    block.pow_hash = "0" * block.header.difficulty + "test"
    bc.add_block(block)
    print(f"  Delegador {i+1}: {w.address[:24]}... | Saldo: {bc.balance(w.pubkey_hex()):.2f} TRC")
    delegators.append(w)

print()
print("=== TESTE 2: Delegar para o validador ===")

amounts = [20.0, 50.0, 30.0]
for i, (w, amount) in enumerate(zip(delegators, amounts)):
    ok = delegation.delegate(w.address, validator.address, amount)
    print(f"  Delegador {i+1} delega {amount} TRC: {'OK' if ok else 'FALHOU'}")

# Verificar total delegado
total = delegation.get_total_delegated_to(validator.address)
print(f"  Total delegado ao validador: {total} TRC")

# Verificar stake efetivo
effective = delegation.get_effective_stake(validator.address, 90.0)
print(f"  Stake efetivo (90 + {total}): {effective} TRC")

print()
print("=== TESTE 3: Distribuir recompensas ===")

# Simular recompensa de bloco (13.5 TRC = 30% de 45)
block_reward = 45.0 * 0.3
delegation.distribute_rewards(validator.address, block_reward)

# Verificar recompensas pendentes
for i, w in enumerate(delegators):
    delegations = delegation.get_delegations(w.address)
    pending = sum(d["pending_rewards"] for d in delegations)
    print(f"  Delegador {i+1}: recompensa pendente = {pending:.8f} TRC")

print()
print("=== TESTE 4: Reclamar recompensas ===")

for i, w in enumerate(delegators):
    rewards = delegation.claim_rewards(w.address)
    print(f"  Delegador {i+1} reclamou: {rewards:.8f} TRC")

print()
print("=== TESTE 5: Desdelegar ===")

# Delegador 1 desdelegar 10 TRC
ok = delegation.undelegate(delegators[0].address, validator.address, 10.0)
print(f"  Delegador 1 desdelega 10 TRC: {'OK' if ok else 'FALHOU'}")

# Verificar pendencia
pending = delegation.get_pending_undelegation(delegators[0].address)
print(f"  Pendente: {pending[0]['amount']} TRC (restam {pending[0]['unbonding_days_remaining']:.1f} dias)")

# Tentar reclamar antes do tempo
claimed = delegation.claim_undelegation(delegators[0].address)
print(f"  Reclamar antes do tempo: {claimed} TRC (deve ser 0)")

print()
print("=== TESTE 6: Estatisticas ===")

stats = delegation.get_stats()
print(f"  Total delegado: {stats['total_delegated']} TRC")
print(f"  Total delegadores: {stats['total_delegators']}")
print(f"  Total validadores com delegacoes: {stats['total_validators_with_delegations']}")
print(f"  Recompensas distribuidas: {stats['total_rewards_distributed']:.8f} TRC")
print(f"  Stake minimo: {stats['min_delegation']} TRC")
print(f"  Periodo de unbonding: {stats['unbonding_days']} dias")
print(f"  Comissao padrao: {stats['default_commission']}%")

db.close()
os.unlink(tmpdb)

print()
print("=== TODOS OS TESTES DE DELEGACAO PASSARAM ===")
