# Politica de Seguranca - TritioCoin

## Versoes Suportadas

| Versao | Suportada |
|--------|-----------|
| 1.2.x  | Sim       |
| 1.1.x  | Sim       |

---

## Como Reportar Vulnerabilidades

Se voce encontrar uma vulnerabilidade:

1. **NAO** abra um issue publico no GitHub
2. Crie um issue PRIVADO no GitHub
3. Inclua:
   - Descricao da vulnerabilidade
   - Passos para reproduzir
   - Impacto potencial
   - Sugerir correcao (se possivel)

---

## Medidas de Seguranca

### Criptografia

| Componente | Algoritmo | Descricao |
|------------|-----------|-----------|
| Armazenamento | AES-256-GCM | Criptografia da carteira |
| Derivacao de chave | PBKDF2 (600K iteracoes) | Protecao contra bruteforce |
| Transporte | TLS 1.3 | Conexao P2P criptografada |
| Assinaturas | ECDSA secp256k1 | Assinatura de transacoes |
| Hashing | SHA-256, Blake2b | Hash de blocos e PoW memory-hard |
| Privacidade | Pedersen Commitments | Valores de transacoes ocultos |

### Como sua carteira e protegida

```
1. Sua chave privada e criptografada com AES-256-GCM
2. A senha e processada com PBKDF2 (600.000 iteracoes)
3. Senha forte obrigatoria (min 8 chars, 1 maiuscula, 1 numero)
4. Arquivo criado com permissoes 0o600 (so owner)
5. Carteira legacy (sem criptografia) e rejeitada
```

### Rede

| Medida | Descricao |
|--------|-----------|
| Rate Limiting API | 100 req/min por IP |
| Rate Limiting P2P | 200 msgs/10s por peer |
| Reputacao | Ban automatico de peers maliciosos |
| Score Recovery | +1 ponto a cada 5 min conectado |
| Timeouts | connect 10s, recv 30s, DHT 5s |
| Max Peers | 50 total, 3 por IP |
| Bind | API em 127.0.0.1 por padrao |

### Consenso

| Protecao | Como funciona |
|----------|---------------|
| Double-spend | UTXO previne gasto duplo |
| Validacao | Todos os blocos e transacoes sao validados |
| Supply cap | Limite de 19M TRC forcado pelo consenso |
| Bloco duplicado | Blocos com mesmo hash ou height sao rejeitados |
| Sync seguro | Checkpoints a cada 1000 blocos |
| Reorg limitado | Max 20 blocos de reorganizacao |
| MTP | Median-time-past previne timestamp manipulation |
| Dificuldade | Algoritmo proporcional com amortecimento 80/20 |

### Transacoes

| Medida | Descricao |
|--------|-----------|
| Commitments | Pedersen Commitments ocultam valores |
| Validacao | Proof de range verificado |
| Expiracao | TXs maiores que 1h sao rejeitadas |
| Limite por sender | Max 50 txs no mempool |
| Fee dinamico | 5x quando mempool > 80% cheio |

### Armazenamento

| Medida | Descricao |
|--------|-----------|
| Escrita atomica | Operacoes seguras contra crashes |
| WAL Mode | SQLite com consistencia garantida |
| Backup | Recuperacao via BIP39 mnemonico |
| Pruning | Limpeza de blocos antigos para economizar espaco |
| Bootstrap | Download do mainnet.db para sync rapida |

---

## Por que TritioCoin e Segura

### 1. Contra hackers
```
Carteira criptografada com AES-256-GCM
Senha forte obrigatoria (min 8 chars)
600.000 iteracoes PBKDF2
Permissoes 0o600 nos arquivos
```

### 2. Contra censura
```
Rede descentralizada - sem autoridade central
Ninguem pode bloquear transacoes
Ninguem pode confiscar moedas
```

### 3. Contra inflacao
```
Supply maximo de 19M TRC
10% das taxas sao queimadas
Halving a cada 190.000 blocos
```

### 4. Contra ataques de rede
```
Rate limiting em todos os niveis
Reputacao com ban automatico
Timeouts para prevenir DoS
Sync com checkpoints
```

### 5. Contra analise de transacoes
```
Pedersen Commitments ocultam valores
Transacoes publicas mas valores privados
```

---

## Auditorias

| Data | Auditor | Status |
|------|---------|--------|
| 2026-06-25 | Interna | 31 vulnerabilidades encontradas e corrigidas |

---

## Historico de Seguranca

### v1.2.0 (2026-06-25)
- Corrigidas 31 vulnerabilidades (4 criticas, 12 altas, 11 medias, 4 baixas)
- Adicionado Pedersen Commitments para privacidade
- Senha forte obrigatoria
- Rate limiting na API
- Timeouts em conexoes
- Permissoes de arquivo restritas
- Score recovery na reputacao
- Sync parcial (nao substitui chain local)

### v1.1.0 (2026-06-24)
- Blake2b com memory-hardness
- Checkpoints a cada 1000 blocos
- Reorg limitado a 20 blocos
- MTP para validacao de timestamps
- Dificuldade proporcional com amortecimento
