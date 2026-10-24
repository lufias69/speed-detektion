# Speed Monitor — Design Specification

**Date:** 2026-10-24  
**Project:** C:\project\sped detektion  
**Goal:** Build a lightweight, cross-platform internet-speed monitoring application that records connectivity and speed measurements into a local SQLite database, runs continuously in the background, and exposes a local web dashboard.

---

## 1. Purpose and Scope

The application monitors internet connectivity every minute using a lightweight ping. It records whether the connection is online or offline, the current Wi-Fi SSID, latency, and—when online—periodic full speed-test results. All data is stored in a local SQLite database. A small web dashboard lets the user inspect history, averages, and the current status.

The app must:
- Run unattended as a background service after a one-time install.
- Auto-start when the OS boots (Windows Service / Linux systemd user service).
- Work on Windows 10/11 and common Linux distributions.
- Keep resource usage low (no Electron, no heavy runtime).
- Keep working when the internet is down, recording offline events.

Out of scope for this first version:
- Remote/cloud access.
- Multi-user authentication.
- Mobile app.
- Alerts/notifications (can be added later).

---

## 2. Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.10+ | Ubiquitous, easy to package, good cross-platform libraries. |
| Web framework | FastAPI + Uvicorn | Lightweight, async-native, simple REST + static files. |
| Scheduler | APScheduler (BackgroundScheduler) | Runs periodic checks without blocking the web server. |
| Database | SQLite + SQLAlchemy ORM | Zero-config local storage, easy backup, portable file. |
| Speed test | `speedtest-cli` (Ookla) via subprocess | Reliable, widely used; fallback path configurable if needed. |
| SSID detection | Shell commands: `netsh` (Windows), `nmcli`/`iwgetid` (Linux) | No heavy dependency; wrapped in a small Python function. |
| Frontend dashboard | Vanilla HTML/CSS/JS + Chart.js | No build step, lightweight, works offline. |
| Service wrapper | Windows Service via `pywin32`; Linux systemd user unit | Standard OS mechanisms for auto-start. |
| Packaging | `requirements.txt` + install scripts (`install.bat` / `install.sh`) | Simple to run once. |

---

## 3. Architecture

The application is split into small, single-purpose modules:

```text
sped_detektion/
├── config.py          # Configuration loading and defaults
├── db.py              # SQLAlchemy models and database access
├── checker.py         # Ping + SSID detection + online/offline decision
├── speedtester.py     # Speed-test wrapper (subprocess)
├── monitor.py         # APScheduler job orchestrator
├── web.py             # FastAPI app, REST endpoints, static dashboard
├── main.py            # Entry point that starts scheduler + web server
├── logs.py            # Rotating file logger setup
├── install_service.py # Creates/removes OS service
├── requirements.txt
├── static/            # Dashboard assets
│   ├── index.html
│   ├── app.js
│   └── style.css
└── config.json        # User-editable config (created on first run if absent)
```

### Module responsibilities

- `config.py` — reads `config.json` and environment variables; provides defaults for ping host, ping timeout, check interval, speed-test interval, database path, log path, and web port.
- `db.py` — defines the `SpeedRecord` model, creates tables, exposes `SessionLocal` and helper functions to insert/query records.
- `checker.py` — `check_connection()` returns a dataclass with `timestamp`, `ssid`, `status`, `ping_ms`, and optional `error_message`. It retries the ping up to 3 times before marking offline.
- `speedtester.py` — `run_speedtest()` executes the external speed-test CLI, parses JSON output, and returns download/upload Mbps. It is only called by `monitor.py` when appropriate. It must never crash the scheduler; all failures are caught and logged.
- `monitor.py` — `Monitor` class holds the last state and decides whether to run a speed test. It is called by APScheduler every minute. It stores each ping result and conditionally appends speed-test data.
- `web.py` — FastAPI application. Serves the dashboard static files and provides JSON endpoints: `/api/status`, `/api/records`, `/api/stats`, `/api/export`.
- `main.py` — initializes logging, database, scheduler, and web server; graceful shutdown on SIGINT/SIGTERM.
- `install_service.py` — OS-specific helpers to register/unregister the background service.

---

## 4. Data Model

### Table: `speed_records`

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | Primary key, autoincrement. |
| `timestamp` | DateTime | UTC timestamp with microsecond precision, stored as ISO string; indexed descending for fast recent lookups. |
| `ssid` | String(255) | Current Wi-Fi SSID; nullable if not connected to Wi-Fi or detection fails. |
| `status` | String(16) | `"online"` or `"offline"`. |
| `ping_ms` | Float | Round-trip latency in milliseconds; nullable when offline. |
| `download_mbps` | Float | Download speed from full speed test; nullable when not measured. |
| `upload_mbps` | Float | Upload speed from full speed test; nullable when not measured. |
| `error_message` | Text | Optional error or fallback note. |

Indexes:
- `idx_timestamp` on `timestamp DESC` for dashboard queries.
- `idx_status` on `status` for statistics.

