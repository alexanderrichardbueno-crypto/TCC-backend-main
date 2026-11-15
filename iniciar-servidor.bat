@echo off
rem Liga o PrevClima como servidor (PC que fica ligado o tempo todo).
rem Usa a chave do banco (chave-banco.json) em vez do login pessoal do Google.
rem Se o servidor parar, ele e religado sozinho. O registro fica em servidor.log.
title PrevClima - servidor
cd /d "%~dp0"
set LOG=%~dp0servidor.log
set PROXY=%~dp0ferramentas\cloud-sql-proxy.exe
set INSTANCIA=prevclimabd:southamerica-east1:prevclimabd-instance
set PORTA=18080
set PORTA_BANCO=5433

if not exist ".env" (
  echo Falta o arquivo .env nesta pasta.
  exit /b 1
)
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
  if /i "%%a"=="PREVCLIMA_PORT" set PORTA=%%b
)
if not exist "chave-banco.json" (
  echo Falta o arquivo chave-banco.json nesta pasta.
  exit /b 1
)
if not exist "%PROXY%" (
  echo Falta o programa ferramentas\cloud-sql-proxy.exe. Rode o instalar-servidor.bat.
  exit /b 1
)
rem O parar-servidor.bat cria parar.flag para este ciclo nao religar o servidor.
if exist "%~dp0parar.flag" del "%~dp0parar.flag"

:ciclo
if exist "%~dp0parar.flag" goto fim
call :log "Ligando o PrevClima na porta %PORTA%"

netstat -ano | findstr /r /c:"127.0.0.1:%PORTA_BANCO% .*LISTENING" >nul
if not errorlevel 1 goto banco_pronto
call :log "Conectando ao banco do Firebase"
start "PrevClima - banco" /min "%PROXY%" --address 127.0.0.1 --port %PORTA_BANCO% --auto-iam-authn --credentials-file "%~dp0chave-banco.json" %INSTANCIA%
set /a TENTATIVAS=0
:aguardar_banco
ping -n 2 127.0.0.1 >nul
netstat -ano | findstr /r /c:"127.0.0.1:%PORTA_BANCO% .*LISTENING" >nul
if not errorlevel 1 goto banco_pronto
set /a TENTATIVAS+=1
if %TENTATIVAS% lss 30 goto aguardar_banco
call :log "O banco nao respondeu. Nova tentativa em 1 minuto (confira a internet)."
ping -n 61 127.0.0.1 >nul
goto ciclo

:banco_pronto
.venv\Scripts\python -m alembic upgrade head >> "%LOG%" 2>&1
if errorlevel 1 (
  call :log "Falha ao acessar o banco. Nova tentativa em 1 minuto."
  ping -n 61 127.0.0.1 >nul
  goto ciclo
)
.venv\Scripts\python -m app.seed >> "%LOG%" 2>&1

echo PrevClima ligado em http://127.0.0.1:%PORTA% - deixe esta janela aberta.
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port %PORTA% >> "%LOG%" 2>&1
if exist "%~dp0parar.flag" goto fim
call :log "O servidor parou. Religando em 15 segundos."
ping -n 16 127.0.0.1 >nul
goto ciclo

:fim
call :log "PrevClima desligado pelo parar-servidor.bat."
exit /b 0

:log
echo [%date% %time%] %~1
echo [%date% %time%] %~1>> "%LOG%"
exit /b 0
