@echo off
cd /d "%~dp0"
:loop
venv\Scripts\python.exe main.py
echo Bot stopped. Restarting in 10 seconds...
timeout /t 10 /nobreak >nul
goto loop