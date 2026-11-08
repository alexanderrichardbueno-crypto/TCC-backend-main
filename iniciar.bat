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

echo.
echo  PrevClima: acesse %URL%
echo  NAO use o endereco 0.0.0.0 que aparece abaixo.
echo  Deixe esta janela aberta enquanto usar o sistema.
echo.

.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m app.seed
start "" /b cmd /c "ping -n 5 127.0.0.1 >nul & explorer %URL%"
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 18080
pause
