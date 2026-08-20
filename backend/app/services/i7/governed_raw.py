"""Governed durable raw conversation writes for I7 Wave-2."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.gate4.policy_prefs_bridge import (
    get_local_now,
    resolve_validated_user_timezone,
)
from backend.app.services.i6.consent_service import PERM_WRITE, has_permission, _active_consent
from backend.app.services.i7.period_summaries import resolve_week_start
from backend.app.services.i7.retention import RAW_VISIBLE_DAYS

GENERATOR = "i7-wave2-governed-raw-v1"


@dataclass
class GovernedRawResult:
    durable: bool
    memory: Optional[models.Memory]
    reason: str
    replayed: bool = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_idempotency_key(
    *,
    user_id: int,
    user_message: str,
    sedi_response: str,
    client_key: Optional[str] = None,
) -> str:
    if client_key:
        return f"client:{client_key}"[:128]
    digest = hashlib.sha256(
        f"{user_id}\n{user_message}\n{sedi_response}".encode("utf-8")
    ).hexdigest()
    return f"auto:{digest}"[:128]


def _local_period_identity(
    db: Session, user_id: int, created_at: datetime
) -> tuple[str, int, date]:
    tz_name = resolve_validated_user_timezone(db, user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    week_start = resolve_week_start(getattr(user, "preferred_language", None) if user else None)
    local_dt = get_local_now(created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc), tz_name)
    return tz_name, week_start, local_dt.date()


def try_durable_raw_write(
    db: Session,
    *,
    user_id: int,
    user_message: str,
    sedi_response: str,
    language: str = "en",
    actor_user_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    provenance: Optional[dict[str, Any]] = None,
    commit: bool = True,
) -> GovernedRawResult:
    """
    Durable raw write requires consent + provenance + idempotency + trusted auth identity.
    Without consent: no durable write and no I7 derivation from this turn.
    """
    if actor_user_id is not None and int(actor_user_id) != int(user_id):
        return GovernedRawResult(False, None, "AUTH_IDENTITY_MISMATCH")

    key = build_idempotency_key(
        user_id=user_id,
        user_message=user_message,
        sedi_response=sedi_response,
        client_key=idempotency_key,
    )
    existing = (
        db.query(models.Memory)
        .filter(models.Memory.user_id == user_id, models.Memory.idempotency_key == key)
        .first()
    )
    if existing is not None:
        return GovernedRawResult(True, existing, "IDEMPOTENT_REPLAY", replayed=True)

    if not has_permission(db, user_id, PERM_WRITE):
        return GovernedRawResult(False, None, "NO_CONSENT")

    consent = _active_consent(db, user_id=user_id)
    if consent is None:
        return GovernedRawResult(False, None, "NO_CONSENT")

    now = _utcnow()
    tz_name, week_start, local_day = _local_period_identity(db, user_id, now)
    prov = provenance or {
        "source": "interact.chat",
        "generator": GENERATOR,
        "actor_user_id": user_id,
        "written_at": now.isoformat(),
    }
    row = models.Memory(
        user_id=user_id,
        user_message=user_message,
        sedi_response=sedi_response,
        language=language,
        created_at=now.replace(tzinfo=None),
        retain_until=now + timedelta(days=RAW_VISIBLE_DAYS),
        consent_id=consent.id,
        provenance_json=json.dumps(prov, sort_keys=True),
        idempotency_key=key,
        period_timezone=tz_name,
        period_week_start=week_start,
        local_period_date=local_day,
        durable_write=True,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return GovernedRawResult(True, row, "DURABLE_WRITTEN")
