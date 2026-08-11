"""Connector run observability — no secrets / no prohibited raw content."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models


def start_run(
    db: Session,
    *,
    connector_key: str,
    request_type: str,
    cursor_snapshot: Optional[str] = None,
) -> models.I5ConnectorRunEvent:
    row = models.I5ConnectorRunEvent(
        connector_key=connector_key,
        request_type=request_type,
        result="STARTED",
        cursor_snapshot=cursor_snapshot,
    )
    db.add(row)
    db.flush()
    return row


def finish_run(
    db: Session,
    row: models.I5ConnectorRunEvent,
    *,
    result: str,
    http_status_class: Optional[str] = None,
    records_discovered: int = 0,
    records_processed: int = 0,
    records_blocked_by_rights: int = 0,
    records_changed: int = 0,
    retractions_detected: int = 0,
    retry_count: int = 0,
    error_summary: Optional[str] = None,
) -> models.I5ConnectorRunEvent:
    row.result = result
    row.finished_at = datetime.utcnow()
    row.http_status_class = http_status_class
    row.records_discovered = records_discovered
    row.records_processed = records_processed
    row.records_blocked_by_rights = records_blocked_by_rights
    row.records_changed = records_changed
    row.retractions_detected = retractions_detected
    row.retry_count = retry_count
    if error_summary:
        # Never log secrets
        lowered = error_summary.lower()
        for secret_token in ("api_key=", "authorization:", "password=", "secret="):
            if secret_token in lowered:
                error_summary = "REDACTED_SECRET_IN_ERROR"
                break
        row.error_summary = error_summary[:2000]
    db.flush()
    return row
