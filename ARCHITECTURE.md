# Arquitetura do TritioCoin — Visao Geral

TritioCoin e uma criptomoeda descentralizada com arquitetura modular projetada para seguranca e desempenho.

---

## Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    Camada de Aplicacao                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  CLI Wallet  │  │  Web UI     │  │   REST API + WS     │ │
│  │  wallet.py   │  │  explorer   │  │   network/api.py    │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
├─────────┼────────────────┼────────────────────┼─────────────┤
│         │     Camada de Logica Principal      │             │
│  ┌──────┴────────────────────────────────────┴──────────┐  │
│  │                                                       │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │  │
│  │  │  Blockchain  │  │    Miner    │  │   Consenso   │ │  │
│  │  │  core/block  │  │  core/miner │  │  core/consen │ │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘ │  │
│  │         │                │                 │          │  │
│  │  ┌──────┴────────────────┴─────────────────┴───────┐ │  │
│  │  │              Motor de Transacoes                 │ │  │
│  │  │  ┌─────────┐  ┌─────────┐  ┌─────────────────┐ │ │  │
│  │  │  │  UTXO   │  │ Mempool │  │ Multi-Sig       │ │ │  │
│  │  │  └─────────┘  └─────────┘  └─────────────────┘ │ │  │
│  │  └─────────────────────────────────────────────────┘ │  │
│  │                                                       │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │  │
│  │  │   Wallet    │  │  HD Wallet  │  │   Multi-Sig  │ │  │
│  │  │  ECDSA/AES  │  │  BIP32/44   │  │  M-of-N      │ │  │
│  │  └─────────────┘  └─────────────┘  └──────────────┘ │  │
│  │                                                       │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    Camada de Rede                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   P2P Node  │  │ Wire Proto  │  │  Peer Reputation   │ │
│  │  PeerSession│  │ 24B Header  │  │  Score/Banning     │ │
│  │  TLS 1.3    │  │ SHA256d CRC │  │  +10/+50/threshold │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Camada de Armazenamento                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   SQLite    │  │    WAL      │  │   Block Pruning     │ │
│  │  Database   │  │   Mode      │  │   Gerenciamento     │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Wire Protocol (P2P Binario)

### Header — 24 bytes, Little-Endian

```
┌──────────────┬──────────────┬───────────────┬──────────────┐
│ Magic (4B)   │ Cmd (12B)    │ Length (4B)   │ Checksum(4B) │
└──────────────┴──────────────┴───────────────┴──────────────┘
```

Struct: `<4s12sII`

| Campo | Tamanho | Descricao |
|-------|---------|-----------|
| Magic | 4 bytes | `\xF9\xBE\xBE\xB4\xD9` — rejeita se diferente |
| Command | 12 bytes | ASCII null-padded (ex: `version\x00\x00\x00\x00\x00`) |
| Payload Length | 4 bytes (uint32) | Tamanho do payload em bytes |
| Checksum | 4 bytes (uint32) | Primeiros 4 bytes de SHA256d(payload) |

### Handshake — Maquina de Estados

```
TCP conectado
    ↓
Envia version (binario <IQQQI>)
    ↓
Recebe version do par
    ↓
Valida: versao >= 70001, nonce != local
    ↓
Envia verack (payload vazio)
    ↓
Recebe verack do par
    ↓
Estado: CONEXAO_ESTABELECIDA
```

### Payload do Version (`<IQQQI`)

| Campo | Tamanho | Descricao |
|-------|---------|-----------|
| Protocol Version | 4 bytes (uint32) | Versao do protocolo (ex: 70015) |
| Services | 8 bytes (uint64) | Bitmask de servicos (1 = Full Node) |
| Timestamp | 8 bytes (uint64) | Unix epoch atual |
| Nonce | 8 bytes (uint64) | Numero aleatorio (prevencao de loopback) |
| Block Height | 4 bytes (uint32) | Altura atual da blockchain |

