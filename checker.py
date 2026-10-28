import platform
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

from config import Config


@dataclass
class CheckResult:
    timestamp: datetime
    ssid: Optional[str]
    status: str
    ping_ms: Optional[float]
    error_message: Optional[str] = None


def _ping_host(host: str, timeout: int) -> Tuple[bool, Optional[float]]:
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout), host]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout + 1,
        )
        success = proc.returncode == 0
        latency = None
        if success:
            latency = _parse_ping_output(proc.stdout, system)
        return success, latency
    except Exception as exc:
        return False, None


def _parse_ping_output(output: str, system: str) -> Optional[float]:
    try:
        if system == "windows":
            # Average = 24ms
            for line in output.splitlines():
                if "Average" in line and "=" in line:
                    part = line.split("=")[-1].strip()
                    return float(part.replace("ms", "").strip())
        else:
            # rtt min/avg/max/mdev = ...
            for line in output.splitlines():
                if "avg" in line and "/" in line:
                    parts = line.split("=")[-1].split("/")
                    return float(parts[1].strip())
    except Exception:
        pass
    return None


def _get_ssid() -> Optional[str]:
    system = platform.system().lower()
    try:
        if system == "windows":
            return _get_ssid_windows()
        return _get_ssid_linux()
    except Exception:
        return None


def _get_ssid_windows() -> Optional[str]:
    proc = subprocess.run(
        ["netsh", "wlan", "show", "interfaces"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
    )
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if "SSID" in line and "BSSID" not in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return None


def _get_ssid_linux() -> Optional[str]:
    for cmd in [
        ["iwgetid", "-r"],
        ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
    ]:
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                if cmd[0] == "iwgetid":
                    return proc.stdout.strip()
                for line in proc.stdout.splitlines():
                    if line.startswith("yes:"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            continue
    return None


def check_connection(config: Config) -> CheckResult:
    timestamp = datetime.now(timezone.utc)
    ssid = _get_ssid()

    # Primary host
    for attempt in range(config.ping_retries):
        success, latency = _ping_host(config.ping_host, config.ping_timeout_seconds)
        if success:
            return CheckResult(
                timestamp=timestamp,
                ssid=ssid,
                status="online",
                ping_ms=latency,
            )

    # Fallback host after configured delay
    if config.fallback_host:
        time.sleep(config.fallback_delay_seconds)
        for attempt in range(config.ping_retries):
            success, latency = _ping_host(config.fallback_host, config.ping_timeout_seconds)
            if success:
                return CheckResult(
                    timestamp=timestamp,
                    ssid=ssid,
                    status="online",
                    ping_ms=latency,
                )

    return CheckResult(
        timestamp=timestamp,
        ssid=ssid,
        status="offline",
        ping_ms=None,
    )
