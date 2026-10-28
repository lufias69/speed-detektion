#!/bin/bash
# run_desktop_tk.sh - Launch Speed Monitor using Tkinter (fallback GUI)
set -e

cd "$(dirname "$0")"

if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
    PIP=".venv/bin/pip"
elif [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON=".venv/Scripts/python.exe"
    PIP=".venv/Scripts/pip.exe"
else
    echo "Creating virtual environment..."
    python3 -m venv .venv
    PYTHON=".venv/bin/python"
    PIP=".venv/bin/pip"
fi

. /dev/null 2>/dev/null

if [ -f ".venv/Scripts/python.exe" ]; then
    echo "Existing venv is Windows-only. Creating Linux venv..."
    rm -rf .venv
    PYTHON=""
    PIP=""
fi

if [ -z "$PYTHON" ] || [ ! -x "$PYTHON" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    PYTHON=".venv/bin/python"
    PIP=".venv/bin/pip"
fi

echo "Installing / updating dependencies (this may take a few minutes on first run)..."

# On ARM64 SBCs, PyQt6 wheels are unavailable and compiling from source is difficult.
# Use the ARM-friendly requirements file if present.
if [ -f "requirements-arm64.txt" ] && $PYTHON -c "import platform; exit(0 if platform.machine().lower() in ('aarch64', 'arm64') else 1)"; then
    echo "ARM64 detected. Using ARM-friendly dependency list."
    $PIP install -r requirements-arm64.txt
else
    $PIP install -r requirements.txt
fi

echo ""
echo "Starting Speed Monitor Desktop (Tkinter)..."
$PYTHON desktop_tk.py "$@"
