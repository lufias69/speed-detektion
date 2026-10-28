import platform
import re
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
    connection_type: Optional[str]
    adapter: Optional[str]
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


def _get_active_connection() -> Tuple[Optional[str], Optional[str]]:
    """Return (ssid_or_adapter, connection_type) for the active network."""
    system = platform.system().lower()
    try:
        if system == "windows":
            return _get_active_connection_windows()
        return _get_active_connection_linux()
    except Exception:
        return None, None


def _get_active_connection_windows() -> Tuple[Optional[str], Optional[str]]:
    # Try Wi-Fi first
    ssid = _get_ssid_windows()
    if ssid:
        return ssid, "WiFi"

    # Otherwise look for an active Ethernet adapter
    proc = subprocess.run(
        ["netsh", "interface", "show", "interface"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
    )
    if proc.returncode != 0:
        return None, None

    for line in proc.stdout.splitlines():
        if "Connected" in line and "Dedicated" in line:
            parts = [p.strip() for p in line.split() if p.strip()]
            # Typical line: Admin State State             Type             Interface Name
            #                Connected    Connected      Dedicated      Ethernet
            if len(parts) >= 4:
                adapter = parts[-1]
                if "wi-fi" in adapter.lower() or "wireless" in adapter.lower():
                    continue
                return adapter, "Ethernet"
    return None, None


def _get_active_connection_linux() -> Tuple[Optional[str], Optional[str]]:
    ssid = _get_ssid_linux()
    if ssid:
        return ssid, "WiFi"

    # Find active ethernet interface (not loopback, state UP, has carrier)
    try:
        proc = subprocess.run(
            ["ip", "-o", "link", "show", "up"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                m = re.match(r"\d+:\s+([^:@]+)[^:]*:", line)
                if not m:
                    continue
                iface = m.group(1).strip()
                if iface == "lo" or iface.startswith("docker") or iface.startswith("br-"):
                    continue
                if "state UP" in line:
                    return iface, "Ethernet"
    except Exception:
        pass
    return None, None


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
    adapter, detected_type = _get_active_connection()

    # If user has overridden the connection type (e.g. Fiber), keep their label
    # but still use the detected adapter name if available.
    connection_type = config.connection_type or detected_type or "Unknown"

    # Primary host
    for attempt in range(config.ping_retries):
        success, latency = _ping_host(config.ping_host, config.ping_timeout_seconds)
        if success:
            return CheckResult(
                timestamp=timestamp,
                ssid=adapter,
                connection_type=connection_type,
                adapter=adapter,
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
                    ssid=adapter,
                    connection_type=connection_type,
                    adapter=adapter,
                    status="online",
                    ping_ms=latency,
                )

    return CheckResult(
        timestamp=timestamp,
        ssid=adapter,
        connection_type=connection_type,
        adapter=adapter,
        status="offline",
        ping_ms=None,
    )
