@echo off
REM run_desktop.bat - Launch Speed Monitor desktop app on Windows
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Installing / updating dependencies...
.venv\Scripts\pip install -q -r requirements.txt

echo Starting Speed Monitor Desktop...
.venv\Scripts\python desktop.py %*
pause
