"""
TritioCoin DAO - Decentralized Autonomous Organization
Governance system for community decisions.
"""
import hashlib
import time
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("DAO")


class ProposalStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PASSED = "passed"
    REJECTED = "rejected"
    EXECUTED = "executed"


class ProposalType(Enum):
    PARAMETER_CHANGE = "parameter_change"
    TREASURY_SPEND = "treasury_spend"
    PROTOCOL_UPGRADE = "protocol_upgrade"
    GRANT = "grant"


@dataclass
class Vote:
    voter: str
    proposal_id: str
    choice: bool  # True = yes, False = no
    weight: float  # Based on stake
    timestamp: float = field(default_factory=time.time)


@dataclass
class Proposal:
    id: str
    title: str
    description: str
    proposer: str
    proposal_type: ProposalType
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    voting_start: float = 0
    voting_end: float = 0
    votes_for: float = 0
    votes_against: float = 0
    total_voters: int = 0
    votes: Dict[str, Vote] = field(default_factory=dict)
    execution_data: Optional[dict] = None

    def is_active(self) -> bool:
        now = time.time()
        return self.status == ProposalStatus.ACTIVE and self.voting_start <= now <= self.voting_end

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "proposer": self.proposer,
            "type": self.proposal_type.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "voting_start": self.voting_start,
            "voting_end": self.voting_end,
            "votes_for": self.votes_for,
            "votes_against": self.votes_against,
            "total_voters": self.total_voters,
            "execution_data": self.execution_data
        }


