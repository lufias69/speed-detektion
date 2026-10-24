import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


DEFAULT_CONFIG = {
    "ping_host": "8.8.8.8",
    "ping_timeout_seconds": 2,
    "ping_retries": 3,
    "check_interval_seconds": 60,
    "speed_test_interval_seconds": 600,
    "run_speed_test_on_recovery": True,
    "speed_test_cli_path": "speedtest-cli",
    "database_path": "data/speed_monitor.db",
    "log_path": "logs/speed_monitor.log",
    "web_host": "127.0.0.1",
    "web_port": 5000,
}


@dataclass
class Config:
    ping_host: str = "8.8.8.8"
    ping_timeout_seconds: int = 2
    ping_retries: int = 3
    check_interval_seconds: int = 60
    speed_test_interval_seconds: int = 600
    run_speed_test_on_recovery: bool = True
    speed_test_cli_path: str = "speedtest-cli"
    database_path: str = "data/speed_monitor.db"
    log_path: str = "logs/speed_monitor.log"
    web_host: str = "127.0.0.1"
    web_port: int = 5000


def load_config(path: str) -> Config:
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return Config(**DEFAULT_CONFIG)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    merged = {**DEFAULT_CONFIG, **data}
    return Config(**merged)
