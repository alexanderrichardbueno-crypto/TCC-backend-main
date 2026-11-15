@echo off
rem Prepara este PC para hospedar o PrevClima. Rode com o botao direito > "Executar como administrador".
title PrevClima - instalacao do servidor
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  echo Clique com o botao direito neste arquivo e escolha "Executar como administrador".
  pause
  exit /b 1
)
if not exist ".env" (
  echo Falta o arquivo .env nesta pasta. Copie-o do pendrive e rode de novo.
  pause
  exit /b 1
)
if not exist "chave-banco.json" (
  echo Falta o arquivo chave-banco.json nesta pasta. Copie-o do pendrive e rode de novo.
  pause
  exit /b 1
)

echo.
echo [1/6] Python 3.12
if exist ".venv\Scripts\python.exe" goto python_pronto
set PY=C:\Program Files\Python312\python.exe
if not exist "%PY%" (
  winget install -e --id Python.Python.3.12 --scope machine --silent --accept-package-agreements --accept-source-agreements
)
if not exist "%PY%" (
  echo Nao consegui instalar o Python. Instale o Python 3.12 "para todos os usuarios" e rode de novo.
  pause
  exit /b 1
)
"%PY%" -m venv .venv
:python_pronto

echo.
echo [2/6] Programas do PrevClima (pode levar alguns minutos)
.venv\Scripts\python -m pip install --upgrade pip -q
.venv\Scripts\python -m pip install . -q
if errorlevel 1 (
  echo Falha ao instalar os programas. Confira a internet e rode de novo.
  pause
  exit /b 1
)
rem SQLAlchemy sem DLL: o Controle Inteligente de Aplicativos do Windows pode bloquear a versao com DLL.
for /f %%v in ('.venv\Scripts\python -c "import sqlalchemy; print(sqlalchemy.__version__)"') do set SAV=%%v
if not exist ferramentas mkdir ferramentas
.venv\Scripts\python -m pip download "sqlalchemy==%SAV%" --no-deps --only-binary=:all: --platform any --python-version 3.12 --implementation py -d ferramentas\wheels -q
for %%f in (ferramentas\wheels\sqlalchemy-%SAV%-py3-none-any.whl) do .venv\Scripts\python -m pip install --force-reinstall --no-deps "%%f" -q

echo.
echo [3/6] Conexao com o banco
if not exist "ferramentas\cloud-sql-proxy.exe" (
  curl -L --fail -o "ferramentas\cloud-sql-proxy.exe" https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.27.0/cloud-sql-proxy.x64.exe
)
if not exist "ferramentas\cloud-sql-proxy.exe" (
  echo Nao consegui baixar o cloud-sql-proxy.exe. Copie-o do pendrive para a pasta ferramentas.
  pause
  exit /b 1
)

echo.
echo [4/6] PC sem suspender nem hibernar (na tomada)
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

echo.
echo [5/6] Ligar o PrevClima sozinho quando o Windows iniciar
schtasks /create /tn "PrevClima servidor" /tr "\"%~dp0iniciar-servidor.bat\"" /sc onstart /delay 0001:00 /ru SYSTEM /rl HIGHEST /f
schtasks /run /tn "PrevClima servidor"

echo.
echo [6/6] Tailscale (endereco na internet)
if not exist "C:\Program Files\Tailscale\tailscale.exe" (
  winget install -e --id Tailscale.Tailscale --silent --accept-package-agreements --accept-source-agreements
)

echo.
echo Pronto. O PrevClima esta ligando (acompanhe em servidor.log).
echo Falta so ativar o endereco na internet: siga o passo "Tailscale" do LEIA-ME.
pause
