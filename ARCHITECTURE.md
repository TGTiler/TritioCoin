# TritioCoin Architecture

## Overview

TritioCoin is a decentralized cryptocurrency with a modular architecture designed for security, performance, and quantum resistance.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Application Layer                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  CLI Wallet  │  │   Web UI    │  │   REST API + WS     │ │
│  │  wallet.py   │  │  explorer   │  │   network/api.py    │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
├─────────┼────────────────┼────────────────────┼─────────────┤
│         │         Core Logic Layer           │              │
│  ┌──────┴────────────────────────────────────┴──────────┐  │
│  │                                                       │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │  │
│  │  │  Blockchain  │  │    Miner    │  │   Consensus  │ │  │
│  │  │  core/block  │  │  core/miner │  │  core/consen │ │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘ │  │
│  │         │                │                 │          │  │
│  │  ┌──────┴────────────────┴─────────────────┴───────┐ │  │
│  │  │              Transaction Engine                 │ │  │
│  │  │  ┌─────────┐  ┌─────────┐  ┌─────────────────┐ │ │  │
│  │  │  │  UTXO   │  │ Mempool │  │ Multi-Sig       │ │ │  │
│  │  │  └─────────┘  └─────────┘  └─────────────────┘ │ │  │
│  │  └─────────────────────────────────────────────────┘ │  │
│  │                                                       │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │  │
│  │  │   Wallet    │  │  HD Wallet  │  │   Quantum    │ │  │
│  │  │  ECDSA/AES  │  │  BIP32/44   │  │  WOTS+/Hybrid│ │  │
│  │  └─────────────┘  └─────────────┘  └──────────────┘ │  │
│  │                                                       │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    Network Layer                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   P2P Node  │  │   TLS 1.3   │  │  Peer Reputation   │ │
│  │  TCP/Gossip │  │  Encryption  │  │  Scoring/Banning   │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Storage Layer                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   SQLite    │  │    WAL      │  │   Block Pruning     │ │
│  │  Database   │  │   Mode      │  │   Disk Management   │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### Transaction Flow

```
1. User creates transaction
2. Transaction signed with ECDSA (+ optional WOTS+)
3. Transaction added to mempool
4. Transaction broadcast to peers
5. Miner selects transactions from mempool
6. Miner creates block with transactions
7. Block broadcast to network
8. Validators sign block (PoS)
9. Block added to blockchain
10. UTXOs updated
```

### Mining Flow

```
1. Miner selects transactions from mempool
2. Creates coinbase transaction (reward)
3. Builds block with header + transactions
4. Computes Merkle root
5. Starts mining loop (Argon2id)
6. Finds valid nonce (hash starts with N zeros)
7. Broadcasts compact block
8. Waits for validator signatures
9. Adds block to chain
```

## Security Model

### Cryptographic Primitives

| Component | Algorithm | Purpose |
|-----------|-----------|---------|
| Signatures | ECDSA (secp256k1) | Transaction authentication |
| Quantum | WOTS+ (SHA-256) | Future-proof signatures |
| Hashing | SHA-256 | Block hashing, Merkle trees |
| Mining | Argon2id | ASIC-resistant PoW |
| Encryption | AES-256-GCM | Wallet encryption |
| KDF | PBKDF2 (600K) | Password derivation |
| P2P | TLS 1.3 | Network encryption |

### Trust Model

- No central authority
- Consensus via PoW + PoS
- Double-spend prevention via UTXO
- Validator stake as economic security

## Consensus Mechanism

### PoW (Proof of Work)

- Algorithm: Argon2id
- Memory: 64MB
- Time cost: 1 iteration
- Target: 30 second blocks

### PoS (Proof of Stake)

- Minimum stake: 100 TRC
- Selection: Stake-weighted random
- Threshold: 3 signatures per block
- Reward: 30% of block reward

### Difficulty Adjustment

- Adjusts every 20 blocks
- Target: 30 second block time
- Increases if blocks too fast
- Decreases if blocks too slow

## Network Protocol

### Message Types

| Type | Direction | Description |
|------|-----------|-------------|
| HANDSHAKE | Both | Initial connection |
| HANDSHAKE_ACK | Both | Connection confirmed |
| NEW_BLOCK | Broadcast | New block announcement |
| COMPACT_BLOCK | Broadcast | Block header + tx hashes |
| NEW_TX | Broadcast | New transaction |
| GET_CHAIN | Request | Request full chain |
| CHAIN | Response | Full chain data |
| REQUEST_SIGNATURE | Request | Validator signature request |
| BLOCK_SIGNATURE | Response | Validator signature |

### Rate Limiting

- 100 messages per 10 seconds per peer
- Automatic ban at -50 reputation score
- Ban duration: 1 hour (configurable)

## Database Schema

### Tables

```sql
blocks (height, hash, previous_hash, timestamp, nonce, difficulty, pow_hash, data)
transactions (tx_hash, block_height, sender, recipient, amount, fee, timestamp)
balances (address, balance)
utxos (tx_hash, sender, recipient, amount, fee, block_height, spent)
mempool (tx_hash, sender, recipient, amount, fee, timestamp)
metadata (key, value)
```

### Indexes

```sql
idx_tx_sender ON transactions(sender)
idx_tx_recipient ON transactions(recipient)
idx_tx_block ON transactions(block_height)
idx_utxo_sender ON utxos(sender, spent)
```