class DAO:
    """
    Decentralized Autonomous Organization for TritioCoin governance.
    
    Features:
    - Proposals for parameter changes
    - Treasury management
    - Grant applications
    - Voting with stake-weighted ballots
    """

    # Governance parameters
    MIN_PROPOSER_STAKE = 100.0  # Minimum TRC to create proposal
    VOTING_PERIOD = 7 * 24 * 3600  # 7 days in seconds
    QUORUM = 0.1  # 10% of total stake must vote
    PASS_THRESHOLD = 0.5  # 51% to pass
    TIMELOCK = 24 * 3600  # 24 hours before execution

    def __init__(self):
        self.proposals: Dict[str, Proposal] = {}
        self.treasury_balance = 0.0
        self.total_stake = 0.0
        self.voters: Dict[str, float] = {}  # address -> stake
        self.proposal_count = 0

    def create_proposal(self, proposer: str, title: str, description: str,
                        proposal_type: ProposalType, execution_data: dict = None) -> Optional[str]:
        """Create a new proposal."""
        # Check minimum stake
        proposer_stake = self.voters.get(proposer, 0)
        if proposer_stake < self.MIN_PROPOSER_STAKE:
            logger.warning(f"Proposer stake too low: {proposer_stake} < {self.MIN_PROPOSER_STAKE}")
            return None

        # Create proposal
        self.proposal_count += 1
        proposal_id = f"PROP-{self.proposal_count:06d}"

        proposal = Proposal(
            id=proposal_id,
            title=title,
            description=description,
            proposer=proposer,
            proposal_type=proposal_type,
            voting_start=time.time(),
            voting_end=time.time() + self.VOTING_PERIOD,
            execution_data=execution_data
        )
        proposal.status = ProposalStatus.ACTIVE

        self.proposals[proposal_id] = proposal
        logger.info(f"Proposal created: {proposal_id} - {title}")
        return proposal_id

    def vote(self, voter: str, proposal_id: str, choice: bool) -> bool:
        """Cast a vote on a proposal."""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            logger.warning(f"Proposal not found: {proposal_id}")
            return False

        if not proposal.is_active():
            logger.warning(f"Proposal not active: {proposal_id}")
            return False

        # Check if already voted
        if voter in proposal.votes:
            logger.warning(f"Already voted: {voter}")
            return False

        # Get voter's stake weight
        stake = self.voters.get(voter, 0)
        if stake <= 0:
            logger.warning(f"No stake: {voter}")
            return False

        # Create vote
        vote = Vote(
            voter=voter,
            proposal_id=proposal_id,
            choice=choice,
            weight=stake
        )

        # Record vote
        proposal.votes[voter] = vote
        proposal.total_voters += 1

        if choice:
            proposal.votes_for += stake
        else:
            proposal.votes_against += stake

        logger.info(f"Vote cast: {voter} voted {'YES' if choice else 'NO'} on {proposal_id} (weight: {stake})")
        return True

    def tally_votes(self, proposal_id: str) -> dict:
        """Tally votes for a proposal."""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            return {}

        total_votes = proposal.votes_for + proposal.votes_against
        quorum_reached = total_votes >= (self.total_stake * self.QUORUM)

        if total_votes > 0:
            pass_rate = proposal.votes_for / total_votes
        else:
            pass_rate = 0

        passed = quorum_reached and pass_rate >= self.PASS_THRESHOLD

        return {
            "proposal_id": proposal_id,
            "votes_for": proposal.votes_for,
            "votes_against": proposal.votes_against,
            "total_votes": total_votes,
            "pass_rate": pass_rate,
            "quorum_reached": quorum_reached,
            "passed": passed
        }

    def close_proposal(self, proposal_id: str):
        """Close voting and determine outcome."""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            return

        tally = self.tally_votes(proposal_id)

        if tally["passed"]:
            proposal.status = ProposalStatus.PASSED
            proposal.voting_end = time.time()
            logger.info(f"Proposal PASSED: {proposal_id}")
        else:
            proposal.status = ProposalStatus.REJECTED
            proposal.voting_end = time.time()
            logger.info(f"Proposal REJECTED: {proposal_id}")

    def execute_proposal(self, proposal_id: str) -> bool:
        """Execute a passed proposal."""
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            return False

        if proposal.status != ProposalStatus.PASSED:
            logger.warning(f"Proposal not passed: {proposal_id}")
            return False

        # Check timelock
        if time.time() < proposal.voting_end + self.TIMELOCK:
            logger.warning(f"Timelock active for: {proposal_id}")
            return False

        # Execute based on type
        if proposal.proposal_type == ProposalType.TREASURY_SPEND:
            amount = proposal.execution_data.get("amount", 0)
            recipient = proposal.execution_data.get("recipient", "")
            if self.treasury_balance >= amount:
                self.treasury_balance -= amount
                proposal.status = ProposalStatus.EXECUTED
                logger.info(f"Treasury spend: {amount} TRC to {recipient}")
                return True

        elif proposal.proposal_type == ProposalType.PARAMETER_CHANGE:
            param = proposal.execution_data.get("parameter", "")
            value = proposal.execution_data.get("value")
            logger.info(f"Parameter change: {param} = {value}")
            proposal.status = ProposalStatus.EXECUTED
            return True

        proposal.status = ProposalStatus.EXECUTED
        return True

    def add_stake(self, address: str, amount: float):
        """Add stake for governance voting."""
        self.voters[address] = self.voters.get(address, 0) + amount
        self.total_stake += amount

    def remove_stake(self, address: str, amount: float) -> bool:
        """Remove stake."""
        current = self.voters.get(address, 0)
        if current < amount:
            return False
        self.voters[address] = current - amount
        self.total_stake -= amount
        return True

    def get_proposals(self, status: Optional[ProposalStatus] = None) -> List[dict]:
        """Get all proposals, optionally filtered by status."""
        proposals = list(self.proposals.values())
        if status:
            proposals = [p for p in proposals if p.status == status]
        return [p.to_dict() for p in proposals]

    def get_proposal(self, proposal_id: str) -> Optional[dict]:
        """Get a specific proposal."""
        proposal = self.proposals.get(proposal_id)
        return proposal.to_dict() if proposal else None

    def get_treasury(self) -> dict:
        """Get treasury information."""
        return {
            "balance": self.treasury_balance,
            "total_stake": self.total_stake,
            "voters": len(self.voters),
            "proposals": len(self.proposals),
            "active_proposals": len([p for p in self.proposals.values() if p.is_active()])
        }

    def get_stats(self) -> dict:
        """Get DAO statistics."""
        return {
            "treasury": self.treasury_balance,
            "total_stake": self.total_stake,
            "total_voters": len(self.voters),
            "total_proposals": len(self.proposals),
            "active_proposals": len([p for p in self.proposals.values() if p.is_active()]),
            "passed_proposals": len([p for p in self.proposals.values() if p.status == ProposalStatus.PASSED]),
            "min_proposer_stake": self.MIN_PROPOSER_STAKE,
            "voting_period_days": self.VOTING_PERIOD // 86400,
            "quorum_percent": self.QUORUM * 100,
            "pass_threshold_percent": self.PASS_THRESHOLD * 100
        }

