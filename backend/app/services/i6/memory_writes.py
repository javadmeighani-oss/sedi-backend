"""I6 canonical memory writes — consent-gated, isolated, idempotent, no schema change."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i6.consent_service import (
    PERM_FORGET,
    PERM_READ,
    PERM_WRITE,
    ConsentDenied,
    require_permission,
)
from backend.app.services.interaction.memory_governance import is_poison_candidate
from backend.app.services.memory.memory_contract import MemoryContract

TEMPORARY_MAX_HOURS = 72
UNSUPPORTED_MEDICAL_INFERENCE = frozenset({"diagnosis", "dose", "prescription", "treatment_plan"})


class MemoryWriteError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _idempotency_key(user_id: int, domain: str, key: str, value: Any) -> str:
    payload = json.dumps({"u": user_id, "d": domain, "k": key, "v": value}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _active_fact(db: Session, user_id: int, domain: str, key: str) -> Optional[models.UserMemoryFact]:
    return (
        db.query(models.UserMemoryFact)
        .filter(
            models.UserMemoryFact.user_id == user_id,
            models.UserMemoryFact.domain == domain,
            models.UserMemoryFact.key == key,
            models.UserMemoryFact.fact_status == "active",
            models.UserMemoryFact.soft_invalidated_at.is_(None),
        )
        .first()
    )


def _finish(db: Session, commit: bool) -> None:
    if commit:
        db.commit()
    else:
        db.flush()


def _invalidate_i7(db: Session, user_id: int, *, reason: str, commit: bool) -> None:
    from backend.app.services.i7.derived_invalidation import invalidate_derived_memory_state

    invalidate_derived_memory_state(db, user_id, reason=reason, commit=commit)


def write_fact(
    db: Session,
    user_id: int,
    domain: str,
    key: str,
    value: Any,
    *,
    durable: bool = True,
    provenance_class: str = "USER_STATED",
    source: str = "manual",
    sensitivity_class: str = "standard",
    valid_until: Optional[datetime] = None,
    commit: bool = True,
) -> models.UserMemoryFact:
    if any(tok in key.lower() for tok in UNSUPPORTED_MEDICAL_INFERENCE):
        raise MemoryWriteError("UNSUPPORTED_MEDICAL_INFERENCE")
    ok, err = MemoryContract.validate_fact(domain, key)
    if not ok:
        raise MemoryWriteError(err or "INVALID_FACT")
    consent = require_permission(db, user_id, PERM_WRITE)
    blob = json.dumps(value, ensure_ascii=False, default=str)
    if not isinstance(value, (int, float, bool)) and is_poison_candidate(blob):
        raise MemoryWriteError("POISON_REJECTED")
    now = _utcnow()
    existing = _active_fact(db, user_id, domain, key)
    if existing is not None and existing.value_json == blob:
        existing.last_seen_at = now
        existing.updated_at = now
        _finish(db, commit)
        db.refresh(existing)
        return existing
    superseded = existing is not None
    if existing is not None:
        existing.fact_status = "superseded"
        existing.updated_at = now
        existing.soft_invalidated_at = now
        existing.invalidation_reason = "superseded_by_correction"
    if not durable and valid_until is None:
        from datetime import timedelta

        valid_until = now + timedelta(hours=TEMPORARY_MAX_HOURS)
    row = models.UserMemoryFact(
        user_id=user_id,
        domain=domain,
        key=key,
        value_json=blob,
        confidence=0.9 if provenance_class == "USER_STATED" else 0.6,
        source=source,
        last_seen_at=now,
        provenance=source,
        provenance_class=provenance_class,
        fact_status="active",
        consent_id=consent.id,
        sensitivity_class=sensitivity_class,
        human_readable_value=str(value)[:500],
        valid_from=now,
        valid_until=valid_until,
        supersedes_fact_id=existing.id if existing is not None else None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _finish(db, commit)
    db.refresh(row)
    if superseded:
        _invalidate_i7(db, user_id, reason="correction", commit=commit)
    return row


def correct_fact(
    db: Session,
    user_id: int,
    domain: str,
    key: str,
    value: Any,
    *,
    commit: bool = True,
) -> models.UserMemoryFact:
    return write_fact(
        db,
        user_id,
        domain,
        key,
        value,
        provenance_class="USER_CONFIRMED",
        source="correction",
        commit=commit,
    )


def delete_fact(
    db: Session,
    user_id: int,
    domain: str,
    key: str,
    *,
    reason: str = "user_deleted",
    commit: bool = True,
) -> bool:
    require_permission(db, user_id, PERM_FORGET)
    row = _active_fact(db, user_id, domain, key)
    if row is None:
        return False
    now = _utcnow()
    row.fact_status = "rejected"
    row.soft_invalidated_at = now
    row.invalidation_reason = reason
    row.valid_until = now
    row.updated_at = now
    _finish(db, commit)
    _invalidate_i7(db, user_id, reason=reason, commit=commit)
    return True


def forget_all(db: Session, user_id: int, *, commit: bool = True) -> int:
    require_permission(db, user_id, PERM_FORGET)
    now = _utcnow()
    rows = (
        db.query(models.UserMemoryFact)
        .filter(models.UserMemoryFact.user_id == user_id, models.UserMemoryFact.fact_status == "active")
        .all()
    )
    for row in rows:
        row.fact_status = "rejected"
        row.soft_invalidated_at = now
        row.invalidation_reason = "forget"
        row.valid_until = now
        row.updated_at = now
    _finish(db, commit)
    _invalidate_i7(db, user_id, reason="forget", commit=commit)
    return len(rows)


def list_facts(db: Session, user_id: int, domain: Optional[str] = None) -> list[models.UserMemoryFact]:
    require_permission(db, user_id, PERM_READ)
    now = _utcnow()
    q = db.query(models.UserMemoryFact).filter(
        models.UserMemoryFact.user_id == user_id,
        models.UserMemoryFact.fact_status == "active",
        models.UserMemoryFact.soft_invalidated_at.is_(None),
    )
    if domain:
        q = q.filter(models.UserMemoryFact.domain == domain)
    out = []
    for row in q.all():
        until = row.valid_until
        if until is not None:
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until <= now:
                row.fact_status = "expired"
                continue
        out.append(row)
    return out


def list_fact_history(
    db: Session, user_id: int, domain: str, key: str
) -> list[models.UserMemoryFact]:
    """Current + superseded/rejected rows. History is retained; active row is current truth."""
    require_permission(db, user_id, PERM_READ)
    return (
        db.query(models.UserMemoryFact)
        .filter(
            models.UserMemoryFact.user_id == user_id,
            models.UserMemoryFact.domain == domain,
            models.UserMemoryFact.key == key,
        )
        .order_by(models.UserMemoryFact.id.asc())
        .all()
    )


def export_memory_bundle(db: Session, user_id: int) -> dict[str, Any]:
    """Export preparation only. No new table. Caller owns delivery."""
    require_permission(db, user_id, PERM_READ)
    facts = (
        db.query(models.UserMemoryFact)
        .filter(models.UserMemoryFact.user_id == user_id)
        .order_by(models.UserMemoryFact.id.asc())
        .all()
    )
    return {
        "owner_user_id": user_id,
        "authority": "I6_FACTS_ARE_SOT",
        "export_is_not_diagnosis": True,
        "facts": [
            {
                "id": row.id,
                "domain": row.domain,
                "key": row.key,
                "value_json": row.value_json,
                "fact_status": row.fact_status,
                "valid_from": row.valid_from.isoformat() if row.valid_from else None,
                "valid_until": row.valid_until.isoformat() if row.valid_until else None,
                "supersedes_fact_id": row.supersedes_fact_id,
                "source": row.source,
            }
            for row in facts
        ],
    }


def assert_user_isolation(db: Session, user_id: int, fact_id: int) -> models.UserMemoryFact:
    row = db.query(models.UserMemoryFact).filter(models.UserMemoryFact.id == fact_id).first()
    if row is None or row.user_id != user_id:
        raise ConsentDenied("CROSS_USER_FORBIDDEN")
    return row