### Ping/Pong

```
ping: 8 bytes nonce (<Q>)
pong: mesmo nonce ecoado (<Q>)
```

- Heartbeat: 30s de inatividade → envia ping
- Timeout: 10s sem pong → fecha conexao

### INV/GETDATA (Gossip Binario)

```
Payload: <I32s> (36 bytes total)
├── Inventory Type (4 bytes): 1=TX, 2=Block
└── Hash (32 bytes): SHA-256 do dado
```

Fluxo:
1. No recebe nova TX/Bloco → valida
2. Envia `inv` com hash para todos os peers
3. Peer receptor verifica se possui o hash
4. Se NAO possuir → responde com `getdata`
5. No original envia mensagem com payload completo

---

## Fluxo de uma Transacao

### Passo a passo

```
1. Usuario cria transacao (valores ocultos com Pedersen Commitments)
2. Transacao assinada com ECDSA
3. Transacao adicionada a mempool (com fee dinamico)
4. Transacao transmitida via inv (hash binario)
5. Peer responde com getdata se nao possui
6. Transacao completa enviada (JSON sobre wire protocol)
7. Minerador seleciona transacoes da mempool
8. Minerador cria bloco com transacoes (70% recompensa)
9. Bloco transmitido via inv para a rede
10. Validadores assinam o bloco (30% recompensa)
11. Bloco adicionado a blockchain (com checkpoint)
12. UTXOs atualizados
```

---

## Anti-DoS e Seguranca de Rede

### Ban Score

| Acao | Pontos | Descricao |
|------|--------|-----------|
| Pacote malformado | +10 | Checksum invalido, magic errado, comando desconhecido |
| Dado invalido | +50 | Bloco/tx corrompido ou com dados invalidos |
| **Threshold** | **100** | **Desconexao + blacklist em memoria** |

### Limites

| Limite | Valor | Acao |
|--------|-------|------|
| Payload maximo | 2 MB | Desconecta IMEDIATAMENTE (antes de ler) |
| Peers totais | 50 | Rejeita novas conexoes |
| Peers por IP | 3 | Rejeita novas conexoes do mesmo IP |
| Mensagens/10s | 200 | Rate limit por peer |
| Cooldown reconexao | 60s | Entre tentativas ao mesmo peer |

### Keep-Alive

```
30s sem atividade → envia ping (8 bytes nonce)
10s sem pong     → fecha conexao
Nonce echo       → valida que pong corresponde ao ping enviado
```

---

## Modelo de Seguranca

### Primitivas Criptograficas

| Componente | Algoritmo | Finalidade |
|------------|-----------|------------|
| Assinaturas | ECDSA (secp256k1) | Autenticacao de transacoes |
| Hashing | SHA-256 | Hash de blocos, Merkle trees, checksums |
| Mineracao | Blake2b memory-hard | PoW resistente a ASIC |
| Criptografia | AES-256-GCM | Criptografia de carteira |
| KDF | PBKDF2 (600K) | Derivacao de senha |
| P2P | TLS 1.3 | Criptografia de rede |
| Wire Protocol | SHA256d checksum | Integridade de mensagens |

### Protecao de Carteira (Anti-Colisao)

| Defesa | Descricao |
|--------|-----------|
| Validacao de range | Chave em [1, n-1] (ordem da curva secp256k1) |
| Validacao de entropia | Bytes nao-zero, diversidade >= 8, retry 3x |
| Base58Check | Checksum do endereco verificado ao carregar |
| Registro local | SHA-256 de enderecos gerados (detecta auto-colisao) |
| Passphrase BIP39 | 256 bits extras de entropia opcional |
| Fallback CSPRNG | `secrets.token_bytes()` se `os.urandom()` falhar |

### Como suas chaves funcionam

