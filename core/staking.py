"""
TritioCoin Public Staking
Staking system for earning rewards and participating in governance.
"""
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("Staking")


@dataclass
class StakeInfo:
    """Information about a stake."""
    address: str
    amount: float
    staked_at: float = field(default_factory=time.time)
    lock_until: float = 0  # 0 = unlocked
    rewards_earned: float = 0
    last_reward: float = 0

    def is_locked(self) -> bool:
        return time.time() < self.lock_until

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "amount": self.amount,
            "staked_at": self.staked_at,
            "lock_until": self.lock_until,
            "rewards_earned": self.rewards_earned,
            "apy": self._calculate_apy()
        }

    def _calculate_apy(self) -> float:
        """Calculate annualized percentage yield based on lock duration."""
        if self.amount <= 0:
            return 0

        base_rate = 5.0

        if self.lock_until > time.time():
            remaining_days = (self.lock_until - time.time()) / 86400
            if remaining_days > 300:
                base_rate *= 1.5
            elif remaining_days > 90:
                base_rate *= 1.25

        return round(base_rate, 2)


class StakingPool:
    """
    Public staking pool for TRC.
    
    Features:
    - Stake TRC to earn rewards
    - Participate in governance
    - Validator selection based on stake
    - Lock periods for security
    """

    # Staking parameters
    MIN_STAKE = 100.0  # Minimum TRC to stake
    MAX_STAKE = 10_000_000.0  # Maximum TRC per address
    REWARD_RATE = 0.05  # 5% annual reward
    LOCK_PERIODS = {
        "none": 0,
        "30d": 30 * 24 * 3600,
        "90d": 90 * 24 * 3600,
        "180d": 180 * 24 * 3600,
        "365d": 365 * 24 * 3600
    }
    UNBONDING_PERIOD = 7 * 24 * 3600  # 7 days unbonding

    def __init__(self):
        self.stakes: Dict[str, StakeInfo] = {}
        self.total_staked = 0.0
        self.total_rewards_distributed = 0.0
        self.reward_pool = 0.0

    def stake(self, address: str, amount: float, lock_period: str = "none") -> bool:
        """Stake TRC tokens."""
        if amount < self.MIN_STAKE:
            logger.warning(f"Stake too low: {amount} < {self.MIN_STAKE}")
            return False

        # Check existing stake
        existing = self.stakes.get(address)
        if existing:
            if existing.amount + amount > self.MAX_STAKE:
                logger.warning(f"Max stake exceeded for {address}")
                return False
            if existing.is_locked():
                logger.warning(f"Stake locked for {address}")
                return False
            existing.amount += amount
            existing.staked_at = time.time()
        else:
            lock_duration = self.LOCK_PERIODS.get(lock_period, 0)
            self.stakes[address] = StakeInfo(
                address=address,
                amount=amount,
                lock_until=time.time() + lock_duration if lock_duration > 0 else 0
            )

        self.total_staked += amount
        logger.info(f"Staked {amount} TRC for {address} (lock: {lock_period})")
        return True

    def unstake(self, address: str, amount: float) -> bool:
        """Unstake TRC tokens (with unbonding period)."""
        stake = self.stakes.get(address)
        if not stake:
            logger.warning(f"No stake found for {address}")
            return False

        if stake.is_locked():
            logger.warning(f"Stake still locked for {address}")
            return False

        if stake.amount < amount:
            logger.warning(f"Insufficient stake: {stake.amount} < {amount}")
            return False

        stake.amount -= amount
        self.total_staked -= amount

        if stake.amount <= 0:
            del self.stakes[address]

        logger.info(f"Unstaked {amount} TRC for {address}")
        return True

    def claim_rewards(self, address: str) -> float:
        """Claim staking rewards."""
        stake = self.stakes.get(address)
        if not stake:
            return 0

        rewards = stake.rewards_earned
        if rewards <= 0:
            return 0

        stake.rewards_earned = 0
        stake.last_reward = time.time()
        self.total_rewards_distributed += rewards

        logger.info(f"Rewards claimed: {rewards:.4f} TRC for {address}")
        return rewards

    def _calculate_rewards(self, stake: StakeInfo) -> float:
        """Calculate pending rewards for a stake."""
        if stake.amount <= 0:
            return 0

        time_staked = time.time() - stake.staked_at
        annual_reward = stake.amount * self.REWARD_RATE
        reward = annual_reward * (time_staked / (365 * 24 * 3600))

        # Subtract already claimed rewards
        pending = reward - stake.rewards_earned
        return max(0, pending)

    def get_stake(self, address: str) -> Optional[dict]:
        """Get stake information for an address."""
        stake = self.stakes.get(address)
        if not stake:
            return None
        return stake.to_dict()

    def get_all_stakes(self) -> List[dict]:
        """Get all stakes."""
        return [s.to_dict() for s in self.stakes.values()]

    def get_validators(self, min_stake: float = None) -> List[str]:
        """Get eligible validator addresses based on stake."""
        min_stake = min_stake or self.MIN_STAKE
        validators = []
        for address, stake in self.stakes.items():
            if stake.amount >= min_stake and not stake.is_locked():
                validators.append(address)
        return sorted(validators, key=lambda a: self.stakes[a].amount, reverse=True)

    def get_stats(self) -> dict:
        """Get staking statistics."""
        total_staked = sum(s.amount for s in self.stakes.values())
        total_rewards = sum(s.rewards_earned for s in self.stakes.values())
        avg_lock = 0
        locked_count = 0

        for stake in self.stakes.values():
            if stake.is_locked():
                locked_count += 1
                avg_lock += stake.lock_until - time.time()

        if locked_count > 0:
            avg_lock /= locked_count

        return {
            "total_staked": total_staked,
            "total_stakers": len(self.stakes),
            "total_rewards": total_rewards,
            "active_stakers": len([s for s in self.stakes.values() if not s.is_locked()]),
            "locked_stakers": locked_count,
            "avg_lock_remaining": avg_lock / 86400,  # days
            "min_stake": self.MIN_STAKE,
            "max_stake": self.MAX_STAKE,
            "reward_rate": self.REWARD_RATE * 100,
            "unbonding_days": self.UNBONDING_PERIOD // 86400
        }

    def distribute_rewards(self, block_reward: float):
        """Distribute block rewards to stakers."""
        if self.total_staked <= 0:
            return

        # 30% of block reward goes to stakers
        staker_pool = block_reward * 0.3

        for address, stake in self.stakes.items():
            if stake.amount <= 0:
                continue

            # Proportional share
            share = (stake.amount / self.total_staked) * staker_pool
            stake.rewards_earned += share
            self.total_rewards_distributed += share

    def get_reward_rate(self, address: str) -> float:
        """Get effective reward rate for an address."""
        stake = self.stakes.get(address)
        if not stake or stake.amount <= 0:
            return 0

        # Base rate + lock bonus
        base_rate = self.REWARD_RATE
        if stake.lock_until > time.time():
            remaining_days = (stake.lock_until - time.time()) / 86400
            if remaining_days > 300:
                base_rate *= 1.5  # 50% bonus for long locks
            elif remaining_days > 90:
                base_rate *= 1.25  # 25% bonus

        return base_rate
