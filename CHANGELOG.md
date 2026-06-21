# Changelog

All notable changes to TritioCoin will be documented in this file.

## [1.0.0] - 2026-06-21 (Production Release)

### Added

#### Core
- Block structure with 86-byte binary headers
- Blockchain with genesis block
- 19M supply cap with halving every 190,000 blocks
- 45 TRC initial block reward
- ~5 minute block time
- Dynamic difficulty adjustment

#### Economics
- Satoshi-based amounts (8 decimal places)
- 10% burn rate on transaction fees
- Deflationary supply model
- Halving schedule

#### Security
- AES-256-GCM wallet encryption (PBKDF2 600K iterations)
- BIP39 24-word mnemonic backup
- TLS 1.3 P2P encryption
- ECDSA secp256k1 signatures
- WOTS+ quantum-resistant signatures (hybrid mode)

#### Wallet
- HD Wallet (BIP32/BIP44) support
- Multi-signature wallets (M-of-N)
- Address generation (TRC standard, QR quantum)
- Wallet import/export

#### Mining
- Argon2id Proof-of-Work (ASIC-resistant)
- Mining pool support
- Share-based reward distribution
- Real-time hashrate monitoring

#### Consensus
- PoW + PoS hybrid consensus
- Validator registration and selection
- Block signing and verification
- Stake-weighted validator selection

#### Storage
- SQLite database with WAL mode
- UTXO-based balance tracking
- Block pruning for disk space
- Atomic writes for crash safety

#### Network
- TCP P2P with TLS 1.3
- Kademlia DHT for decentralized peer discovery
- NAT traversal (UPnP)
- Peer reputation system
- Rate limiting
- Compact block relay
- Orphan block handling

#### API
- REST API with 11+ endpoints
- WebSocket for real-time updates
- Block explorer web interface

#### Governance
- DAO with proposals and voting
- Treasury management
- Public staking with rewards
- Micropayment channels

#### CLI
- Wallet creation and management
- Balance checking
- Transaction sending
- Mining control
- Network status

#### Other
- Mainnet and Testnet support
- Light Client (SPV)
- Docker deployment
- Systemd service
- 80 automated tests
- Comprehensive documentation
