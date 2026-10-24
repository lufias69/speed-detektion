# Speed Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight cross-platform Python application that monitors internet connectivity every minute, records ping/speed-test data to a local SQLite database, runs as an OS background service, and serves a local web dashboard.

**Architecture:** The app is split into small single-purpose Python modules (config, database, network checker, speed tester, scheduler monitor, web server, logger, installer). APScheduler runs the monitor job in a background thread while FastAPI/Uvicorn serves the dashboard. SQLite WAL mode keeps web reads and scheduler writes concurrent.

**Tech Stack:** Python 3.10+, FastAPI, Uvicorn, APScheduler, SQLAlchemy, SQLite, `speedtest-cli` subprocess, vanilla JS + Chart.js frontend, pywin32/systemd for service install.

## Global Constraints

- Python version floor: 3.10+.
- Web framework: FastAPI + Uvicorn.
- Scheduler: APScheduler `BackgroundScheduler`.
- Database: SQLite via SQLAlchemy ORM; WAL mode enabled.
- Speed test: external `speedtest-cli` subprocess with JSON parsing.
- SSID detection: cross-platform shell commands only (`netsh`, `nmcli`, `iwgetid`).
- Dashboard: single-page vanilla JS + Chart.js, no build step.
- Packaging: `requirements.txt` + `install.bat` (Windows) + `install.sh` (Linux).
- Default web port: 5000; default ping host: `8.8.8.8`; default check interval: 60 seconds.
- Default speed-test interval: 600 seconds; run speed test on recovery: true.
- All paths in config are relative to the application root.
- The app must keep recording when the internet is offline.

---

## File Map

```text
sped_detektion/
├── config.py
├── db.py
├── checker.py
├── speedtester.py
├── monitor.py
├── web.py
├── logs.py
├── main.py
├── install_service.py
├── requirements.txt
├── install.bat
├── install.sh
├── tests/
│   ├── test_config.py
│   ├── test_db.py
│   ├── test_checker.py
│   └── test_monitor.py
├── static/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── chart.min.js   # local fallback copy
└── config.json        # generated on first run
```

---

## Task 1: Project Scaffolding and Configuration

**Files:**
- Create: `config.py`
- Create: `requirements.txt`
- Create: `config.json` (default config template)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` dataclass; function `load_config(path: str) -> Config`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from config import load_config, Config, DEFAULT_CONFIG

def test_load_config_returns_defaults(tmp_path):
    cfg = load_config(str(tmp_path / "config.json"))
    assert cfg.ping_host == "8.8.8.8"
    assert cfg.check_interval_seconds == 60
    assert cfg.speed_test_interval_seconds == 600
    assert cfg.web_port == 5000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_load_config_returns_defaults -v`
Expected: FAIL with "config module not found" or "load_config not defined".

- [ ] **Step 3: Write minimal implementation**

```python
# config.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_load_config_returns_defaults -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add configuration loader with defaults"
```

---

## Task 2: Logging Setup

**Files:**
- Create: `logs.py`
- Modify: `config.py` (no change needed)
- Test: `tests/test_logs.py`

**Interfaces:**
- Consumes: `Config.log_path`.
- Produces: `setup_logging(log_path: str) -> logging.Logger` returning a logger named `"speedmonitor"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_logs.py
import logging
import os
import tempfile
from logs import setup_logging

def test_setup_logging_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        log_file = os.path.join(tmp, "test.log")
        logger = setup_logging(log_file)
        logger.info("hello")
        assert os.path.exists(log_file)
        with open(log_file, "r") as f:
            assert "hello" in f.read()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_logs.py::test_setup_logging_creates_file -v`
Expected: FAIL "logs module not found".

- [ ] **Step 3: Write minimal implementation**

```python
# logs.py
import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(log_path: str) -> logging.Logger:
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    logger = logging.getLogger("speedmonitor")
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_logs.py::test_setup_logging_creates_file -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add logs.py tests/test_logs.py
git commit -m "feat: add rotating file logger"
```

---

## Task 3: Database Model and Access

