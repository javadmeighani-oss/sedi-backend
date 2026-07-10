"""User medication CRUD and schedule management (Phase V1.1B)."""

from __future__ import annotations

import os
import re
from datetime import datetime, time
from typing import List, Optional, Tuple

import pytz
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from backend.app import models
from backend.app.schemas.medical import UserMedicationCreateIn, UserMedicationOut, UserMedicationUpdateIn

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
DEFAULT_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Tehran")


class DuplicateUserMedicationError(Exception):
    """User already has this medication assigned."""


class UserMedicationNotFoundError(Exception):
    """Assignment not found for user."""


def parse_hhmm(value: str) -> time:
    """Parse HH:MM to time; raise ValueError if invalid."""
    trimmed = value.strip()
    match = _TIME_RE.match(trimmed)
    if not match:
        raise ValueError(f"Invalid time format: {value!r} (expected HH:MM)")
    return time(int(match.group(1)), int(match.group(2)))


def format_time_of_day(t: time) -> str:
    return t.strftime("%H:%M")


def validate_timezone(tz_name: Optional[str]) -> str:
    """Return valid IANA timezone or default."""
    if not tz_name or not str(tz_name).strip():
        return DEFAULT_TIMEZONE
    name = str(tz_name).strip()
    try:
        pytz.timezone(name)
    except pytz.UnknownTimeZoneError as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc
    return name


def normalize_medication_name(name: str) -> str:
    return name.strip()


def find_or_create_medication(
    db: Session,
    name: str,
    generic_name: Optional[str] = None,
    dosage_form: Optional[str] = None,
) -> models.Medication:
    """Find global Medication by case-insensitive name or create catalog row."""
    normalized = normalize_medication_name(name)
    existing = (
        db.query(models.Medication)
        .filter(func.lower(models.Medication.name) == normalized.lower())
        .first()
    )
    if existing:
        return existing
    med = models.Medication(
        name=normalized,
        generic_name=generic_name.strip() if generic_name and generic_name.strip() else None,
        dosage_form=dosage_form.strip() if dosage_form and dosage_form.strip() else None,
        default_dosage=None,
    )
    db.add(med)
    db.flush()
    return med


def _replace_schedules(db: Session, um: models.UserMedication, reminder_times: List[str]) -> None:
    for row in list(um.schedules):
        db.delete(row)
    db.flush()
    seen: set[str] = set()
    for raw in reminder_times:
        t = parse_hhmm(raw)
        key = format_time_of_day(t)
        if key in seen:
            continue
        seen.add(key)
        db.add(
            models.UserMedicationSchedule(
                user_medication_id=um.id,
                time_of_day=t,
                days_of_week=None,
            )
        )


from backend.app.services.section10.medication_stock_service import stock_level_for_medication


def build_user_medication_out(um: models.UserMedication, med: models.Medication) -> dict:
    times = sorted(format_time_of_day(s.time_of_day) for s in (um.schedules or []))
    stock = stock_level_for_medication(um)
    return UserMedicationOut(
        id=um.id,
        medication_id=um.medication_id,
        name=med.name,
        generic_name=med.generic_name,
        dosage_form=med.dosage_form,
        user_dosage=um.user_dosage,
        instructions=um.instructions,
        reminder_enabled=um.reminder_enabled,
        timezone=um.timezone,
        reminder_times=times,
        interval_hours=um.interval_hours,
        remaining_quantity=um.remaining_quantity,
        quantity_unit=um.quantity_unit,
        refill_threshold=um.refill_threshold,
        last_refill_at=um.last_refill_at,
        estimated_end_at=um.estimated_end_at,
        stock_level=stock["stock_level"],
        created_at=um.created_at,
    ).model_dump()


def list_user_medications(db: Session, user_id: int) -> List[dict]:
    rows = (
        db.query(models.UserMedication)
        .options(joinedload(models.UserMedication.schedules), joinedload(models.UserMedication.medication))
        .filter(models.UserMedication.user_id == user_id)
        .order_by(models.UserMedication.id)
        .all()
    )
    return [build_user_medication_out(um, um.medication) for um in rows]


def create_user_medication(db: Session, user_id: int, body: UserMedicationCreateIn) -> dict:
    name = normalize_medication_name(body.name)
    if not name:
        raise ValueError("name must not be empty")

    med = find_or_create_medication(
        db,
        name=name,
        generic_name=body.generic_name,
        dosage_form=body.dosage_form,
    )

    existing = (
        db.query(models.UserMedication)
        .filter(
            models.UserMedication.user_id == user_id,
            models.UserMedication.medication_id == med.id,
        )
        .first()
    )
    if existing:
        raise DuplicateUserMedicationError()

    tz = validate_timezone(body.timezone) if body.timezone is not None else DEFAULT_TIMEZONE
    um = models.UserMedication(
        user_id=user_id,
        medication_id=med.id,
        interval_hours=body.interval_hours if body.interval_hours is not None else 8,
        user_dosage=body.user_dosage.strip() if body.user_dosage and body.user_dosage.strip() else None,
        instructions=body.instructions.strip() if body.instructions and body.instructions.strip() else None,
        reminder_enabled=body.reminder_enabled,
        timezone=tz,
    )
    db.add(um)
    db.flush()

    if body.reminder_times:
        _replace_schedules(db, um, body.reminder_times)

    db.commit()
    db.refresh(um)
    db.refresh(med)
    return build_user_medication_out(um, med)


def get_user_medication_owned(
    db: Session, user_id: int, um_id: int
) -> Tuple[models.UserMedication, models.Medication]:
    um = (
        db.query(models.UserMedication)
        .options(joinedload(models.UserMedication.schedules), joinedload(models.UserMedication.medication))
        .filter(models.UserMedication.id == um_id, models.UserMedication.user_id == user_id)
        .first()
    )
    if not um:
        raise UserMedicationNotFoundError()
    return um, um.medication


def update_user_medication(db: Session, user_id: int, um_id: int, body: UserMedicationUpdateIn) -> dict:
    um, med = get_user_medication_owned(db, user_id, um_id)

    if body.user_dosage is not None:
        um.user_dosage = body.user_dosage.strip() if body.user_dosage.strip() else None
    if body.instructions is not None:
        um.instructions = body.instructions.strip() if body.instructions.strip() else None
    if body.reminder_enabled is not None:
        um.reminder_enabled = body.reminder_enabled
    if body.timezone is not None:
        um.timezone = validate_timezone(body.timezone)
    if body.interval_hours is not None:
        um.interval_hours = body.interval_hours
    if body.reminder_times is not None:
        _replace_schedules(db, um, body.reminder_times)
    if body.remaining_quantity is not None:
        um.remaining_quantity = body.remaining_quantity
    if body.quantity_unit is not None:
        um.quantity_unit = body.quantity_unit.strip() if body.quantity_unit.strip() else None
    if body.refill_threshold is not None:
        um.refill_threshold = body.refill_threshold
    if body.last_refill_at is not None:
        um.last_refill_at = body.last_refill_at
    if body.estimated_end_at is not None:
        um.estimated_end_at = body.estimated_end_at

    um.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(um)
    return build_user_medication_out(um, med)


def delete_user_medication(db: Session, user_id: int, um_id: int) -> None:
    um, _ = get_user_medication_owned(db, user_id, um_id)
    db.delete(um)
    db.commit()
