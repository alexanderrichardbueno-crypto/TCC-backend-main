@echo off
title PrevClima - servidor
cd /d "%~dp0"
set URL=http://127.0.0.1:18080

netstat -ano | findstr /r /c:":18080 .*LISTENING" >nul
if not errorlevel 1 (
  echo O PrevClima ja esta ligado. Abrindo %URL%
  explorer "%URL%"
  exit /b 0
)

findstr /b /c:"DATABASE_URL=postgresql" .env >nul
if errorlevel 1 goto servidor

netstat -ano | findstr /r /c:"127.0.0.1:5432 .*LISTENING" >nul
if not errorlevel 1 goto servidor

set PROXY=%LOCALAPPDATA%\PrevClima\cloud-sql-proxy\cloud-sql-proxy.exe
if not exist "%PROXY%" (
  echo Nao encontrei o programa de conexao com o banco em:
  echo %PROXY%
  pause
  exit /b 1
)
echo Conectando ao banco do Firebase...
start "PrevClima - banco" /min "%PROXY%" --port 5432 --auto-iam-authn prevclimabd:southamerica-east1:prevclimabd-instance
set /a TENTATIVAS=0
:aguardar_banco
ping -n 2 127.0.0.1 >nul
netstat -ano | findstr /r /c:"127.0.0.1:5432 .*LISTENING" >nul
if not errorlevel 1 goto servidor
set /a TENTATIVAS+=1
if %TENTATIVAS% lss 20 goto aguardar_banco
echo Nao foi possivel ligar a conexao com o banco do Firebase.
pause
exit /b 1

:servidor
echo.
echo  PrevClima: acesse %URL%
echo  NAO use o endereco 0.0.0.0 que aparece abaixo.
echo  Deixe esta janela aberta enquanto usar o sistema.
echo.

.venv\Scripts\python -m alembic upgrade head
if errorlevel 1 (
  echo Nao foi possivel acessar o banco de dados. Confira a internet e o login do Google.
  pause
  exit /b 1
)
.venv\Scripts\python -m app.seed
start "" /b cmd /c "ping -n 5 127.0.0.1 >nul & explorer %URL%"
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 18080
pause
