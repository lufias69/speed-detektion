#!/bin/bash
# install_autostart_linux.sh - Register Speed Monitor as systemd user service
set -e

cd "$(dirname "$0")"

ROOT="$(pwd)"
UNIT_NAME="speedmonitor.service"
UNIT_DIR="$HOME/.config/systemd/user"

ARCH=$(uname -m)
IS_ARM64=false
if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    IS_ARM64=true
fi

# Detect venv layout
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
    if [ "$IS_ARM64" = true ]; then
        python3 -m venv .venv --system-site-packages
    else
        python3 -m venv .venv
    fi
fi

PYTHON="$ROOT/.venv/bin/python"
PIP="$ROOT/.venv/bin/pip"

echo "Installing / updating dependencies (this may take a few minutes on first run)..."
if [ "$IS_ARM64" = true ] && [ -f "requirements-arm64.txt" ]; then
    echo "ARM64 detected. Using ARM-friendly dependency list."
    "$PIP" install -r requirements-arm64.txt
else
    "$PIP" install -r requirements.txt
fi

# Choose the right entry point for the platform
if [ "$IS_ARM64" = true ]; then
    SCRIPT="$ROOT/desktop_tk.py"
    echo "ARM64 detected: using lightweight Tkinter background service."
else
    SCRIPT="$ROOT/desktop.py"
fi

mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/$UNIT_NAME" <<EOF
[Unit]
Description=Speed Monitor Background
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$PYTHON $SCRIPT --background
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
if [ "$IS_ARM64" = true ]; then
    echo "To view dashboard: ./run_desktop_tk.sh"
else
    echo "To view dashboard: ./run_desktop.sh"
fi
echo "To remove: ./uninstall_autostart_linux.sh"
