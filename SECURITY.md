# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public GitHub issue
2. Email security@tritiocoin.example.com (or create a private issue)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Security Measures

### Cryptographic

- **Key Storage**: AES-256-GCM encryption with PBKDF2 (600K iterations)
- **Transport**: TLS 1.3 for all P2P communication
- **Signatures**: ECDSA secp256k1 + WOTS+ (quantum-resistant)
- **Hashing**: SHA-256 for block hashing and Merkle trees

### Network

- **Rate Limiting**: 100 messages/10s per peer
- **Peer Reputation**: Automatic banning of malicious peers
- **Message Validation**: All messages validated before processing
- **Max Message Size**: 10MB limit

### Consensus

- **Double-Spend**: UTXO tracking prevents double-spending
- **Block Validation**: Full validation of all blocks and transactions
- **Supply Cap**: Hard cap of 21M TRC enforced at consensus level

### Storage

- **Atomic Writes**: Crash-safe database operations
- **WAL Mode**: SQLite Write-Ahead Logging for consistency
- **Backup**: BIP39 mnemonics for wallet recovery

## Known Limitations

1. Self-signed TLS certificates (not CA-verified)
2. No SPV (Simplified Payment Verification) yet
3. No formal security audit completed

## Update Policy

Security updates will be released as soon as possible after vulnerability disclosure.
