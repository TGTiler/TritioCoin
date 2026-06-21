@echo off
title TritioCoin v1.0 - Instalacao
color 0A
cls

echo.
echo  ============================================
echo       TRITIOCOIN v1.0 - INSTALACAO
echo  ============================================
echo.
echo  Este script vai instalar o TritioCoin
echo  no seu computador.
echo.
echo  Requisitos:
echo    - Python 3.8 ou superior
echo    - Conexao com a internet
echo.
echo  ============================================
echo.
pause

echo.
echo [1/4] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado!
    echo Baixe em: https://python.org
    pause
    exit /b 1
)
echo  Python encontrado!
echo.

echo [2/4] Instalando dependencias...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERRO: Falha ao instalar dependencias!
    pause
    exit /b 1
)
echo  Dependencias instaladas!
echo.

echo [3/4] Criando carteira...
python -c "from core.wallet import Wallet; w = Wallet.create(); print(f'Carteira criada: {w.address}')"
echo.

echo [4/4] Instalacao concluida!
echo.
echo  ============================================
echo       INSTALACAO COMPLETA!
echo  ============================================
echo.
echo  Para iniciar, clique em "TritioCoin.bat"
echo.
pause
