"""Medication per-dose adherence occurrence — truthful state without medical inference."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from backend.app import models


class MedicationAdherenceState(str, Enum):
    DUE = "DUE"
    CONFIRMED_TAKEN = "CONFIRMED_TAKEN"
    UNKNOWN = "UNKNOWN"
    MISSED = "MISSED"


class MedicationAdherenceError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_medication_occurrence_key(
    *,
    user_id: int,
    user_medication_id: int,
    schedule_id: Optional[int],
    scheduled_for: datetime,
    schedule_time: Optional[str],
) -> str:
    date_str = scheduled_for.strftime("%Y-%m-%d")
    if schedule_time:
        return (
            f"i10:med:dose:{user_id}:{user_medication_id}:{schedule_id or 0}:"
            f"{date_str}:{schedule_time}"
        )
    hour_bucket = (scheduled_for.hour // 8) * 8
    return f"i10:med:dose:{user_id}:{user_medication_id}:legacy:{date_str}:{hour_bucket:02d}"


def get_or_create_dose_occurrence(
    db: Session,
    *,
    user_id: int,
    user_medication_id: int,
    schedule_id: Optional[int],
    scheduled_for: datetime,
    occurrence_key: str,
    commit: bool = True,
) -> Tuple[models.MedicationDoseOccurrence, bool]:
    """Return (occurrence, created). Idempotent on occurrence_key."""
    existing = (
        db.query(models.MedicationDoseOccurrence)
        .filter(
            models.MedicationDoseOccurrence.user_id == user_id,
            models.MedicationDoseOccurrence.occurrence_key == occurrence_key,
        )
        .first()
    )
    if existing is not None:
        return existing, False
    when = scheduled_for
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    row = models.MedicationDoseOccurrence(
        user_id=user_id,
        user_medication_id=user_medication_id,
        schedule_id=schedule_id,
        scheduled_for=when,
        occurrence_key=occurrence_key,
        state=MedicationAdherenceState.DUE.value,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row, True


def link_occurrence_notification(
    db: Session,
    occurrence: models.MedicationDoseOccurrence,
    notification_id: int,
    *,
    commit: bool = True,
) -> None:
    occurrence.source_notification_id = notification_id
    occurrence.updated_at = _utc_now().replace(tzinfo=None)
    if commit:
        db.commit()
        db.refresh(occurrence)
    else:
        db.flush()


def occurrence_blocks_reminder(occurrence: models.MedicationDoseOccurrence) -> bool:
    """True when a reminder must not be sent again for this occurrence."""
    if occurrence.state == MedicationAdherenceState.CONFIRMED_TAKEN.value:
        return True
    return occurrence.source_notification_id is not None


def confirm_dose_taken_by_notification(
    db: Session,
    *,
    user_id: int,
    notification_id: int,
    confirmation_source: str = "USER_EXPLICIT",
    commit: bool = True,
) -> models.MedicationDoseOccurrence:
    occurrence = (
        db.query(models.MedicationDoseOccurrence)
        .filter(
            models.MedicationDoseOccurrence.source_notification_id == notification_id,
            models.MedicationDoseOccurrence.user_id == user_id,
        )
        .first()
    )
    if occurrence is None:
        raise MedicationAdherenceError("MEDICATION_OCCURRENCE_NOT_FOUND")
    if occurrence.state == MedicationAdherenceState.CONFIRMED_TAKEN.value:
        return occurrence
    now = _utc_now()
    occurrence.state = MedicationAdherenceState.CONFIRMED_TAKEN.value
    occurrence.confirmed_at = now
    occurrence.confirmation_source = confirmation_source
    occurrence.updated_at = now.replace(tzinfo=None)
    if commit:
        db.commit()
        db.refresh(occurrence)
    else:
        db.flush()
    return occurrence


def mark_occurrence_unknown_if_due_elapsed(
    db: Session,
    occurrence: models.MedicationDoseOccurrence,
    *,
    commit: bool = False,
) -> None:
    """Optional helper — B09 does not auto-call; MISSED authority absent."""
    if occurrence.state != MedicationAdherenceState.DUE.value:
        return
    occurrence.state = MedicationAdherenceState.UNKNOWN.value
    occurrence.updated_at = _utc_now().replace(tzinfo=None)
    if commit:
        db.commit()