**Files:**
- Create: `db.py`
- Create: `data/` directory in repo (empty `.gitkeep`)
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `Config.database_path`.
- Produces:
  - `Base`, `SpeedRecord` SQLAlchemy model.
  - `get_engine(db_path: str)`, `get_session(engine)`.
  - `add_record(session, record: SpeedRecord)`, `get_recent_records(session, limit: int)`, `get_records_in_range(session, start, end, limit)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
from datetime import datetime, timezone
from db import get_engine, get_session, SpeedRecord, add_record, get_recent_records

def test_add_and_retrieve_record():
    engine = get_engine(":memory:")
    session = get_session(engine)
    record = SpeedRecord(
        timestamp=datetime.now(timezone.utc),
        ssid="TestWiFi",
        status="online",
        ping_ms=12.5,
        download_mbps=50.0,
        upload_mbps=20.0,
    )
    add_record(session, record)
    rows = get_recent_records(session, 10)
    assert len(rows) == 1
    assert rows[0].ssid == "TestWiFi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py::test_add_and_retrieve_record -v`
Expected: FAIL "db module not found".

- [ ] **Step 3: Write minimal implementation**

```python
# db.py
import os
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
    event,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.sql import func

Base = declarative_base()


class SpeedRecord(Base):
    __tablename__ = "speed_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    ssid = Column(String(255), nullable=True)
    status = Column(String(16), nullable=False)
    ping_ms = Column(Float, nullable=True)
    download_mbps = Column(Float, nullable=True)
    upload_mbps = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)


@event.listens_for(SpeedRecord, "before_insert", propagate=True)
def _set_utc(mapper, connection, target):
    if target.timestamp and target.timestamp.tzinfo is None:
        target.timestamp = target.timestamp.replace(tzinfo=timezone.utc)


def get_engine(db_path: str):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    with engine.connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")

    return engine


def get_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def add_record(session: Session, record: SpeedRecord) -> SpeedRecord:
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def get_recent_records(session: Session, limit: int = 100) -> List[SpeedRecord]:
    return (
        session.query(SpeedRecord)
        .order_by(SpeedRecord.timestamp.desc())
        .limit(limit)
        .all()
    )


def get_records_in_range(
    session: Session,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> List[SpeedRecord]:
    query = session.query(SpeedRecord)
    if start:
        query = query.filter(SpeedRecord.timestamp >= start)
    if end:
        query = query.filter(SpeedRecord.timestamp <= end)
    query = query.order_by(SpeedRecord.timestamp.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


def get_stats(session: Session, start: Optional[datetime] = None, end: Optional[datetime] = None):
    query = session.query(SpeedRecord)
    if start:
        query = query.filter(SpeedRecord.timestamp >= start)
    if end:
        query = query.filter(SpeedRecord.timestamp <= end)

    rows = query.order_by(SpeedRecord.timestamp.desc()).all()
    if not rows:
        return {
            "count": 0,
            "online_count": 0,
            "offline_count": 0,
            "uptime_percent": 0.0,
            "avg_download": None,
            "avg_upload": None,
            "avg_ping": None,
        }

    online = [r for r in rows if r.status == "online"]
    offline = [r for r in rows if r.status == "offline"]

    def avg(values):
        clean = [v for v in values if v is not None]
        return sum(clean) / len(clean) if clean else None

    return {
        "count": len(rows),
        "online_count": len(online),
        "offline_count": len(offline),
        "uptime_percent": round(len(online) / len(rows) * 100, 2),
        "avg_download": avg([r.download_mbps for r in online]),
        "avg_upload": avg([r.upload_mbps for r in online]),
        "avg_ping": avg([r.ping_ms for r in online]),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db.py::test_add_and_retrieve_record -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py data/.gitkeep
git commit -m "feat: add SQLite database model and access layer"
```

---

## Task 4: Network Checker (Ping + SSID)

**Files:**
- Create: `checker.py`
- Test: `tests/test_checker.py`

