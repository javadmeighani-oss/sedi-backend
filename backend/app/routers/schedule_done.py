"""R-031: the user marks something done in My Schedule (took the medication, attended the appointment / meeting).

POST /user/schedule/done  - record (or undo) one occurrence through its owner and the I7 "user did it" ledger.
GET  /user/schedule/done  - occurrences of a day that are currently done (so the app can show the ticks).

Owners are never bypassed: a medication dose is confirmed on ``medication_dose_occurrences`` (the same row its reminder
uses, so that dose is not reminded again); a one-off UserEvent becomes ``completed``; a repeating event keeps its series
and is recorded per occurrence in the ledger (``backend.app.services.i7.user_done``). Nothing is copied elsewhere -
I7 signals, reminders, chat context and the profile summary READ the ledger.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timezone
from typing import Literal, Optional

import pytz
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.database import get_db
from backend.app.routers.auth_otp import get_current_user
from backend.app.schemas import APIResponse
from backend.app.services.i7 import user_done

router = APIRouter()


class ScheduleDoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["event", "medication"]
    id: int = Field(..., ge=1)
    day: Optional[date] = None  # the occurrence's local day; default = today (or the event's own day)
    time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")  # medication dose time, HH:MM
    done: bool = True  # false = undo


def _user_zone(db: Session, user_id: int):
    try:
        from backend.app.services.gate4.policy_prefs_bridge import resolve_validated_user_timezone

        return pytz.timezone(resolve_validated_user_timezone(db, user_id))
    except Exception:
        return pytz.timezone("Asia/Tehran")


def _memory_recorded(db: Session, user_id: int) -> bool:
    """True when the user's memory consent lets I7 keep this (the done mark itself always works)."""
    try:
        from backend.app.services.i6.consent_service import PERM_WRITE, has_permission_readonly

        return bool(has_permission_readonly(db, user_id, PERM_WRITE))
    except Exception:
        return False


def _mark_event(db: Session, user: models.User, body: ScheduleDoneIn, zone) -> tuple[str, str]:
    ev = (
        db.query(models.UserEvent)
        .filter(models.UserEvent.id == body.id, models.UserEvent.user_id == user.id)
        .first()
    )
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if body.day is not None:
        day = body.day
    elif ev.starts_at is not None and not ev.recurrence_rule:
        day = ev.starts_at.date()
    else:
        day = datetime.now(zone).date()
    domain = user_done.domain_for("event", ev.event_type, ev.event_domain)
    if not ev.recurrence_rule:
        ev.status = "completed" if body.done else "scheduled"
        ev.updated_at = datetime.utcnow()
    user_done.record(db, user.id, kind="event", ref_id=ev.id, day=day, hhmm=None, domain=domain, done=body.done)
    return user_done.occurrence_id("event", ev.id, day), domain


def _mark_medication(db: Session, user: models.User, body: ScheduleDoneIn, zone) -> tuple[str, str]:
    from backend.app.services.i10.medication_adherence import (
        MedicationAdherenceState,
        build_medication_occurrence_key,
        get_or_create_dose_occurrence,
    )

    if not body.time:
        raise HTTPException(status_code=422, detail="time (HH:MM) is required for a medication dose")
    um = (
        db.query(models.UserMedication)
        .filter(models.UserMedication.id == body.id, models.UserMedication.user_id == user.id)
        .first()
    )
    if um is None:
        raise HTTPException(status_code=404, detail="Medication not found")
    try:
        hh, mm = (int(x) for x in body.time.split(":"))
        at = dtime(hh, mm)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid time") from None
    day = body.day or datetime.now(zone).date()
    schedule = (
        db.query(models.UserMedicationSchedule)
        .filter(
            models.UserMedicationSchedule.user_medication_id == um.id,
            models.UserMedicationSchedule.time_of_day == at,
        )
        .first()
    )
    local = zone.localize(datetime.combine(day, at))
    scheduled_utc = local.astimezone(pytz.UTC).replace(tzinfo=None)
    key = build_medication_occurrence_key(
        user_id=user.id,
        user_medication_id=um.id,
        schedule_id=schedule.id if schedule else None,
        scheduled_for=scheduled_utc,
        schedule_time=body.time,
    )
    occ, _created = get_or_create_dose_occurrence(
        db,
        user_id=user.id,
        user_medication_id=um.id,
        schedule_id=schedule.id if schedule else None,
        scheduled_for=scheduled_utc,
        occurrence_key=key,
        commit=False,
    )
    now = datetime.now(timezone.utc)
    if body.done:
        occ.state = MedicationAdherenceState.CONFIRMED_TAKEN.value
        occ.confirmed_at = now
        occ.confirmation_source = "USER_SCHEDULE_UI"
    elif occ.state == MedicationAdherenceState.CONFIRMED_TAKEN.value:
        occ.state = MedicationAdherenceState.DUE.value
        occ.confirmed_at = None
        occ.confirmation_source = None
    occ.updated_at = now.replace(tzinfo=None)
    user_done.record(
        db, user.id, kind="medication", ref_id=um.id, day=day, hhmm=body.time, domain="medication", done=body.done
    )
    return user_done.occurrence_id("medication", um.id, day, body.time), "medication"


@router.post("/schedule/done", response_model=APIResponse)
def post_schedule_done(
    body: ScheduleDoneIn,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    zone = _user_zone(db, auth_user.id)
    if body.kind == "event":
        occ, domain = _mark_event(db, auth_user, body, zone)
    else:
        occ, domain = _mark_medication(db, auth_user, body, zone)
    db.commit()
    return APIResponse(
        ok=True,
        data={
            "occurrence_id": occ,
            "done": body.done,
            "domain": domain,
            "in_memory": _memory_recorded(db, auth_user.id),
        },
    )


@router.get("/schedule/done", response_model=APIResponse)
def get_schedule_done(
    day: Optional[date] = None,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    zone = _user_zone(db, auth_user.id)
    target = day or datetime.now(zone).date()
    return APIResponse(
        ok=True,
        data={"day": target.isoformat(), "items": user_done.done_occurrences(db, auth_user.id, target)},
    )
