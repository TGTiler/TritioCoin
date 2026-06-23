@echo off
title TritioCoin v1.0
color 0A
cls

:MENU
echo.
echo  ============================================
echo       TRITIOCOIN v1.0
echo  ============================================
echo.
echo   [INSTALACAO]
echo    1. Instalar dependencias
echo.
echo   [CARTEIRA]
echo    2. Criar carteira
echo    3. Criar carteira quantica
echo    4. Ver saldo
echo    5. Enviar TRC
echo    6. Historico
echo    7. Listar carteiras
echo.
echo   [REDE]
echo    8. Conectar (automatico)
echo    9. Iniciar como SEED
echo   10. Ver info da rede
echo   11. Ver peers conectados
echo.
echo   [MINERACAO]
echo   12. Minerar blocos
echo   13. Minerar e virar SEED
echo.
echo   [UTILITARIOS]
echo   14. Parar todos os processos
echo.
echo   0. Sair
echo.
echo  ============================================
set /p opcao="  Selecione: "

if "%opcao%"=="1" goto INSTALAR
if "%opcao%"=="2" goto CRIAR
if "%opcao%"=="3" goto CRIAR_Q
if "%opcao%"=="4" goto SALDO
if "%opcao%"=="5" goto ENVIAR
if "%opcao%"=="6" goto HISTORICO
if "%opcao%"=="7" goto LISTAR
if "%opcao%"=="8" goto CONECTAR
if "%opcao%"=="9" goto SEED
if "%opcao%"=="10" goto INFO
if "%opcao%"=="11" goto PEERS
if "%opcao%"=="12" goto MINERAR
if "%opcao%"=="13" goto MINERAR_SEED
if "%opcao%"=="14" goto PARAR
if "%opcao%"=="0" goto SAIR

echo Opcao invalida!
timeout /t 2 >nul
goto MENU

:INSTALAR
cls
echo.
echo  Instalando dependencias...
echo.
pip install -r requirements.txt
echo.
echo  Dependencias instaladas!
echo.
pause
goto MENU

:CRIAR
cls
echo.
echo  Criando carteira...
echo.
python wallet.py create
echo.
pause
goto MENU

:CRIAR_Q
cls
echo.
echo  Criando carteira quantica...
echo.
python wallet.py create --quantum
echo.
pause
goto MENU

:SALDO
cls
echo.
python wallet.py balance
echo.
pause
goto MENU

:ENVIAR
cls
echo.
set /p destino="  Endereco do destinatario: "
set /p valor="  Valor (TRC): "
set /p taxa="  Taxa (padrao 0.001): "
if "%taxa%"=="" set taxa=0.001
echo.
python wallet.py send %destino% %valor% %taxa%
echo.
pause
goto MENU

:HISTORICO
cls
echo.
python wallet.py history
echo.
pause
goto MENU

:LISTAR
cls
echo.
python wallet.py list
echo.
pause
goto MENU

:CONECTAR
cls
echo.
echo  ============================================
echo    CONECTAR AUTOMATICO
echo  ============================================
echo.
echo  Buscando peers automaticamente...
echo  (GitHub + seeds.json local)
echo.
echo  Conectando...
echo  Deixe este terminal ABERTO!
echo.
python main.py --mode passive
pause
goto MENU

:SEED
cls
echo.
echo  ============================================
echo    INICIAR COMO SEED
echo  ============================================
echo.
echo  Este PC sera o primeiro no da rede.
echo.
set /p porta="  Porta (padrao 8333): "
if "%porta%"=="" set porta=8333
echo.
echo  Iniciando seed na porta %porta%...
echo  Deixe este terminal ABERTO!
echo.
python main.py --port %porta% --mode passive --become-seed
pause
goto MENU

:INFO
cls
echo.
python wallet.py info
echo.
pause
goto MENU

:PEERS
cls
echo.
python wallet.py peers
echo.
pause
goto MENU

:MINERAR
cls
echo.
echo  Conectando e minerando...
echo  Ctrl+C para parar.
echo.
python main.py --mode miner
pause
goto MENU

:MINERAR_SEED
cls
echo.
echo  Mineração + Seed
echo.
set /p porta="  Porta (padrao 8333): "
if "%porta%"=="" set porta=8333
echo.
python main.py --port %porta% --mode miner --become-seed
pause
goto MENU

:PARAR
cls
echo.
echo  Parando todos os processos TritioCoin...
echo.
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 >nul
echo  Processos parados!
echo.
pause
goto MENU

:SAIR
cls
echo.
echo  Obrigado por usar TritioCoin!
echo.
timeout /t 2 >nul
exit
