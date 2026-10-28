#!/bin/bash
# install_autostart_linux.sh - Register Speed Monitor as systemd user service
set -e

cd "$(dirname "$0")"

ROOT="$(pwd)"
UNIT_NAME="speedmonitor.service"
UNIT_DIR="$HOME/.config/systemd/user"

# Detect venv layout
if [ -f ".venv/bin/python" ]; then
    PYTHON="$ROOT/.venv/bin/python"
elif [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON="$ROOT/.venv/Scripts/python.exe"
else
    echo "Creating virtual environment..."
    python3 -m venv .venv
    PYTHON="$ROOT/.venv/bin/python"
fi

"$PYTHON" -m pip install -q -r requirements.txt

mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/$UNIT_NAME" <<EOF
[Unit]
Description=Speed Monitor Background
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$PYTHON $ROOT/desktop.py --background
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "$UNIT_NAME"

echo ""
echo "Speed Monitor registered as user service."
echo "Status: systemctl --user status $UNIT_NAME"
echo "Logs:   journalctl --user -u $UNIT_NAME -f"
echo "To view dashboard: ./run_desktop.sh"
echo "To remove: ./uninstall_autostart_linux.sh"
