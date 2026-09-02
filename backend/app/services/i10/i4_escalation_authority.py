"""I10-B16 — bind authoritative Section-10 escalation records to HealthSubject (no I4 re-decision)."""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models

AUTHORITATIVE_ESCALATION_STATE = "caregiver_escalation_ready"
TERMINAL_NON_ESCALATION_STATES = frozenset({"resolved", "cancelled", "expired", "failed"})


def is_authoritative_care_safety_escalation(record: models.EmergencyEscalationRecord) -> bool:
    """True only when Section-10 escalation is ready with valid I4 provenance."""
    from backend.app.services.section10.i4_escalation_provenance import (
        record_has_valid_i4_provenance,
    )

    if record.current_state != AUTHORITATIVE_ESCALATION_STATE:
        return False
    if record.current_state in TERMINAL_NON_ESCALATION_STATES:
        return False
    if record.resolved_at is not None:
        return False
    if not record_has_valid_i4_provenance(record):
        return False
    return True


def _metadata_dict(record: models.EmergencyEscalationRecord) -> dict:
    raw = record.metadata_json
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def resolve_escalation_health_subject_id(
    db: Session,
    record: models.EmergencyEscalationRecord,
) -> Optional[int]:
    """Resolve target HealthSubject without inferring risk from raw measurements."""
    meta = _metadata_dict(record)
    hs_raw = meta.get("health_subject_id")
    if hs_raw is not None:
        try:
            hs_id = int(hs_raw)
        except (TypeError, ValueError):
            hs_id = None
        if hs_id is not None:
            subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == hs_id).first()
            if subject is not None and subject.status == "active":
                return hs_id

    if record.care_episode_id is not None:
        link = (
            db.query(models.CareEpisodeLink)
            .filter(
                models.CareEpisodeLink.episode_id == record.care_episode_id,
                models.CareEpisodeLink.link_type == "health_subject",
                models.CareEpisodeLink.link_table == "health_subjects",
            )
            .first()
        )
        if link is not None:
            try:
                hs_id = int(link.link_id)
            except (TypeError, ValueError):
                hs_id = None
            if hs_id is not None:
                subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == hs_id).first()
                if subject is not None and subject.status == "active":
                    return hs_id

    subject = (
        db.query(models.HealthSubject)
        .filter(
            models.HealthSubject.linked_user_id == record.owner_user_id,
            models.HealthSubject.status == "active",
        )
        .order_by(models.HealthSubject.id.asc())
        .first()
    )
    return subject.id if subject is not None else None


def list_authoritative_escalations_for_subject(
    db: Session,
    *,
    health_subject_id: int,
) -> list[models.EmergencyEscalationRecord]:
    rows = (
        db.query(models.EmergencyEscalationRecord)
        .filter(models.EmergencyEscalationRecord.current_state == AUTHORITATIVE_ESCALATION_STATE)
        .order_by(models.EmergencyEscalationRecord.id.asc())
        .all()
    )
    matched: list[models.EmergencyEscalationRecord] = []
    for row in rows:
        if not is_authoritative_care_safety_escalation(row):
            continue
        bound = resolve_escalation_health_subject_id(db, row)
        if bound == health_subject_id:
            matched.append(row)
    return matched
