from config import load_config, Config, DEFAULT_CONFIG

def test_load_config_returns_defaults(tmp_path):
    cfg = load_config(str(tmp_path / "config.json"))
    assert cfg.ping_host == "8.8.8.8"
    assert cfg.check_interval_seconds == 60
    assert cfg.speed_test_interval_seconds == 600
    assert cfg.web_port == 5000
