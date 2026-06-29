# Changelog

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
