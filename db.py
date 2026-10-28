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
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import func, text

Base = declarative_base()


class SpeedRecord(Base):
    __tablename__ = "speed_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    ssid = Column(String(255), nullable=True)
    connection_type = Column(String(32), nullable=True)
    adapter = Column(String(255), nullable=True)
    status = Column(String(16), nullable=False)
    ping_ms = Column(Float, nullable=True)
    ping_ttl = Column(Integer, nullable=True)
    packet_size = Column(Integer, nullable=True)
    ping_min_ms = Column(Float, nullable=True)
    ping_max_ms = Column(Float, nullable=True)
    ping_avg_ms = Column(Float, nullable=True)
    packet_loss_percent = Column(Float, nullable=True)
    download_mbps = Column(Float, nullable=True)
    upload_mbps = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)
    cloud_id = Column(String(255), nullable=True)


@event.listens_for(SpeedRecord, "before_insert", propagate=True)
def _set_utc(mapper, connection, target):
    if target.timestamp and target.timestamp.tzinfo is None:
        target.timestamp = target.timestamp.replace(tzinfo=timezone.utc)


def _migrate_columns(engine):
    """Add any columns that exist on the ORM model but are missing from the DB."""
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(speed_records)"))
        existing = {row[1] for row in result}

    model_columns = {
        "connection_type": "VARCHAR(32)",
        "adapter": "VARCHAR(255)",
        "ping_ttl": "INTEGER",
        "packet_size": "INTEGER",
        "ping_min_ms": "FLOAT",
        "ping_max_ms": "FLOAT",
        "ping_avg_ms": "FLOAT",
        "packet_loss_percent": "FLOAT",
        "synced_at": "DATETIME",
        "cloud_id": "VARCHAR(255)",
    }
    for col_name, col_type in model_columns.items():
        if col_name not in existing:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE speed_records ADD COLUMN {col_name} {col_type}"))
                conn.commit()


def get_engine(db_path: str):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    # ":memory:" needs StaticPool so every thread shares the single connection;
    # the default SingletonThreadPool gives each thread its own empty database.
    if db_path == ":memory:":
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    _migrate_columns(engine)

    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))
        conn.execute(text("PRAGMA synchronous=NORMAL;"))

    return engine


def get_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def add_record(session: Session, record: SpeedRecord) -> SpeedRecord:
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def get_unsynced_records(session: Session, limit: int = 100) -> List[SpeedRecord]:
    return (
        session.query(SpeedRecord)
        .filter(SpeedRecord.synced_at.is_(None))
        .order_by(SpeedRecord.timestamp.asc())
        .limit(limit)
        .all()
    )


def mark_record_synced(session: Session, record: SpeedRecord, cloud_id: str):
    record.synced_at = datetime.now(timezone.utc)
    record.cloud_id = cloud_id
    session.commit()


def get_recent_records(session: Session, limit: int = 100) -> List[SpeedRecord]:
    return (
        session.query(SpeedRecord)
        .order_by(SpeedRecord.timestamp.desc())
        .limit(limit)
        .all()
    )


def _as_utc_naive(dt: Optional[datetime]) -> Optional[datetime]:
    # Stored timestamps are naive UTC; drop offsets from filter bounds so the
    # string-backed comparison matches regardless of the client's timezone.
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def get_records_in_range(
    session: Session,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> List[SpeedRecord]:
    query = session.query(SpeedRecord)
    if start:
        query = query.filter(SpeedRecord.timestamp >= _as_utc_naive(start))
    if end:
        query = query.filter(SpeedRecord.timestamp <= _as_utc_naive(end))
    query = query.order_by(SpeedRecord.timestamp.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


def get_stats(session: Session, start: Optional[datetime] = None, end: Optional[datetime] = None):
    query = session.query(SpeedRecord)
    if start:
        query = query.filter(SpeedRecord.timestamp >= _as_utc_naive(start))
    if end:
        query = query.filter(SpeedRecord.timestamp <= _as_utc_naive(end))

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
