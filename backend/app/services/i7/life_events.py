# backend.app.services.i7.life_events
"""R-021 / M1: the user's life-event TIMELINE (I7 temporal memory).

No second canonical event table (see ``timeline.py``): life events live in ``user_events`` as completed, source-tagged rows
whose ``description`` carries a bounded JSON marker (kind, subject, precision). Only a short, sanitized summary (the
``title``) is stored — never the raw chat text. Everything is consent-gated (I6 memory.read / memory.write /
memory.forget) and ownership-scoped. Reads fail open to an empty list; writes return None when not permitted.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models

LIFE_MARK = "@@SEDI_LIFE@@"
MAX_TITLE = 140

KINDS = (
    "loss", "job_loss", "separation", "surgery", "accident", "diagnosis", "medication_change", "procedure",
    "medical_document", "move", "milestone", "other",
)
_DOMAIN_BY_KIND = {
    "loss": "family", "job_loss": "work", "separation": "family", "surgery": "medical", "accident": "medical",
    "diagnosis": "medical", "medication_change": "medical", "procedure": "medical", "medical_document": "medical",
    "move": "personal",
    "milestone": "personal", "other": "personal",
}
SUBJECTS = ("self", "mother", "father", "spouse", "child", "sibling", "relative", "friend", "other")
PRECISIONS = ("day", "month", "year", "approx")
SOURCES = ("conversation", "manual", "document", "caregiver", "system")

# Neutral, event-kind titles (used when no specific summary is known). Never contain private details.
KIND_LABELS: dict[str, dict[str, str]] = {
    "loss": {"fa": "از دست دادن یکی از عزیزان", "en": "losing someone dear", "ar": "فقدان عزيز"},
    "job_loss": {"fa": "از دست دادن کار", "en": "losing a job", "ar": "فقدان العمل"},
    "separation": {"fa": "جدایی/طلاق", "en": "a separation or divorce", "ar": "انفصال أو طلاق"},
    "surgery": {"fa": "عمل جراحی", "en": "surgery", "ar": "عملية جراحية"},
    "accident": {"fa": "تصادف", "en": "an accident", "ar": "حادث"},
    "diagnosis": {"fa": "تشخیص یک بیماری", "en": "a diagnosis", "ar": "تشخيص مرض"},
    "medication_change": {"fa": "تغییر در دارو", "en": "a change in medication", "ar": "تغيير في الدواء"},
    "procedure": {"fa": "یک اقدام درمانی", "en": "a medical procedure", "ar": "إجراء طبي"},
    "medical_document": {"fa": "یک مدرک پزشکی", "en": "a medical document", "ar": "وثيقة طبية"},
    "move": {"fa": "نقل‌مکان", "en": "moving", "ar": "انتقال"},
    "milestone": {"fa": "یک اتفاق مهم زندگی", "en": "a life milestone", "ar": "حدث مهم في الحياة"},
    "other": {"fa": "یک اتفاق مهم", "en": "something important", "ar": "حدث مهم"},
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _lang_of(db: Session, user_id: int) -> str:
    try:
        row = db.query(models.User.preferred_language).filter(models.User.id == user_id).first()
        raw = ((row[0] if row else None) or "fa").strip().lower().split("-")[0]
        return raw if raw in ("fa", "en", "ar") else "en"
    except Exception:
        return "fa"


def kind_label(kind: str, lang: str) -> str:
    return KIND_LABELS.get(kind, KIND_LABELS["other"]).get(lang) or KIND_LABELS["other"]["en"]


def _pack(kind: str, subject: str, precision: str, evidence: Optional[str]) -> str:
    meta = {"kind": kind, "subject": subject, "precision": precision}
    if evidence:
        meta["evidence"] = " ".join(str(evidence).split())[:200]
    return LIFE_MARK + json.dumps(meta, ensure_ascii=False, separators=(",", ":"))


def parse_life_meta(description: Optional[str]) -> Optional[dict[str, Any]]:
    if not description or not description.startswith(LIFE_MARK):
        return None
    try:
        data = json.loads(description[len(LIFE_MARK):])
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def is_life_event(row: models.UserEvent) -> bool:
    return parse_life_meta(getattr(row, "description", None)) is not None


def _as_dict(row: models.UserEvent) -> dict[str, Any]:
    meta = parse_life_meta(row.description) or {}
    return {
        "id": int(row.id),
        "kind": meta.get("kind", "other"),
        "subject": meta.get("subject", "other"),
        "precision": meta.get("precision", "approx"),
        "title": row.title,
        "occurred_at": row.starts_at.isoformat() if row.starts_at else None,
        "source": row.source,
        "status": row.status,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _has(db: Session, user_id: int, perm: str) -> bool:
    from backend.app.services.i6.consent_service import has_permission

    try:
        return bool(has_permission(db, user_id, perm))
    except Exception:
        return False


def record_life_event(
    db: Session,
    user_id: int,
    *,
    kind: str,
    summary: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
    precision: str = "approx",
    subject: str = "other",
    source: str = "conversation",
    evidence: Optional[str] = None,
    commit: bool = True,
) -> Optional[dict[str, Any]]:
    """Add one event to the timeline; ``None`` when memory.write is not granted or the input is invalid. Idempotent: the
    same kind+subject within 7 days returns the existing event (no duplicates from repeated mentions)."""
    from backend.app.services.i6.consent_service import PERM_WRITE

    kind = kind if kind in KINDS else "other"
    subject = subject if subject in SUBJECTS else "other"
    precision = precision if precision in PRECISIONS else "approx"
    source = source if source in SOURCES else "conversation"
    if not _has(db, user_id, PERM_WRITE):
        return None
    when = occurred_at.replace(tzinfo=None) if occurred_at is not None and occurred_at.tzinfo else (occurred_at or _utcnow())
    title = " ".join((summary or kind_label(kind, _lang_of(db, user_id))).split())[:MAX_TITLE]
    recent = (
        db.query(models.UserEvent)
        .filter(
            models.UserEvent.user_id == user_id,
            models.UserEvent.status == "completed",
            models.UserEvent.event_type == "important_day",
            models.UserEvent.starts_at >= when - timedelta(days=7),
            models.UserEvent.starts_at <= when + timedelta(days=7),
        )
        .all()
    )
    for ev in recent:
        meta = parse_life_meta(ev.description)
        if not meta or meta.get("kind") != kind:
            continue
        old_subject = meta.get("subject", "other")
        if old_subject == subject or "other" in (old_subject, subject):
            if old_subject == "other" and subject != "other":  # a later, richer mention completes the event
                ev.description = _pack(kind, subject, meta.get("precision", precision), meta.get("evidence") or evidence)
                if summary and summary.strip():
                    ev.title = title
                ev.updated_at = _utcnow()
                if commit:
                    db.commit()
                    db.refresh(ev)
            return _as_dict(ev)
    now = _utcnow()
    row = models.UserEvent(
        user_id=user_id,
        title=title,
        description=_pack(kind, subject, precision, evidence),
        event_domain=_DOMAIN_BY_KIND.get(kind, "personal"),
        event_type="important_day",
        starts_at=when,
        status="completed",
        importance="high" if kind in ("loss", "surgery", "accident", "diagnosis") else "normal",
        reminder_enabled=False,
        source=source,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return _as_dict(row)


def list_life_events(db: Session, user_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    """Newest first. [] without memory.read (fail-open for callers, fail-closed for data)."""
    from backend.app.services.i6.consent_service import PERM_READ

    if not _has(db, user_id, PERM_READ):
        return []
    try:
        rows = (
            db.query(models.UserEvent)
            .filter(
                models.UserEvent.user_id == user_id,
                models.UserEvent.event_type == "important_day",
                models.UserEvent.status == "completed",
                models.UserEvent.description.like(f"{LIFE_MARK}%"),
            )
            .order_by(models.UserEvent.starts_at.desc())
            .limit(max(1, min(int(limit), 200)))
            .all()
        )
    except Exception:
        return []
    return [_as_dict(r) for r in rows if is_life_event(r)]


def _owned(db: Session, user_id: int, event_id: int) -> Optional[models.UserEvent]:
    row = (
        db.query(models.UserEvent)
        .filter(models.UserEvent.id == event_id, models.UserEvent.user_id == user_id)
        .first()
    )
    return row if row is not None and is_life_event(row) else None


def update_life_event(
    db: Session,
    user_id: int,
    event_id: int,
    *,
    summary: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
    kind: Optional[str] = None,
    subject: Optional[str] = None,
    precision: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """The user's own correction (source becomes 'manual'). None when not found / not permitted."""
    from backend.app.services.i6.consent_service import PERM_WRITE

    if not _has(db, user_id, PERM_WRITE):
        return None
    row = _owned(db, user_id, event_id)
    if row is None:
        return None
    meta = parse_life_meta(row.description) or {}
    if kind in KINDS:
        meta["kind"] = kind
        row.event_domain = _DOMAIN_BY_KIND.get(kind, "personal")
    if subject in SUBJECTS:
        meta["subject"] = subject
    if precision in PRECISIONS:
        meta["precision"] = precision
    row.description = _pack(meta.get("kind", "other"), meta.get("subject", "other"), meta.get("precision", "approx"), meta.get("evidence"))
    if summary is not None and summary.strip():
        row.title = " ".join(summary.split())[:MAX_TITLE]
    if occurred_at is not None:
        row.starts_at = occurred_at.replace(tzinfo=None) if occurred_at.tzinfo else occurred_at
    row.source = "manual"
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return _as_dict(row)


def delete_life_event(db: Session, user_id: int, event_id: int) -> bool:
    """Soft delete (status=cancelled, valid_to set) — hidden from every read. Needs memory.forget."""
    from backend.app.services.i6.consent_service import PERM_FORGET

    if not _has(db, user_id, PERM_FORGET):
        return False
    row = _owned(db, user_id, event_id)
    if row is None:
        return False
    row.status = "cancelled"
    row.valid_to = _utcnow()
    row.updated_at = _utcnow()
    db.commit()
    return True