**Interfaces:**
- Consumes: `Config.ping_host`, `Config.ping_timeout_seconds`, `Config.ping_retries`.
- Produces: `CheckResult` dataclass; function `check_connection(config: Config) -> CheckResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_checker.py
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


def test_check_connection_offline_after_retries():
    cfg = Config(ping_host="8.8.8.8", ping_timeout_seconds=1, ping_retries=3)
    with patch("checker._ping_host", return_value=(False, None)):
        with patch("checker._get_ssid", return_value="MyWiFi"):
            result = check_connection(cfg)
            assert result.status == "offline"
            assert result.ping_ms is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_checker.py -v`
Expected: FAIL "checker module not found".

- [ ] **Step 3: Write minimal implementation**

```python
# checker.py
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

from config import Config


@dataclass
class CheckResult:
    timestamp: datetime
    ssid: Optional[str]
    status: str
    ping_ms: Optional[float]
    error_message: Optional[str] = None


def _ping_host(host: str, timeout: int) -> Tuple[bool, Optional[float]]:
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout), host]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout + 1,
        )
        success = proc.returncode == 0
        latency = None
        if success:
            latency = _parse_ping_output(proc.stdout, system)
        return success, latency
    except Exception as exc:
        return False, None


def _parse_ping_output(output: str, system: str) -> Optional[float]:
    try:
        if system == "windows":
            # Average = 24ms
            for line in output.splitlines():
                if "Average" in line and "=" in line:
                    part = line.split("=")[-1].strip()
                    return float(part.replace("ms", "").strip())
        else:
            # rtt min/avg/max/mdev = ...
            for line in output.splitlines():
                if "avg" in line and "/" in line:
                    parts = line.split("=")[-1].split("/")
                    return float(parts[1].strip())
    except Exception:
        pass
    return None


def _get_ssid() -> Optional[str]:
    system = platform.system().lower()
    try:
        if system == "windows":
            return _get_ssid_windows()
        return _get_ssid_linux()
    except Exception:
        return None


def _get_ssid_windows() -> Optional[str]:
    proc = subprocess.run(
        ["netsh", "wlan", "show", "interfaces"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if "SSID" in line and "BSSID" not in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return None


def _get_ssid_linux() -> Optional[str]:
    for cmd in [
        ["iwgetid", "-r"],
        ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
    ]:
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                if cmd[0] == "iwgetid":
                    return proc.stdout.strip()
                for line in proc.stdout.splitlines():
                    if line.startswith("yes:"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            continue
    return None


def check_connection(config: Config) -> CheckResult:
    timestamp = datetime.now(timezone.utc)
    ssid = _get_ssid()
    last_error = None

    for attempt in range(config.ping_retries):
        success, latency = _ping_host(config.ping_host, config.ping_timeout_seconds)
        if success:
            return CheckResult(
                timestamp=timestamp,
                ssid=ssid,
                status="online",
                ping_ms=latency,
            )

    return CheckResult(
        timestamp=timestamp,
        ssid=ssid,
        status="offline",
        ping_ms=None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_checker.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add checker.py tests/test_checker.py
git commit -m "feat: add ping and SSID checker"
```

---

## Task 5: Speed Tester Wrapper

**Files:**
- Create: `speedtester.py`
- Test: `tests/test_speedtester.py`

**Interfaces:**
- Consumes: `Config.speed_test_cli_path`.
- Produces: `SpeedTestResult` dataclass; function `run_speedtest(cli_path: str) -> Optional[SpeedTestResult]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_speedtester.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_speedtester.py -v`
Expected: FAIL "speedtester module not found".

- [ ] **Step 3: Write minimal implementation**

