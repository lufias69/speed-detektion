#!/bin/bash
# run_desktop.sh - Launch Speed Monitor desktop app on Linux/WSL
set -e

cd "$(dirname "$0")"

# Detect venv layout: Linux uses bin/, Windows uses Scripts/.
if [ -f ".venv/Scripts/python.exe" ]; then
    echo "Existing venv is Windows-only. Creating Linux venv..."
    rm -rf .venv
fi

if [ -f ".venv/bin/python" ] && [ ! -x ".venv/bin/python" ]; then
    echo "Existing venv has broken python symlink. Recreating Linux venv..."
    rm -rf .venv
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

PYTHON=".venv/bin/python"
PIP=".venv/bin/pip"

echo "Installing / updating dependencies (this may take a few minutes on first run)..."

# On ARM64 SBCs, PyQt6 wheels are unavailable and compiling from source is difficult.
# Use the ARM-friendly requirements file if present.
if [ -f "requirements-arm64.txt" ] && .venv/bin/python -c "import platform; exit(0 if platform.machine().lower() in ('aarch64', 'arm64') else 1)"; then
    echo "ARM64 detected. Use ./run_desktop_tk.sh for the lightweight GUI; PyQt6 requires apt packages."
    $PIP install -r requirements-arm64.txt
else
    $PIP install -r requirements.txt
fi

echo ""
echo "Starting Speed Monitor Desktop..."
$PYTHON desktop.py "$@"
