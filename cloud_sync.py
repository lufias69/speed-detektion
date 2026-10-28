import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

import requests

from config import Config
from db import SpeedRecord, get_session, get_unsynced_records, mark_record_synced

logger = logging.getLogger("speedmonitor")


class FirestoreSync:
    """Sync local SQLite records to Firebase Firestore via REST API."""

    def __init__(self, config: Config):
        self.config = config
        self._refresh_from_config()

    def _refresh_from_config(self):
        self.base_url = f"https://firestore.googleapis.com/v1/projects/{self.config.firebase_project_id}/databases/(default)/documents/{self.config.firebase_collection}"
        self.api_key = self.config.firebase_api_key
        self.network = self.config.network_name or "unknown"
        self.location = self.config.location or "unknown"

    def enabled(self) -> bool:
        self._refresh_from_config()
        return bool(self.config.firebase_api_key and self.config.firebase_project_id)

    def _record_to_doc(self, record: SpeedRecord) -> dict:
        ts = record.timestamp
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        iso_ts = ts.isoformat().replace("+00:00", "Z") if ts else None
        return {
            "fields": {
                "timestamp": {"timestampValue": iso_ts},
                "ssid": {"stringValue": record.ssid or ""},
                "connection_type": {"stringValue": record.connection_type or ""},
                "adapter": {"stringValue": record.adapter or ""},
                "status": {"stringValue": record.status},
                "ping_ms": {"doubleValue": record.ping_ms} if record.ping_ms is not None else {"nullValue": None},
                "ping_ttl": {"integerValue": str(record.ping_ttl)} if record.ping_ttl is not None else {"nullValue": None},
                "packet_size": {"integerValue": str(record.packet_size)} if record.packet_size is not None else {"nullValue": None},
                "ping_min_ms": {"doubleValue": record.ping_min_ms} if record.ping_min_ms is not None else {"nullValue": None},
                "ping_max_ms": {"doubleValue": record.ping_max_ms} if record.ping_max_ms is not None else {"nullValue": None},
                "ping_avg_ms": {"doubleValue": record.ping_avg_ms} if record.ping_avg_ms is not None else {"nullValue": None},
                "packet_loss_percent": {"doubleValue": record.packet_loss_percent} if record.packet_loss_percent is not None else {"nullValue": None},
                "download_mbps": {"doubleValue": record.download_mbps} if record.download_mbps is not None else {"nullValue": None},
                "upload_mbps": {"doubleValue": record.upload_mbps} if record.upload_mbps is not None else {"nullValue": None},
                "error_message": {"stringValue": record.error_message or ""},
                "network_name": {"stringValue": self.network},
                "location": {"stringValue": self.location},
            }
        }

    def _extract_doc_id(self, response: dict) -> Optional[str]:
        name = response.get("name", "")
        if "/" in name:
            return name.split("/")[-1]
        return name or None

    def push_record(self, record: SpeedRecord) -> Optional[str]:
        # Firestore REST public API requires the Web API key in the query string.
        # Avoid logging the URL; log only sanitized information on failure.
        url = f"{self.base_url}?key={self.api_key}"
        try:
            resp = requests.post(url, json=self._record_to_doc(record), timeout=30)
            resp.raise_for_status()
            return self._extract_doc_id(resp.json())
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "cloud sync failed for record %s: %s (status=%s)",
                record.id,
                type(exc).__name__,
                getattr(exc.response, "status_code", None),
            )
            return None
        except Exception as exc:
            logger.warning("cloud sync failed for record %s: %s", record.id, type(exc).__name__)
            return None

    def push_batch(self, records: List[SpeedRecord]) -> int:
        synced = 0
        for record in records:
            doc_id = self.push_record(record)
            if doc_id:
                session = None
                try:
                    # each mark needs its own session because requests may run in another thread
                    from db import get_engine
                    session = get_session(get_engine(self.config.database_path))
                    mark_record_synced(session, record, doc_id)
                    synced += 1
                except Exception as exc:
                    logger.warning("failed to mark record %s synced: %s", record.id, type(exc).__name__)
                finally:
                    if session:
                        session.close()
            else:
                break  # stop at first failure; retry next cycle
            time.sleep(0.2)
        return synced

    def run_once(self, limit: int = 50) -> int:
        if not self.enabled():
            return 0
        session = get_session(__import__("db").get_engine(self.config.database_path))
        try:
            records = get_unsynced_records(session, limit=limit)
        finally:
            session.close()
        if not records:
            return 0
        return self.push_batch(records)
