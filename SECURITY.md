# Politica de Seguranca - TritioCoin

## Versoes Suportadas

| Versao | Suportada |
|--------|-----------|
| 1.3.x  | Sim       |
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
| Wire Protocol | SHA256d checksum | Integridade de mensagens na rede |
| Privacidade | Pedersen Commitments | Valores de transacoes ocultos |

### Wire Protocol (v1.3)

| Protecao | Como funciona |
|----------|---------------|
| Magic Bytes | `\xF9\xBE\xB4\xD9` — rejeita dados de rede errada |
| Checksum SHA256d | Primeiros 4 bytes de SHA256(SHA256(payload)) |
| Payload Limit | 2MB max — desconnecta ANTES de ler dados |
| Command Validation | Comandos desconhecidos → +10 ban score |
| Binary Header | 24 bytes fixos — previne parsing ambiguo |

### Anti-DoS (Ban Score)

| Acao | Pontos | Efeito |
|------|--------|--------|
| Checksum invalido | +10 | Acumula ate threshold |
| Magic errado | +10 | Acumula ate threshold |
| Comando desconhecido | +10 | Acumula ate threshold |
| Payload > 2MB | +10 | Desconecta imediatamente |
| Bloco/tx corrompido | +50 | Penalidade pesada |
| **Threshold** | **100** | **Desconexao + blacklist** |

### Keep-Alive

| Parametro | Valor |
|-----------|-------|
| Intervalo de ping | 30s de inatividade |
| Timeout de pong | 10s |
| Nonce echo | Pong deve conter exatamente o nonce do ping |

### Handshake

| Etapa | Descricao |
|-------|-----------|
| 1. TCP conectado | Conexao TLS estabelecida |
| 2. Envia version | Payload binario `<IQQQI>` com versao, nonce, height |
| 3. Recebe version | Valida versao >= 70001, nonce != local |
| 4. Envia verack | Payload vazio, confirma handshake |
| 5. Recebe verack | Handshake completo, pode trocar dados |

### Carteira (Anti-Colisao)

| Defesa | Descricao |
|--------|-----------|
| Validacao de range | Chave privada em [1, n-1] (ordem secp256k1) |
| Validacao de entropia | Verifica bytes nao-zero, diversidade >= 8 |
| Retry automatico | 3 tentativas se entropia fraca |
| Base58Check | Checksum do endereco verificado ao carregar |
| Registro local | SHA-256 de enderecos gerados (auto-colisao) |
| Passphrase BIP39 | 256 bits extras de entropia opcional |
| Fallback CSPRNG | `secrets.token_bytes()` se `os.urandom()` falhar |

### Como sua carteira e protegida

```
1. Chave privada validada: 1 ≤ k < n (ordem da curva)
2. Entropia verificada: nao-zero, diversidade >= 8 bytes
3. Criptografada com AES-256-GCM
4. Senha processada com PBKDF2 (600.000 iteracoes)
5. Senha forte obrigatoria (min 8 chars, 1 maiuscula, 1 numero)
6. Arquivo criado com permissoes 0o600 (so owner)
7. Carteira legacy (sem criptografia) e rejeitada
8. Endereco validado com Base58Check ao carregar
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
| Wire Protocol | Checksum SHA256d, magic bytes, payload limit |
| Keep-alive | Ping/pong com nonce a cada 30s |

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
Chave privada validada contra a curva
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
Wire protocol com checksum SHA256d
Magic bytes para validacao de rede
Payload limit (2MB) previne memory exhaustion
Ban score remove peers maliciosos
Rate limiting em todos os niveis
Keep-alive detecta peers mortos
Self-connection prevention evita loops
```

### 5. Contra analise de transacoes
```
Pedersen Commitments ocultam valores
Transacoes publicas mas valores privados
```

### 6. Contra colisao de carteiras
```
Espaco de chaves: 2^256 ≈ 10^77
Probabilidade com 1B carteiras: ≈ 10^-60
Validacao de range da chave privada
Validacao de entropia na geracao
Registro local de enderecos
Passphrase BIP39 opcional
```

---

## Auditorias

| Data | Auditor | Status |
|------|---------|--------|
| 2026-07-05 | Interna | P2P wire protocol + wallet anti-collision |
| 2026-06-25 | Interna | 31 vulnerabilidades encontradas e corrigidas |

---

## Historico de Seguranca

### v1.3.0 (2026-07-05)
- **P2P**: Wire protocol binario com header 24 bytes (magic, command, length, checksum SHA256d)
- **P2P**: Handshake version/verack com maquina de estados rigida
- **P2P**: Keep-alive com ping/pong nonce echo (30s intervalo, 10s timeout)
- **P2P**: Anti-DoS com ban score (+10 malformed, +50 invalid, threshold 100)
- **P2P**: Payload limit 2MB (desconecta antes de ler)
- **P2P**: Self-connection prevention via nonce
- **P2P**: INV/GETDATA binario com dedup por sessao
- **P2P**: PeerSession com state machine e write lock
- **Wallet**: Validacao de range da chave privada (1 ≤ k < n)
- **Wallet**: Validacao de entropia (bytes nao-zero, diversidade >= 8)
- **Wallet**: Validacao Base58Check de enderecos
- **Wallet**: Registro local de colisao (AddressRegistry)
- **Wallet**: Suporte a passphrase BIP39 (256 bits extras)
- **Wallet**: Fallback CSPRNG (secrets.token_bytes)
- **Testes**: 64 testes (26 wallet + 38 P2P)

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
