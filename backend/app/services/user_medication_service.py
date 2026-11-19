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


class ScheduleTimeCollisionError(Exception):
    """Moving a dose onto a time where the same medicine already has another dose."""


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
        remaining_quantity=body.remaining_quantity,
        quantity_unit=body.quantity_unit.strip() if body.quantity_unit and body.quantity_unit.strip() else None,
        refill_threshold=body.refill_threshold,
        last_refill_at=body.last_refill_at,
        estimated_end_at=body.estimated_end_at,
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


def move_schedule_time(db: Session, user_id: int, um_id: int, old_hhmm: str, new_hhmm: str) -> dict:
    """Move ONE dose time in place, in ONE transaction: the weekday filter of that dose is kept and the other doses are not
    touched (the full ``reminder_times`` replacement would briefly store daily schedules and could merge two doses). Used by the
    chat time-change path (R-103). Raises UserMedicationNotFoundError (no such dose) / ScheduleTimeCollisionError."""
    um, med = get_user_medication_owned(db, user_id, um_id)
    old_t, new_t = parse_hhmm(old_hhmm), parse_hhmm(new_hhmm)
    rows = list(um.schedules or [])
    target = next((r for r in rows if r.time_of_day == old_t), None)
    if target is None:
        raise UserMedicationNotFoundError()
    if any(r is not target and r.time_of_day == new_t for r in rows):
        raise ScheduleTimeCollisionError()
    target.time_of_day = new_t
    um.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(um)
    return build_user_medication_out(um, med)


def convert_hhmm(hhmm: str, from_tz: Optional[str], to_tz: Optional[str]) -> str:
    """The same instant (today) as a wall-clock time of ``to_tz``. A request made in another timezone than the medicine's own must
    not be stored unchanged under the medicine's timezone (Codex P2, PR 193). Unknown/equal zones leave the time as it is."""
    if not from_tz or not to_tz or from_tz == to_tz:
        return hhmm
    try:
        t = parse_hhmm(hhmm)
        src, dst = pytz.timezone(from_tz), pytz.timezone(to_tz)
        local = src.localize(datetime.combine(datetime.now(src).date(), t))
        return format_time_of_day(local.astimezone(dst).time())
    except Exception:  # noqa: BLE001
        return hhmm


def add_schedule_time(
    db: Session, user_id: int, um_id: int, hhmm: str, days_of_week: Optional[str] = None, from_tz: Optional[str] = None
) -> dict:
    """Add ONE more dose time to a registered medicine, in one transaction (R-103 step B: «the same pill, a second time»).
    ``from_tz``: the timezone the time was spoken in (converted into the medicine's own). The SAME time with other weekdays merges
    the weekday coverage (Codex P2, PR 193); raises ScheduleTimeCollisionError only when nothing would change, ValueError beyond the
    schedule limit."""
    from backend.app.schemas.medical import MAX_REMINDER_TIMES

    um, med = get_user_medication_owned(db, user_id, um_id)
    t = parse_hhmm(convert_hhmm(hhmm, from_tz, getattr(um, "timezone", None)))
    rows = list(um.schedules or [])
    same = next((r for r in rows if r.time_of_day == t), None)
    if same is not None:
        merged = _merge_days(same.days_of_week, days_of_week)
        if merged == same.days_of_week:
            raise ScheduleTimeCollisionError()
        same.days_of_week = merged
        um.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(um)
        return build_user_medication_out(um, med)
    if len(rows) >= MAX_REMINDER_TIMES:
        raise ValueError("too many reminder times")
    db.add(models.UserMedicationSchedule(user_medication_id=um.id, time_of_day=t, days_of_week=days_of_week))
    um.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(um)
    return build_user_medication_out(um, med)


_BYDAY_INDEX = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _days_from_rule(rule: Optional[str], starts_at: Optional[datetime] = None) -> Optional[str]:
    """«FREQ=WEEKLY;BYDAY=MO,TH» -> «0,3» (Monday = 0); daily or no rule -> None (every day). A weekly rule WITHOUT BYDAY repeats
    on the weekday of its first occurrence (the event scheduler does the same), so that weekday is kept (Codex P1, PR 193)."""
    m = re.search(r"BYDAY=([A-Z,]+)", rule or "")
    if not m:
        if starts_at is not None and re.search(r"FREQ=WEEKLY", (rule or "").upper()):
            return str(starts_at.weekday())
        return None
    days = sorted({_BYDAY_INDEX[d] for d in m.group(1).split(",") if d in _BYDAY_INDEX})
    return ",".join(str(d) for d in days) or None


