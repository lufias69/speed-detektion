@echo off
REM install_autostart_windows.bat - Register Speed Monitor to run at logon in the background
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "TASK_NAME=SpeedMonitorBackground"
set "PYTHONW=.venv\Scripts\pythonw.exe"
set "SCRIPT=%CD%\desktop.py"
set "LOG_DIR=%CD%\logs"

if not exist "%PYTHONW%" (
    echo Creating virtual environment and installing dependencies...
    python -m venv .venv
    .venv\Scripts\python -m ensurepip --upgrade
    .venv\Scripts\python -m pip install -r requirements.txt
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

schtasks /query /tn "%TASK_NAME%" >nul 2>&1 && (
    echo Existing task found. Removing old task...
    schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
)

echo Registering autostart task...
schtasks /create /tn "%TASK_NAME%" /tr "\"%CD%\%PYTHONW%\" \"%SCRIPT%\" --background" /sc onlogon /rl highest /f /np >nul 2>&1

if %errorlevel% neq 0 (
    echo FAILED to register task. Make sure you run this batch as Administrator.
    pause
    exit /b 1
)

echo Speed Monitor will start automatically at logon and run in the background.
echo To view the dashboard, run run_desktop.bat manually.
echo To remove autostart, run uninstall_autostart_windows.bat.
pause
