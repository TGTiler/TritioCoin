import hashlib
import time
import logging
import ecdsa
from typing import List, Dict, Optional
from core.block import Block
from core.blockchain import Blockchain
from core.wallet import Wallet

logger = logging.getLogger("Consensus")


class Validator:
    """Representa um validador na rede (ESP32, ARM, ou qualquer dispositivo leve)."""

    def __init__(self, wallet: Wallet, stake: float = 0.0):
        self.wallet = wallet
        self.stake = stake
        self.address = wallet.address
        self.pubkey_hex = wallet.pubkey_hex()
        self.is_active = False
        self.blocks_signed = 0
        self.last_active = 0

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "pubkey": self.pubkey_hex,
            "stake": self.stake,
            "active": self.is_active,
            "blocks_signed": self.blocks_signed
        }


class ConsensusEngine:
    """
    Motor de consenso Proof-of-Stake (PoS) TritioCoin.
    Permite que dispositivos leves (ESP32, ARM) atuem como validadores.
    Anti-ASIC: validadores assinam blocos com ECDSA, sem necessidade de poder computacional.
    """

    def __init__(self, blockchain: Blockchain):
        self.blockchain = blockchain
        self.validators: Dict[str, Validator] = {}
        self.min_stake = 100.0  # stake mínimo para ser validador
        self.epoch_length = 50  # blocos por epoch
        self.signature_threshold = 3  # assinaturas mínimas para confirmar bloco

    def register_validator(self, wallet: Wallet, stake: float) -> bool:
        """Registra um novo validador na rede."""
        if stake < self.min_stake:
            logger.warning(f"Stake insuficiente: {stake} < {self.min_stake} TRC")
            return False

        if wallet.address in self.validators:
            logger.warning(f"Validador {wallet.address[:16]}... já registrado")
            return False

        validator = Validator(wallet, stake)
        validator.is_active = True
        self.validators[wallet.address] = validator

        logger.info(f"Validador registrado: {wallet.address[:16]}... | Stake: {stake} TRC")
        return True

    def unregister_validator(self, address: str) -> bool:
        """Remove um validador da rede."""
        if address in self.validators:
            del self.validators[address]
            logger.info(f"Validador removido: {address[:16]}...")
            return True
        return False

    def add_stake(self, address: str, amount: float) -> bool:
        """Adiciona stake a um validador existente."""
        if address not in self.validators:
            return False
        self.validators[address].stake += amount
        logger.info(f"Stake adicionado: {amount} TRC para {address[:16]}...")
        return True

    def select_validators_for_block(self, block_index: int) -> List[str]:
        """
        Seleciona validadores para assinar um bloco usando selecao ponderada por stake.
        """
        active_validators = [v for v in self.validators.values() if v.is_active]
        if not active_validators:
            return []

        total_stake = sum(v.stake for v in active_validators)
        if total_stake == 0:
            return []

        num_select = min(5, max(3, len(active_validators)))
        selected = []

        # Seed unica para todas as iteracoes
        seed = hashlib.sha256(str(block_index).encode()).digest()

        for i in range(num_select):
            # Usa bytes diferentes para cada selecao
            offset = (i * 4) % len(seed)
            chunk = seed[offset:offset+4]
            if len(chunk) < 4:
                chunk = chunk + seed[:4-len(chunk)]
            rng = int.from_bytes(chunk, 'big')
            weighted = rng % int(total_stake * 1000)

            cumulative = 0
            for v in active_validators:
                cumulative += v.stake * 1000
                if cumulative > weighted:
                    if v.address not in selected:
                        selected.append(v.address)
                    break

        return selected

    def sign_block(self, block: Block, validator_wallet: Wallet) -> Optional[str]:
        """
        Um validador assina um bloco com sua chave privada.
        Retorna a assinatura em hex ou None se falhar.
        """
        try:
            # Dados do bloco para assinar
            block_data = f"{block.header.index}{block.hash}".encode()
            block_hash = hashlib.sha256(block_data).digest()

            # Assina com ECDSA
            signature = validator_wallet.private_key.sign(block_hash)

            # Verifica se é um validador registrado
            validator_addr = validator_wallet.address
            if validator_addr in self.validators:
                self.validators[validator_addr].blocks_signed += 1
                self.validators[validator_addr].last_active = int(time.time())

            logger.info(f"Bloco #{block.header.index} assinado por {validator_addr[:16]}...")
            return signature.hex()

        except Exception as e:
            logger.error(f"Erro ao assinar bloco: {e}")
            return None

    def verify_block_signature(self, block: Block, validator_address: str, signature_hex: str) -> bool:
        """Verifica a assinatura de um validador em um bloco."""
        if validator_address not in self.validators:
            return False

        validator = self.validators[validator_address]
        try:
            vk_bytes = bytes.fromhex(validator.pubkey_hex)
            vk = ecdsa.VerifyingKey.from_string(vk_bytes, curve=ecdsa.SECP256k1)

            block_data = f"{block.header.index}{block.hash}".encode()
            block_hash = hashlib.sha256(block_data).digest()

            signature = bytes.fromhex(signature_hex)
            return vk.verify(signature, block_hash)

        except Exception:
            return False

    def is_block_confirmed(self, block: Block) -> bool:
        """
        Verifica se um bloco tem assinaturas suficientes para ser considerado confirmado.
        """
        signatures = block.validator_signatures
        valid_count = 0

        for sig_data in signatures:
            if self.verify_block_signature(block, sig_data["address"], sig_data["signature"]):
                valid_count += 1

        return valid_count >= self.signature_threshold

    def get_active_validators(self) -> List[Dict]:
        """Retorna lista de validadores ativos."""
        return [v.to_dict() for v in self.validators.values() if v.is_active]

    def get_validator_stats(self) -> dict:
        """Retorna estatísticas dos validadores."""
        active = [v for v in self.validators.values() if v.is_active]
        total_stake = sum(v.stake for v in active)
        total_signed = sum(v.blocks_signed for v in self.validators.values())

        return {
            "total_validators": len(self.validators),
            "active_validators": len(active),
            "total_stake": total_stake,
            "total_blocks_signed": total_signed,
            "min_stake": self.min_stake,
            "signature_threshold": self.signature_threshold
        }

    def distribute_block_rewards(self, block: Block):
        """Distribui recompensas entre os validadores que assinaram o bloco."""
        if not block.validator_signatures:
            return

        from core.constants import trc_to_satoshis

        reward_per_validator = self.blockchain.reward_at() * 0.3
        share = reward_per_validator / len(block.validator_signatures)
        share_sat = trc_to_satoshis(share)

        for sig_data in block.validator_signatures:
            addr = sig_data["address"]
            if addr in self.validators:
                self.validators[addr].stake += share
                # Persist in database
                current = self.blockchain.db.get_balance(addr)
                self.blockchain.db.set_balance(addr, current + share_sat)
                logger.debug(f"Recompensa distribuida: {share:.8f} TRC para {addr[:16]}...")
