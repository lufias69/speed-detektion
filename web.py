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
    # SQLite returns naive datetimes; values are stored as UTC, so re-attach
    # UTC before serializing (isoformat() alone emits no offset, and JS would
    # then parse the string as local time).
    ts = record.timestamp
    if ts and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return {
        "id": record.id,
        "timestamp": ts.isoformat().replace("+00:00", "Z") if ts else None,
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
    def export(
        format: str = Query("json"),
        start: Optional[datetime] = Query(None),
        end: Optional[datetime] = Query(None),
    ):
        session = get_db()
        try:
            rows = get_records_in_range(session, start, end)
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
