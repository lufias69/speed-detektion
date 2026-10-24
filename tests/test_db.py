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
