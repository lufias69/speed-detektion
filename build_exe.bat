@echo off
REM build_exe.bat - Build a standalone Windows executable
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Installing dependencies...
.venv\Scripts\python -m ensurepip --upgrade
.venv\Scripts\python -m pip install -r requirements.txt

echo Building executable...
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name SpeedMonitor ^
    --add-data "config.json;." ^
    --add-data "requirements.txt;." ^
    desktop.py

if %errorlevel% neq 0 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build complete: dist\SpeedMonitor.exe
echo You can copy this file to another Windows machine.
pause
