<div align="center">

# TritioCoin

**Criptomoeda para uso do dia a dia com mineracao memory-hard**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-v1.1%20Production-brightgreen.svg)]()

</div>

---

## O que e TritioCoin?

TritioCoin e uma criptomoeda descentralizada criada para funcionar em computadores antigos e dispositivos leves (Intel Celeron, ESP32, ARM). Utiliza Blake2b com memory-hardness para resistencia a ASICs.

### Por que TritioCoin?

- **Funciona em qualquer PC** - Nao precisa de placa de video cara
- **Mineracao memory-hard** - Blake2b com 256KB de memoria por hash
- **Rede descentralizada** - Sem autoridade central, sem censura
- **Deflacionaria** - 10% das taxas sao queimadas, valorizacao natural

---

## Comece Aqui (Passo a Passo)

### Opcao 1: Windows (Mais Facil)

```
1. Clique duas vezes em "instalar.bat" (instala dependencias)
2. Clique duas vezes em "TritioCoin.bat"
3. Selecione: 2 (Criar carteira)
4. Digite uma senha forte
5. ANOTE as 24 palavras de recuperacao (MUITO IMPORTANTE!)
6. Selecione: 7 (Conectar automatico)
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

# 4. Conecte a rede
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
 3. Ver saldo
 4. Enviar TRC
 5. Historico
 6. Listar carteiras

[REDE]
 7. Conectar (automatico)
 8. Iniciar como SEED (primeiro no da rede)
 9. Ver info da rede
10. Ver peers conectados

[MINERACAO]
11. Minerar blocos
12. Minerar e virar SEED

[UTILITARIOS]
13. Parar todos os processos
```

---

## Como Minerar

```
1. Abra TritioCoin.bat
2. Selecione: 11 (Minerar blocos)
3. Aguarde - seu PC vai trabalhar encontrando blocos
4. Quando encontrar um bloco, voce ganha 50 TRC!
5. Ctrl+C para parar
```

**Dica:** Mineracao funciona melhor em PCs ligados 24h.

---

## Como Enviar TRC

```
1. Abra TritioCoin.bat
2. Selecione: 4 (Enviar TRC)
3. Digite o endereco do destinatario (comeca com T)
4. Digite o valor em TRC
5. Digite a taxa (padrao: 0.001)
6. Confirme
```

---

## Recuperar Carteira

Se perdeu acesso ao arquivo da carteira, use as 24 palavras:

```bash
python wallet.py recover
# Digite as 24 palavras quando solicitado
```

**IMPORTANTE:** Sem as 24 palavras, voce PERDE suas moedas para sempre!

---

## Recursos

| Recurso | Descricao |
|---------|-----------|
| **Supply Maximo** | 19.000.000 TRC |
| **Recompensa** | 50 TRC por bloco |
| **Halving** | A cada 190.000 blocos |
| **Tempo de Bloco** | ~5 minutos |
| **Taxa Minima** | 0.0001 TRC |
| **Queima** | 10% das taxas |
| **Consenso** | PoW (Blake2b memory-hard) + PoS |
| **Assinaturas** | ECDSA secp256k1 |
| **Carteiras** | BIP32/BIP44 HD, Multi-sig |
| **Rede** | DHT, NAT traversal, TLS 1.3 |

---

## Arquitetura

```
TritioCoin/
├── core/
│   ├── blockchain.py      # Gerenciamento da chain
│   ├── block.py           # Estrutura do bloco
│   ├── pow.py             # PoW Blake2b memory-hard
│   ├── miner.py           # Mineracao
│   ├── mempool.py         # Pool de transacoes
│   ├── transaction.py     # Transacoes baseadas em satoshis
│   ├── utxo.py            # Gerenciamento UTXO
│   ├── wallet.py          # Carteiras criptografadas
│   ├── hdwallet.py        # Carteiras HD BIP32/BIP44
│   ├── multisig.py        # Carteiras multi-assinatura
│   ├── consensus.py       # Motor PoS
│   ├── pool.py            # Mining pool
│   ├── dao.py             # Governanca DAO
│   ├── staking.py         # Staking publico
│   ├── micropay.py        # Micropagamentos
│   ├── light_client.py    # Cliente leve SPV
│   ├── constants.py       # Constantes em satoshis
│   ├── database.py        # Persistencia SQLite
│   └── network_config.py  # Configs Mainnet/Testnet
├── network/
│   ├── p2p_node.py        # P2P com TLS
│   ├── api.py             # REST + WebSocket API
│   ├── dht.py             # Kademlia DHT
│   ├── discovery.py       # Descoberta de peers
│   └── reputation.py      # Reputacao de peers
├── main.py                # Ponto de entrada do no
├── wallet.py              # Carteira CLI
├── explorer.html          # Explorador web
├── tests/                 # Testes automatizados
└── requirements.txt       # Dependencias
```

---

## API

| Endpoint | Descricao |
|----------|-----------|
| `GET /api/status` | Status da rede |
| `GET /api/block/{height}` | Dados do bloco |
| `GET /api/balance/{address}` | Saldo do endereco |
| `GET /api/tx/{hash}` | Dados da transacao |
| `GET /api/mempool` | Transacoes pendentes |
| `GET /api/peers` | Peers conectados |
| `GET /api/validators` | Validadores ativos |
| `POST /api/tx` | Enviar transacao |
| `WS /ws` | WebSocket em tempo real |
| `GET /explorer` | Explorador de blocos |

---

## Economia

| Parametro | Valor |
|-----------|-------|
| Supply Maximo | 19.000.000 TRC |
| Recompensa Inicial | 50 TRC |
| Intervalo de Halving | 190.000 blocos |
| Tempo de Bloco | ~5 minutos |
| Taxa Minima | 0.0001 TRC |
| Taxa de Queima | 10% das taxas |
| Satoshis | 1 TRC = 100.000.000 sat |

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

**TritioCoin v1.1 - Producao**
