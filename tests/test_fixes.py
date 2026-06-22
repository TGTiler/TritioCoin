"""
Testa as correcoes:
1. Wallet nao encontrada
2. Senha incorreta
3. Bloco duplicado rejeitado
4. Bloco mesmo height rejeitado
"""
import tempfile
import os
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.wallet import Wallet
from core.database import Database
from core.blockchain import Blockchain
from core.block import Block
from core.network_config import MAINNET
from core.transaction import TransactionBuilder


def test_duplicate_block():
    print("TESTE: Bloco duplicado (mesmo hash) rejeitado")
    tmpdb = tempfile.mktemp(suffix='.db')
    db = Database(tmpdb)
    bc = Blockchain(MAINNET, db)

    # Mine first block
    coinbase = TransactionBuilder.create_coinbase('miner1', bc.reward_at_satoshis(), bc.height())
    block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
    block.hash = block.content_hash()
    block.pow_hash = '0' * block.header.difficulty + 'aaa'
    assert bc.add_block(block) == True

    # Try duplicate
    dup = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
    dup.hash = block.hash
    dup.pow_hash = '0' * block.header.difficulty + 'bbb'
    assert bc.add_block(dup) == False, "Duplicado deveria ser rejeitado"

    db.close()
    os.unlink(tmpdb)
    print("  OK")


def test_same_height_block():
    print("TESTE: Bloco no mesmo height rejeitado")
    tmpdb = tempfile.mktemp(suffix='.db')
    db = Database(tmpdb)
    bc = Blockchain(MAINNET, db)

    # Mine block at height 1
    coinbase = TransactionBuilder.create_coinbase('miner1', bc.reward_at_satoshis(), bc.height())
    block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
    block.hash = block.content_hash()
    block.pow_hash = '0' * block.header.difficulty + 'aaa'
    assert bc.add_block(block) == True
    assert bc.height() == 2

    # Try block at height 1 again
    coinbase2 = TransactionBuilder.create_coinbase('miner2', bc.reward_at_satoshis(), 1)
    block2 = Block(1, '0' * 64, [coinbase2.to_dict()], bc.difficulty)
    block2.hash = block2.content_hash()
    block2.pow_hash = '0' * block.header.difficulty + 'ccc'
    assert bc.add_block(block2) == False, "Mesmo height deveria ser rejeitado"

    db.close()
    os.unlink(tmpdb)
    print("  OK")


def test_has_block_with_hash():
    print("TESTE: has_block_with_hash")
    tmpdb = tempfile.mktemp(suffix='.db')
    db = Database(tmpdb)
    bc = Blockchain(MAINNET, db)

    coinbase = TransactionBuilder.create_coinbase('miner1', bc.reward_at_satoshis(), bc.height())
    block = Block(bc.height(), bc.latest().hash, [coinbase.to_dict()], bc.difficulty)
    block.hash = block.content_hash()
    block.pow_hash = '0' * block.header.difficulty + 'aaa'
    bc.add_block(block)

    assert db.has_block_with_hash(block.hash) == True
    assert db.has_block_with_hash('a' * 64) == False

    db.close()
    os.unlink(tmpdb)
    print("  OK")


def test_wallet_not_found():
    print("TESTE: Carteira nao encontrada")
    orig = os.getcwd()
    tmpdir = tempfile.mkdtemp()
    os.chdir(tmpdir)
    os.makedirs('tritiocoin_data', exist_ok=True)

    captured = []
    orig_stdout = sys.stdout
    sys.stdout = type('Capture', (), {'write': lambda s, t: captured.append(t), 'flush': lambda s: None})()

    exit_code = None
    try:
        from wallet import get_wallet
        get_wallet(False, 'any')
    except SystemExit as e:
        exit_code = e.code
    finally:
        sys.stdout = orig_stdout

    os.chdir(orig)
    shutil.rmtree(tmpdir)

    msg = ''.join(captured)
    assert exit_code == 1, f"Exit code should be 1, got {exit_code}"
    assert 'Carteira' in msg, f"Should mention 'Carteira', got: {msg}"
    assert 'ERRO' in msg, f"Should have ERRO, got: {msg}"
    assert 'opcao 2' in msg, f"Should mention opcao 2, got: {msg}"
    print("  OK")


def test_wallet_wrong_password():
    print("TESTE: Senha incorreta")
    orig = os.getcwd()
    tmpdir = tempfile.mkdtemp()
    os.chdir(tmpdir)
    os.makedirs('tritiocoin_data', exist_ok=True)

    # Create encrypted wallet
    w = Wallet.create()
    w.save('tritiocoin_data/wallet.json', 'senha_certa')

    captured = []
    orig_stdout = sys.stdout
    sys.stdout = type('Capture', (), {'write': lambda s, t: captured.append(t), 'flush': lambda s: None})()

    exit_code = None
    try:
        from wallet import get_wallet
        get_wallet(False, 'senha_errada')
    except SystemExit as e:
        exit_code = e.code
    finally:
        sys.stdout = orig_stdout

    os.chdir(orig)
    shutil.rmtree(tmpdir)

    msg = ''.join(captured)
    assert exit_code == 1, f"Exit code should be 1, got {exit_code}"
    assert 'incorreta' in msg.lower(), f"Should mention 'incorreta', got: {msg}"
    print("  OK")


if __name__ == '__main__':
    test_duplicate_block()
    test_same_height_block()
    test_has_block_with_hash()
    test_wallet_not_found()
    test_wallet_wrong_password()
    print()
    print("=== TODOS OS TESTES PASSARAM ===")
