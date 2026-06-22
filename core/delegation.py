"""
TritioCoin Delegation System
Allow users to delegate TRC to validators and earn rewards.
"""
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("Delegation")


@dataclass
class Delegation:
    """Represents a delegation from a delegator to a validator."""
    delegator: str
    validator: str
    amount: float
    created_at: float = field(default_factory=time.time)
    last_claim: float = 0
    pending_rewards: float = 0

    def to_dict(self) -> dict:
        return {
            "delegator": self.delegator,
            "validator": self.validator,
            "amount": self.amount,
            "created_at": self.created_at,
            "pending_rewards": self.pending_rewards,
            "days_delegated": (time.time() - self.created_at) / 86400
        }


class DelegationPool:
    """
    Delegation pool for TRC.

    Features:
    - Delegate TRC to active validators
    - Earn proportional rewards
    - Validator commission (default 10%)
    - Unbonding period (7 days)
    - Auto-compound option
    """

    MIN_DELEGATION = 1.0  # Minimum 1 TRC to delegate
    MAX_DELEGATIONS = 100  # Max delegations per address
    UNBONDING_PERIOD = 7 * 24 * 3600  # 7 days
    DEFAULT_COMMISSION = 0.10  # 10% validator commission

    def __init__(self):
        self.delegations: Dict[str, List[Delegation]] = {}  # delegator -> [Delegation]
        self.validator_delegations: Dict[str, List[Delegation]] = {}  # validator -> [Delegation]
        self.total_delegated = 0.0
        self.total_rewards_distributed = 0.0
        self.pending_undelegations: Dict[str, List[dict]] = {}  # delegator -> [undelegation_info]

    def delegate(self, delegator: str, validator: str, amount: float,
                 commission: float = None) -> bool:
        """
        Delegate TRC to a validator.

        Args:
            delegator: Address of the delegator
            validator: Address of the validator
            amount: Amount of TRC to delegate
            commission: Validator commission rate (optional, uses default if None)
        """
        if amount < self.MIN_DELEGATION:
            logger.warning(f"Delegation too low: {amount} < {self.MIN_DELEGATION} TRC")
            return False

        # Check max delegations
        delegator_delegations = self.delegations.get(delegator, [])
        if len(delegator_delegations) >= self.MAX_DELEGATIONS:
            logger.warning(f"Max delegations reached for {delegator[:16]}...")
            return False

        # Check if already delegated to this validator
        for d in delegator_delegations:
            if d.validator == validator:
                # Add to existing delegation
                d.amount += amount
                self.total_delegated += amount
                logger.info(f"Added {amount} TRC to delegation {delegator[:16]}... -> {validator[:16]}...")
                return True

        # Create new delegation
        delegation = Delegation(
            delegator=delegator,
            validator=validator,
            amount=amount
        )

        # Add to delegator's list
        if delegator not in self.delegations:
            self.delegations[delegator] = []
        self.delegations[delegator].append(delegation)

        # Add to validator's list
        if validator not in self.validator_delegations:
            self.validator_delegations[validator] = []
        self.validator_delegations[validator].append(delegation)

        self.total_delegated += amount
        logger.info(f"Delegated {amount} TRC: {delegator[:16]}... -> {validator[:16]}...")
        return True

    def undelegate(self, delegator: str, validator: str, amount: float) -> bool:
        """
        Start undelegation process (with unbonding period).
        """
        delegator_delegations = self.delegations.get(delegator, [])
        for d in delegator_delegations:
            if d.validator == validator:
                if d.amount < amount:
                    logger.warning(f"Insufficient delegation: {d.amount} < {amount}")
                    return False

                # Start unbonding
                if delegator not in self.pending_undelegations:
                    self.pending_undelegations[delegator] = []

                self.pending_undelegations[delegator].append({
                    "validator": validator,
                    "amount": amount,
                    "unbonding_until": time.time() + self.UNBONDING_PERIOD,
                    "rewards_claimed": d.pending_rewards
                })

                # Reduce delegation immediately
                d.amount -= amount
                self.total_delegated -= amount

                # Remove if empty
                if d.amount <= 0:
                    delegator_delegations.remove(d)
                    if validator in self.validator_delegations:
                        self.validator_delegations[validator] = [
                            x for x in self.validator_delegations[validator]
                            if x.delegator != delegator or x.amount > 0
                        ]

                logger.info(f"Undelegation started: {amount} TRC from {validator[:16]}... "
                           f"(unbonding {self.UNBONDING_PERIOD // 86400} days)")
                return True

        logger.warning(f"No delegation found: {delegator[:16]}... -> {validator[:16]}...")
        return False

    def claim_undelegation(self, delegator: str) -> float:
        """
        Claim undelegated tokens after unbonding period.
        Returns total amount claimed.
        """
        pending = self.pending_undelegations.get(delegator, [])
        completed = []
        total_claimed = 0.0

        for u in pending:
            if time.time() >= u["unbonding_until"]:
                total_claimed += u["amount"]
                completed.append(u)

        # Remove completed undelegations
        for u in completed:
            pending.remove(u)

        if total_claimed > 0:
            logger.info(f"Undelegation completed: {total_claimed} TRC for {delegator[:16]}...")

        return total_claimed

    def get_pending_undelegation(self, delegator: str) -> List[dict]:
        """Get pending undelegations for an address."""
        pending = self.pending_undelegations.get(delegator, [])
        result = []
        for u in pending:
            remaining = max(0, u["unbonding_until"] - time.time())
            result.append({
                "validator": u["validator"],
                "amount": u["amount"],
                "unbonding_days_remaining": remaining / 86400,
                "completed": remaining <= 0
            })
        return result

    def distribute_rewards(self, validator: str, block_reward: float,
                          commission_rate: float = None):
        """
        Distribute rewards to delegators of a validator.

        Args:
            validator: Validator address
            block_reward: Total reward for the block
            commission_rate: Validator commission (default 10%)
        """
        commission_rate = commission_rate or self.DEFAULT_COMMISSION
        delegations = self.validator_delegations.get(validator, [])

        if not delegations:
            return

        # Calculate total delegated to this validator
        total_validator_delegated = sum(d.amount for d in delegations)
        if total_validator_delegated <= 0:
            return

        # Validator commission (from their own stake + delegations)
        commission = block_reward * commission_rate

        # Remaining rewards for delegators
        delegator_pool = block_reward - commission

        # Distribute proportionally
        for delegation in delegations:
            share = (delegation.amount / total_validator_delegated) * delegator_pool
            delegation.pending_rewards += share

        logger.info(f"Distributed {delegator_pool:.8f} TRC to {len(delegations)} delegators "
                   f"of {validator[:16]}... (commission: {commission:.8f} TRC)")

    def claim_rewards(self, delegator: str, validator: str = None) -> float:
        """
        Claim pending rewards from delegations.
        If validator is None, claims from all delegations.
        """
        delegations = self.delegations.get(delegator, [])
        total_claimed = 0.0

        for d in delegations:
            if validator and d.validator != validator:
                continue

            if d.pending_rewards > 0:
                total_claimed += d.pending_rewards
                d.pending_rewards = 0
                d.last_claim = time.time()

        self.total_rewards_distributed += total_claimed

        if total_claimed > 0:
            logger.info(f"Rewards claimed: {total_claimed:.8f} TRC for {delegator[:16]}...")

        return total_claimed

    def get_delegations(self, delegator: str) -> List[dict]:
        """Get all delegations for an address."""
        delegations = self.delegations.get(delegator, [])
        return [d.to_dict() for d in delegations]

    def get_validator_delegations(self, validator: str) -> List[dict]:
        """Get all delegations to a validator."""
        delegations = self.validator_delegations.get(validator, [])
        return [d.to_dict() for d in delegations]

    def get_total_delegated_to(self, validator: str) -> float:
        """Get total amount delegated to a validator."""
        delegations = self.validator_delegations.get(validator, [])
        return sum(d.amount for d in delegations)

    def get_effective_stake(self, validator: str, own_stake: float) -> float:
        """
        Get effective stake including delegations.
        Used for validator selection in consensus.
        """
        delegated = self.get_total_delegated_to(validator)
        return own_stake + delegated

    def get_stats(self) -> dict:
        """Get delegation statistics."""
        total_pending_rewards = 0
        for delegations in self.delegations.values():
            for d in delegations:
                total_pending_rewards += d.pending_rewards

        pending_undelegation_amount = 0
        for pending in self.pending_undelegations.values():
            for u in pending:
                pending_undelegation_amount += u["amount"]

        return {
            "total_delegated": self.total_delegated,
            "total_delegators": len(self.delegations),
            "total_validators_with_delegations": len(self.validator_delegations),
            "total_rewards_distributed": self.total_rewards_distributed,
            "total_pending_rewards": total_pending_rewards,
            "pending_undelegation_amount": pending_undelegation_amount,
            "min_delegation": self.MIN_DELEGATION,
            "unbonding_days": self.UNBONDING_PERIOD // 86400,
            "default_commission": self.DEFAULT_COMMISSION * 100
        }
