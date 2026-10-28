import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from config import Config
from checker import check_connection, CheckResult
from db import SpeedRecord, add_record
from speedtester import SpeedTester, SpeedTestResult

logger = logging.getLogger("speedmonitor")


class Monitor:
    def __init__(self, config: Config, session_factory):
        # A SQLAlchemy Session is not thread-safe; each tick receives its own
        # session via session_factory so scheduler threads never share one.
        self.config = config
        self._session_factory = session_factory
        self.last_speed_test: Optional[datetime] = None
        self.was_online: bool = True
        self._speed_tester = SpeedTester(
            cli_path=config.speed_test_cli_path,
            interval_seconds=config.speed_test_interval_seconds,
            cooldown_file="data/.speedtest_last_run",
        )

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
            connection_type=result.connection_type,
            adapter=result.adapter,
            status=result.status,
            ping_ms=result.ping_ms,
            ping_ttl=result.ping_ttl,
            packet_size=result.packet_size,
            ping_min_ms=result.ping_min_ms,
            ping_max_ms=result.ping_max_ms,
            ping_avg_ms=result.ping_avg_ms,
            packet_loss_percent=result.packet_loss_percent,
        )

        if result.status == "online":
            if self.config.run_speed_tests and self._should_run_speedtest(result.timestamp):
                speed = self._speed_tester.run()
                if speed:
                    record.download_mbps = speed.download_mbps
                    record.upload_mbps = speed.upload_mbps
                    record.ping_ms = speed.ping_ms
                    self.last_speed_test = result.timestamp
                else:
                    # do not pollute records with speedtest errors; ping-only mode is valid
                    logger.debug("speedtest skipped/failed, keeping ping-only record")
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
