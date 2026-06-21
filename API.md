# TritioCoin API Documentation

## Base URL

```
http://localhost:8080
```

## Authentication

No authentication required for public endpoints. Private key required for transaction submission.

## Endpoints

### GET /api/status

Returns network status information.

**Response:**
```json
{
    "height": 148,
    "transactions": 40,
    "difficulty": 2,
    "reward": 50.0,
    "total_mined": 7350.0,
    "supply_remaining": 20992650.0,
    "peers": 5,
    "mempool": 0,
    "version": "1.0.0"
}
```

### GET /api/block/{height}

Returns block data by height.

**Parameters:**
- `height` (integer) - Block height

**Response:**
```json
{
    "header": {
        "version": 1,
        "index": 148,
        "timestamp": 1687500000,
        "previous_hash": "...",
        "merkle_root": "...",
        "difficulty": 2,
        "nonce": 12345
    },
    "transactions": [...],
    "hash": "...",
    "pow_hash": "..."
}
```

### GET /api/blocks

Returns list of blocks with pagination.

**Query Parameters:**
- `limit` (integer, default: 10) - Number of blocks
- `offset` (integer, default: 0) - Starting offset

**Response:**
```json
{
    "blocks": [...],
    "total": 148
}
```

### GET /api/balance/{address}

Returns balance for an address.

**Parameters:**
- `address` (string) - TritioCoin address

**Response:**
```json
{
    "address": "T1AcSHHR...",
    "balance": 150.0
}
```

### GET /api/tx/{tx_hash}

Returns transaction details.

**Parameters:**
- `tx_hash` (string) - Transaction hash

**Response:**
```json
{
    "tx_hash": "...",
    "block_height": 148,
    "sender": "...",
    "recipient": "...",
    "amount": 10.0,
    "fee": 0.001,
    "timestamp": 1687500000
}
```

### GET /api/address/{address}

Returns address details and transaction history.

**Parameters:**
- `address` (string) - TritioCoin address

**Response:**
```json
{
    "address": "T1AcSHHR...",
    "balance": 150.0,
    "transactions": [...]
}
```

### GET /api/mempool

Returns pending transactions.

**Response:**
```json
{
    "mempool": [...],
    "count": 5
}
```

### GET /api/peers

Returns connected peers.

**Response:**
```json
{
    "peers": ["192.168.1.10:8333", "192.168.1.20:8333"],
    "count": 2
}
```

### GET /api/validators

Returns active validators.

**Response:**
```json
{
    "validators": [...],
    "stats": {
        "total_validators": 10,
        "active_validators": 8,
        "total_stake": 2000.0
    }
}
```

### POST /api/tx

Submit a new transaction.

**Request Body:**
```json
{
    "sender": "sender_public_key_hex",
    "recipient": "recipient_address",
    "amount": 10.0,
    "fee": 0.001,
    "private_key": "optional_private_key_hex"
}
```

**Response:**
```json
{
    "status": "ok",
    "hash": "transaction_hash"
}
```

### POST /api/validator/register

Register as a validator.

**Request Body:**
```json
{
    "address": "validator_address",
    "stake": 200.0,
    "pubkey": "public_key_hex"
}
```

**Response:**
```json
{
    "status": "ok"
}
```

## WebSocket

### Connection

```
ws://localhost:8080/ws
```

### Events Received

```json
{
    "type": "connected",
    "height": 148,
    "peers": 5
}

{
    "type": "new_block",
    "height": 149,
    "hash": "...",
    "tx_count": 3
}

{
    "type": "new_tx",
    "tx": {...}
}
```

### Messages Sent

```json
{"type": "get_status"}
{"type": "get_block", "height": 100}
{"type": "get_balance", "address": "T1AcSHHR..."}
{"type": "ping"}
```
