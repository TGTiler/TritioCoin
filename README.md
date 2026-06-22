<div align="center">

# TritioCoin

**Criptomoeda resistente a computacao quantica para uso do dia a dia**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-v1.0%20Production-brightgreen.svg)]()

</div>

---

## O que e TritioCoin?

TritioCoin e uma criptomoeda descentralizada criada para funcionar em computadores antigos e dispositivos leves (Intel Celeron, ESP32, ARM). Ela protege seus dados contra ataques de computadores quanticos futuros.

### Por que TritioCoin?

- **Funciona em qualquer PC** - Nao precisa de placa de video cara
- **Segura contra computacao quantica** - Suas moedas estao protegidas para o futuro
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
 3. Criar carteira quantica (resistente a quantum)
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

```
1. Abra TritioCoin.bat
2. Selecione: 12 (Minerar blocos)
3. Aguarde - seu PC vai trabalhar encontrando blocos
4. Quando encontrar um bloco, voce ganha 45 TRC!
5. Ctrl+C para parar
```

**Dica:** Mineracao funciona melhor em PCs ligados 24h.

---

## Como Enviar TRC

```
1. Abra TritioCoin.bat
2. Selecione: 5 (Enviar TRC)
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
| **Recompensa** | 45 TRC por bloco |
| **Halving** | A cada 190.000 blocos |
| **Tempo de Bloco** | ~5 minutos |
| **Taxa Minima** | 0.0001 TRC |
| **Queima** | 10% das taxas |
| **Consenso** | PoW (Argon2id) + PoS |
| **Quantum** | ECDSA + WOTS+ hibrido |
| **Carteiras** | BIP32/BIP44 HD, Multi-sig |
| **Rede** | DHT, NAT traversal |

---

## Arquitetura

```
TritioCoin/
├── core/
│   ├── blockchain.py      # Gerenciamento da chain
│   ├── block.py           # Estrutura do bloco
│   ├── miner.py           # Mineracao Argon2id
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
│   ├── quantum.py         # WOTS+ resistente a quantum
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
| Recompensa Inicial | 45 TRC |
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

**TritioCoin v1.0 - Producao**
