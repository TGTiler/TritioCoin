"""
TritioCoin Micropayments
Dynamic fee system optimized for small transactions.
"""
import hashlib
import time
import logging
from typing import Optional, List, Dict

logger = logging.getLogger("Micropay")


class FeeEstimator:
    """
    Dynamic fee estimator for micropayments.
    
    Features:
    - Dynamic fees based on network congestion
    - Priority levels (low, medium, high)
    - Fee averaging over time
    - Minimum fee enforcement
    """

    # Fee levels
    FEE_LEVELS = {
        "micro": 0.00001,    # For micropayments (< 1 TRC)
        "low": 0.0001,       # Normal transactions
        "medium": 0.001,     # Faster confirmation
        "high": 0.01,        # Priority confirmation
        "urgent": 0.1        # Immediate confirmation
    }

    # Dynamic adjustment parameters
    TARGET_BLOCK_FULLNESS = 0.5  # 50% block fullness target
    FEE_ADJUSTMENT_RATE = 0.1    # 10% adjustment per period
    MIN_FEE = 0.00001
    MAX_FEE = 10.0

    def __init__(self):
        self.recent_fees: list = []
        self.block_fullness_history: list = []
        self.current_min_fee = 0.0001

    def estimate_fee(self, tx_size_bytes: int = 250,
                     priority: str = "low") -> float:
        """
        Estimate fee for a transaction.
        
        Args:
            tx_size_bytes: Estimated transaction size in bytes
            priority: "micro", "low", "medium", "high", "urgent"
            
        Returns:
            Estimated fee in TRC
        """
        # Base fee from priority level
        base_fee = self.FEE_LEVELS.get(priority, self.FEE_LEVELS["low"])

        # Size-based adjustment (fee per byte)
        size_factor = tx_size_bytes / 250  # 250 bytes = standard tx
        size_fee = size_factor * 0.00001

        # Congestion adjustment
        congestion_factor = self._get_congestion_factor()
        adjusted_fee = (base_fee + size_fee) * congestion_factor

        # Enforce limits
        adjusted_fee = max(self.MIN_FEE, min(self.MAX_FEE, adjusted_fee))

        return round(adjusted_fee, 8)

    def _get_congestion_factor(self) -> float:
        """Calculate congestion multiplier."""
        if not self.block_fullness_history:
            return 1.0

        avg_fullness = sum(self.block_fullness_history[-10:]) / len(self.block_fullness_history[-10:])

        if avg_fullness > 0.8:
            return 2.0  # High congestion
        elif avg_fullness > 0.5:
            return 1.5  # Medium congestion
        elif avg_fullness < 0.2:
            return 0.7  # Low congestion
        else:
            return 1.0  # Normal

    def record_block_fullness(self, tx_count: int, max_txs: int = 500):
        """Record block fullness for fee estimation."""
        fullness = min(tx_count / max_txs, 1.0)
        self.block_fullness_history.append(fullness)

        # Keep only recent history
        if len(self.block_fullness_history) > 100:
            self.block_fullness_history = self.block_fullness_history[-100:]

    def record_fee(self, fee: float):
        """Record a paid fee for averaging."""
        self.recent_fees.append(fee)
        if len(self.recent_fees) > 1000:
            self.recent_fees = self.recent_fees[-1000:]

    def get_recommended_fee(self, priority: str = "low") -> dict:
        """Get recommended fee with estimation."""
        fee = self.estimate_fee(priority=priority)
        congestion = self._get_congestion_factor()

        return {
            "fee": fee,
            "priority": priority,
            "congestion_level": self._get_congestion_name(congestion),
            "confirmation_time": self._estimate_confirmation_time(priority)
        }

    def _get_congestion_name(self, factor: float) -> str:
        if factor >= 2.0:
            return "high"
        elif factor >= 1.5:
            return "medium"
        elif factor <= 0.7:
            return "low"
        else:
            return "normal"

    def _estimate_confirmation_time(self, priority: str) -> str:
        """Estimate confirmation time based on priority."""
        times = {
            "micro": "~30 min",
            "low": "~15 min",
            "medium": "~5 min",
            "high": "~2 min",
            "urgent": "~1 min"
        }
        return times.get(priority, "~15 min")

    def get_stats(self) -> dict:
        """Get fee statistics."""
        avg_fee = sum(self.recent_fees) / len(self.recent_fees) if self.recent_fees else 0
        return {
            "current_min_fee": self.current_min_fee,
            "average_fee": avg_fee,
            "fee_levels": self.FEE_LEVELS,
            "congestion_factor": self._get_congestion_factor(),
            "recent_fees_count": len(self.recent_fees)
        }


