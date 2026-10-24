#!/bin/bash
# install.sh - Linux one-command installer for Speed Monitor
set -e

cd "$(dirname "$0")"

echo "[1/5] Creating virtual environment..."
python3 -m venv .venv

echo "[2/5] Installing dependencies..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

echo "[3/5] Creating default config..."
if [ ! -f config.json ]; then
    .venv/bin/python -c "from config import DEFAULT_CONFIG; import json; json.dump(DEFAULT_CONFIG, open('config.json','w'), indent=2)"
fi

echo "[4/5] Installing systemd user service..."
.venv/bin/python install_service.py --os linux

echo "[5/5] Starting service..."
systemctl --user daemon-reload
systemctl --user enable --now speedmonitor

echo ""
echo "============================================"
echo "Speed Monitor installed and running."
echo "Open dashboard: http://127.0.0.1:5000"
echo ""
echo "Status check : systemctl --user status speedmonitor"
echo "Logs         : systemctl --user logs -f speedmonitor"
echo "============================================"
