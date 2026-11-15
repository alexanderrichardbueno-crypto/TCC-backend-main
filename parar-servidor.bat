@echo off
rem Desliga o PrevClima servidor (o programa, o banco e o religamento automatico).
cd /d "%~dp0"
set PORTA=18080
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
  if /i "%%a"=="PREVCLIMA_PORT" set PORTA=%%b
)
rem Avisa o iniciar-servidor.bat para nao religar.
echo parar> "%~dp0parar.flag"
schtasks /end /tn "PrevClima servidor" >nul 2>&1
for %%p in (%PORTA% 5433) do (
  for /f "tokens=5" %%i in ('netstat -ano ^| findstr /r /c:"127.0.0.1:%%p .*LISTENING"') do taskkill /PID %%i /T /F >nul 2>&1
)
rem Confere de novo, caso o banco tenha sido religado enquanto o servidor parava.
ping -n 4 127.0.0.1 >nul
for /f "tokens=5" %%i in ('netstat -ano ^| findstr /r /c:"127.0.0.1:5433 .*LISTENING"') do taskkill /PID %%i /T /F >nul 2>&1
echo PrevClima desligado. Para ligar de novo, reinicie o PC ou rode o iniciar-servidor.bat.
pause
