from unittest.mock import patch, MagicMock
from config import Config
from checker import check_connection, CheckResult


def test_check_connection_online():
    cfg = Config(ping_host="8.8.8.8", ping_timeout_seconds=1, ping_retries=1)
    with patch("checker._ping_host", return_value=(True, 24.0)):
        with patch("checker._get_ssid", return_value="MyWiFi"):
            result = check_connection(cfg)
            assert result.status == "online"
            assert result.ping_ms == 24.0
            assert result.ssid == "MyWiFi"


def test_check_connection_fallback_success():
    cfg = Config(
        ping_host="8.8.8.8",
        fallback_host="8.8.4.4",
        ping_timeout_seconds=1,
        ping_retries=1,
        fallback_delay_seconds=0,
    )
    def _fake_ping(host, timeout):
        if host == "8.8.8.8":
            return (False, None)
        return (True, 32.0)

    with patch("checker._ping_host", side_effect=_fake_ping):
        with patch("checker._get_ssid", return_value="MyWiFi"):
            result = check_connection(cfg)
            assert result.status == "online"
            assert result.ping_ms == 32.0


def test_check_connection_offline_after_retries():
    cfg = Config(
        ping_host="8.8.8.8",
        fallback_host="8.8.4.4",
        ping_timeout_seconds=1,
        ping_retries=3,
        fallback_delay_seconds=0,
    )
    with patch("checker._ping_host", return_value=(False, None)):
        with patch("checker._get_ssid", return_value="MyWiFi"):
            result = check_connection(cfg)
            assert result.status == "offline"
            assert result.ping_ms is None
