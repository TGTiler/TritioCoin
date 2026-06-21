#!/bin/bash
# TritioCoin Production Deployment Script

set -e

echo "=========================================="
echo "  TritioCoin v1.0 Production Deployment"
echo "=========================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
fi

if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Create data directory
mkdir -p data

# Set password
if [ -z "$TRC_PASSWORD" ]; then
    read -sp "Enter wallet password (min 12 chars): " TRC_PASSWORD
    echo
    if [ ${#TRC_PASSWORD} -lt 12 ]; then
        echo "Password must be at least 12 characters!"
        exit 1
    fi
fi

# Create .env file
cat > .env << EOF
TRC_PASSWORD=$TRC_PASSWORD
TRC_NETWORK=mainnet
TRC_MODE=miner
TRC_PORT=8333
TRC_API_PORT=8080
EOF

echo ""
echo "Building Docker image..."
docker-compose build

echo ""
echo "Starting TritioCoin node..."
docker-compose up -d

echo ""
echo "Waiting for node to start..."
sleep 10

# Check status
if curl -s http://localhost:8080/api/status > /dev/null 2>&1; then
    STATUS=$(curl -s http://localhost:8080/api/status)
    HEIGHT=$(echo $STATUS | python -c "import sys, json; print(json.load(sys.stdin)['height'])")
    
    echo ""
    echo "=========================================="
    echo "  TritioCoin v1.0 Deployed Successfully!"
    echo "=========================================="
    echo ""
    echo "  API:        http://localhost:8080"
    echo "  Explorer:   http://localhost:8080/explorer"
    echo "  P2P Port:   8333"
    echo "  Chain Height: $HEIGHT blocks"
    echo ""
    echo "  Management:"
    echo "    View logs:    docker-compose logs -f"
    echo "    Stop node:    docker-compose down"
    echo "    Restart:      docker-compose restart"
    echo "    Update:       docker-compose pull && docker-compose up -d"
    echo ""
    echo "  Your node is now part of the TritioCoin network!"
    echo "=========================================="
else
    echo ""
    echo "Node may still be starting. Check logs:"
    echo "  docker-compose logs -f"
fi