---

## 5. Check Flow (Every Minute)

1. Capture current timestamp in UTC with microsecond precision.
2. Detect current SSID via platform-specific command.
3. Ping configured host (default `8.8.8.8`) with timeout (default 2 s) and up to 3 retries.
4. If all pings fail:
   - Record `status = offline`, `ping_ms = NULL`, no speed test.
   - Set internal state `was_online = False`.
5. If ping succeeds:
   - Record `status = online`, `ping_ms = median or last latency`.
   - Decide whether to run a speed test:
     - `speed_test_due` if `now - last_speed_test_time >= speed_test_interval`.
     - `recovery_test` if `was_online == False` (just came back online).
   - If either is true, run speed test; append results; update `last_speed_test_time`.
   - Set `was_online = True`.
6. Insert record into SQLite.

The speed-test interval is configurable; default is 1 hour. The recovery speed test ensures the first measurement after an outage is captured.

---

## 6. Error Handling

- All scheduler exceptions are caught and logged; a failed job must not stop subsequent checks.
- Speed-test failures produce a record with `status = online`, `download_mbps = NULL`, `upload_mbps = NULL`, and an `error_message` explaining the failure.
- Ping retries avoid false offline events on transient packet loss.
- If SSID detection fails, the record is still saved with `ssid = NULL`.
- SQLite operations use a short-lived session per job; connections are not held open long-term.
- Web server runs read-only except for the scheduler writer; SQLite WAL mode is enabled to reduce lock contention.

---

## 7. Dashboard (Web UI)

The dashboard is a single-page static app at `http://localhost:5000`.

Endpoints:
- `GET /` — dashboard HTML.
- `GET /api/status` — current online/offline status, last seen, current SSID.
- `GET /api/records?limit=100&start=...&end=...` — paginated/filtered records as JSON.
- `GET /api/stats?start=...&end=...` — averages, min/max, uptime percentage.
- `GET /api/export?format=csv|json` — download full or filtered records.

Dashboard UI sections:
1. **Header** — app name and current status badge (online/offline).
2. **Summary cards** — average download, average upload, average ping, uptime % for selected range.
3. **Charts** — line chart of download/upload over time and line chart of ping latency.
4. **History table** — last N records with timestamp, SSID, status, ping, download, upload.
5. **Date filter** — pick start/end date; defaults to last 24 hours.

Frontend stack: vanilla JS + Chart.js loaded from CDN, with a local fallback copy included for offline environments.

---

## 8. Installation and Auto-Start

### Windows
1. Install Python 3.10+ and ensure `python` is on PATH.
2. Run `install.bat`:
   - Creates virtual environment in `.venv`.
   - Installs `requirements.txt`.
   - Writes `config.json` if missing.
   - Registers a Windows Service named `SpeedMonitor` using `pywin32`.
   - Starts the service and sets it to auto-start.
3. Open `http://localhost:5000` in a browser.

### Linux
1. Ensure Python 3.10+ and `pip` are installed.
2. Run `./install.sh`:
   - Creates virtual environment in `.venv`.
   - Installs dependencies.
   - Writes `config.json` if missing.
   - Creates a systemd user unit `~/.config/systemd/user/speedmonitor.service`.
   - Enables and starts the service.
3. Open `http://localhost:5000` in a browser.

### Manual / development mode
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux
pip install -r requirements.txt
python main.py
```

---

## 9. Configuration

`config.json` example:

```json
{
  "ping_host": "8.8.8.8",
  "ping_timeout_seconds": 2,
  "ping_retries": 3,
  "check_interval_seconds": 60,
  "speed_test_interval_seconds": 3600,
  "run_speed_test_on_recovery": true,
  "speed_test_cli_path": "speedtest-cli",
  "database_path": "data/speed_monitor.db",
  "log_path": "logs/speed_monitor.log",
  "web_host": "127.0.0.1",
  "web_port": 5000
}
```

All paths are relative to the application root. The config file is created with defaults on first run if it does not exist.

---

## 10. Testing Strategy

- Unit tests for `checker.py` using mock subprocess calls and fake SSID commands.
- Unit tests for `db.py` using an in-memory SQLite database.
- Unit tests for `monitor.py` decision logic using mocked checker and speed tester.
- Manual test: run locally, disconnect Wi-Fi or network cable for a few minutes, reconnect, verify offline and recovery records appear in dashboard.
- Service test: install on target OS, reboot, confirm process starts and dashboard is reachable.

---

## 11. Future Enhancements (Not in This Version)

- Email/desktop notifications when internet goes down or speed drops below threshold.
- Configurable speed-test servers.
- Dark/light theme toggle.
- Multi-interface detection (Ethernet vs. Wi-Fi).
- Remote read-only dashboard via tunnel/reverse proxy (out of scope by design).

---

## 12. Approval

Design approved by user on 2026-10-24. Proceed to implementation plan.
