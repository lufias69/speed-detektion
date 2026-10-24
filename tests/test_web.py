from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from config import Config
from db import get_engine, get_session, SpeedRecord, add_record
from web import create_app


def _app_and_client():
    cfg = Config(database_path=":memory:", web_port=5000)
    engine = get_engine(cfg.database_path)
    app = create_app(cfg, engine)
    return app, engine, TestClient(app)


def _add(session, minutes_ago, status="online", download=None):
    rec = SpeedRecord(
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        ssid="WiFi",
        status=status,
        ping_ms=10.0,
        download_mbps=download,
    )
    return add_record(session, rec)


def test_status_endpoint():
    _, _, client = _app_and_client()
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unknown"
    assert "last_record" in data


def test_records_timestamps_are_utc_aware():
    # Timestamps must serialize with a UTC designator ("Z" or "+00:00") so the
    # dashboard does not reinterpret them as local time.
    app, engine, client = _app_and_client()
    session = get_session(engine)
    _add(session, 5)

    data = client.get("/api/records").json()
    assert data, "expected at least one record"
    ts = data[0]["timestamp"]
    assert ts.endswith("Z") or ts.endswith("+00:00"), f"naive timestamp: {ts}"


def test_export_respects_date_filter():
    # /api/export must honor start/end like /api/records and /api/stats do.
    app, engine, client = _app_and_client()
    session = get_session(engine)
    _add(session, minutes_ago=2)        # inside the filter window
    _add(session, minutes_ago=10_000)   # ~7 days old, outside

    start = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    resp = client.get("/api/export", params={"format": "csv", "start": start})
    assert resp.status_code == 200
    # Only the header plus the one record inside the window.
    body_lines = [line for line in resp.text.splitlines() if line.strip()]
    assert len(body_lines) == 2, f"expected header + 1 row, got: {body_lines}"
