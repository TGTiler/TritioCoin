#!/bin/bash
# TritioWallet - Install for Termux/UserLAND
# Run: bash install_termux.sh

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║  TritioWallet v2.0 - Installer           ║"
echo "  ║  Validator/ARM Edition                   ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# Detect environment
if [ -d "/data/data/com.termux" ] || [ -d "/data/data/io.neoterm" ]; then
    ENV="termux"
    echo "  Detectado: Termux"
    pkg update -y
    pkg install -y python
elif command -v apt-get &> /dev/null; then
    ENV="debian"
    echo "  Detectado: Debian/Ubuntu"
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip
elif command -v apk &> /dev/null; then
    ENV="alpine"
    echo "  Detectado: Alpine (UserLAND)"
    sudo apk update
    sudo apk add python3 py3-pip
else
    ENV="generic"
    echo "  Detectado: Sistema generico"
fi

echo ""
echo "  Instalando pacotes Python..."
pip install -r requirements.txt 2>/dev/null || pip3 install -r requirements.txt 2>/dev/null

echo ""
echo "  Criando diretorio de dados..."
mkdir -p tritiocoin_wallet

echo ""
echo "  ═══════════════════════════════════════"
echo "  Instalacao concluida!"
echo ""
echo "  Para usar:"
echo "    python tritio_wallet.py"
echo ""
echo "  Primeiros passos:"
echo "    1  Instalar dependencias"
echo "    9  Conectar automatico"
echo "    2  Criar carteira"
echo "    14 Registrar como validador"
echo "  ═══════════════════════════════════════"