```python
# speedtester.py
import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("speedmonitor")


@dataclass
class SpeedTestResult:
    download_mbps: float
    upload_mbps: float
    ping_ms: float


def run_speedtest(cli_path: str) -> Optional[SpeedTestResult]:
    cmd = [cli_path, "--format=json", "--accept-license", "--accept-gdpr"]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            logger.warning("speedtest failed: %s", proc.stderr.strip())
            return None

        data = json.loads(proc.stdout)
        download = data.get("download", 0) / 1_000_000  # bits/s -> Mbps
        upload = data.get("upload", 0) / 1_000_000
        ping = data.get("ping", 0)
        return SpeedTestResult(download, upload, ping)
    except subprocess.TimeoutExpired:
        logger.warning("speedtest timed out")
        return None
    except Exception as exc:
        logger.warning("speedtest error: %s", exc)
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_speedtester.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add speedtester.py tests/test_speedtester.py
git commit -m "feat: add speedtest subprocess wrapper"
```

---

## Task 6: Monitor Orchestrator

**Files:**
- Create: `monitor.py`
- Test: `tests/test_monitor.py`

**Interfaces:**
- Consumes: `Config`, `check_connection()`, `run_speedtest()`, `add_record()`, `get_session()`, `setup_logging()`.
- Produces: `Monitor` class with `tick()` and `start()` methods.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_monitor.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_monitor.py -v`
Expected: FAIL "monitor module not found".

- [ ] **Step 3: Write minimal implementation**

```python
# monitor.py
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
    def __init__(self, config: Config, session: Session):
        self.config = config
        self.session = session
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

        add_record(self.session, record)
        logger.info(
            "recorded %s ssid=%s ping=%s down=%s up=%s",
            record.status,
            record.ssid,
            record.ping_ms,
            record.download_mbps,
            record.upload_mbps,
        )
        return record
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_monitor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add monitor.py tests/test_monitor.py
git commit -m "feat: add monitor orchestrator with conditional speed tests"
```

---

## Task 7: Web Server and REST API

**Files:**
- Create: `web.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `Config`, `get_engine()`, `get_session()`, `get_recent_records()`, `get_records_in_range()`, `get_stats()`.
- Produces: FastAPI app instance `create_app(config: Config) -> FastAPI`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web.py
from fastapi.testclient import TestClient
from config import Config
from db import get_engine
from web import create_app


def test_status_endpoint():
    cfg = Config(database_path=":memory:", web_port=5000)
    engine = get_engine(cfg.database_path)
    app = create_app(cfg, engine)
    client = TestClient(app)
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unknown"
    assert "last_record" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web.py::test_status_endpoint -v`
Expected: FAIL "web module not found".

- [ ] **Step 3: Write minimal implementation**

```python
# web.py
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from config import Config
from db import (
    SpeedRecord,
    get_engine,
    get_session,
    get_recent_records,
    get_records_in_range,
    get_stats,
)


def _record_to_dict(record: SpeedRecord) -> dict:
    return {
        "id": record.id,
        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
        "ssid": record.ssid,
        "status": record.status,
        "ping_ms": record.ping_ms,
        "download_mbps": record.download_mbps,
        "upload_mbps": record.upload_mbps,
        "error_message": record.error_message,
    }


