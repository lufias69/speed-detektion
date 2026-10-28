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

$PIP install -q -r requirements.txt

echo "Starting Speed Monitor Desktop (Tkinter)..."
$PYTHON desktop_tk.py "$@"
