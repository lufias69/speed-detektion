import win32serviceutil
import win32service
import win32event
import servicemanager
import subprocess
import sys
import os

ROOT = r"C:\project\sped detektion"
PYTHON = r"C:\project\sped detektion\.venv\Scripts\python.exe"

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
