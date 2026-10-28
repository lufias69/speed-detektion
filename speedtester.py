import json
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("speedmonitor")


@dataclass
class SpeedTestResult:
    download_mbps: float
    upload_mbps: float
    ping_ms: float


def _read_last_run(path: str) -> Optional[datetime]:
    """Read the last successful speedtest timestamp from a file."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            ts = f.read().strip()
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except Exception:
        return None


def _write_last_run(path: str):
    """Write the current UTC timestamp to the cooldown file."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(datetime.now(timezone.utc).timestamp()))
    except OSError as exc:
        logger.warning("could not write speedtest cooldown file: %s", exc)


def _should_run(last_run: Optional[datetime], interval_seconds: int) -> bool:
    """Return True if enough time has passed since the last run."""
    if last_run is None:
        return True
    elapsed = (datetime.now(timezone.utc) - last_run).total_seconds()
    return elapsed >= interval_seconds


class SpeedTester:
    """Speedtest runner with file-based rate limiting.

    Prevents speedtests from running more often than the configured interval,
    so the monitor can tick every minute without hammering the network.
    """

    def __init__(
        self,
        cli_path: str = "speedtest-cli",
        interval_seconds: int = 3600,
        cooldown_file: str = "data/.speedtest_last_run",
    ):
        self.cli_path = cli_path
        self.interval_seconds = interval_seconds
        self.cooldown_file = cooldown_file

    def is_available(self) -> bool:
        """Check whether the configured speedtest-cli executable is available."""
        try:
            proc = subprocess.run(
                [self.cli_path, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            available = proc.returncode == 0
            if not available:
                logger.warning(
                    "speedtest-cli not available at %s (exit code %s): %s",
                    self.cli_path,
                    proc.returncode,
                    proc.stderr.strip() or "no output",
                )
            return available
        except FileNotFoundError:
            logger.error(
                "speedtest-cli executable not found: %s. "
                "Install it with: sudo apt-get install speedtest-cli (Debian/Ubuntu) "
                "or pip install speedtest-cli.",
                self.cli_path,
            )
            return False
        except Exception as exc:
            logger.error("speedtest-cli availability check failed: %s", exc)
            return False

    def _execute(self) -> Optional[SpeedTestResult]:
        """Run speedtest-cli directly and parse the JSON output."""
        cmd = [self.cli_path, "--json"]
        logger.info("running speedtest command: %s", " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                stderr = proc.stderr.strip()
                logger.error(
                    "speedtest failed with exit code %s: %s",
                    proc.returncode,
                    stderr or "(no stderr)",
                )
                return None

            if not proc.stdout.strip():
                logger.error("speedtest returned empty output")
                return None

            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                logger.error(
                    "speedtest returned invalid JSON: %s\nOutput: %s",
                    exc,
                    proc.stdout[:500],
                )
                return None

            download = data.get("download", 0) / 1_000_000  # bits/s -> Mbps
            upload = data.get("upload", 0) / 1_000_000
            ping = data.get("ping", 0)
            logger.info(
                "speedtest succeeded: down=%.2f Mbps up=%.2f Mbps ping=%.1f ms",
                download,
                upload,
                ping,
            )
            return SpeedTestResult(download, upload, ping)
        except subprocess.TimeoutExpired:
            logger.error("speedtest timed out after 120 seconds")
            return None
        except Exception as exc:
            logger.error("speedtest error: %s", exc, exc_info=True)
            return None

    def run(self, force: bool = False) -> Optional[SpeedTestResult]:
        """Run a speedtest if the cooldown has expired.

        Args:
            force: If True, skip the cooldown check.

        Returns:
            SpeedTestResult on success, None on failure or if skipped.
        """
        if not self.is_available():
            logger.error(
                "cannot run speedtest: %s is not available", self.cli_path
            )
            return None

        if not force:
            last_run = _read_last_run(self.cooldown_file)
            if not _should_run(last_run, self.interval_seconds):
                remaining = self.interval_seconds
                if last_run is not None:
                    elapsed = (datetime.now(timezone.utc) - last_run).total_seconds()
                    remaining = max(0, self.interval_seconds - elapsed)
                logger.info("speedtest skipped: %.0f seconds remaining", remaining)
                return None

        result = self._execute()
        if result is not None:
            _write_last_run(self.cooldown_file)
        else:
            logger.warning("speedtest produced no result; cooldown not updated")
        return result

    def __repr__(self) -> str:
        return (
            f"SpeedTester(cli_path={self.cli_path!r}, "
            f"interval_seconds={self.interval_seconds})"
        )


def run_speedtest(cli_path: str) -> Optional[SpeedTestResult]:
    """Backward-compatible function: run speedtest-cli once without cooldown."""
    tester = SpeedTester(cli_path=cli_path)
    return tester.run(force=True)
