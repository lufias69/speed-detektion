@echo off
REM run_desktop_tk.bat - Launch Speed Monitor using Tkinter (fallback GUI)
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Ensuring pip is installed...
.venv\Scripts\python -m ensurepip --upgrade

echo Installing / updating dependencies...
.venv\Scripts\python -m pip install -q -r requirements.txt

echo Starting Speed Monitor Desktop (Tkinter)...
.venv\Scripts\python desktop_tk.py %*
if errorlevel 1 (
    echo Desktop app exited with an error.
    pause
)
