# Speed Monitor — Installation Guide

## Pre-Built Binaries (Recommended)

Download the ready-to-use package from the GitHub Releases page:

- **Windows**: `SpeedMonitor-Windows-x64.zip`
- **Linux**: `SpeedMonitor-Linux-x64.tar.gz`

After downloading, follow the section for your operating system below.

---

## Windows

### Option A — Pre-built executable (no Python required)

1. Extract `SpeedMonitor-Windows-x64.zip` to any folder, e.g. `C:\SpeedMonitor`.
2. Optionally edit `config.json` with your network name, location, timezone, and Firebase settings.
3. Double-click `SpeedMonitor.exe` to open the dashboard.
4. On first run, if `config.json` is missing or incomplete, the Setup Wizard will appear automatically.

### Option B — Run from source (Python required)

Requires **Python 3.10 or newer** and the Windows version of `ping` (installed by default).

```cmd
cd SpeedMonitor-Windows-x64
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git .
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python desktop.py
```

Or simply double-click `run_desktop.bat`.

### Autostart on Windows

Run as Administrator:

```cmd
install_autostart_windows.bat
```

This registers a scheduled task that runs Speed Monitor in the background at logon.
To remove autostart, run `uninstall_autostart_windows.bat`.

---

## Linux

### Option A — Pre-built executable (no Python required)

1. Download `SpeedMonitor-Linux-x64.tar.gz`.
2. Extract it:

   ```bash
   tar -xzf SpeedMonitor-Linux-x64.tar.gz
   cd SpeedMonitor-Linux-x64
   ```

3. Make the binary executable:

   ```bash
   chmod +x SpeedMonitor
   ```

4. Run the dashboard:

   ```bash
   ./SpeedMonitor
   ```

5. On first run, if `config.json` is missing or incomplete, the Setup Wizard will appear automatically.

### Option B — Run from source (Python required)

Requires **Python 3.10 or newer**, `python3-venv`, and the system `ping` utility.

```bash
cd SpeedMonitor-Linux-x64
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python desktop.py
```

Or simply run `./run_desktop.sh`.

### Autostart on Linux

```bash
chmod +x install_autostart_linux.sh
./install_autostart_linux.sh
```

This creates a user `systemd` service. To check status:

```bash
systemctl --user status speedmonitor.service
```

To remove autostart:

```bash
./uninstall_autostart_linux.sh
```

---

## Notes

- The pre-built binaries include everything needed to run the GUI and background monitor.
- Keep `config.json` and `data/speed_monitor.db` in the same folder as the executable. Do not move the database file separately unless you update the `database_path` in `config.json`.
- For cloud sync, open **Settings → Firebase Project ID / API Key**, then click **Sync to Cloud**.
