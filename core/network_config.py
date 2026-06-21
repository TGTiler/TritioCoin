"""
TritioCoin Network Configuration
Testnet and Mainnet parameters with satoshi-based amounts.
"""
from dataclasses import dataclass
from core.constants import (
    SATOSHIS_PER_TRC, MAX_SUPPLY_SATOSHIS, INITIAL_REWARD_SATOSHIS,
    MIN_FEE_SATOSHIS, BURN_RATE, TARGET_BLOCK_TIME, HALVING_INTERVAL
)


@dataclass
class NetworkConfig:
    name: str
    port: int
    difficulty: int
    initial_reward_satoshis: int
    halving_interval: int
    max_supply_satoshis: int
    block_time: int
    min_fee_satoshis: int
    max_block_size: int
    mempool_max: int
    burn_rate: float

    @property
    def is_testnet(self) -> bool:
        return self.name == "testnet"

    @property
    def initial_reward_trc(self) -> float:
        return self.initial_reward_satoshis / SATOSHIS_PER_TRC

    @property
    def max_supply_trc(self) -> float:
        return self.max_supply_satoshis / SATOSHIS_PER_TRC

    @property
    def min_fee_trc(self) -> float:
        return self.min_fee_satoshis / SATOSHIS_PER_TRC


MAINNET = NetworkConfig(
    name="mainnet",
    port=8333,
    difficulty=4,
    initial_reward_satoshis=INITIAL_REWARD_SATOSHIS,  # 45 TRC = 4,500,000,000 satoshis
    halving_interval=HALVING_INTERVAL,
    max_supply_satoshis=MAX_SUPPLY_SATOSHIS,
    block_time=TARGET_BLOCK_TIME,
    min_fee_satoshis=MIN_FEE_SATOSHIS,
    max_block_size=1_000_000,
    mempool_max=5_000,
    burn_rate=BURN_RATE
)

TESTNET = NetworkConfig(
    name="testnet",
    port=18333,
    difficulty=2,
    initial_reward_satoshis=INITIAL_REWARD_SATOSHIS,
    halving_interval=1_000,
    max_supply_satoshis=MAX_SUPPLY_SATOSHIS,
    block_time=30,
    min_fee_satoshis=MIN_FEE_SATOSHIS,
    max_block_size=1_000_000,
    mempool_max=1_000,
    burn_rate=BURN_RATE
)

NETWORKS = {
    "mainnet": MAINNET,
    "testnet": TESTNET
}


def get_network(name: str = "mainnet") -> NetworkConfig:
    return NETWORKS.get(name, MAINNET)
