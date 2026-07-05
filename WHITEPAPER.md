# TritioCoin Whitepaper

**A Decentralized Cryptocurrency for Everyday Use**

Version 1.3.0
Date: July 2026

---

## Abstract

TritioCoin is a decentralized, peer-to-peer electronic cash system designed for everyday use. The system uses a hybrid Proof-of-Work/Proof-of-Stake consensus mechanism, delegation system, a binary wire protocol for efficient network communication, and a fully decentralized peer discovery system based on Kademlia DHT.

---

## 1. Introduction

### 1.1 Problem Statement

Current cryptocurrencies face several challenges:

1. **Centralization Risk**: Many cryptocurrencies rely on centralized seed nodes for peer discovery, creating single points of failure.

2. **ASIC Centralization**: Mining hardware centralization leads to network control by a few entities.

3. **Network Inefficiency**: Text-based protocols (JSON) waste bandwidth and are vulnerable to parsing ambiguities.

### 1.2 Solution

TritioCoin addresses these challenges with:

- **Memory-Hard PoW**: Blake2b with 256KB memory requirement per hash, resisting ASIC/FPGA optimization
- **Binary Wire Protocol**: Fixed 24-byte header with SHA256d checksums for efficient, validated communication
- **DHT Peer Discovery**: Kademlia-based decentralized peer discovery without central authorities
- **Dual Consensus**: PoW + PoS for security and decentralization
- **Delegation System**: Users can delegate TRC to validators without running infrastructure

---

## 2. Architecture

### 2.1 System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│  CLI Wallet │ Web Explorer │ REST API │ WebSocket           │
├─────────────────────────────────────────────────────────────┤
│                     Core Layer                               │
│  Blockchain │ Mining │ Transactions │ Consensus             │
│  Wallet │ HD Wallet │ Multi-Sig │ UTXO │ Delegation        │
├─────────────────────────────────────────────────────────────┤
│                    Network Layer                             │
│  P2P TCP │ TLS 1.3 │ Binary Wire Protocol │ DHT │ Gossip   │
├─────────────────────────────────────────────────────────────┤
│                    Storage Layer                             │
│  SQLite │ UTXO Set │ Block Pruning                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Block Structure

Each block contains:

| Field | Size | Description |
|-------|------|-------------|
| Version | 2 bytes | Protocol version |
| Index | 4 bytes | Block height |
| Timestamp | 8 bytes | Unix timestamp |
| Previous Hash | 32 bytes | Hash of previous block |
| Merkle Root | 32 bytes | Root of transaction tree |
| Difficulty | 4 bytes | Current mining difficulty |
| Nonce | 4 bytes | Proof-of-Work nonce |

Total header size: 86 bytes (binary, Big-Endian)

---

## 3. Cryptography

### 3.1 ECDSA (Elliptic Curve Digital Signature Algorithm)

- **Curve**: secp256k1 (same as Bitcoin)
- **Purpose**: Transaction signatures
- **Key Size**: 256 bits
- **Key Validation**: 1 ≤ k < n (curve order ≈ 2^256)

### 3.2 Key Derivation