def _merge_days(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Weekday coverage of two schedules at the SAME time: daily (None) wins, otherwise the union (Codex P2, PR 193)."""
    if a is None or b is None:
        return None
    days = sorted({int(x) for x in (a + "," + b).split(",") if x.strip().isdigit()})
    return ",".join(str(d) for d in days) or None


def promote_event_to_medication(
    db: Session, user_id: int, event_id: int, name: str, new_hhmm: str, days_of_week: Optional[str] = None, from_tz: Optional[str] = None,
    also_event_ids: Optional[list[int]] = None,
) -> dict:
    """An older repeating chat reminder (UserEvent) becomes a REGISTERED medicine with its old dose time AND the new one, and the
    older event is soft-cancelled (status cancelled + valid_to; the row is never deleted) - all in ONE transaction so the user is
    never reminded twice (R-103 step B/C). An existing UserMedication of that name receives the times instead of a duplicate."""
    ev = (
        db.query(models.UserEvent)
        .filter(models.UserEvent.id == event_id, models.UserEvent.user_id == user_id, models.UserEvent.status.in_(["scheduled", "confirmed"]))
        .first()
    )
    clean = normalize_medication_name(name or "")
    if ev is None or ev.starts_at is None or not clean:
        raise UserMedicationNotFoundError()
    if re.search(r"[1-9]", getattr(ev, "reminder_offsets_json", None) or ""):
        raise UserMedicationNotFoundError()  # an advance reminder would silently fire at the dose time instead of before it
    med = find_or_create_medication(db, name=clean)
    db.flush()
    um = (
        db.query(models.UserMedication)
        .filter(models.UserMedication.user_id == user_id, models.UserMedication.medication_id == med.id)
        .first()
    )
    if um is None:
        um = models.UserMedication(
            user_id=user_id,
            medication_id=med.id,
            interval_hours=8,
            reminder_enabled=True,
            timezone=validate_timezone(ev.timezone) if ev.timezone else DEFAULT_TIMEZONE,
        )
        db.add(um)
        db.flush()
    if not um.reminder_enabled:
        um.reminder_enabled = True  # the user has an ACTIVE reminder for this pill (the event being promoted): it must keep working
    # the OTHER active repeating reminders of the same pill are promoted with it, so none keeps reminding next to the registered pill
    events = [ev]
    for oid in (also_event_ids or []):
        other = (
            db.query(models.UserEvent)
            .filter(models.UserEvent.id == oid, models.UserEvent.user_id == user_id, models.UserEvent.status.in_(["scheduled", "confirmed"]))
            .first()
        )
        if other is not None and other.starts_at is not None and not re.search(r"[1-9]", getattr(other, "reminder_offsets_json", None) or ""):
            events.append(other)
    have = {r.time_of_day: r for r in (um.schedules or [])}
    # each dose keeps ITS OWN weekdays (older dose: its event's; new dose: the new request's); two doses at the same time merge
    # their weekday coverage instead of dropping one (Codex P1/P2, PR 193)
    entries = [(time(e.starts_at.hour, e.starts_at.minute), _days_from_rule(e.recurrence_rule, e.starts_at)) for e in events]
    entries.append((parse_hhmm(convert_hhmm(new_hhmm, from_tz, ev.timezone)), days_of_week))
    for t, days in entries:
        row = have.get(t)
        if row is None:
            row = models.UserMedicationSchedule(user_medication_id=um.id, time_of_day=t, days_of_week=days)
            have[t] = row
            db.add(row)
        else:
            row.days_of_week = _merge_days(row.days_of_week, days)
    now = datetime.utcnow()
    for e in events:
        e.status = "cancelled"
        e.valid_to = now
        e.updated_at = now
    um.updated_at = now
    db.commit()
    db.refresh(um)
    return build_user_medication_out(um, med)


def delete_user_medication(db: Session, user_id: int, um_id: int) -> None:
    um, _ = get_user_medication_owned(db, user_id, um_id)
    db.delete(um)
    db.commit()
