import platform
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple, List

from config import Config


@dataclass
class PingStatistics:
    sent: int = 0
    received: int = 0
    lost: int = 0
    loss_percent: Optional[float] = None
    min_ms: Optional[float] = None
    max_ms: Optional[float] = None
    avg_ms: Optional[float] = None


@dataclass
class PingReply:
    bytes_size: int = 0
    time_ms: Optional[float] = None
    ttl: Optional[int] = None


@dataclass
class PingResult:
    success: bool
    replies: List[PingReply] = field(default_factory=list)
    stats: PingStatistics = field(default_factory=PingStatistics)


@dataclass
class CheckResult:
    timestamp: datetime
    ssid: Optional[str]
    connection_type: Optional[str]
    adapter: Optional[str]
    status: str
    ping_ms: Optional[float]
    ping_ttl: Optional[int]
    packet_size: Optional[int]
    ping_min_ms: Optional[float]
    ping_max_ms: Optional[float]
    ping_avg_ms: Optional[float]
    packet_loss_percent: Optional[float]
    error_message: Optional[str] = None


def _parse_windows_ping_line(line: str) -> Optional[PingReply]:
    # Reply from 8.8.8.8: bytes=32 time=76ms TTL=117
    m = re.search(r"bytes=(\d+)\s+time[<=]=(\d+)ms\s+TTL=(\d+)", line, re.IGNORECASE)
    if m:
        return PingReply(
            bytes_size=int(m.group(1)),
            time_ms=float(m.group(2)),
            ttl=int(m.group(3)),
        )
    return None


def _parse_linux_ping_line(line: str) -> Optional[PingReply]:
    # 64 bytes from 8.8.8.8: icmp_seq=1 ttl=117 time=76.0 ms
    m = re.search(r"(\d+)\s+bytes\s+from\s+.*?ttl=(\d+)\s+time[<=]=([\d.]+)\s*ms", line, re.IGNORECASE)
    if m:
        return PingReply(
            bytes_size=int(m.group(1)),
            ttl=int(m.group(2)),
            time_ms=float(m.group(3)),
        )
    return None


def _parse_ping_output(output: str, system: str) -> PingResult:
    result = PingResult(success=False)
    lines = output.splitlines()

    if system == "windows":
        for line in lines:
            reply = _parse_windows_ping_line(line)
            if reply:
                result.success = True
                result.replies.append(reply)

        # Ping statistics for 8.8.8.8:
        #     Packets: Sent = 4, Received = 4, Lost = 0 (0% loss),
        # Approximate round trip times in milli-seconds:
        #     Minimum = 74ms, Maximum = 494ms, Average = 182ms
        for line in lines:
            m = re.search(r"Sent\s*=\s*(\d+),\s*Received\s*=\s*(\d+),\s*Lost\s*=\s*(\d+)\s*\((\d+)%\s*loss", line, re.IGNORECASE)
            if m:
                result.stats.sent = int(m.group(1))
                result.stats.received = int(m.group(2))
                result.stats.lost = int(m.group(3))
                result.stats.loss_percent = float(m.group(4))
            m = re.search(r"Minimum\s*=\s*([\d.]+)ms\s*,\s*Maximum\s*=\s*([\d.]+)ms\s*,\s*Average\s*=\s*([\d.]+)ms", line, re.IGNORECASE)
            if m:
                result.stats.min_ms = float(m.group(1))
                result.stats.max_ms = float(m.group(2))
                result.stats.avg_ms = float(m.group(3))
    else:
        for line in lines:
            reply = _parse_linux_ping_line(line)
            if reply:
                result.success = True
                result.replies.append(reply)

        # 4 packets transmitted, 4 received, 0% packet loss, time 3005ms
        for line in lines:
            m = re.search(r"(\d+)\s+packets?\s+transmitted,\s*(\d+)\s+received,?\s*(?:\+\d+\s+errors?,?\s*)?(\d+)%\s*packet\s+loss", line, re.IGNORECASE)
            if m:
                result.stats.sent = int(m.group(1))
                result.stats.received = int(m.group(2))
                result.stats.loss_percent = float(m.group(3))
                result.stats.lost = result.stats.sent - result.stats.received
            # rtt min/avg/max/mdev = 74.123/182.456/494.789/...
            m = re.search(r"rtt\s+min/avg/max(?:/mdev)?\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)", line, re.IGNORECASE)
            if m:
                result.stats.min_ms = float(m.group(1))
                result.stats.avg_ms = float(m.group(2))
                result.stats.max_ms = float(m.group(3))

    return result


def _ping_host(host: str, timeout: int, retries: int) -> PingResult:
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", str(retries), "-w", str(timeout * 1000), host]
    else:
        cmd = ["ping", "-c", str(retries), "-W", str(timeout), host]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout * retries + 2,
        )
        return _parse_ping_output(proc.stdout, system)
    except Exception as exc:
        return PingResult(success=False)


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
    ssid = _get_ssid_windows()
    if ssid:
        return ssid, "WiFi"

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
    connection_type = config.connection_type or detected_type or "Unknown"

    ping = _ping_host(config.ping_host, config.ping_timeout_seconds, config.ping_retries)

    if ping.success:
        first = ping.replies[0]
        return CheckResult(
            timestamp=timestamp,
            ssid=adapter,
            connection_type=connection_type,
            adapter=adapter,
            status="online",
            ping_ms=ping.stats.avg_ms if ping.stats.avg_ms is not None else first.time_ms,
            ping_ttl=first.ttl,
            packet_size=first.bytes_size,
            ping_min_ms=ping.stats.min_ms,
            ping_max_ms=ping.stats.max_ms,
            ping_avg_ms=ping.stats.avg_ms,
            packet_loss_percent=ping.stats.loss_percent,
        )

    if config.fallback_host:
        time.sleep(config.fallback_delay_seconds)
        ping = _ping_host(config.fallback_host, config.ping_timeout_seconds, config.ping_retries)
        if ping.success:
            first = ping.replies[0]
            return CheckResult(
                timestamp=timestamp,
                ssid=adapter,
                connection_type=connection_type,
                adapter=adapter,
                status="online",
                ping_ms=ping.stats.avg_ms if ping.stats.avg_ms is not None else first.time_ms,
                ping_ttl=first.ttl,
                packet_size=first.bytes_size,
                ping_min_ms=ping.stats.min_ms,
                ping_max_ms=ping.stats.max_ms,
                ping_avg_ms=ping.stats.avg_ms,
                packet_loss_percent=ping.stats.loss_percent,
            )

    return CheckResult(
        timestamp=timestamp,
        ssid=adapter,
        connection_type=connection_type,
        adapter=adapter,
        status="offline",
        ping_ms=None,
        ping_ttl=None,
        packet_size=None,
        ping_min_ms=None,
        ping_max_ms=None,
        ping_avg_ms=None,
        packet_loss_percent=None,
    )