class MicropaymentChannel:
    """
    Off-chain micropayment channel for instant transactions.
    """

    def __init__(self, sender: str, receiver: str, capacity: float):
        self.sender = sender
        self.receiver = receiver
        self.capacity = capacity
        self.balance_sender = capacity
        self.balance_receiver = 0
        self.nonce = 0
        self.opened_at = time.time()
        self.last_update = time.time()
        self.is_open = True

    def create_payment(self, amount: float, sender: str) -> Optional[dict]:
        """Create an off-chain payment."""
        if not self.is_open:
            logger.warning("Channel is closed")
            return None

        if sender == self.sender:
            if self.balance_sender < amount:
                logger.warning("Insufficient channel balance")
                return None
            self.balance_sender -= amount
            self.balance_receiver += amount
        elif sender == self.receiver:
            if self.balance_receiver < amount:
                logger.warning("Insufficient channel balance")
                return None
            self.balance_receiver -= amount
            self.balance_sender += amount
        else:
            logger.warning("Unknown sender in channel")
            return None

        self.nonce += 1
        self.last_update = time.time()

        # Create payment record
        payment = {
            "channel_id": self._get_channel_id(),
            "sender": sender,
            "amount": amount,
            "nonce": self.nonce,
            "balance_sender": self.balance_sender,
            "balance_receiver": self.balance_receiver,
            "timestamp": self.last_update
        }

        return payment

    def close(self) -> dict:
        """Close the channel and return final balances."""
        self.is_open = False
        return {
            "channel_id": self._get_channel_id(),
            "final_balance_sender": self.balance_sender,
            "final_balance_receiver": self.balance_receiver,
            "total_payments": self.nonce
        }

    def _get_channel_id(self) -> str:
        """Generate channel ID."""
        data = f"{self.sender}:{self.receiver}:{self.opened_at}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def get_status(self) -> dict:
        """Get channel status."""
        return {
            "channel_id": self._get_channel_id(),
            "sender": self.sender,
            "receiver": self.receiver,
            "capacity": self.capacity,
            "balance_sender": self.balance_sender,
            "balance_receiver": self.balance_receiver,
            "is_open": self.is_open,
            "payments": self.nonce
        }


class MicropaymentHub:
    """Hub for managing multiple micropayment channels."""

    def __init__(self):
        self.channels: Dict[str, MicropaymentChannel] = {}
        self.fee_estimator = FeeEstimator()

    def open_channel(self, sender: str, receiver: str, capacity: float) -> Optional[str]:
        """Open a new micropayment channel."""
        if capacity <= 0:
            return None

        channel = MicropaymentChannel(sender, receiver, capacity)
        channel_id = channel._get_channel_id()
        self.channels[channel_id] = channel

        logger.info(f"Channel opened: {channel_id} ({sender} -> {receiver}, {capacity} TRC)")
        return channel_id

    def create_payment(self, channel_id: str, amount: float, sender: str) -> Optional[dict]:
        """Create a payment through a channel."""
        channel = self.channels.get(channel_id)
        if not channel:
            return None

        return channel.create_payment(amount, sender)

    def close_channel(self, channel_id: str) -> Optional[dict]:
        """Close a channel."""
        channel = self.channels.get(channel_id)
        if not channel:
            return None

        result = channel.close()
        logger.info(f"Channel closed: {channel_id}")
        return result

    def get_channel(self, channel_id: str) -> Optional[dict]:
        """Get channel status."""
        channel = self.channels.get(channel_id)
        return channel.get_status() if channel else None

    def get_channels_for_address(self, address: str) -> List[dict]:
        """Get all channels for an address."""
        channels = []
        for channel in self.channels.values():
            if channel.sender == address or channel.receiver == address:
                channels.append(channel.get_status())
        return channels

    def get_stats(self) -> dict:
        """Get hub statistics."""
        total_capacity = sum(c.capacity for c in self.channels.values())
        open_channels = sum(1 for c in self.channels.values() if c.is_open)

        return {
            "total_channels": len(self.channels),
            "open_channels": open_channels,
            "total_capacity": total_capacity,
            "fee_estimator": self.fee_estimator.get_stats()
        }
