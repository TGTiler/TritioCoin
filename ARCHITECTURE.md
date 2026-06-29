# Arquitetura do TritioVisao Geral

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
│  │   P2P Node  │  │   TLS 1.3   │  │  Peer Reputation   │ │
│  │  TCP/Gossip │  │  Criptografia │  │  Score/Banning     │ │
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

## Fluxo de uma Transacao

### Passo a passo

```
1. Usuario cria transacao (valores ocultos com Pedersen Commitments)
2. Transacao assinada com ECDSA
3. Transacao adicionada a mempool (com fee dinamico)
4. Transacao transmitida via gossip
5. Minerador seleciona transacoes da mempool
6. Minerador cria bloco com transacoes (70% recompensa)
7. Bloco transmitido para a rede (batch de 50)
8. Validadores assinam o bloco (30% recompensa)
9. Bloco adicionado a blockchain (com checkpoint)
10. UTXOs atualizados
```

### Como funciona na pratica

```
Usuario clica "Enviar"
     ↓
Carteira cria transacao
     ↓
Assina com chave privada (ECDSA)
     ↓
Envia para mempool (pool de pendentes)
     ↓
Minerador pega transacoes do pool
     ↓
Inclui no bloco que esta minerando
     ↓
Encontra nonce valido (Blake2b memory-hard)
     ↓
Transmite bloco para rede
     ↓
Validadores verificam e assinam
     ↓
Bloco confirmado na chain
     ↓
Saldo atualizado
```

---

## Fluxo de Mineracao

```
1. Minerador seleciona transacoes da mempool
2. Cria transacao coinbase (recompensa)
3. Monta bloco com header + transacoes
4. Calcula Merkle root
5. Inicia loop de mineracao (Argon2id)
6. Encontra nonce valido (hash com N zeros)
7. Transmite bloco compacto
8. Espera assinaturas de validadores
9. Adiciona bloco a chain
```

---

## Modelo de Seguranca

### Primitivas Criptograficas

| Componente | Algoritmo | Finalidade |
|------------|-----------|------------|
| Assinaturas | ECDSA (secp256k1) | Autenticacao de transacoes |
| Quantum | WOTS+ (SHA-256) | Assinaturas futuras |
| Hashing | SHA-256 | Hash de blocos, Merkle trees |
| Mineracao | Argon2id | PoW resistente a ASIC |
| Criptografia | AES-256-GCM | Criptografia de carteira |
| KDF | PBKDF2 (600K) | Derivacao de senha |
| P2P | TLS 1.3 | Criptografia de rede |

### Como suas chaves funcionam

```
Chave Privada (secreta)
     ↓
Assina transacoes
     ↓
Gera Chave Publica
     ↓
Gera Endereco (T1ABC...)
     ↓
Other people enviam TRC para este endereco
```

---

## Modelo de Confiabilidade

- Sem autoridade central
- Consenso via PoW + PoS
- Prevencao de double-spend via UTXO
- Stake dos validadores como seguranca economica

---

## Mecanismo de Consenso

### PoW (Proof of Work)

- **Algoritmo:** Argon2id
- **Memoria:** 64 MB
- **Custo de tempo:** 1 iteracao
- **Paralelismo:** 1
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
- **Max delegacoes:** 100 por endereco

### Ajuste de Dificuldade

- **Intervalo:** A cada 10 blocos
- **Alvo:** 5 minutos por bloco
- **Ajuste:** ±1 baseado na diferenca do tempo

---

## Protocolo de Rede

### Tipos de Mensagem

| Tipo | Direcao | Descricao |
|------|---------|-----------|
| HANDSHAKE | Ambos | Conexao inicial com negociacao de versao |
| HANDSHAKE_ACK | Ambos | Conexao confirmada |
| BLOCK_ANNOUNCE | Broadcast | Anuncio de bloco (hash + height) |
| TX_ANNOUNCE | Broadcast | Anuncio de transacao (hash) |
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
| PING/PONG | Ambos | Keepalive |

### Rate Limiting

- 200 mensagens por 10 segundos por peer
- Ban automatico em score de reputacao -50
- Duracao do ban: 1 hora (configuravel)
- Cooldown de reconexao: 60 segundos

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

### Indices

```sql
idx_tx_sender ON transactions(sender)
idx_tx_recipient ON transactions(recipient)
idx_tx_block ON transactions(block_height)
idx_utxo_sender ON utxos(sender, spent)
```

---

## Fluxo de Dados

### Transacao

```
1. Usuario cria transacao
2. Transacao assinada com ECDSA (+ opcional WOTS+)
3. Transacao adicionada a mempool
4. Transacao transmitida para peers
5. Minerador seleciona transacoes da mempool
6. Minerador cria bloco com transacoes
7. Bloco transmitido para a rede
8. Validadores assinam bloco (PoS)
9. Bloco adicionado a blockchain
10. UTXOs atualizados
```

### Mineracao

```
1. Minerador seleciona transacoes da mempool
2. Cria transacao coinbase (recompensa)
3. Monta bloco com header + transacoes
4. Calcula Merkle root
5. Inicia loop de mineracao (Argon2id)
6. Encontra nonce valido (hash com N zeros)
7. Transmite bloco compacto
8. Espera assinaturas de validadores
9. Adiciona bloco a chain
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
- Rate limiting previne DoS
- Reputacao previne Sybil
- DHT descentralizado previne Eclipse
- TLS previne MitM
```
