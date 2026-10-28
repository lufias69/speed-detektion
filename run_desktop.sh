#!/bin/bash
# run_desktop.sh - Launch Speed Monitor desktop app on Linux
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

.venv/bin/pip install -q -r requirements.txt

.venv/bin/python desktop.py "$@"
