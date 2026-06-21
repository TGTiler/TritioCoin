# TritioCoin Server Deployment Guide

## Prerequisites

- Docker and Docker Compose
- 2GB RAM minimum
- 20GB disk space
- Port 8333 (P2P) and 8080 (API) open

## Quick Deploy (Docker)

```bash
# Clone the repository
git clone https://github.com/yourusername/TritioCoin.git
cd TritioCoin

# Run deployment script
chmod +x deploy.sh
./deploy.sh
```

## Manual Deploy (Docker)

```bash
# Build image
docker-compose build

# Start node
docker-compose up -d

# Check logs
docker-compose logs -f

# Stop node
docker-compose down
```

## Deploy on Linux Server (systemd)

```bash
# Create user
sudo useradd -r -s /bin/false tritiocoin

# Copy files
sudo cp -r . /opt/tritiocoin
sudo chown -R tritiocoin:tritiocoin /opt/tritiocoin

# Install service
sudo cp tritiocoin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tritiocoin
sudo systemctl start tritiocoin

# Check status
sudo systemctl status tritiocoin
sudo journalctl -u tritiocoin -f
```

## Configuration

Edit `.env` file:

```bash
TRC_PASSWORD=your_secure_password
TRC_NETWORK=mainnet
TRC_MODE=miner
```

## Ports

| Port | Protocol | Description |
|------|----------|-------------|
| 8333 | TCP | P2P networking |
| 8080 | TCP | REST API + WebSocket |

## Monitoring

```bash
# Check API status
curl http://localhost:8080/api/status

# View connected peers
curl http://localhost:8080/api/peers

# View blockchain height
curl http://localhost:8080/api/status | jq '.height'
```

## Backup

```bash
# Backup wallet
cp data/wallet.json backup/wallet_$(date +%Y%m%d).json

# Backup blockchain
cp data/mainnet.db backup/blockchain_$(date +%Y%m%d).db
```

## Troubleshooting

```bash
# View logs
docker-compose logs -f

# Restart node
docker-compose restart

# Clear data and start fresh
docker-compose down
rm -rf data/*
docker-compose up -d
```
