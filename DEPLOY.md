# Guia de Deploy do TritioCoin

## Requisitos

- Python 3.12+
- 2GB RAM minimo
- 20GB de espaco em disco
- Portas 8333 (P2P) e 8080 (API) abertas

---

## Deploy Rapido (Windows)

### 1. Instale as dependencias
```
Clique duas vezes em "instalar.bat"
```

### 2. Inicie o no
```
Clique duas vezes em "TritioCoin.bat"
Selecione: 9 (Iniciar como SEED)
```

---

## Deploy com Docker

### Instalar Docker

```bash
# Linux
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Windows: Instale Docker Desktop
# https://docs.docker.com/desktop/install/windows-install/
```

### Deploy

```bash
# Clone
git clone https://github.com/TGTiler/TritioCoin.git
cd TritioCoin

# Execute o script de deploy
chmod +x deploy.sh
./deploy.sh
```

### Gerenciar Docker

```bash
# Ver logs
docker-compose logs -f

# Reiniciar
docker-compose restart

# Parar
docker-compose down

# Atualizar
git pull
docker-compose build
docker-compose up -d
```

---

## Deploy no Linux (systemd)

### 1. Criar usuario

```bash
sudo useradd -r -s /bin/false tritiocoin
```

### 2. Copiar arquivos

```bash
sudo cp -r . /opt/tritiocoin
sudo chown -R tritiocoin:tritiocoin /opt/tritiocoin
```

### 3. Instalar servico

```bash
sudo cp tritiocoin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tritiocoin
sudo systemctl start tritiocoin
```

### 4. Verificar

```bash
sudo systemctl status tritiocoin
sudo journalctl -u tritiocoin -f
```

---

## Configuracao

### Arquivo .env

```bash
# Copie o modelo
cp .env.production .env

# Edite com sua senha
nano .env
```

### Variaveis de ambiente

| Variavel | Descricao | Padrao |
|----------|-----------|--------|
| TRC_PASSWORD | Senha da carteira | - |
| TRC_NETWORK | Rede (mainnet/testnet) | mainnet |
| TRC_MODE | Modo (miner/validator/passive) | passive |
| TRC_PORT | Porta P2P | 8333 |

---

## Portas

| Porta | Protocolo | Descricao | Firewall |
|-------|-----------|-----------|----------|
| 8333 | TCP | P2P networking | Abrir |
| 8334 | TCP | DHT discovery | Abrir |
| 8080 | TCP | REST API + WebSocket | Opcional |

### Abrir portas no Linux

```bash
# UFW
sudo ufw allow 8333/tcp
sudo ufw allow 8334/tcp
sudo ufw allow 8080/tcp

# Firewalld
sudo firewall-cmd --permanent --add-port=8333/tcp
sudo firewall-cmd --permanent --add-port=8334/tcp
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

### Abrir portas no Windows

```
1. Painel de Controle -> Firewall
2. Regras de Entrada -> Nova Regra
3. Porta -> TCP -> 8333, 8334, 8080
4. Permitir conexao
5. Aplicar em todas as redes
```

---

## Monitoramento

### Verificar status

```bash
# API
curl http://localhost:8080/api/status

# Ver peers
curl http://localhost:8080/api/peers

# Ver altura da blockchain
curl http://localhost:8080/api/status | jq '.height'

# Ver saldo
curl http://localhost:8080/api/balance/SEU_ENDERECO
```

### Explorador Web

Acesse no navegador:
```
http://localhost:8080/explorer
```

---

## Backup

### Backup da carteira

```bash
# Copie o arquivo da carteira
cp tritiocoin_data/wallet.json backup/wallet_$(date +%Y%m%d).json

# OU use as 24 palavras para recuperar em qualquer lugar
```

### Backup da blockchain

```bash
cp tritiocoin_data/mainnet.db backup/blockchain_$(date +%Y%m%d).db
```

### Backup completo

```bash
tar -czf backup_$(date +%Y%m%d).tar.gz tritiocoin_data/
```

---

## Restaurar Backup

```bash
# Restaurar carteira
cp backup/wallet.json tritiocoin_data/wallet.json

# Restaurar blockchain
cp backup/blockchain.db tritiocoin_data/mainnet.db
```

---

## Solucao de Problemas

### "Porta ja em uso"

```bash
# Encontre o processo
netstat -ano | findstr :8333

# Mude a porta
python main.py --port 8433
```

### "Nenhum peer encontrado"

1. Verifique se tem internet
2. Adicione IPs no seeds.json
3. Verifique se as portas estao abertas

### "Erro de conexao"

```bash
# Teste a conexao
telnet 192.168.1.10 8333

# Verifique o firewall
sudo ufw status
```

### "Carteira corrompida"

```bash
# Use as 24 palavras para recuperar
python wallet.py recover
```

### "Banco de dados corrompido"

```bash
# Delete e re-sincronize
rm tritiocoin_data/mainnet.db
python main.py --mode passive
```

---

## Atualizar TritioCoin

```bash
# Baixe as atualizacoes
git pull

# Reinstale dependencias
pip install -r requirements.txt

# Execute testes (64 testes)
python -m pytest tests/ -v

# Reinicie o no
python main.py --mode passive
```

---

## Desempenho

### Requisitos minimos

| Recurso | Minimo | Recomendado |
|---------|--------|-------------|
| CPU | 1 nucleo | 2+ nucleos |
| RAM | 512MB | 2GB+ |
| Disco | 1GB | 20GB+ |
| Internet | 1 Mbps | 10+ Mbps |

### Otimizacoes

1. **Use SSD** - Leitura/escrita mais rapida
2. **Mantenha ligado** - Mais blocos minerados
3. **Conexao estavel** - Menos desconexoes
4. **Poucos processos** - Mais CPU para mineracao