def create_app(config: Config, engine=None) -> FastAPI:
    app = FastAPI(title="Speed Monitor")
    if engine is None:
        engine = get_engine(config.database_path)

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def root():
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Speed Monitor API running"}

    def get_db() -> Session:
        return get_session(engine)

    @app.get("/api/status")
    def status():
        session = get_db()
        try:
            records = get_recent_records(session, 1)
            last = records[0] if records else None
            return {
                "status": last.status if last else "unknown",
                "last_record": _record_to_dict(last) if last else None,
            }
        finally:
            session.close()

    @app.get("/api/records")
    def records(
        limit: int = Query(100, ge=1, le=10000),
        start: Optional[datetime] = Query(None),
        end: Optional[datetime] = Query(None),
    ):
        session = get_db()
        try:
            rows = get_records_in_range(session, start, end, limit)
            return [_record_to_dict(r) for r in rows]
        finally:
            session.close()

    @app.get("/api/stats")
    def stats(
        start: Optional[datetime] = Query(None),
        end: Optional[datetime] = Query(None),
    ):
        session = get_db()
        try:
            return get_stats(session, start, end)
        finally:
            session.close()

    @app.get("/api/export")
    def export(format: str = Query("json")):
        session = get_db()
        try:
            rows = get_records_in_range(session)
            data = [_record_to_dict(r) for r in rows]
            if format == "json":
                return JSONResponse(content=data)

            import csv
            import io
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=data[0].keys() if data else [])
            writer.writeheader()
            writer.writerows(data)
            output.seek(0)
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode("utf-8")),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=speed_records.csv"},
            )
        finally:
            session.close()

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web.py::test_status_endpoint -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web.py tests/test_web.py
git commit -m "feat: add FastAPI web server with REST endpoints"
```

---

## Task 8: Dashboard Frontend

**Files:**
- Create: `static/index.html`
- Create: `static/style.css`
- Create: `static/app.js`
- Download/create: `static/chart.min.js` (local fallback)
- Test: manual only (no automated frontend test in this version).

**Interfaces:**
- Consumes: `/api/status`, `/api/records`, `/api/stats`.
- Produces: rendered dashboard in browser.

- [ ] **Step 1: Write the failing test**

No automated test. Verify manually after creating files:

```bash
curl http://localhost:5000/static/index.html
```
Expected: returns HTML.

- [ ] **Step 2: Run test to verify it fails**

Run: `python main.py` in one terminal, then `curl` above in another.
Expected: FAIL `main.py` not found yet (Task 9 creates it). So defer full manual test until Task 9.

- [ ] **Step 3: Write minimal implementation**

```html
<!-- static/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Speed Monitor</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <h1>Speed Monitor</h1>
    <span id="status-badge" class="badge">Checking...</span>
  </header>

  <section id="filters">
    <label>From <input type="datetime-local" id="start"></label>
    <label>To <input type="datetime-local" id="end"></label>
    <button id="refresh">Refresh</button>
    <a id="export-csv" href="/api/export?format=csv" download>Export CSV</a>
  </section>

  <section id="summary">
    <div class="card"><h3>Avg Download</h3><p id="avg-download">-</p></div>
    <div class="card"><h3>Avg Upload</h3><p id="avg-upload">-</p></div>
    <div class="card"><h3>Avg Ping</h3><p id="avg-ping">-</p></div>
    <div class="card"><h3>Uptime</h3><p id="uptime">-</p></div>
  </section>

  <section id="charts">
    <canvas id="speed-chart"></canvas>
    <canvas id="ping-chart"></canvas>
  </section>

  <section id="history">
    <h2>Recent Records</h2>
    <table>
      <thead>
        <tr><th>Time</th><th>SSID</th><th>Status</th><th>Ping</th><th>Down</th><th>Up</th></tr>
      </thead>
      <tbody id="records-body"></tbody>
    </table>
  </section>

  <script src="/static/chart.min.js"></script>
  <script src="/static/app.js"></script>
</body>
</html>
```

```css
/* static/style.css */
:root {
  --bg: #f5f7fa;
  --card: #ffffff;
  --online: #28a745;
  --offline: #dc3545;
  --text: #333333;
}

