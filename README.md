<div align="center">

# TritioCoin

**A quantum-resistant cryptocurrency built for everyday use**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-v1.0%20Production-brightgreen.svg)]()

</div>

---

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone and deploy
git clone https://github.com/yourusername/TritioCoin.git
cd TritioCoin
chmod +x deploy.sh
./deploy.sh
```

### Option 2: Manual

```bash
# Clone
git clone https://github.com/yourusername/TritioCoin.git
cd TritioCoin

# Install dependencies
pip install -r requirements.txt

# Create wallet
python wallet.py create

# Start mining
python wallet.py mine
```

## Features

| Feature | Description |
|---------|-------------|
| **Supply Cap** | 19,000,000 TRC |
| **Block Reward** | 45 TRC (halving every 190,000 blocks) |
| **Block Time** | ~5 minutes |
| **Burn Rate** | 10% of transaction fees |
| **Consensus** | PoW (Argon2id) + PoS |
| **Quantum Resistant** | ECDSA + WOTS+ hybrid signatures |
| **Encryption** | AES-256-GCM wallet, TLS 1.3 P2P |
| **Wallets** | BIP32/BIP44 HD wallets, Multi-sig |
| **Network** | DHT peer discovery, NAT traversal |
| **Governance** | DAO with proposals and voting |
| **Staking** | Public staking with rewards |
| **Micropayments** | Payment channels with low fees |

## Architecture

```
TritioCoin/
├── core/
│   ├── blockchain.py      # Chain management
│   ├── block.py           # Block structure
│   ├── miner.py           # Argon2id mining
│   ├── mempool.py         # Transaction pool
│   ├── transaction.py     # Satoshis-based transactions
│   ├── utxo.py            # UTXO management
│   ├── wallet.py          # Encrypted wallets
│   ├── hdwallet.py        # BIP32/BIP44 HD wallets
│   ├── multisig.py        # Multi-signature wallets
│   ├── consensus.py       # PoS validator engine
│   ├── pool.py            # Mining pool
│   ├── dao.py             # DAO governance
│   ├── staking.py         # Public staking
│   ├── micropay.py        # Micropayments
│   ├── light_client.py    # SPV light client
│   ├── quantum.py         # WOTS+ quantum resistance
│   ├── constants.py       # Satoshi-based constants
│   ├── database.py        # SQLite persistence
│   └── network_config.py  # Mainnet/Testnet configs
├── network/
│   ├── p2p_node.py        # TLS P2P networking
│   ├── api.py             # REST + WebSocket API
│   ├── dht.py             # Kademlia DHT
│   └── reputation.py      # Peer reputation
├── main.py                # Node entry point
├── wallet.py              # CLI wallet
├── explorer.html          # Web block explorer
├── tests/                 # 80 automated tests
└── requirements.txt       # Dependencies
```

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Network status |
| `GET /api/block/{height}` | Block data |
| `GET /api/balance/{address}` | Address balance |
| `GET /api/tx/{hash}` | Transaction data |
| `GET /api/mempool` | Pending transactions |
| `GET /api/peers` | Connected peers |
| `GET /api/validators` | Active validators |
| `POST /api/tx` | Submit transaction |
| `WS /ws` | WebSocket real-time |
| `GET /explorer` | Block explorer |

## Economics

| Parameter | Value |
|-----------|-------|
| Max Supply | 19,000,000 TRC |
| Initial Reward | 45 TRC |
| Halving Interval | 190,000 blocks |
| Block Time | ~5 minutes |
| Min Fee | 0.0001 TRC |
| Burn Rate | 10% of fees |
| Satoshis | 1 TRC = 100,000,000 sat |

## Deployment

### Docker

```bash
# Production deployment
cp .env.production .env
# Edit .env with your password
docker-compose up -d
```

### Linux Server

```bash
# Install as service
sudo cp tritiocoin.service /etc/systemd/system/
sudo systemctl enable tritiocoin
sudo systemctl start tritiocoin
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific module
python -m pytest tests/test_wallet.py -v
```

## Documentation

- [Whitepaper](WHITEPAPER.md)
- [API Documentation](API.md)
- [Architecture](ARCHITECTURE.md)
- [Deployment Guide](DEPLOY.md)
- [Security Policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## License

MIT License - See [LICENSE](LICENSE)

---

**TritioCoin v1.0 - Production Ready**
