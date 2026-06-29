# Documentacao da API TritioCoin

## URL Base

```
http://127.0.0.1:8080
```

## Autenticacao

Nenhuma autenticacao necessaria para endpoints publicos.
Chave privada necessaria para enviar transacoes (assinar client-side).

## Rate Limiting

- **Limite**: 100 requisicoes por minuto por IP
- **Resposta**: HTTP 429 quando excedido

---

## Como Usar a API

### Via navegador

Acesse `http://localhost:8080/explorer` para o explorador visual.

### Via curl (Linux/Mac)

```bash
# Ver status
curl http://localhost:8080/api/status

# Ver saldo
curl http://localhost:8080/api/balance/T1AcSHHR...

# Enviar transacao
curl -X POST http://localhost:8080/api/tx \
  -H "Content-Type: application/json" \
  -d '{"sender":"...","recipient":"...","amount":10,"fee":0.001}'
```

### Via Python

```python
import requests

# Ver status
resp = requests.get("http://localhost:8080/api/status")
print(resp.json())

# Ver saldo
resp = requests.get("http://localhost:8080/api/balance/T1AcSHHR...")
print(resp.json()["balance"])
```

---

## Endpoints

### GET /api/status

Retorna informacoes sobre a rede.

**Exemplo de resposta:**
```json
{
    "network": "mainnet",
    "height": 148,
    "transactions": 40,
    "difficulty": 2,
    "reward_trc": 45.0,
    "total_mined_trc": 6660.0,
    "total_burned_trc": 10.5,
    "circulating_trc": 6649.5,
    "supply_remaining_trc": 12350350.5,
    "peers": 5,
    "mempool": 0,
    "addresses": 15,
    "version": "1.0.0"
}
```

**O que significa cada campo:**
- `height` - Quantos blocos existem na chain
- `transactions` - Total de transacoes ja feitas
- `difficulty` - Dificuldade atual da mineracao
- `reward_trc` - Quanto ganha por bloco minerado
- `total_mined_trc` - Total de TRC ja minerados
- `total_burned_trc` - Total de TRC queimados (10% das taxas)
- `circulating_trc` - TRC em circulacao (minado - queimado)
- `peers` - Quantos peers estao conectados
- `mempool` - Transacoes esperando ser processadas

---

### GET /api/block/{height}

Retorna dados de um bloco pela altura.

**Parametros:**
- `height` (inteiro) - Altura do bloco

**Exemplo:**
```
GET /api/block/100
```

**Resposta:**
```json
{
    "header": {
        "version": 1,
        "index": 100,
        "timestamp": 1687500000,
        "previous_hash": "0000000000000000...",
        "merkle_root": "abc123...",
        "difficulty": 2,
        "nonce": 12345
    },
    "transactions": [
        {
            "sender": "COINBASE",
            "recipient": "T1AcSHHR...",
            "amount": 45.0,
            "fee": 0,
            "hash": "def456..."
        }
    ],
    "hash": "0000abc123...",
    "pow_hash": "0000def789...",
    "validator_signatures": []
}
```

---

### GET /api/blocks

Retorna lista de blocos com paginacao.

**Parametros de query:**
- `limit` (inteiro, padrao: 10) - Numero de blocos
- `offset` (inteiro, padrao: 0) - Posicao inicial

**Exemplo:**
```
GET /api/blocks?limit=5&offset=0
```

**Resposta:**
```json
{
    "blocks": [...],
    "total": 148
}
```

---

### GET /api/balance/{address}

Retorna o saldo de um endereco.

**Parametros:**
- `address` (string) - Endereco TritioCoin

**Exemplo:**
```
GET /api/balance/T1AcSHHR...
```

**Resposta:**
```json
{
    "address": "T1AcSHHR...",
    "balance": 150.0
}
```

**Notas:**
- O saldo e em TRC (nao satoshis)
- Inclui todas as transacoes confirmadas

---

### GET /api/tx/{tx_hash}

Retorna detalhes de uma transacao.

**Parametros:**
- `tx_hash` (string) - Hash da transacao

**Exemplo:**
```
GET /api/tx/abc123def456...
```

