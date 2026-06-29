<div align="center">

# TritioCoin

**Criptomoeda para uso do dia a dia com mineracao memory-hard e transacoes criptografadas**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-v1.2%20Production-brightgreen.svg)]()

</div>

---

## O que e TritioCoin?

TritioCoin e uma criptomoeda descentralizada criada para funcionar em computadores antigos e dispositivos leves. Utiliza Blake2b com memory-hardness para resistencia a ASICs e Pedersen Commitments para privacidade de transacoes.

### Por que TritioCoin?

- **Funciona em qualquer PC** - Nao precisa de placa de video cara
- **Mineracao memory-hard** - Blake2b com 256KB de memoria por hash
- **Transacoes criptografadas** - Valores ocultos com Pedersen Commitments
- **Rede descentralizada** - Sem autoridade central, sem censura
- **Deflacionaria** - 10% das taxas sao queimadas, valorizacao natural
- **Seguranca reforcada** - Senha forte obrigatoria, permissoes restritas, rate limiting

---

## Comece Aqui (Passo a Passo)

### Opcao 1: Windows (Mais Facil)

```
1. Clique duas vezes em "instalar.bat" (instala dependencias)
2. Clique duas vezes em "TritioCoin.bat"
3. Selecione: 2 (Criar carteira)
4. Digite uma senha forte (min 8 chars, 1 maiuscula, 1 numero)
5. ANOTE as 24 palavras de recuperacao (MUITO IMPORTANTE!)
6. Selecione: 8 (Conectar automatico)
7. Aguarde sincronizar com a rede
```

### Opcao 2: Linux/Mac

```bash
# 1. Clone o repositorio
git clone https://github.com/TGTiler/TritioCoin.git
cd TritioCoin

# 2. Instale dependencias
pip install -r requirements.txt

# 3. Crie uma carteira
python wallet.py create

# 4. Conecte a rede (node precisa estar rodando)
python main.py --mode passive
```

### Opcao 3: Docker

```bash
git clone https://github.com/TGTiler/TritioCoin.git
cd TritioCoin
chmod +x deploy.sh
./deploy.sh
```

---

## Menu do TritioCoin.bat

```
[INSTALACAO]
 1. Instalar dependencias

[CARTEIRA]
 2. Criar carteira
 3. Recuperar carteira (24 palavras)
 4. Ver saldo
 5. Enviar TRC
 6. Historico
 7. Listar carteiras

[REDE]
 8. Conectar (automatico)
 9. Iniciar como SEED (primeiro no da rede)
 10. Ver info da rede
 11. Ver peers conectados

[MINERACAO]
12. Minerar blocos
13. Minerar e virar SEED

[UTILITARIOS]
14. Parar todos os processos
```

---

## Como Minerar

**IMPORTANTE:** Mineracao so funciona com node rodando e peers conectados.

```bash
# Terminal 1: Iniciar node
python main.py --mode passive

# Terminal 2: Minerar
python wallet.py mine
```

Ou via TritioCoin.bat (opcao 12).

---

## Como Enviar TRC

```bash
# Usando CLI
python wallet.py send

# Usando GUI
python gui_wallet.py
```

---

## GUI Wallet

```bash
python gui_wallet.py
```

Interface grafica com:
- Dashboard (altura, saldo, peers)
- Carteira (criar, abrir, recuperar, historico)
- Envio de TRC
- Mineracao integrada
- Status da rede

---

## Recursos

| Recurso | Descricao |
|---------|-----------|
| **Supply Maximo** | 19.000.000 TRC |
| **Recompensa** | 50 TRC por bloco (70% minerador, 30% validadores) |
| **Halving** | A cada 190.000 blocos |
| **Tempo de Bloco** | ~5 minutos |
| **Taxa Minima** | 0.0001 TRC |
| **Queima** | 10% das taxas |
| **Consenso** | PoW (Blake2b memory-hard) + PoS |
| **Assinaturas** | ECDSA secp256k1 |
| **Privacidade** | Pedersen Commitments (valores ocultos) |
| **Carteiras** | BIP32/BIP44 HD, Multi-sig, AES-256-GCM |
| **Rede** | DHT, NAT traversal, TLS 1.3, Rate Limiting |

---

## Arquitetura

