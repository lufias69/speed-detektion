# install_service.py
import argparse
import platform
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


def install_windows():
    try:
        import win32serviceutil  # noqa: F401
    except ImportError:
        print("pywin32 not installed. Run: .venv\\Scripts\\pip install pywin32")
        sys.exit(1)

    python_exe = VENV / "Scripts" / "python.exe"
    service_script = ROOT / "windows_service.py"
    service_script.write_text(
        f'''import win32serviceutil
import win32service
import win32event
import servicemanager
import subprocess
import sys
import os

ROOT = r"{ROOT}"
PYTHON = r"{python_exe}"

class SpeedMonitorService(win32serviceutil.ServiceFramework):
    _svc_name_ = "SpeedMonitor"
    _svc_display_name_ = "Speed Monitor"
    _svc_description_ = "Monitors internet speed and connectivity."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        proc = subprocess.Popen([PYTHON, os.path.join(ROOT, "main.py")], cwd=ROOT)
        while proc.poll() is None:
            rc = win32event.WaitForSingleObject(self.hWaitStop, 1000)
            if rc == win32event.WAIT_OBJECT_0:
                proc.terminate()
                break

if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(SpeedMonitorService)
''',
        encoding="utf-8",
    )
    print(f"Created {service_script}")
    print("Run as Administrator: .venv\\Scripts\\python windows_service.py install")
    print("Then: .venv\\Scripts\\python windows_service.py start")


def install_linux():
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    python_exe = VENV / "bin" / "python"
    unit_file = unit_dir / "speedmonitor.service"
    unit_file.write_text(
        f"""[Unit]
Description=Speed Monitor
After=network.target

[Service]
Type=simple
WorkingDirectory={ROOT}
ExecStart={python_exe} {ROOT / "main.py"}
Restart=on-failure

[Install]
WantedBy=default.target
""",
        encoding="utf-8",
    )
    print(f"Created {unit_file}")
    print("Run: systemctl --user daemon-reload")
    print("Run: systemctl --user enable --now speedmonitor")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--os", choices=["windows", "linux"], default=None)
    args = parser.parse_args()

    system = args.os or platform.system().lower()
    if system == "windows":
        install_windows()
    elif system == "linux":
        install_linux()
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)


if __name__ == "__main__":
    main()
