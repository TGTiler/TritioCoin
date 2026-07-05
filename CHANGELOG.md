# Changelog

Todas as mudancas notaveis no TritioCoin serao documentadas neste arquivo.

## [1.3.0] - 2026-07-05

### Alterado

#### Rede (P2P) — Wire Protocol Binario
- **Wire Protocol**: Substituido JSON+length-prefix por header binario de 24 bytes (`<4s12sII`):
  - Magic Bytes: `\xF9\xBE\xB4\xD9` (4 bytes, rejeita se diferente)
  - Command: ASCII null-padded para 12 bytes
  - Payload Length: uint32 LE
  - Checksum: primeiros 4 bytes de SHA256d(payload)
- **Handshake**: Maquina de estados rigida `version`/`verack` (formato binario `<IQQQI>`)
  - Protocol Version (4B), Services (8B), Timestamp (8B), Nonce (8B), Block Height (4B)
  - Rejeita versoes abaixo de 70001
- **PeerSession**: Cada conexao encapsulada em classe com state machine, write lock, known_inventory, ban_score
- **Keep-alive**: Ping a cada 30s de inatividade, pong deve ecoar nonce em 10s
- **Anti-DoS**: Ban score: +10 pacote malformado, +50 dado invalido, threshold 100 → ban + blacklist
- **Protecao de memoria**: Payload > 2MB → desconexao imediata (antes de ler bytes)
- **Self-connection**: Nonce no version — se igual ao local, rejeita
- **INV/GETDATA**: Protocolo binario `<I32s>` com dedup por `known_inventory` por sessao
- **Gossip**: Atualizado para usar inv/getdata binario ao inves de BLOCK_ANNOUNCE/TX_ANNOUNCE JSON

#### Carteira — Defesas Anti-Colisao
- **Validacao de range**: Chave privada deve estar em [1, n-1] onde n = ordem da curva secp256k1
- **Validacao de entropia**: Verifica bytes nao-zero, diversidade >= 8 valores, retry 3x se fraco
- **Validacao Base58Check**: `validate_address()` verifica checksum ao carregar carteira
- **Registro de colisao local**: `AddressRegistry` salva SHA-256 de enderecos gerados (detecta auto-colisao)
- **Passphrase BIP39**: `Wallet.create(passphrase="...")` adiciona 256 bits extras de entropia
- **Fallback CSPRNG**: Se `os.urandom()` falhar, usa `secrets.token_bytes()` como backup
- **Versao da carteira**: Arquivo criptografado agora usa versao 3 (compativel com v2)

### Adicionado

#### Testes
- **test_p2p_protocol.py**: 38 testes do protocolo P2P
  - TestWireProtocol (11): header, magic, command, checksum, roundtrip
  - TestHandshake (3): handshake completo, troca de versoes, rejeicao de versao antiga
  - TestSelfConnectionPrevention (1): nonce identico → rejeicao
  - TestTxPropagation (1): TX via 3 nos reais (Node1 → Node2 → Node3)
  - TestBadChecksumBan (1): checksum errado → ban → desconexao
  - TestOversizedPayload (1): payload 3MiB → desconexao imediata
  - TestPingPong (1): nonce ecoado no pong
  - TestRateLimiter (5): budget, reset, independentes, cleanup
  - TestBanScore (3): malformed, invalid, abaixo do threshold
  - TestGossipProtocol (8): inventory, eviction, sync ranges
  - TestUnknownCommand (1): comando desconhecido → ban
  - TestInvGetdata (2): formato binario `<I32s>`
- **test_wallet.py**: 17 testes novos de seguranca da carteira
  - TestKeyRangeValidation (4): chave zero, > ordem, tamanho errado, valida
  - TestEntropyQuality (2): 100 carteiras unicas, chave nunca zero
  - TestAddressValidation (5): valido, adulterado, prefixo errado, curto, vazio
  - TestMnemonicPassphrase (3): passphrase diferente = endereco diferente
  - TestAddressRegistry (3): registro, duplicado, contagem
- **Total**: 64 testes (26 wallet + 38 P2P)

---

## [1.2.0] - 2026-06-25

### Alterado

#### Seguranca
- **Carteira**: Senha forte obrigatoria (min 8 chars, 1 maiuscula, 1 numero)
- **Carteira**: Removido fallback de carteira nao-criptografada
- **Permissoes**: Arquivos criados com 0o600 (sem race condition)
- **API**: Rate limiting (100 req/min por IP)
- **API**: Bind em 127.0.0.1 por padrao (nao 0.0.0.0)
- **API**: Mensagens de erro genericas (nao vaza excecoes internas)
- **GUI**: Senha nunca armazenada em memoria
- **privkey_hex()**: Usa bytearray para limpar memoria

#### Privacidade
- **Transacoes**: Pedersen Commitments para ocultar valores
- **Novo modulo**: `core/commitment.py` com implementacao Pedersen

#### Conexao
- **Sync**: Blocos em vez de full chain replacement
- **Batch**: HANDSHAKE_ACK envia blocos em batches de 50
- **Broadcast**: Retry 1x antes de marcar peer como dead
- **Handshake**: Espera HANDSHAKE_ACK com timeout 10s
- **Timeouts**: connect 10s, recv 30s, DHT 5s
- **Reputacao**: Score recovery (+1 ponto a cada 5 min conectado)
- **Rate limit**: Desconecta mas NAO penaliza reputacao
- **Mining**: Exige pelo menos 1 peer para minerar

