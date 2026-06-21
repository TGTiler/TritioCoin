"""
TritioCoin Test Configuration
Fixtures and shared test utilities.
"""
import pytest
import tempfile
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))

from core.database import Database
from core.blockchain import Blockchain
from core.mempool import Mempool
from core.miner import Miner
from core.wallet import Wallet
from core.transaction import Transaction
from core.block import Block
from core.utxo import UTXOManager
from core.multisig import MultiSigWallet, create_multisig_wallet
from core.hdwallet import HDWallet
from core.consensus import ConsensusEngine
from core.network_config import TESTNET, MAINNET


@pytest.fixture
def tmp_dir():
    """Create a temporary directory for test files."""
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def db(tmp_dir):
    """Create a fresh test database."""
    return Database(tmp_dir / "test.db")


@pytest.fixture
def testnet():
    """Return testnet config."""
    return TESTNET


@pytest.fixture
def mainnet():
    """Return mainnet config."""
    return MAINNET


@pytest.fixture
def blockchain(db, testnet):
    """Create a blockchain with testnet config."""
    return Blockchain(testnet, db)


@pytest.fixture
def mempool(db):
    """Create a mempool."""
    return Mempool(db)


@pytest.fixture
def utxo_manager(db):
    """Create a UTXO manager."""
    return UTXOManager(db)


@pytest.fixture
def miner(blockchain, mempool):
    """Create a miner."""
    return Miner(blockchain, mempool)


@pytest.fixture
def wallet():
    """Create a random wallet."""
    return Wallet.create()


@pytest.fixture
def quantum_wallet():
    """Create a quantum-resistant wallet."""
    return Wallet.create(quantum=True)


@pytest.fixture
def funded_blockchain(db, testnet):
    """Create a blockchain with funded wallets."""
    bc = Blockchain(testnet, db)
    wallets = []

    # Mine 10 blocks to fund wallets
    for i in range(10):
        w = Wallet.create()
        wallets.append(w)
        coinbase = Transaction("COINBASE", w.pubkey_hex(), bc.reward_at())
        coinbase.timestamp = int(time.time() * 1000) + i
        coinbase.tx_hash = coinbase.compute_hash()
        block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
        block.hash = block.content_hash()
        block.pow_hash = "0" * bc.difficulty + "test"
        bc.add_block(block)

    return bc, wallets


@pytest.fixture
def consensus(blockchain):
    """Create a consensus engine with validators."""
    ce = ConsensusEngine(blockchain)
    for i in range(5):
        w = Wallet.create()
        ce.register_validator(w, 200.0)
    return ce