```
TritioCoin/
├── core/
│   ├── blockchain.py      # Gerenciamento da chain + reorg
│   ├── block.py           # Estrutura do bloco
│   ├── pow.py             # PoW Blake2b memory-hard
│   ├── miner.py           # Mineracao com multiprocessing
│   ├── mempool.py         # Pool de transacoes com fee dinamico
│   ├── transaction.py     # Transacoes com commitments
│   ├── commitment.py      # Pedersen Commitments (privacidade)
│   ├── utxo.py            # Gerenciamento UTXO
│   ├── wallet.py          # Carteiras com senha forte
│   ├── hdwallet.py        # Carteiras HD BIP32/BIP44
│   ├── multisig.py        # Carteiras multi-assinatura
│   ├── consensus.py       # Motor PoS (70/30 split)
│   ├── pool.py            # Mining pool
│   ├── dao.py             # Governanca DAO
│   ├── staking.py         # Staking publico
│   ├── micropay.py        # Micropagamentos com settlement
│   ├── light_client.py    # Cliente leve SPV
│   ├── constants.py       # Constantes em satoshis
│   ├── database.py        # Persistencia SQLite
│   └── network_config.py  # Configs Mainnet/Testnet
├── network/
│   ├── p2p_node.py        # P2P com TLS + timeouts
│   ├── api.py             # REST + WebSocket API (rate limited)
│   ├── gossip.py          # Protocolo gossip (sync, announce)
│   ├── dht.py             # Kademlia DHT
│   ├── discovery.py       # Descoberta de peers
│   └── reputation.py      # Reputacao de peers
├── main.py                # Ponto de entrada do no
├── wallet.py              # Carteira CLI
├── gui_wallet.py          # Carteira GUI com mineracao
├── explorer.html          # Explorador web
├── tests/                 # Testes automatizados
└── requirements.txt       # Dependencias
```

---

## API

| Endpoint | Descricao |
|----------|-----------|
| `GET /api/status` | Status da rede |
| `GET /api/sync` | Status de sincronizacao |
| `GET /api/block/{height}` | Dados do bloco |
| `GET /api/balance/{address}` | Saldo do endereco |
| `GET /api/wallet/{address}` | Dados completos da carteira |
| `GET /api/tx/{hash}` | Dados da transacao |
| `GET /api/address/{address}` | Detalhes do endereco + historico |
| `GET /api/mempool` | Transacoes pendentes |
| `GET /api/peers` | Peers conectados |
| `GET /api/validators` | Validadores ativos |
| `POST /api/tx` | Enviar transacao (assinar client-side) |
| `POST /api/block` | Enviar bloco minerado |
| `WS /ws` | WebSocket em tempo real |
| `GET /explorer` | Explorador de blocos |

---

## Economia

| Parametro | Valor |
|-----------|-------|
| Supply Maximo | 19.000.000 TRC |
| Recompensa Inicial | 50 TRC (70% minerador, 30% validadores) |
| Intervalo de Halving | 190.000 blocos |
| Tempo de Bloco | ~5 minutos |
| Taxa Minima | 0.0001 TRC |
| Taxa de Queima | 10% das taxas |
| Satoshis | 1 TRC = 100.000.000 sat |

---

## Seguranca

| Medida | Descricao |
|--------|-----------|
| **Senha forte** | Min 8 chars, 1 maiuscula, 1 numero |
| **Criptografia** | AES-256-GCM + PBKDF2 600K iteracoes |
| **Permissoes** | Arquivos com 0o600 (so owner) |
| **Rate limiting** | 100 req/min por IP na API |
| **Reputacao** | Ban automatico de peers maliciosos |
| **Timeouts** | Conexao 10s, recv 30s |
| **Sync seguro** | Checkpoints a cada 1000 blocos |

---

## Deploy

### Docker

```bash
cp .env.production .env
# Edite .env com sua senha
docker-compose up -d
```

### Linux Server

```bash
sudo cp tritiocoin.service /etc/systemd/system/
sudo systemctl enable tritiocoin
sudo systemctl start tritiocoin
```

---

## Bootstrap (Download do mainnet.db)

```bash
# Exportar (no seed):
python main.py --export-db

# Importar (em outro computador):
python main.py --bootstrap --mode miner --seed <IP>:8333
```

---

## Testes

```bash
# Executar todos os testes
python -m pytest tests/ -v

# Teste especifico
python -m pytest tests/test_wallet.py -v
```

---

## Documentacao

- [Whitepaper](WHITEPAPER.md) - Documento tecnico completo
- [API](API.md) - Documentacao da API
- [Arquitetura](ARCHITECTURE.md) - Detalhes tecnicos
- [Deploy](DEPLOY.md) - Guia de implantacao
- [Seguranca](SECURITY.md) - Politica de seguranca
- [Contribuir](CONTRIBUTING.md) - Como contribuir
- [Changelog](CHANGELOG.md) - Historico de versoes
- [Como Conectar](COMO_CONECTAR.md) - Guia de conexao

---

## Licenca

MIT License - Veja [LICENSE](LICENSE)

---

**TritioCoin v1.2 - Producao**
