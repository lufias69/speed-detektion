@echo off
REM test_window.bat - Verify PyQt6 can display a window on this machine
cd /d "%~dp0"

echo Running PyQt6 window test...
.venv\Scripts\python test_window.py
