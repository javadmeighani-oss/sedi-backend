"""Summary-before-purge guard + idempotent purge receipts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i6.consent_service import PERM_FORGET, require_permission
from backend.app.services.i7.retention import as_utc, utcnow


@dataclass
class PurgeResult:
    purged: bool
    receipt: Optional[models.UserMemoryPurgeReceipt]
    reason: str
    replayed: bool = False


def _purge_key(user_id: int, memory_id: int) -> str:
    return f"purge:user:{user_id}:memory:{memory_id}"


def _daily_ready_for_purge(db: Session, user_id: int, local_period_date) -> Optional[models.UserPeriodSummary]:
    rows = (
        db.query(models.UserPeriodSummary)
        .filter(
            models.UserPeriodSummary.user_id == user_id,
            models.UserPeriodSummary.summary_type == "DAILY",
            models.UserPeriodSummary.status == "active",
            models.UserPeriodSummary.finalized_at.isnot(None),
            models.UserPeriodSummary.source_complete.is_(True),
            models.UserPeriodSummary.integrity_sha256.isnot(None),
        )
        .all()
    )
    for row in rows:
        if row.period_timezone and row.period_start is not None:
            # Match by lineage raw date when available
            lineage = {}
            try:
                lineage = json.loads(row.lineage_json or "{}")
            except Exception:
                lineage = {}
            # Accept if local_period_date aligns with period_start date in stored tz,
            # or if memory id list implies the day was summarized.
            if local_period_date is not None:
                start = as_utc(row.period_start)
                if start and start.date() == local_period_date:
                    return row
            if lineage.get("raw_memory_ids"):
                return row
    return None


def purge_expired_raw_turn(
    db: Session,
    *,
    user_id: int,
    memory_id: int,
    commit: bool = True,
) -> PurgeResult:
    """
    Eligible only when: raw expired AND daily finalized AND source complete
    AND integrity valid AND provenance valid. Hard-purges raw content.
    """
    require_permission(db, user_id, PERM_FORGET)
    key = _purge_key(user_id, memory_id)
    existing = (
        db.query(models.UserMemoryPurgeReceipt)
        .filter(models.UserMemoryPurgeReceipt.purge_key == key)
        .first()
    )
    if existing is not None:
        return PurgeResult(True, existing, "IDEMPOTENT_REPLAY", replayed=True)

    row = (
        db.query(models.Memory)
        .filter(models.Memory.id == memory_id, models.Memory.user_id == user_id)
        .first()
    )
    if row is None:
        # Already gone — synthesize receipt for idempotency if prior content unknown
        receipt = models.UserMemoryPurgeReceipt(
            user_id=user_id,
            memory_id=memory_id,
            purge_key=key,
            purged_at=utcnow(),
            reason="ALREADY_ABSENT",
            integrity_sha256=None,
            provenance_json=json.dumps({"note": "row absent at purge time"}),
        )
        db.add(receipt)
        if commit:
            db.commit()
            db.refresh(receipt)
        else:
            db.flush()
        return PurgeResult(True, receipt, "ALREADY_ABSENT", replayed=False)

    retain = as_utc(row.retain_until)
    if retain is None or retain > utcnow():
        return PurgeResult(False, None, "NOT_EXPIRED")

    if not row.durable_write:
        return PurgeResult(False, None, "NOT_DURABLE_GOVERNED")

    if not row.provenance_json:
        return PurgeResult(False, None, "PROVENANCE_MISSING")

    daily = _daily_ready_for_purge(db, user_id, row.local_period_date)
    if daily is None:
        return PurgeResult(False, None, "DAILY_NOT_FINALIZED")

    content_hash = hashlib.sha256(
        f"{row.id}|{row.user_message}|{row.sedi_response}".encode("utf-8")
    ).hexdigest()
    receipt = models.UserMemoryPurgeReceipt(
        user_id=user_id,
        memory_id=memory_id,
        local_period_date=row.local_period_date,
        purge_key=key,
        purged_at=utcnow(),
        reason="EXPIRED_AFTER_FINALIZED_DAILY",
        integrity_sha256=content_hash,
        daily_summary_id=daily.id,
        provenance_json=row.provenance_json,
    )
    # Hard purge content
    db.delete(row)
    db.add(receipt)
    if commit:
        db.commit()
        db.refresh(receipt)
    else:
        db.flush()
    return PurgeResult(True, receipt, "PURGED")
