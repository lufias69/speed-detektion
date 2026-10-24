import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from config import Config
from checker import check_connection, CheckResult
from db import SpeedRecord, add_record
from speedtester import run_speedtest, SpeedTestResult

logger = logging.getLogger("speedmonitor")


class Monitor:
    def __init__(self, config: Config, session_factory):
        # A SQLAlchemy Session is not thread-safe; each tick receives its own
        # session via session_factory so scheduler threads never share one.
        self.config = config
        self._session_factory = session_factory
        self.last_speed_test: Optional[datetime] = None
        self.was_online: bool = True

    def _should_run_speedtest(self, now: datetime) -> bool:
        if self.last_speed_test is None:
            return True
        elapsed = (now - self.last_speed_test).total_seconds()
        if elapsed >= self.config.speed_test_interval_seconds:
            return True
        if self.config.run_speed_test_on_recovery and not self.was_online:
            return True
        return False

    def tick(self) -> SpeedRecord:
        result = check_connection(self.config)
        record = SpeedRecord(
            timestamp=result.timestamp,
            ssid=result.ssid,
            status=result.status,
            ping_ms=result.ping_ms,
        )

        if result.status == "online":
            if self._should_run_speedtest(result.timestamp):
                speed = run_speedtest(self.config.speed_test_cli_path)
                if speed:
                    record.download_mbps = speed.download_mbps
                    record.upload_mbps = speed.upload_mbps
                    record.ping_ms = speed.ping_ms
                    self.last_speed_test = result.timestamp
                else:
                    record.error_message = "speedtest failed"
            self.was_online = True
        else:
            self.was_online = False

        add_record(self._session_factory(), record)
        logger.info(
            "recorded %s ssid=%s ping=%s down=%s up=%s",
            record.status,
            record.ssid,
            record.ping_ms,
            record.download_mbps,
            record.upload_mbps,
        )
        return record
