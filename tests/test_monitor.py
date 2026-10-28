from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from config import Config
from monitor import Monitor
from checker import CheckResult


def _check_result():
    return CheckResult(
        timestamp=datetime.now(timezone.utc),
        ssid="WiFi",
        status="online",
        ping_ms=10.0,
    )


def test_monitor_records_online_without_speedtest():
    # Second tick soon after a completed speed test: no new speed test.
    cfg = Config(check_interval_seconds=60, speed_test_interval_seconds=600)
    session = MagicMock()
    monitor = Monitor(cfg, lambda: session)
    monitor.last_speed_test = datetime.now(timezone.utc)  # just ran one

    with patch("monitor.check_connection") as mock_check:
        mock_check.return_value = _check_result()
        with patch("monitor.run_speedtest", return_value=None) as mock_speed:
            monitor.tick()
            assert session.add.call_count == 1
            record = session.add.call_args[0][0]
            assert record.status == "online"
            mock_speed.assert_not_called()


def test_monitor_runs_speedtest_when_due():
    cfg = Config(
        check_interval_seconds=60,
        speed_test_interval_seconds=60,
        run_speed_tests=True,
    )
    session = MagicMock()
    monitor = Monitor(cfg, lambda: session)
    monitor.last_speed_test = datetime.now(timezone.utc) - timedelta(seconds=120)

    with patch("monitor.check_connection") as mock_check:
        mock_check.return_value = _check_result()
        with patch("monitor.run_speedtest") as mock_speed:
            mock_speed.return_value = MagicMock(download_mbps=50.0, upload_mbps=20.0, ping_ms=12.0)
            monitor.tick()
            mock_speed.assert_called_once()
            record = session.add.call_args[0][0]
            assert record.download_mbps == 50.0


def test_monitor_start_speed_test_due_from_init():
    # A fresh Monitor has never run a speed test, so the first online tick
    # must attempt one (spec §5: speed_test_due when now - last >= interval).
    cfg = Config(
        check_interval_seconds=60,
        speed_test_interval_seconds=600,
        run_speed_tests=True,
    )
    session = MagicMock()
    monitor = Monitor(cfg, lambda: session)

    with patch("monitor.check_connection", return_value=_check_result()):
        with patch("monitor.run_speedtest", return_value=None) as mock_speed:
            monitor.tick()
            mock_speed.assert_called_once()
            record = session.add.call_args[0][0]
            assert record.download_mbps is None


def test_monitor_ping_only_mode():
    cfg = Config(
        check_interval_seconds=60,
        speed_test_interval_seconds=60,
        run_speed_tests=False,
    )
    session = MagicMock()
    monitor = Monitor(cfg, lambda: session)

    with patch("monitor.check_connection", return_value=_check_result()):
        with patch("monitor.run_speedtest") as mock_speed:
            monitor.tick()
            mock_speed.assert_not_called()
            record = session.add.call_args[0][0]
            assert record.status == "online"
            assert record.download_mbps is None
