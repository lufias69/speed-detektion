import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("speedmonitor")


@dataclass
class SpeedTestResult:
    download_mbps: float
    upload_mbps: float
    ping_ms: float


def run_speedtest(cli_path: str) -> Optional[SpeedTestResult]:
    # sivel/speedtest-cli: --json flag, output units are bits/s
    cmd = [cli_path, "--json"]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            logger.warning("speedtest failed: %s", proc.stderr.strip())
            return None

        data = json.loads(proc.stdout)
        download = data.get("download", 0) / 1_000_000  # bits/s -> Mbps
        upload = data.get("upload", 0) / 1_000_000
        ping = data.get("ping", 0)
        return SpeedTestResult(download, upload, ping)
    except subprocess.TimeoutExpired:
        logger.warning("speedtest timed out")
        return None
    except Exception as exc:
        logger.warning("speedtest error: %s", exc)
        return None