- **BIP32**: Hierarchical Deterministic wallets
- **BIP39**: 24-word mnemonic backup (256-bit entropy)
- **BIP39 Passphrase**: Optional extra 256-bit entropy layer
- **BIP44**: Multi-account derivation (m/44'/9999'/0'/0/0)

### 3.3 Encryption

- **Wallet Storage**: AES-256-GCM
- **Key Derivation**: PBKDF2 (600,000 iterations)
- **Transport**: TLS 1.3

### 3.4 Collision Resistance

The secp256k1 curve has order n ≈ 2^256 ≈ 1.16 × 10^77.

| Metric | Value |
|--------|-------|
| Key space | 2^256 ≈ 1.16 × 10^77 |
| Birthday paradox threshold | ≈ 2^128 ≈ 3.4 × 10^38 wallets |
| Probability with 1 billion wallets | ≈ 10^-60 |

Additional defenses:
- Private key range validation (1 ≤ k < n)
- Entropy quality checks (non-zero, diversity ≥ 8)
- Local address collision registry
- BIP39 passphrase for extra entropy

---

## 4. Consensus

### 4.1 Proof-of-Work (PoW)

- **Algorithm**: Blake2b with memory-hardness
- **Memory**: 256 KB per hash
- **Structure**: Memory fill + random reads + chained rounds
- **Purpose**: ASIC/FPGA-resistant mining
- **Multi-threading**: Uses all CPU cores

### 4.2 Proof-of-Stake (PoS)

- **Minimum Stake**: Dynamic (2x current block reward, min 10 TRC, max 200 TRC)
- **Selection**: Stake-weighted random
- **Signature Threshold**: 3 validators per block
- **Reward Share**: 30% of block reward

### 4.3 Delegation

- **Minimum Delegation**: 1 TRC
- **Validator Commission**: 10%
- **Unbonding Period**: 7 days
- **Max Delegations**: 100 per address

### 4.4 Difficulty Adjustment

- **Interval**: Every 10 blocks
- **Target Block Time**: 5 minutes
- **Adjustment**: ±1 based on block time deviation

---

## 5. Economics

### 5.1 Supply

| Parameter | Value |
|-----------|-------|
| Maximum Supply | 19,000,000 TRC |
| Initial Block Reward | 50 TRC |
| Halving Interval | 190,000 blocks |
| Minimum Reward | 0.00000001 TRC |

### 5.2 Emission Schedule

```
Blocks 0-190,000:       50 TRC/block
Blocks 190,001-380,000: 25 TRC/block
Blocks 380,001-570,000: 12.5 TRC/block
...continues halving until ~0.00000001 TRC
```

### 5.3 Transaction Fees

- **Minimum Fee**: 0.0001 TRC
- **Fee Market**: Users set fees, miners prioritize higher fees
- **Burn Rate**: 10% of fees are burned (deflationary)

---

## 6. Network

### 6.1 Wire Protocol

TritioCoin uses a binary wire protocol inspired by Bitcoin's network protocol.

#### Header Format (24 bytes, Little-Endian)

```
┌──────────────┬──────────────┬───────────────┬──────────────┐
│ Magic (4B)   │ Cmd (12B)    │ Length (4B)   │ Checksum(4B) │
└──────────────┴──────────────┴───────────────┴──────────────┘
```

Struct: `<4s12sII`

| Field | Size | Description |
|-------|------|-------------|
| Magic | 4 bytes | `\xF9\xBE\xB4\xD9` — reject if mismatch |
| Command | 12 bytes | ASCII null-padded (e.g., `version\x00\x00\x00\x00\x00`) |
| Payload Length | 4 bytes (uint32) | Payload size in bytes |
| Checksum | 4 bytes (uint32) | First 4 bytes of SHA256d(payload) |

#### Security Properties

- **Magic bytes**: Prevents processing data from wrong network
- **SHA256d checksum**: Detects transmission corruption
- **Payload limit**: 2MB maximum — disconnects before reading oversized data
- **Fixed header**: Eliminates parsing ambiguities

### 6.2 Handshake Protocol

The handshake follows a strict state machine:

```
TCP connected → send version → receive version → validate →
send verack → receive verack → CONNECTION ESTABLISHED
```

#### Version Payload (`<IQQQI`, 28 bytes)

| Field | Size | Description |
|-------|------|-------------|
| Protocol Version | 4 bytes (uint32) | Protocol version (e.g., 70015) |
| Services | 8 bytes (uint64) | Service bitmask (1 = Full Node) |
| Timestamp | 8 bytes (uint64) | Current Unix epoch |
| Nonce | 8 bytes (uint64) | Random number (loopback prevention) |
| Block Height | 4 bytes (uint32) | Current blockchain height |

#### Validation Rules

- Reject connections if peer version < 70001
- Disconnect if received nonce == local nonce (self-connection)
- Both sides must exchange version + verack before any data

### 6.3 Gossip Protocol

#### Inventory Messages (Binary)

```
inv / getdata payload: <I32s> (36 bytes)
├── Inventory Type (4 bytes): 1=TX, 2=Block
└── Hash (32 bytes): SHA-256 of the data
```

#### Propagation Flow

1. Node receives new TX/Block and validates it
2. Sends `inv` with hash to all connected peers
3. Receiving peer checks if it has the hash locally
4. If NOT possessed → replies with `getdata`
5. Original node responds with full payload (JSON)

#### Deduplication

Each `PeerSession` maintains a `known_inventory` set to prevent redundant announcements to the same peer.

### 6.4 Keep-Alive

- **Interval**: 30 seconds of inactivity
- **Mechanism**: `ping` with 8-byte nonce (`<Q>`)
- **Response**: `pong` with identical nonce
- **Timeout**: 10 seconds without pong → disconnect

### 6.5 Anti-DoS (Ban Score)

| Action | Points | Description |
|--------|--------|-------------|
| Malformed packet | +10 | Bad checksum, wrong magic, unknown command |
| Invalid data | +50 | Corrupted block/transaction |
| **Threshold** | **100** | **Disconnect + blacklist** |

### 6.6 Peer Discovery

#### Primary: Kademlia DHT

- **Node ID**: 160-bit random identifier
- **Routing Table**: 160 k-buckets (K=20)
- **Operations**: FIND_NODE, STORE, GET_PEERS
- **Discovery**: Iterative lookup with alpha=3 concurrency

#### Fallback: Seed Nodes

- GitHub-hosted seed list
- Local seeds.json file
- Can be specified via CLI: `--seed IP:PORT`

### 6.7 Security Summary

| Layer | Protection |
|-------|------------|
| Wire Protocol | SHA256d checksum, magic bytes, fixed header |
| Handshake | Version validation, nonce-based self-connection prevention |
| Transport | TLS 1.3 encryption |
| Rate Limiting | 200 messages/10s per peer |
| Ban System | Score-based banning (threshold 100) |
| Keep-Alive | Ping/pong with nonce echo |
| Memory Safety | 2MB payload limit, disconnect before reading |
| Inventory | Per-peer deduplication sets |

---

## 7. UTXO Model

### 7.1 Transaction Structure

```json
{
    "sender": "public_key_hex",
    "recipient": "address",
    "amount": 10.0,
    "fee": 0.001,
    "inputs": ["utxo_hash_1", "utxo_hash_2"],
    "change": 4.999,
    "signature": "ecdsa_hex"
}
```

### 7.2 UTXO Selection

- **Algorithm**: Largest-first
- **Automatic Change**: Change outputs created automatically
- **Double-Spend Prevention**: UTXO tracking in database

---

## 8. Multi-Signature

### 8.1 Scheme

- **Format**: M-of-N (e.g., 2-of-3, 3-of-5)
- **Address Prefix**: M (e.g., M3KNb77w6V9FtESt...)
- **Redeem Script**: Standard Bitcoin-like CHECKMULTISIG

### 8.2 Use Cases

- Shared wallets (families, businesses)
- Escrow services
- Treasury management

---

## 9. API

### 9.1 REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/status | Network status |
| GET | /api/block/{height} | Block data |
| GET | /api/balance/{address} | Address balance |
| GET | /api/tx/{hash} | Transaction data |
| GET | /api/mempool | Pending transactions |
| GET | /api/peers | Connected peers |
| GET | /api/validators | Active validators |
| GET | /api/delegations/{address} | Delegations |
| GET | /api/delegation/stats | Delegation statistics |
| POST | /api/tx | Submit transaction |
| POST | /api/validator/register | Register as validator |
| POST | /api/delegate | Delegate TRC |
| POST | /api/undelegate | Start undelegation |
| POST | /api/claim | Claim rewards |

### 9.2 WebSocket

Real-time updates for:
- New blocks
- New transactions
- Network status changes

---

## 10. Security Analysis

### 10.1 Quantum Resistance

| Attack | ECDSA | WOTS+ | Hybrid |
|--------|-------|-------|--------|
| Shor's Algorithm | Vulnerable | Secure | Secure |
| Grover's Algorithm | Secure | Secure | Secure |
| Brute Force | Secure | Secure | Secure |

### 10.2 Consensus Security

- **51% Attack**: Requires majority of hash power (PoW) OR stake (PoS)
- **Nothing-at-Stake**: Mitigated by validator requirements
- **Long-Range Attack**: Mitigated by checkpointing

### 10.3 Network Security

- **Eclipse Attack**: Mitigated by diverse peer connections
- **Sybil Attack**: Mitigated by reputation system and stake requirements
- **DoS Attack**: Mitigated by rate limiting, connection cooldowns, ban score system
- **Data Corruption**: Mitigated by SHA256d checksums in wire protocol
- **Memory Exhaustion**: Mitigated by 2MB payload limit
- **Self-Connection**: Mitigated by nonce comparison in version handshake

### 10.4 Wallet Security

- **Key Space**: 2^256 ≈ 10^77 (collision probability ≈ 10^-60 for 1B wallets)
- **Key Validation**: Range check against curve order
- **Entropy Quality**: Multi-layer validation with retry
- **Storage**: AES-256-GCM with PBKDF2 (600K iterations)
- **Recovery**: BIP39 24-word mnemonic with optional passphrase

---

## 11. Comparison

| Feature | Bitcoin | Ethereum | TritioCoin |
|---------|---------|----------|------------|
| Consensus | PoW | PoS | PoW + PoS |
| Quantum Safe | No | No | Yes |
| Block Time | 10 min | 12 sec | 5 min |
| Max Supply | 21M | ∞ | 19M |
| Multi-Sig | Yes | Yes | Yes |
| HD Wallet | Yes | Yes | Yes |
| DHT Discovery | No | No | Yes |
| Delegation | No | Yes | Yes |
| Burn Rate | No | Yes | 10% |
| Dynamic Stake | No | No | Yes |
| Binary Wire Protocol | Yes | No | Yes |
| Anti-DoS Ban Score | No | No | Yes |

---

## 12. Conclusion

TritioCoin provides a secure, decentralized cryptocurrency suitable for everyday use with built-in protection against future quantum computing threats. The binary wire protocol ensures efficient and validated network communication, while the anti-collision defenses in wallet generation provide mathematical certainty against key reuse. The hybrid consensus mechanism, delegation system, and decentralized peer discovery make it a robust platform for the post-quantum era.

---

## References

1. Nakamoto, S. (2008). Bitcoin: A Peer-to-Peer Electronic Cash System.
2. BIP32 - Hierarchical Deterministic Wallets
3. BIP39 - Mnemonic Code for Generating Deterministic Keys
4. BIP44 - Multi-Account Hierarchy
5. Kademlia: A Peer-to-Peer Information System Based on the XOR Metric
6. Blake2b: Fast Secure Hash Function
7. secp256k1: Elliptic Curve Parameters
