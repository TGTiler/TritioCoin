"""
TritioCoin Mining Validator
============================

Detecta mineradores que modificam o algoritmo para obter vantagem injusta.

Capacidades:
1. Verificar se o PoW foi computado com TritioHash correto
2. Detectar transações trocadas após mineração
3. Verificar coinbase correta (70% do minerador)
4. Medir tempo de execução do TritioHash (32MB memory-hard deve levar >100ms)
5. Validar parâmetros da rede (dificuldade, recompensa, halving)
"""
import time
import logging
from typing import Dict, Any

from core.pow import tritio_hash, MEMORY_SIZE, READ_COUNT
from core.block import Block
from core.network_config import NetworkConfig, MAINNET
from core.constants import (
    SATOSHIS_PER_TRC, MAX_FUTURE_DRIFT, MAX_PAST_DRIFT,
    MAX_TX_AGE, BURN_RATE
)

logger = logging.getLogger("MiningValidator")

# Tempo mínimo esperado para TritioHash (32MB memory-hard + 128 reads)
# Em hardware normal, deve levar pelo menos 50ms
MIN_TRITIO_HASH_TIME_MS = 50

# Tempo máximo esperado (não deveria levar mais de 10 segundos)
MAX_TRITIO_HASH_TIME_MS = 10000