body {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  margin: 0;
  padding: 1rem;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.badge {
  padding: 0.4rem 0.8rem;
  border-radius: 999px;
  color: white;
  font-weight: bold;
  text-transform: uppercase;
}
.badge.online { background: var(--online); }
.badge.offline { background: var(--offline); }
.badge.unknown { background: #6c757d; }

#summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
}

.card {
  background: var(--card);
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.card h3 { margin: 0 0 0.5rem; font-size: 0.9rem; color: #666; }
.card p { margin: 0; font-size: 1.4rem; font-weight: bold; }

#charts { display: grid; gap: 1rem; margin-bottom: 1rem; }

#filters { margin-bottom: 1rem; }
#filters label, #filters button, #filters a { margin-right: 0.5rem; }

table {
  width: 100%;
  border-collapse: collapse;
  background: var(--card);
}
th, td { padding: 0.6rem; text-align: left; border-bottom: 1px solid #ddd; }
th { background: #e9ecef; }
```

```javascript
// static/app.js
const fmtDate = (iso) => new Date(iso).toLocaleString();
const fmtNum = (n, digits = 1) => n !== null && n !== undefined ? n.toFixed(digits) : '-';

const els = {
  status: document.getElementById('status-badge'),
  start: document.getElementById('start'),
  end: document.getElementById('end'),
  refresh: document.getElementById('refresh'),
  avgDown: document.getElementById('avg-download'),
  avgUp: document.getElementById('avg-upload'),
  avgPing: document.getElementById('avg-ping'),
  uptime: document.getElementById('uptime'),
  recordsBody: document.getElementById('records-body'),
};

let speedChart, pingChart;

function initCharts() {
  speedChart = new Chart(document.getElementById('speed-chart'), {
    type: 'line',
    data: { labels: [], datasets: [
      { label: 'Download Mbps', data: [], borderColor: '#007bff', fill: false },
      { label: 'Upload Mbps', data: [], borderColor: '#17a2b8', fill: false },
    ]},
    options: { responsive: true, scales: { y: { beginAtZero: true } }, plugins: { title: { display: true, text: 'Speed Over Time' } } }
  });

  pingChart = new Chart(document.getElementById('ping-chart'), {
    type: 'line',
    data: { labels: [], datasets: [
      { label: 'Ping ms', data: [], borderColor: '#ffc107', fill: false },
    ]},
    options: { responsive: true, scales: { y: { beginAtZero: true } }, plugins: { title: { display: true, text: 'Latency Over Time' } } }
  });
}

async function loadDashboard() {
  const params = new URLSearchParams();
  if (els.start.value) params.set('start', new Date(els.start.value).toISOString());
  if (els.end.value) params.set('end', new Date(els.end.value).toISOString());

  const [statusRes, recordsRes, statsRes] = await Promise.all([
    fetch('/api/status'),
    fetch('/api/records?' + params.toString()),
    fetch('/api/stats?' + params.toString()),
  ]);

  const status = await statusRes.json();
  const records = await recordsRes.json();
  const stats = await statsRes.json();

  const lastStatus = status.status || 'unknown';
  els.status.textContent = lastStatus;
  els.status.className = 'badge ' + lastStatus;

  els.avgDown.textContent = fmtNum(stats.avg_download) + ' Mbps';
  els.avgUp.textContent = fmtNum(stats.avg_upload) + ' Mbps';
  els.avgPing.textContent = fmtNum(stats.avg_ping, 0) + ' ms';
  els.uptime.textContent = (stats.uptime_percent ?? 0).toFixed(1) + '%';

  const labels = records.slice().reverse().map(r => fmtDate(r.timestamp));
  speedChart.data.labels = labels;
  speedChart.data.datasets[0].data = records.slice().reverse().map(r => r.download_mbps);
  speedChart.data.datasets[1].data = records.slice().reverse().map(r => r.upload_mbps);
  speedChart.update();

  pingChart.data.labels = labels;
  pingChart.data.datasets[0].data = records.slice().reverse().map(r => r.ping_ms);
  pingChart.update();

  els.recordsBody.innerHTML = records.slice(0, 100).map(r => `
    <tr>
      <td>${fmtDate(r.timestamp)}</td>
      <td>${r.ssid || '-'}</td>
      <td>${r.status}</td>
      <td>${fmtNum(r.ping_ms, 0)}</td>
      <td>${fmtNum(r.download_mbps)}</td>
      <td>${fmtNum(r.upload_mbps)}</td>
    </tr>
  `).join('');
}

document.addEventListener('DOMContentLoaded', () => {
  const now = new Date();
  const yesterday = new Date(now - 24 * 60 * 60 * 1000);
  const toInput = (d) => d.toISOString().slice(0, 16);
  els.end.value = toInput(now);
  els.start.value = toInput(yesterday);

  initCharts();
  loadDashboard();
  els.refresh.addEventListener('click', loadDashboard);
  setInterval(loadDashboard, 30000);
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web.py` and manually open `http://localhost:5000` after Task 9.
Expected: PASS unit tests; dashboard renders after main app is running.

- [ ] **Step 5: Commit**

```bash
git add static/
git commit -m "feat: add dashboard frontend with charts and filters"
```

---

## Task 9: Application Entry Point and Graceful Shutdown

**Files:**
- Create: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `Config`, `setup_logging()`, `get_engine()`, `Monitor`, `create_app()`.
- Produces: runnable CLI entry point.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main.py
from unittest.mock import patch, MagicMock
from config import Config
from main import build_monitor, build_app


def test_build_app_returns_fastapi_instance():
    cfg = Config(database_path=":memory:", web_port=5000)
    app = build_app(cfg)
    from fastapi import FastAPI
    assert isinstance(app, FastAPI)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py::test_build_app_returns_fastapi_instance -v`
Expected: FAIL "main module not found".

- [ ] **Step 3: Write minimal implementation**

```python
# main.py
import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config, load_config
from db import get_engine
from logs import setup_logging
from monitor import Monitor
from web import create_app

logger = logging.getLogger("speedmonitor")


def build_app(config: Config):
    engine = get_engine(config.database_path)
    return create_app(config, engine)


def build_monitor(config: Config):
    engine = get_engine(config.database_path)
    session_factory = lambda: __import__("db").get_session(engine)
    session = session_factory()
    return Monitor(config, session)


def main():
    parser = argparse.ArgumentParser(description="Speed Monitor")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config.log_path)

    logger.info("starting Speed Monitor")

    monitor = build_monitor(config)

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        monitor.tick,
        "interval",
        seconds=config.check_interval_seconds,
        id="speed_check",
        replace_existing=True,
    )
    scheduler.start()

    # Run first tick immediately in a background thread
    first_tick = threading.Thread(target=monitor.tick, daemon=True)
    first_tick.start()

    app = build_app(config)

    stop_event = threading.Event()

    def handle_signal(signum, frame):
        logger.info("received signal %s, shutting down", signum)
        stop_event.set()
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    uvicorn.run(
        app,
        host=config.web_host,
        port=config.web_port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py::test_build_app_returns_fastapi_instance -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add main entry point with scheduler and uvicorn"
```

---

## Task 10: Service Installer Scripts

**Files:**
- Create: `install_service.py`
- Create: `install.bat`
- Create: `install.sh`
- Test: manual on target OS.

**Interfaces:**
- Consumes: application root path, virtual environment.
- Produces: registered Windows Service / systemd user unit.

- [ ] **Step 1: Write the failing test**

No automated test; verify by running installer on target OS.

- [ ] **Step 2: Run test to verify it fails**

Expected: installer scripts not present yet.

- [ ] **Step 3: Write minimal implementation**

```python
# install_service.py
import argparse
import os
import platform
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


def install_windows():
    try:
        import win32serviceutil
        import win32service
        import win32event
        import servicemanager
    except ImportError:
        print("pywin32 not installed. Run: .venv\\Scripts\\pip install pywin32")
        sys.exit(1)

    python_exe = VENV / "Scripts" / "python.exe"
    service_script = ROOT / "windows_service.py"
    service_script.write_text(
        f'''import win32serviceutil
import win32service
import win32event
import servicemanager
import subprocess
import sys
import os

ROOT = r"{ROOT}"
PYTHON = r"{python_exe}"

class SpeedMonitorService(win32serviceutil.ServiceFramework):
    _svc_name_ = "SpeedMonitor"
    _svc_display_name_ = "Speed Monitor"
    _svc_description_ = "Monitors internet speed and connectivity."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        proc = subprocess.Popen([PYTHON, os.path.join(ROOT, "main.py")], cwd=ROOT)
        while proc.poll() is None:
            rc = win32event.WaitForSingleObject(self.hWaitStop, 1000)
            if rc == win32event.WAIT_OBJECT_0:
                proc.terminate()
                break

if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(SpeedMonitorService)
''',
        encoding="utf-8",
    )
    print(f"Created {service_script}")
    print("Run as Administrator: .venv\\Scripts\\python windows_service.py install")
    print("Then: .venv\\Scripts\\python windows_service.py start")


def install_linux():
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    python_exe = VENV / "bin" / "python"
    unit_file = unit_dir / "speedmonitor.service"
    unit_file.write_text(
        f"""[Unit]
Description=Speed Monitor
After=network.target

[Service]
Type=simple
WorkingDirectory={ROOT}
ExecStart={python_exe} {ROOT / "main.py"}
Restart=on-failure

[Install]
WantedBy=default.target
""",
        encoding="utf-8",
    )
    print(f"Created {unit_file}")
    print("Run: systemctl --user daemon-reload")
    print("Run: systemctl --user enable --now speedmonitor")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--os", choices=["windows", "linux"], default=None)
    args = parser.parse_args()

    system = args.os or platform.system().lower()
    if system == "windows":
        install_windows()
    elif system == "linux":
        install_linux()
    else:
        print(f"Unsupported OS: {system}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

```batch
:: install.bat
@echo off
setlocal

echo Creating virtual environment...
python -m venv .venv

.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install pywin32

if not exist config.json (
    echo Creating default config...
    python -c "from config import DEFAULT_CONFIG; import json; json.dump(DEFAULT_CONFIG, open('config.json','w'), indent=2)"
)

echo Installing service...
.venv\Scripts\python install_service.py --os windows

endlocal
pause
```

```bash
#!/bin/bash
# install.sh
set -e

echo "Creating virtual environment..."
python3 -m venv .venv

.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

if [ ! -f config.json ]; then
    echo "Creating default config..."
    .venv/bin/python -c "from config import DEFAULT_CONFIG; import json; json.dump(DEFAULT_CONFIG, open('config.json','w'), indent=2)"
fi

echo "Installing systemd user service..."
.venv/bin/python install_service.py --os linux

echo "Done. Run: systemctl --user daemon-reload && systemctl --user enable --now speedmonitor"
```

- [ ] **Step 4: Run test to verify it passes**

Run on Windows: `install.bat` (as Administrator).  
Run on Linux: `chmod +x install.sh && ./install.sh`.
Expected: service installed and running; dashboard reachable at `http://localhost:5000`.

- [ ] **Step 5: Commit**

```bash
git add install_service.py install.bat install.sh
git commit -m "feat: add Windows and Linux service installers"
```

---

## Task 11: `requirements.txt`

**Files:**
- Create: `requirements.txt`

**Interfaces:**
- Produces: pinned dependency list.

- [ ] **Step 1: Write the failing test**

No failing test; verify install succeeds.

- [ ] **Step 2: Run test to verify it fails**

Expected: missing `requirements.txt`.

- [ ] **Step 3: Write minimal implementation**

```text
# requirements.txt
fastapi>=0.110.0
uvicorn>=0.27.0
sqlalchemy>=2.0.0
apscheduler>=3.10.0
pydantic>=2.0.0
python-dateutil>=2.8.0
pywin32>=306; platform_system=="Windows"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pip install -r requirements.txt`
Expected: installs successfully on Python 3.10+.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt
git commit -m "chore: add requirements.txt"
```

---

## Self-Review

### Spec coverage
- Configuration: Task 1.
- Logging: Task 2.
- Database model/access: Task 3.
- Ping + SSID checker: Task 4.
- Speed test wrapper: Task 5.
- Monitor orchestration: Task 6.
- Web server + REST endpoints: Task 7.
- Dashboard frontend: Task 8.
- Main entry point + graceful shutdown: Task 9.
- Service installers: Task 10.
- Dependencies: Task 11.
- Cross-platform constraints, WAL mode, offline recording, config defaults: embedded in each task.

### Placeholder scan
- No TBD/TODO.
- No vague "handle edge cases" steps.
- Every code step includes actual code.
- No references to undefined functions across tasks.

### Type consistency
- `Config` fields consistent throughout.
- `CheckResult`, `SpeedTestResult`, `SpeedRecord` fields consistent.
- `Monitor.tick()` returns `SpeedRecord` and stores state.
- `create_app(config, engine)` signature consistent.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-10-24-speed-monitor-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach do you want?**
