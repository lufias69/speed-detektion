#!/bin/bash
# install_orangepi.sh - Install Speed Monitor on ARM64 SBCs (Orange Pi, Raspberry Pi, etc.)
# PyQt6 wheels are not available for ARM64, so we use system packages and Tkinter fallback.
set -e

cd "$(dirname "$0")"

echo "Speed Monitor installer for ARM64 / Orange Pi"
echo "=============================================="
echo ""

# Detect Debian/Ubuntu-based distro
if [ ! -f /etc/debian_version ]; then
    echo "WARNING: This installer is optimized for Debian/Ubuntu-based systems."
    echo "You may need to adapt package names for your distro."
    echo ""
fi

echo "Installing system packages..."
sudo apt-get update

# Install Python, Tkinter, and core build tools
sudo apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    python3-tk \
    python3-dev \
    libffi-dev \
    libssl-dev \
    libegl1 \
    libxkbcommon-x11-0 \
    libxcb-cursor0 \
    libxcb-util1 \
    libxcb-xkb1 \
    libxcb-icccm4 \
    libxcb-render-util0 \
    libxcb-image0 \
    libxcb-keysyms1

# Install optional system packages if available (helps matplotlib on ARM)
sudo apt-get install -y python3-matplotlib || true
sudo apt-get install -y python3-pyqt6 || true
sudo apt-get install -y python3-pyqt6.qtsvg || true

echo ""
echo "Setting up Python virtual environment..."

# Remove broken venv if present
if [ -f ".venv/Scripts/python.exe" ]; then
    echo "Existing venv is Windows-only. Recreating..."
    rm -rf .venv
fi

if [ -d ".venv" ]; then
    echo "Existing .venv found. Reusing with system site-packages access."
    # Re-create with system-site-packages so apt-installed PyQt6/matplotlib are available
    rm -rf .venv
fi

python3 -m venv .venv --system-site-packages

echo ""
echo "Installing Python dependencies..."

# Install packages that compile cleanly on ARM64, excluding PyQt6 and Windows-only packages
.venv/bin/pip install --upgrade pip
.venv/bin/pip install \
    sqlalchemy>=2.0.0 \
    python-dateutil>=2.8.0 \
    speedtest-cli>=2.1.3 \
    requests>=2.31.0 \
    cryptography>=41.0.0 \
    keyring>=24.0.0 \
    pyinstaller>=6.0.0

# Try to install matplotlib; if it fails to build, rely on system python3-matplotlib
if ! .venv/bin/python -c "import matplotlib" 2>/dev/null; then
    echo "Installing matplotlib from PyPI..."
    .venv/bin/pip install matplotlib>=3.8.0 || {
        echo "WARNING: matplotlib install failed. Falling back to system package."
        echo "Analytics/chart window may be unavailable until system matplotlib is installed."
    }
fi

echo ""
echo "Installation complete!"
echo ""
echo "Run the lightweight Tkinter GUI:"
echo "  ./run_desktop_tk.sh"
echo ""
echo "Run with PyQt6 GUI (only if python3-pyqt6 was installed from apt):"
echo "  ./run_desktop.sh"
echo ""
echo "Run headless background monitor:"
echo "  .venv/bin/python desktop.py --background"
