from unittest.mock import patch, MagicMock
from speedtester import run_speedtest, SpeedTestResult


def test_run_speedtest_parses_json():
    fake_json = """{"download": 62500000, "upload": 25000000, "ping": 12.5}"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_json, stderr="")
        result = run_speedtest("speedtest-cli")
        assert result is not None
        assert round(result.download_mbps, 2) == 50.0
        assert round(result.upload_mbps, 2) == 20.0
        assert result.ping_ms == 12.5


def test_run_speedtest_returns_none_on_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = run_speedtest("speedtest-cli")
        assert result is None
