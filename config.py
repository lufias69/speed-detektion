import json
import os
from dataclasses import dataclass


DEFAULT_CONFIG = {
    "ping_host": "8.8.8.8",
    "fallback_host": "8.8.4.4",
    "ping_timeout_seconds": 2,
    "ping_retries": 3,
    "fallback_delay_seconds": 10,
    "check_interval_seconds": 60,
    "speed_test_interval_seconds": 3600,
    "run_speed_tests": True,
    "run_speed_test_on_recovery": True,
    "speed_test_cli_path": "speedtest-cli",
    "database_path": "data/speed_monitor.db",
    "log_path": "logs/speed_monitor.log",
    "web_host": "127.0.0.1",
    "web_port": 5000,
    "network_name": "",
    "location": "",
    "firebase_api_key": "",
    "firebase_project_id": "",
    "firebase_collection": "speed_records",
    "timezone": "Asia/Makassar",
}


@dataclass
class Config:
    ping_host: str = "8.8.8.8"
    fallback_host: str = "8.8.4.4"
    ping_timeout_seconds: int = 2
    ping_retries: int = 3
    fallback_delay_seconds: int = 10
    check_interval_seconds: int = 60
    speed_test_interval_seconds: int = 3600
    run_speed_tests: bool = True
    run_speed_test_on_recovery: bool = True
    speed_test_cli_path: str = "speedtest-cli"
    database_path: str = "data/speed_monitor.db"
    log_path: str = "logs/speed_monitor.log"
    web_host: str = "127.0.0.1"
    web_port: int = 5000
    network_name: str = ""
    location: str = ""
    firebase_api_key: str = ""
    firebase_project_id: str = ""
    firebase_collection: str = "speed_records"
    timezone: str = "Asia/Makassar"


def load_config(path: str) -> Config:
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return Config(**DEFAULT_CONFIG)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    merged = {**DEFAULT_CONFIG, **data}
    return Config(**merged)