```
Chave Privada (256-bit, secp256k1)
     ↓
Validada: 1 ≤ k < n (ordem da curva)
     ↓
Assina transacoes (ECDSA)
     ↓
Gera Chave Publica (64 bytes)
     ↓
SHA-256 → RIPEMD-160 → Base58Check
     ↓
Endereco (T1ABC...)
```

---

## Mecanismo de Consenso

### PoW (Proof of Work)

- **Algoritmo:** Blake2b com memory-hardness (256KB)
- **Multi-threading:** Usa todas as CPUs
- **Proposito:** Mineracao resistente a ASIC

### PoS (Proof of Stake)

- **Stake minimo:** Dinamico (2x recompensa atual, min 10, max 200 TRC)
- **Selecao:** Ponderada por stake
- **Limiar:** 3 assinaturas por bloco
- **Recompensa:** 30% da recompensa do bloco

### Delegacao

- **Stake minimo para delegar:** 1 TRC
- **Comissao do validador:** 10%
- **Periodo de unbonding:** 7 dias

---

## Protocolo de Rede — Tipos de Mensagem

### Wire Protocol (Binario)

| Comando | Payload | Descricao |
|---------|---------|-----------|
| `version` | `<IQQQI>` (28B) | Handshake: versao, services, timestamp, nonce, height |
| `verack` | vazio (0B) | Confirmacao do handshake |
| `ping` | `<Q>` (8B) | Keep-alive com nonce |
| `pong` | `<Q>` (8B) | Resposta com mesmo nonce |
| `inv` | `<I32s>` (36B) | Anuncio de inventario (TX ou Block) |
| `getdata` | `<I32s>` (36B) | Solicitacao de item de inventario |

### JSON sobre Wire Protocol (Backward-Compatible)

| Tipo | Direcao | Descricao |
|------|---------|-----------|
| `json` | Ambos | Mensagem JSON genérica (blocos, txs, sync) |
| NEW_BLOCK | Broadcast | Bloco completo |
| COMPACT_BLOCK | Broadcast | Header + hashes de tx |
| NEW_TX | Broadcast | Nova transacao |
| GET_BLOCK | Request | Solicita bloco especifico |
| GET_TX | Request | Solicita transacao especifica |
| GET_CHAIN | Request | Sincronizacao da chain |
| CHAIN | Response | Dados completos da chain |
| SYNC_REQUEST | Request | Sincronizacao em lote |
| SYNC_BLOCK_BATCH | Response | Lote de blocos |
| REQUEST_SIGNATURE | Request | Solicitacao de assinatura |
| BLOCK_SIGNATURE | Response | Assinatura do validador |
| REGISTER_VALIDATOR | Broadcast | Registro de validador |
| DELEGATE | Broadcast | Delegacao de stake |

---

## Schema do Banco de Dados

### Tabelas

```sql
blocks (height, hash, previous_hash, timestamp, nonce, difficulty, pow_hash, data)
transactions (tx_hash, block_height, sender, recipient, amount, fee, timestamp)
balances (address, balance)
utxos (tx_hash, sender, recipient, amount, fee, block_height, spent)
mempool (tx_hash, sender, recipient, amount, fee, timestamp)
metadata (key, value)
```

---

## Prevencao de Problemas

### Double-spend (Gasto duplo)
```
- UTXO rastreia cada saida de transacao
- Se um UTXO ja foi gasto, nao pode ser gasto novamente
- Validacao em tempo real antes de aceitar transacao
```

### Blocos duplicados
```
- Verificacao de hash duplicado
- Verificacao de height duplicado
- Apenas o primeiro bloco e aceito
```

### Ataques a rede
```
- Wire protocol com checksum SHA256d → previne corrupcao
- Magic bytes → previne processamento de dados errados
- Ban score → Remove peers maliciosos
- Rate limiting → Previne DoS
- Keep-alive com nonce → Detecta peers mortos
- Payload limit (2MB) → Previne estouro de memoria
- Self-connection prevention → Evita loops
```