class MiningValidator:
    """
    Valida que um bloco segue todos os parâmetros da rede.

    Pode ser usado por qualquer node para auditar blocos de outros mineradores.
    """

    def __init__(self, config: NetworkConfig = None):
        self.config = config or MAINNET

    def validate_pow_integrity(self, block: Block) -> Dict[str, Any]:
        """
        Verifica que o PoW foi realmente computado com TritioHash.

        Detecta:
        - pow_hash forjado (prefixo válido mas hash real errado)
        - Implementação leve (sem 32MB memory-hard)
        - Algoritmo diferente (não TritioHash)
        """
        result = {
            "valid": True,
            "checks": {},
            "errors": []
        }

        # 1. Verificar se pow_hash existe
        if not block.pow_hash:
            result["valid"] = False
            result["errors"].append("Missing pow_hash")
            return result

        # 2. RECOMPUTAR tritio_hash(header.to_bytes())
        header_bytes = block.header.to_bytes()
        start_time = time.time()
        expected_pow_hash = tritio_hash(header_bytes)
        elapsed_ms = (time.time() - start_time) * 1000

        # 3. Comparar com pow_hash armazenado
        if block.pow_hash != expected_pow_hash:
            result["valid"] = False
            result["errors"].append(
                f"PoW hash mismatch: submitted={block.pow_hash[:16]}... "
                f"recomputed={expected_pow_hash[:16]}..."
            )
            result["checks"]["pow_hash_match"] = False
        else:
            result["checks"]["pow_hash_match"] = True

        # 4. Verificar prefixo de dificuldade
        difficulty = block.header.difficulty
        if not expected_pow_hash.startswith("0" * difficulty):
            result["valid"] = False
            result["errors"].append(
                f"PoW does not meet difficulty {difficulty}"
            )
            result["checks"]["difficulty_met"] = False
        else:
            result["checks"]["difficulty_met"] = True

        # 5. Medir tempo de recomputação (detectar implementação leve)
        result["checks"]["recompute_time_ms"] = round(elapsed_ms, 2)

        if elapsed_ms < MIN_TRITIO_HASH_TIME_MS:
            result["checks"]["timing_suspicious"] = True
            result["errors"].append(
                f"TritioHash too fast ({elapsed_ms:.1f}ms < {MIN_TRITIO_HASH_TIME_MS}ms). "
                f"Possible lightweight implementation."
            )
        else:
            result["checks"]["timing_suspicious"] = False

        return result

    def validate_merkle_integrity(self, block: Block) -> Dict[str, Any]:
        """
        Verifica que o merkle root no header corresponde às transações reais.

        Detecta:
        - Merkle root forjado
        - Transações trocadas após mineração
        """
        result = {
            "valid": True,
            "checks": {},
            "errors": []
        }

        # Recomputar merkle root
        expected_merkle = Block._merkle_root(block.transactions)

        if block.header.merkle_root != expected_merkle:
            result["valid"] = False
            result["errors"].append(
                f"Merkle root mismatch: header={block.header.merkle_root.hex()[:16]}... "
                f"computed={expected_merkle.hex()[:16]}..."
            )
            result["checks"]["merkle_match"] = False
        else:
            result["checks"]["merkle_match"] = True

        return result

    def validate_coinbase(self, block: Block) -> Dict[str, Any]:
        """
        Verifica que a recompensa coinbase está correta.

        Detecta:
        - Valor da coinbase manipulado (maior que 70%)
        - Mais de 1 coinbase por bloco
        - Coinbase sem destinatário
        """
        from core.transaction import Transaction

        result = {
            "valid": True,
            "checks": {},
            "errors": []
        }

        # Calcular recompensa esperada
        halvings = block.header.index // self.config.halving_interval
        expected_reward_sat = self.config.initial_reward_satoshis // (2 ** halvings)
        expected_reward_sat = max(expected_reward_sat, 1)
        miner_reward_sat = int(expected_reward_sat * 0.7)  # 70%

        # Contar coinbases e verificar valores
        coinbase_count = 0
        total_coinbase_sat = 0

        for tx_data in block.transactions:
            tx = Transaction.from_dict(tx_data)
            if tx.sender_pubkey == "COINBASE":
                coinbase_count += 1
                tx_amount_sat = int(round(tx.amount * SATOSHIS_PER_TRC))
                total_coinbase_sat += tx_amount_sat

                # Verificar valor exato
                if tx_amount_sat != miner_reward_sat:
                    result["valid"] = False
                    result["errors"].append(
                        f"Wrong coinbase amount: {tx_amount_sat} satoshis "
                        f"(expected {miner_reward_sat})"
                    )
                    result["checks"]["coinbase_amount"] = False

                # Verificar destinatário
                if not tx.recipient_pubkey:
                    result["valid"] = False
                    result["errors"].append("Coinbase with empty recipient")
                    result["checks"]["coinbase_recipient"] = False

        # Verificar quantidade de coinbases
        if coinbase_count > 1:
            result["valid"] = False
            result["errors"].append(f"Multiple coinbases: {coinbase_count}")
            result["checks"]["coinbase_count"] = False
        elif coinbase_count == 0:
            result["valid"] = False
            result["errors"].append("No coinbase transaction")
            result["checks"]["coinbase_count"] = False
        else:
            result["checks"]["coinbase_count"] = True

        result["checks"]["coinbase_count_value"] = coinbase_count
        result["checks"]["total_coinbase_satoshis"] = total_coinbase_sat

        return result

    def detect_lightweight_pow(self, block: Block) -> Dict[str, Any]:
        """
        Detecta implementação PoW leve (sem memory-hardness real).

        Mede o tempo de execução do TritioHash e compara com o esperado.
        Uma implementação correta com 32MB deve levar pelo menos 50ms.
        """
        result = {
            "valid": True,
            "checks": {},
            "errors": []
        }

        header_bytes = block.header.to_bytes()

        # Executar TritioHash e medir tempo
        start_time = time.time()
        computed_hash = tritio_hash(header_bytes)
        elapsed_ms = (time.time() - start_time) * 1000

        result["checks"]["execution_time_ms"] = round(elapsed_ms, 2)
        result["checks"]["expected_min_ms"] = MIN_TRITIO_HASH_TIME_MS

        # Verificar se é suspeitamente rápido
        if elapsed_ms < MIN_TRITIO_HASH_TIME_MS:
            result["valid"] = False
            result["errors"].append(
                f"TritioHash execution too fast ({elapsed_ms:.1f}ms). "
                f"Expected at least {MIN_TRITIO_HASH_TIME_MS}ms for 32MB memory-hard algorithm. "
                f"Possible lightweight or ASIC implementation."
            )
            result["checks"]["timing_suspicious"] = True
        else:
            result["checks"]["timing_suspicious"] = False

        # Verificar se o hash resultante é consistente
        if computed_hash != block.pow_hash:
            # Isso já é detectado em validate_pow_integrity
            pass

        return result

    def validate_network_params(self, block: Block, chain_height: int) -> Dict[str, Any]:
        """
        Verifica que o bloco segue parâmetros da rede.
        """
        result = {
            "valid": True,
            "checks": {},
            "errors": []
        }

        # 1. Timestamp não muito no futuro
        current_time = int(time.time())
        if block.header.timestamp > current_time + MAX_FUTURE_DRIFT:
            result["valid"] = False
            result["errors"].append(
                f"Timestamp too far in future: {block.header.timestamp} "
                f"(max {current_time + MAX_FUTURE_DRIFT})"
            )
            result["checks"]["timestamp_future"] = False
        else:
            result["checks"]["timestamp_future"] = True

        # 2. Dificuldade esperada
        expected_difficulty = self.config.difficulty  # Simplified
        if block.header.difficulty != expected_difficulty:
            result["checks"]["difficulty_match"] = False
            # Não necessariamente um erro, pode ser ajuste de dificuldade
        else:
            result["checks"]["difficulty_match"] = True

        # 3. Tamanho do bloco
        block_size = len(str(block.serialize()))
        max_block_size = 1_000_000  # 1MB
        if block_size > max_block_size:
            result["valid"] = False
            result["errors"].append(
                f"Block too large: {block_size} bytes (max {max_block_size})"
            )
            result["checks"]["block_size"] = False
        else:
            result["checks"]["block_size"] = True
            result["checks"]["block_size_bytes"] = block_size

        # 4. Nonce deve ser uint32 válido
        if not (0 <= block.header.nonce <= 0xFFFFFFFF):
            result["valid"] = False
            result["errors"].append(f"Invalid nonce: {block.header.nonce}")
            result["checks"]["nonce_valid"] = False
        else:
            result["checks"]["nonce_valid"] = True

        return result

    def full_audit(self, block: Block, chain_height: int = 0) -> Dict[str, Any]:
        """
        Auditoria completa do bloco.

        Retorna um dicionário com todos os resultados de validação.
        """
        results = {
            "block_height": block.header.index,
            "block_hash": block.hash[:16] if block.hash else "None",
            "pow_hash": block.pow_hash[:16] if block.pow_hash else "None",
            "checks": {},
            "errors": [],
            "overall_valid": True
        }

        # Executar todas as validações
        validations = [
            ("pow_integrity", self.validate_pow_integrity(block)),
            ("merkle_integrity", self.validate_merkle_integrity(block)),
            ("coinbase", self.validate_coinbase(block)),
            ("lightweight_detection", self.detect_lightweight_pow(block)),
            ("network_params", self.validate_network_params(block, chain_height)),
        ]

        for name, validation in validations:
            results["checks"][name] = validation["checks"]
            if not validation["valid"]:
                results["overall_valid"] = False
                results["errors"].extend(
                    [f"[{name}] {e}" for e in validation["errors"]]
                )

        results["total_checks"] = sum(
            len(v["checks"]) for _, v in validations
        )
        results["passed_checks"] = sum(
            1 for _, v in validations if v["valid"]
        )

        return results

    def quick_check(self, block: Block) -> bool:
        """
        Verificação rápida (apenas PoW integrity).

        Útil para filtragem inicial antes de auditoria completa.
        """
        result = self.validate_pow_integrity(block)
        return result["valid"]


def create_validator(config: NetworkConfig = None) -> MiningValidator:
    """Factory function para criar um MiningValidator."""
    return MiningValidator(config)
