"""I10-B15 managed-subject binding for persisted I8OperationalPlanAction."""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models

HEALTH_SUBJECT_REF_TYPE = "health_subject"


def build_health_subject_context_refs_json(health_subject_id: int) -> str:
    payload = [{"ref_type": HEALTH_SUBJECT_REF_TYPE, "ref_id": int(health_subject_id)}]
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def parse_action_context_refs(action: models.I8OperationalPlanAction) -> list[dict[str, Any]]:
    raw = action.context_refs_json
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(loaded, list):
        return []
    return [entry for entry in loaded if isinstance(entry, dict)]


def resolve_action_health_subject_id(
    db: Session,
    action: models.I8OperationalPlanAction,
) -> Optional[int]:
    """Return HealthSubject id from governed context_refs when present."""
    for ref in parse_action_context_refs(action):
        if ref.get("ref_type") != HEALTH_SUBJECT_REF_TYPE:
            continue
        ref_id = ref.get("ref_id")
        if ref_id is None:
            continue
        try:
            subject_id = int(ref_id)
        except (TypeError, ValueError):
            continue
        subject = (
            db.query(models.HealthSubject)
            .filter(
                models.HealthSubject.id == subject_id,
                models.HealthSubject.status == "active",
            )
            .first()
        )
        if subject is not None:
            return int(subject.id)
    return None


def is_managed_health_subject(db: Session, health_subject_id: int) -> bool:
    subject = (
        db.query(models.HealthSubject)
        .filter(
            models.HealthSubject.id == health_subject_id,
            models.HealthSubject.status == "active",
        )
        .first()
    )
    if subject is None:
        return False
    return subject.linked_user_id is None
