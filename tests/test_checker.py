from unittest.mock import patch
from config import Config
from checker import check_connection, PingResult, PingReply, PingStatistics, CheckResult


def _ping_result(success=True, time_ms=24.0, ttl=117, bytes_size=32, loss=0.0, min_ms=None, max_ms=None, avg_ms=None):
    result = PingResult(success=success)
    if success:
        result.replies.append(PingReply(bytes_size=bytes_size, time_ms=time_ms, ttl=ttl))
        result.stats = PingStatistics(
            sent=1,
            received=1,
            lost=0,
            loss_percent=loss,
            min_ms=min_ms if min_ms is not None else time_ms,
            max_ms=max_ms if max_ms is not None else time_ms,
            avg_ms=avg_ms if avg_ms is not None else time_ms,
        )
    return result


def test_check_connection_online():
    cfg = Config(ping_host="8.8.8.8", ping_timeout_seconds=1, ping_retries=1)
    with patch("checker._ping_host", return_value=_ping_result()):
        with patch("checker._get_active_connection", return_value=("MyWiFi", "WiFi")):
            result = check_connection(cfg)
            assert result.status == "online"
            assert result.ping_ms == 24.0
            assert result.ping_ttl == 117
            assert result.packet_size == 32
            assert result.packet_loss_percent == 0.0
            assert result.ssid == "MyWiFi"
            assert result.connection_type == "WiFi"


def test_check_connection_fallback_success():
    cfg = Config(
        ping_host="8.8.8.8",
        fallback_host="8.8.4.4",
        ping_timeout_seconds=1,
        ping_retries=1,
        fallback_delay_seconds=0,
    )
    def _fake_ping(host, timeout, retries):
        if host == "8.8.8.8":
            return PingResult(success=False)
        return _ping_result(time_ms=32.0, ttl=64)

    with patch("checker._ping_host", side_effect=_fake_ping):
        with patch("checker._get_active_connection", return_value=("MyWiFi", "WiFi")):
            result = check_connection(cfg)
            assert result.status == "online"
            assert result.ping_ms == 32.0
            assert result.ping_ttl == 64


def test_check_connection_offline_after_retries():
    cfg = Config(
        ping_host="8.8.8.8",
        fallback_host="8.8.4.4",
        ping_timeout_seconds=1,
        ping_retries=3,
        fallback_delay_seconds=0,
    )
    with patch("checker._ping_host", return_value=PingResult(success=False)):
        with patch("checker._get_active_connection", return_value=("MyWiFi", "WiFi")):
            result = check_connection(cfg)
            assert result.status == "offline"
            assert result.ping_ms is None
