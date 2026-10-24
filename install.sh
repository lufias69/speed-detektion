#!/bin/bash
# install.sh
set -e

echo "Creating virtual environment..."
python3 -m venv .venv

.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

if [ ! -f config.json ]; then
    echo "Creating default config..."
    .venv/bin/python -c "from config import DEFAULT_CONFIG; import json; json.dump(DEFAULT_CONFIG, open('config.json','w'), indent=2)"
fi

echo "Installing systemd user service..."
.venv/bin/python install_service.py --os linux

echo "Done. Run: systemctl --user daemon-reload && systemctl --user enable --now speedmonitor"
