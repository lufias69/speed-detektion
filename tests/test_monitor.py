from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from config import Config
from monitor import Monitor
from checker import CheckResult


def test_monitor_records_online_without_speedtest():
    cfg = Config(check_interval_seconds=60, speed_test_interval_seconds=600)
    session = MagicMock()
    monitor = Monitor(cfg, session)

    with patch("monitor.check_connection") as mock_check:
        mock_check.return_value = CheckResult(
            timestamp=datetime.now(timezone.utc),
            ssid="WiFi",
            status="online",
            ping_ms=10.0,
        )
        with patch("monitor.run_speedtest", return_value=None) as mock_speed:
            monitor.tick()
            assert session.add.call_count == 1
            record = session.add.call_args[0][0]
            assert record.status == "online"
            mock_speed.assert_not_called()


def test_monitor_runs_speedtest_when_due():
    cfg = Config(check_interval_seconds=60, speed_test_interval_seconds=60)
    session = MagicMock()
    monitor = Monitor(cfg, session)
    monitor.last_speed_test = datetime.now(timezone.utc) - timedelta(seconds=120)

    with patch("monitor.check_connection") as mock_check:
        mock_check.return_value = CheckResult(
            timestamp=datetime.now(timezone.utc),
            ssid="WiFi",
            status="online",
            ping_ms=10.0,
        )
        with patch("monitor.run_speedtest") as mock_speed:
            mock_speed.return_value = MagicMock(download_mbps=50.0, upload_mbps=20.0, ping_ms=12.0)
            monitor.tick()
            mock_speed.assert_called_once()
            record = session.add.call_args[0][0]
            assert record.download_mbps == 50.0