**Resposta:**
```json
{
    "tx_hash": "abc123...",
    "block_height": 148,
    "sender": "T1XYZ...",
    "recipient": "T1ABC...",
    "amount": 10.0,
    "fee": 0.001,
    "timestamp": 1687500000,
    "signature_mode": "ecdsa"
}
```

---

### GET /api/address/{address}

Retorna detalhes do endereco e historico.

**Parametros:**
- `address` (string) - Endereco TritioCoin

**Resposta:**
```json
{
    "address": "T1AcSHHR...",
    "balance": 150.0,
    "transactions": [
        {
            "tx_hash": "abc123...",
            "sender": "T1XYZ...",
            "amount": 50.0,
            "block_height": 100
        }
    ]
}
```

---

### GET /api/mempool

Retorna transacoes pendentes (nao confirmadas).

**Resposta:**
```json
{
    "mempool": [
        {
            "tx_hash": "abc123...",
            "sender": "T1XYZ...",
            "recipient": "T1ABC...",
            "amount": 5.0,
            "fee": 0.001
        }
    ],
    "count": 1
}
```

---

### GET /api/peers

Retorna peers conectados.

**Resposta:**
```json
{
    "peers": ["192.168.1.10:8333", "192.168.1.20:8333"],
    "count": 2
}
```

---

### GET /api/validators

Retorna validadores ativos.

**Resposta:**
```json
{
    "validators": [
        {
            "address": "T1Validator...",
            "stake": 200.0,
            "active": true,
            "blocks_signed": 15
        }
    ],
    "stats": {
        "total_validators": 10,
        "active_validators": 8,
        "total_stake": 2000.0,
        "min_stake": 100.0,
        "signature_threshold": 3
    }
}
```

---

### POST /api/tx

Envia uma nova transacao.

**Corpo da requisicao:**
```json
{
    "sender": "chave_publica_hex",
    "recipient": "endereco_destinatario",
    "amount": 10.0,
    "fee": 0.001,
    "private_key": "chave_privada_hex_opcional"
}
```

**Resposta (sucesso):**
```json
{
    "status": "ok",
    "hash": "abc123def456..."
}
```

**Resposta (erro):**
```json
{
    "error": "Saldo insuficiente"
}
```

**Exemplo com Python:**
```python
import requests

data = {
    "sender": "sua_chave_publica",
    "recipient": "T1Destinatario...",
    "amount": 10.0,
    "fee": 0.001,
    "private_key": "sua_chave_privada"
}

resp = requests.post("http://localhost:8080/api/tx", json=data)
print(resp.json())
```

---

### POST /api/validator/register

Registra um novo validador.

**Corpo da requisicao:**
```json
{
    "address": "endereco_validador",
    "stake": 200.0,
    "pubkey": "chave_publica_hex"
}
```

**Resposta:**
```json
{
    "status": "ok"
}
```

---

## WebSocket

### Conexao

```
ws://localhost:8080/ws
```

### Eventos Recebidos

Quando conectado, voce recebe:

```json
// Conexao estabelecida
{
    "type": "connected",
    "height": 148,
    "peers": 5
}

// Novo bloco mined
{
    "type": "new_block",
    "height": 149,
    "hash": "0000abc...",
    "tx_count": 3
}

// Nova transacao
{
    "type": "new_tx",
    "tx": {
        "hash": "abc123...",
        "amount": 10.0,
        "recipient": "T1ABC..."
    }
}
```

### Mensagens Enviadas

```json
// Pedir status
{"type": "get_status"}

// Pedir bloco especifico
{"type": "get_block", "height": 100}

// Pedir saldo
{"type": "get_balance", "address": "T1ABC..."}

// Manter conexao viva
{"type": "ping"}
```

### Exemplo com JavaScript

```javascript
const ws = new WebSocket('ws://localhost:8080/ws');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Recebido:', data);
};

ws.onopen = function() {
    // Pedir status apos conectar
    ws.send(JSON.stringify({"type": "get_status"}));
};
```

---

## Erros Comuns

| Erro | Significado | Solucao |
|------|-------------|---------|
| 404 | Endereco/bloco nao encontrado | Verifique o hash/endereco |
| 400 | Dados invalidos | Verifique o JSON enviado |
| 500 | Erro interno | Verifique os logs do servidor |
| Connection refused | API nao esta rodando | Inicie o no com `python main.py` |
