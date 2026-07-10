"""Caregiver notification preference resolver — no external delivery."""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app import models

NOTIFICATION_TYPE_TO_PREF: Dict[str, str] = {
    "daily_health_status": "notify_daily_status",
    "care_summary": "notify_care_summary",
    "important_vital_alert": "notify_vital_alerts",
    "emergency_escalation": "notify_emergency",
}


def caregiver_eligible_for_notification(
    caregiver: models.UserCaregiver,
    notification_type: str,
) -> bool:
    if not caregiver.is_active:
        return False
    pref_field = NOTIFICATION_TYPE_TO_PREF.get(notification_type)
    if pref_field is None:
        return False
    return bool(getattr(caregiver, pref_field, False))


def resolve_eligible_caregivers(
    db: Session,
    owner_user_id: int,
    notification_type: str,
) -> List[models.UserCaregiver]:
    rows = (
        db.query(models.UserCaregiver)
        .filter(
            models.UserCaregiver.owner_user_id == owner_user_id,
            models.UserCaregiver.is_active == True,  # noqa: E712
        )
        .order_by(models.UserCaregiver.priority.asc(), models.UserCaregiver.id.asc())
        .all()
    )
    return [r for r in rows if caregiver_eligible_for_notification(r, notification_type)]


def build_dedupe_key(
    owner_user_id: int,
    caregiver_id: int,
    notification_type: str,
    source_entity_type: Optional[str],
    source_entity_id: Optional[int],
    bucket: str,
) -> str:
    return (
        f"caregiver_intent:{owner_user_id}:{caregiver_id}:{notification_type}:"
        f"{source_entity_type or 'none'}:{source_entity_id or 0}:{bucket}"
    )
