#!/bin/bash
# run_desktop.sh - Launch Speed Monitor desktop app on Linux/WSL
set -e

cd "$(dirname "$0")"

# Detect venv layout: Linux uses bin/, Windows uses Scripts/.
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

echo "Installing / updating dependencies..."
$PIP install -q -r requirements.txt

echo "Starting Speed Monitor Desktop..."
$PYTHON desktop.py "$@"
