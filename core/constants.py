"""
TritioCoin Constants
Defines the fundamental constants of the TritioCoin protocol.
"""

# Satoshis: smallest unit of TRC
# 1 TRC = 100,000,000 satoshis (8 decimal places)
SATOSHIS_PER_TRC = 100_000_000

# Supply
MAX_SUPPLY_TRC = 19_000_000
MAX_SUPPLY_SATOSHIS = MAX_SUPPLY_TRC * SATOSHIS_PER_TRC

# Block rewards
INITIAL_REWARD_TRC = 50.0
INITIAL_REWARD_SATOSHIS = int(INITIAL_REWARD_TRC * SATOSHIS_PER_TRC)

# Minimum reward (dust threshold)
MIN_REWARD_SATOSHIS = 1

# Halving
HALVING_INTERVAL = 190_000  # blocks

# Fees
MIN_FEE_TRC = 0.0001
MIN_FEE_SATOSHIS = int(MIN_FEE_TRC * SATOSHIS_PER_TRC)

# Burn rate (percentage of fees burned)
BURN_RATE = 0.10  # 10%

# Block time
TARGET_BLOCK_TIME = 300  # 5 minutes in seconds

# Security: Timestamp validation
MAX_FUTURE_DRIFT = 120    # 2 minutes ahead
MAX_PAST_DRIFT = 7200     # 2 hours behind
MTP_WINDOW = 11           # Median time past window

# Security: Confirmations and reorg
MIN_CONFIRMATIONS = 6
CHECKPOINT_INTERVAL = 1000
MAX_REORG_DEPTH = 20

# Security: Mempool
MAX_TXS_PER_SENDER = 50
MAX_TX_AGE = 3600         # 1 hour


def trc_to_satoshis(trc: float) -> int:
    """Convert TRC to satoshis."""
    return int(round(trc * SATOSHIS_PER_TRC))


def satoshis_to_trc(satoshis: int) -> float:
    """Convert satoshis to TRC."""
    return satoshis / SATOSHIS_PER_TRC


def format_trc(satoshis: int) -> str:
    """Format satoshis as TRC string with 8 decimal places."""
    trc = satoshis / SATOSHIS_PER_TRC
    return f"{trc:.8f}"


def format_trc_short(satoshis: int) -> str:
    """Format satoshis as TRC string with variable decimals."""
    trc = satoshis / SATOSHIS_PER_TRC
    if trc == 0:
        return "0 TRC"
    elif trc < 0.00000001:
        return f"{satoshis} sat"
    elif trc < 0.0001:
        return f"{trc:.8f} TRC"
    elif trc < 1:
        return f"{trc:.6f} TRC"
    elif trc < 1000:
        return f"{trc:.4f} TRC"
    else:
        return f"{trc:,.2f} TRC"
