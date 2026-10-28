#!/bin/bash
set -e

UNIT_NAME="speedmonitor.service"
UNIT_DIR="$HOME/.config/systemd/user"

echo "Stopping and disabling $UNIT_NAME..."
systemctl --user stop "$UNIT_NAME" 2>/dev/null || true
systemctl --user disable "$UNIT_NAME" 2>/dev/null || true

if [ -f "$UNIT_DIR/$UNIT_NAME" ]; then
    rm "$UNIT_DIR/$UNIT_NAME"
    systemctl --user daemon-reload
    echo "Removed $UNIT_DIR/$UNIT_NAME"
else
    echo "Service file not found."
fi

echo "Autostart removed."