#### Bootstrap
- **Novo comando**: `--export-db` para exportar mainnet.db
- **Novo comando**: `--bootstrap` para baixar mainnet.db do GitHub

### Corrigido
- **Sync**: Nao apaga mais blocos locais (sync parcial apenas)
- **MTP**: IndexError em _median_time_past com poucos blocos
- **Difficulty**: AttributeError em adjust_difficulty
- **Block.deserialize()**: Converte previous_hash bytes para hex string
- **Progress**: Print a cada 10s em vez de 0.5s
- **Seeds.json**: IPs privados removidos

---

## [1.1.0] - 2026-06-24

### Alterado

#### Seguranca
- **PoW**: Blake2b puro substituido por Blake2b com memory-hardness (256KB, random reads, chained rounds)
- **Timestamps**: Validacao MTP (median-time-past) com margem de ±2h
- **Difficulty**: Algoritmo proporcional com amortecimento 80/20 e cap ±25%
- **Supply**: Underflow guard em _debit_satoshis(), re-verificacao apos apply
- **Reorg**: Checkpoints a cada 1000 blocos, max reorg depth 20
- **Mempool**: Limite 50 txs/sender, fee dinamico, eviction em lote
- **Conexoes**: MAX_PEERS=50, MAX_PER_IP=3, reputacao inicializada por padrao
- **Wallet**: Permissoes 0o600 em arquivos de carteira
- **API**: Chave privada removida do endpoint de envio
- **Senha**: Fallback hardcoded removido (exige TRC_PASSWORD)

#### Economia
- Recompensa inicial: 45 TRC → 50 TRC

#### Removido
- Sistema quantico (WOTS+, hybrid signatures, quantum_mode)
- Argumento --quantum do CLI

### Corrigido
- Bare except clauses (18 ocorrencias) substituidas por Exception
- Float precision em balance check (usa satoshis diretamente)
- Dead code removido (return duplicado em light_client.py)

---

## [1.0.1] - 2026-06-21

### Corrigido

#### Seguranca
- Previne blocos duplicados (mesmo hash) de serem aceitos
- Previne blocos no mesmo height de serem aceitos
- Novo metodo `has_block_with_hash()` no Database
- Melhor mensagem de erro quando carteira nao existe
- Melhor mensagem de erro quando senha esta incorreta

#### Confiabilidade
- Verificacao de blocos duplicados antes de validar
- Log claro quando bloco e rejeitado
- Tratamento de erro InvalidTag com isinstance()

---

## [1.0.0] - 2026-06-21 (Versao de Producao)

### Adicionado

#### Core
- Estrutura de bloco com headers binarios de 86 bytes
- Blockchain com bloco genesis
- Supply cap de 19M com halving a cada 190.000 blocos
- Recompensa inicial de 45 TRC
- Tempo de bloco de ~5 minutos
- Ajuste dinamico de dificuldade

#### Economia
- Valores baseados em satoshis (8 casas decimais)
- Taxa de queima de 10% nas transacoes
- Modelo de supply deflacionario
- Agenda de halving

#### Seguranca
- Criptografia AES-256-GCM para carteiras (PBKDF2 600K iteracoes)
- Backup BIP39 com 24 palavras
- Criptografia TLS 1.3 para P2P
- Assinaturas ECDSA secp256k1
- Assinaturas WOTS+ resistentes a quantum (modo hibrido)

#### Carteira
- Suporte a HD Wallet (BIP32/BIP44)
- Carteiras multi-assinatura (M-of-N)
- Geracao de enderecos (TRC padrao, QR quantum)
- Import/export de carteiras

#### Mineracao
- Proof-of-Work Argon2id (resistente a ASIC)
- Suporte a mining pool
- Distribuicao de recompensas baseada em shares
- Monitoramento de hashrate em tempo real

#### Consenso
- Consenso hibrido PoW + PoS
- Registro e selecao de validadores
- Assinatura e verificacao de blocos
- Selecao de validadores ponderada por stake

#### Armazenamento
- Banco SQLite com modo WAL
- Rastreamento de saldo baseado em UTXO
- Pruning de blocos para espaco em disco
- Escritas atomicas para seguranca contra crashes

#### Rede
- P2P TCP com TLS 1.3
- Kademlia DHT para descoberta descentralizada de peers
- NAT traversal (UPnP)
- Sistema de reputacao de peers
- Rate limiting
- Relay de blocos compactos
- Tratamento de blocos orfaos

#### API
- REST API com 11+ endpoints
- WebSocket para atualizacoes em tempo real
- Interface web do explorador de blocos

#### Governanca
- DAO com propostas e votacao
- Gerenciamento de tesouraria
- Staking publico com recompensas
- Canais de micropagamentos

#### CLI
- Criacao e gerenciamento de carteiras
- Verificacao de saldo
- Envio de transacoes
- Controle de mineracao
- Status da rede

#### Outros
- Suporte a Mainnet e Testnet
- Light Client (SPV)
- Deploy com Docker
- Servico systemd
- 80 testes automatizados
- Documentacao completa
