@echo off
setlocal

set "TASK_NAME=SpeedMonitorBackground"

echo Removing autostart task...
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

if %errorlevel% equ 0 (
    echo Autostart removed.
) else (
    echo Task not found or already removed.
)
pause
