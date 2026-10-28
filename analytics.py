from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo


@dataclass
class HourlyStatus:
    hour: int
    online_minutes: float = 0.0
    offline_minutes: float = 0.0
    online_count: int = 0
    offline_count: int = 0
    avg_ping_ms: Optional[float] = None
    avg_ttl: Optional[float] = None


@dataclass
class DailySummary:
    date: datetime
    day_name: str
    online_hours: float = 0.0
    offline_hours: float = 0.0
    uptime_percent: float = 0.0
    avg_ping_ms: Optional[float] = None
    avg_ttl: Optional[float] = None
    avg_packet_loss: Optional[float] = None
    hourly: List[HourlyStatus] = field(default_factory=list)
    online_times: List[str] = field(default_factory=list)
    offline_times: List[str] = field(default_factory=list)


def _localize(dt: datetime, tz_name: str) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(tz_name))


def _to_minutes(td: timedelta) -> float:
    return td.total_seconds() / 60.0


def analyze_daily(records: list, timezone_name: str) -> List[DailySummary]:
    """Group records by local date and calculate daily + hourly uptime stats."""
    tz = ZoneInfo(timezone_name)
    by_date: Dict[str, List] = defaultdict(list)

    for r in records:
        local_ts = _localize(r.timestamp, timezone_name)
        key = local_ts.strftime("%Y-%m-%d")
        by_date[key].append((local_ts, r))

    summaries = []
    for date_str in sorted(by_date.keys()):
        day_records = by_date[date_str]
        day_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)
        summary = DailySummary(
            date=day_dt,
            day_name=day_dt.strftime("%A"),
        )

        # Sort by time
        day_records.sort(key=lambda x: x[0])

        # Hourly buckets
        hourly_buckets: Dict[int, HourlyStatus] = {
            h: HourlyStatus(hour=h) for h in range(24)
        }

        pings = []
        ttls = []
        losses = []

        for i, (local_ts, rec) in enumerate(day_records):
            hour = local_ts.hour
            bucket = hourly_buckets[hour]

            next_ts = None
            if i + 1 < len(day_records):
                next_ts = day_records[i + 1][0]
            else:
                # Last record: assume state holds until next check interval or end of hour
                next_ts = local_ts + timedelta(minutes=1)

            duration = _to_minutes(next_ts - local_ts)
            if rec.status == "online":
                bucket.online_minutes += duration
                bucket.online_count += 1
                time_label = local_ts.strftime("%H:%M")
                summary.online_times.append(time_label)
            else:
                bucket.offline_minutes += duration
                bucket.offline_count += 1
                time_label = local_ts.strftime("%H:%M")
                summary.offline_times.append(time_label)

            if rec.ping_ms is not None:
                pings.append(rec.ping_ms)
            if rec.ping_ttl is not None:
                ttls.append(rec.ping_ttl)
            if rec.packet_loss_percent is not None:
                losses.append(rec.packet_loss_percent)

            if rec.ping_ms is not None:
                if bucket.avg_ping_ms is None:
                    bucket.avg_ping_ms = rec.ping_ms
                else:
                    bucket.avg_ping_ms = (bucket.avg_ping_ms * (bucket.online_count - 1) + rec.ping_ms) / bucket.online_count
            if rec.ping_ttl is not None:
                if bucket.avg_ttl is None:
                    bucket.avg_ttl = rec.ping_ttl
                else:
                    bucket.avg_ttl = (bucket.avg_ttl * (bucket.online_count - 1) + rec.ping_ttl) / bucket.online_count

        total_online = sum(b.online_minutes for b in hourly_buckets.values())
        total_offline = sum(b.offline_minutes for b in hourly_buckets.values())
        total = total_online + total_offline

        summary.online_hours = round(total_online / 60.0, 2)
        summary.offline_hours = round(total_offline / 60.0, 2)
        summary.uptime_percent = round(total_online / total * 100, 2) if total else 0.0
        summary.avg_ping_ms = round(sum(pings) / len(pings), 2) if pings else None
        summary.avg_ttl = round(sum(ttls) / len(ttls), 2) if ttls else None
        summary.avg_packet_loss = round(sum(losses) / len(losses), 2) if losses else None
        summary.hourly = [hourly_buckets[h] for h in range(24)]

        summaries.append(summary)

    return summaries
