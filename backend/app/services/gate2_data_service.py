"""Gate 2 CRUD services for habits, goals, restrictions, doctors, events, lifestyle events, care plan items."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, List, Optional, Type

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.gate2 import (
    CarePlanItemCreateIn,
    CarePlanItemUpdateIn,
    DoctorCreateIn,
    DoctorUpdateIn,
    EventCreateIn,
    EventUpdateIn,
    GoalCreateIn,
    GoalUpdateIn,
    HabitCreateIn,
    HabitUpdateIn,
    LifestyleEventCreateIn,
    RestrictionCreateIn,
    RestrictionUpdateIn,
)


class Gate2NotFoundError(Exception):
    pass


def _json_dump(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_load(raw: Optional[str]) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _dt_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _habit_dict(row: models.UserHabit) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "name": row.name,
        "frequency": row.frequency,
        "target": _json_load(row.target_json),
        "status": row.status,
        "source": row.source,
        "notes": row.notes,
        "valid_to": _dt_iso(row.valid_to),
        "created_at": _dt_iso(row.created_at),
        "updated_at": _dt_iso(row.updated_at),
    }


def list_habits(db: Session, user_id: int) -> List[dict]:
    now = datetime.utcnow()
    rows = (
        db.query(models.UserHabit)
        .filter(
            models.UserHabit.user_id == user_id,
            (models.UserHabit.valid_to.is_(None)) | (models.UserHabit.valid_to > now),
        )
        .order_by(models.UserHabit.updated_at.desc())
        .all()
    )
    return [_habit_dict(r) for r in rows]


def create_habit(db: Session, user_id: int, body: HabitCreateIn) -> dict:
    now = datetime.utcnow()
    row = models.UserHabit(
        user_id=user_id,
        name=body.name.strip(),
        frequency=body.frequency,
        target_json=_json_dump(body.target),
        status=body.status,
        source=body.source,
        notes=body.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _habit_dict(row)


def update_habit(db: Session, user_id: int, habit_id: int, body: HabitUpdateIn) -> dict:
    row = (
        db.query(models.UserHabit)
        .filter(models.UserHabit.id == habit_id, models.UserHabit.user_id == user_id)
        .first()
    )
    if row is None or (row.valid_to and row.valid_to <= datetime.utcnow()):
        raise Gate2NotFoundError()
    if body.name is not None:
        row.name = body.name.strip()
    if body.frequency is not None:
        row.frequency = body.frequency
    if body.target is not None:
        row.target_json = _json_dump(body.target)
    if body.status is not None:
        row.status = body.status
    if body.notes is not None:
        row.notes = body.notes
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _habit_dict(row)


def delete_habit(db: Session, user_id: int, habit_id: int) -> None:
    row = (
        db.query(models.UserHabit)
        .filter(models.UserHabit.id == habit_id, models.UserHabit.user_id == user_id)
        .first()
    )
    if row is None:
        raise Gate2NotFoundError()
    row.valid_to = datetime.utcnow()
    row.status = "inactive"
    row.updated_at = datetime.utcnow()
    db.commit()


def _goal_dict(row: models.UserGoal) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "category": row.category,
        "title": row.title,
        "description": row.description,
        "target": _json_load(row.target_json),
        "status": row.status,
        "source": row.source,
        "priority": row.priority,
        "valid_to": _dt_iso(row.valid_to),
        "created_at": _dt_iso(row.created_at),
        "updated_at": _dt_iso(row.updated_at),
    }


def list_goals(db: Session, user_id: int) -> List[dict]:
    now = datetime.utcnow()
    rows = (
        db.query(models.UserGoal)
        .filter(
            models.UserGoal.user_id == user_id,
            (models.UserGoal.valid_to.is_(None)) | (models.UserGoal.valid_to > now),
        )
        .order_by(models.UserGoal.updated_at.desc())
        .all()
    )
    return [_goal_dict(r) for r in rows]


def create_goal(db: Session, user_id: int, body: GoalCreateIn) -> dict:
    now = datetime.utcnow()
    row = models.UserGoal(
        user_id=user_id,
        category=body.category,
        title=body.title.strip(),
        description=body.description,
        target_json=_json_dump(body.target),
        status=body.status,
        source=body.source,
        priority=body.priority,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _goal_dict(row)


def update_goal(db: Session, user_id: int, goal_id: int, body: GoalUpdateIn) -> dict:
    row = (
        db.query(models.UserGoal)
        .filter(models.UserGoal.id == goal_id, models.UserGoal.user_id == user_id)
        .first()
    )
    if row is None or (row.valid_to and row.valid_to <= datetime.utcnow()):
        raise Gate2NotFoundError()
    for field, attr in (
        ("category", "category"),
        ("title", "title"),
        ("description", "description"),
        ("status", "status"),
        ("priority", "priority"),
    ):
        val = getattr(body, field)
        if val is not None:
            setattr(row, attr, val.strip() if field == "title" else val)
    if body.target is not None:
        row.target_json = _json_dump(body.target)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _goal_dict(row)


def delete_goal(db: Session, user_id: int, goal_id: int) -> None:
    row = (
        db.query(models.UserGoal)
        .filter(models.UserGoal.id == goal_id, models.UserGoal.user_id == user_id)
        .first()
    )
    if row is None:
        raise Gate2NotFoundError()
    row.valid_to = datetime.utcnow()
    row.status = "cancelled"
    row.updated_at = datetime.utcnow()
    db.commit()


def _restriction_dict(row: models.UserRestriction) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "restriction_type": row.restriction_type,
        "title": row.title,
        "description": row.description,
        "severity": row.severity,
        "status": row.status,
        "source": row.source,
        "valid_from": _dt_iso(row.valid_from),
        "valid_to": _dt_iso(row.valid_to),
        "created_at": _dt_iso(row.created_at),
        "updated_at": _dt_iso(row.updated_at),
    }


def list_restrictions(db: Session, user_id: int) -> List[dict]:
    now = datetime.utcnow()
    rows = (
        db.query(models.UserRestriction)
        .filter(
            models.UserRestriction.user_id == user_id,
            (models.UserRestriction.valid_to.is_(None)) | (models.UserRestriction.valid_to > now),
        )
        .order_by(models.UserRestriction.updated_at.desc())
        .all()
    )
    return [_restriction_dict(r) for r in rows]


def create_restriction(db: Session, user_id: int, body: RestrictionCreateIn) -> dict:
    now = datetime.utcnow()
    row = models.UserRestriction(
        user_id=user_id,
        restriction_type=body.restriction_type,
        title=body.title.strip(),
        description=body.description,
        severity=body.severity,
        status=body.status,
        source=body.source,
        valid_from=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _restriction_dict(row)


def update_restriction(db: Session, user_id: int, restriction_id: int, body: RestrictionUpdateIn) -> dict:
    row = (
        db.query(models.UserRestriction)
        .filter(models.UserRestriction.id == restriction_id, models.UserRestriction.user_id == user_id)
        .first()
    )
    if row is None or (row.valid_to and row.valid_to <= datetime.utcnow()):
        raise Gate2NotFoundError()
    for field in ("restriction_type", "title", "description", "severity", "status"):
        val = getattr(body, field)
        if val is not None:
            setattr(row, field, val.strip() if field == "title" else val)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _restriction_dict(row)


def delete_restriction(db: Session, user_id: int, restriction_id: int) -> None:
    row = (
        db.query(models.UserRestriction)
        .filter(models.UserRestriction.id == restriction_id, models.UserRestriction.user_id == user_id)
        .first()
    )
    if row is None:
        raise Gate2NotFoundError()
    row.valid_to = datetime.utcnow()
    row.status = "inactive"
    row.updated_at = datetime.utcnow()
    db.commit()


def _doctor_dict(row: models.UserDoctor) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "name": row.name,
        "specialty": row.specialty,
        "phone": row.phone,
        "clinic": row.clinic,
        "notes": row.notes,
        "is_primary": row.is_primary,
        "is_active": row.is_active,
        "source": row.source,
        "created_at": _dt_iso(row.created_at),
        "updated_at": _dt_iso(row.updated_at),
    }


def list_doctors(db: Session, user_id: int, active_only: bool = True) -> List[dict]:
    q = db.query(models.UserDoctor).filter(models.UserDoctor.user_id == user_id)
    if active_only:
        q = q.filter(models.UserDoctor.is_active == True)  # noqa: E712
    rows = q.order_by(models.UserDoctor.is_primary.desc(), models.UserDoctor.updated_at.desc()).all()
    return [_doctor_dict(r) for r in rows]


def create_doctor(db: Session, user_id: int, body: DoctorCreateIn) -> dict:
    now = datetime.utcnow()
    if body.is_primary:
        db.query(models.UserDoctor).filter(
            models.UserDoctor.user_id == user_id,
            models.UserDoctor.is_primary == True,  # noqa: E712
        ).update({"is_primary": False})
    row = models.UserDoctor(
        user_id=user_id,
        name=body.name.strip(),
        specialty=body.specialty,
        phone=body.phone,
        clinic=body.clinic,
        notes=body.notes,
        is_primary=body.is_primary,
        source=body.source,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _doctor_dict(row)


def update_doctor(db: Session, user_id: int, doctor_id: int, body: DoctorUpdateIn) -> dict:
    row = (
        db.query(models.UserDoctor)
        .filter(models.UserDoctor.id == doctor_id, models.UserDoctor.user_id == user_id)
        .first()
    )
    if row is None:
        raise Gate2NotFoundError()
    if body.is_primary is True:
        db.query(models.UserDoctor).filter(
            models.UserDoctor.user_id == user_id,
            models.UserDoctor.id != doctor_id,
            models.UserDoctor.is_primary == True,  # noqa: E712
        ).update({"is_primary": False})
    for field in ("name", "specialty", "phone", "clinic", "notes", "is_primary", "is_active"):
        val = getattr(body, field)
        if val is not None:
            setattr(row, field, val.strip() if field == "name" else val)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _doctor_dict(row)


def delete_doctor(db: Session, user_id: int, doctor_id: int) -> None:
    row = (
        db.query(models.UserDoctor)
        .filter(models.UserDoctor.id == doctor_id, models.UserDoctor.user_id == user_id)
        .first()
    )
    if row is None:
        raise Gate2NotFoundError()
    row.is_active = False
    row.updated_at = datetime.utcnow()
    db.commit()


def _event_dict(row: models.UserEvent) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "doctor_id": row.doctor_id,
        "title": row.title,
        "description": row.description,
        "event_domain": row.event_domain,
        "event_type": row.event_type,
        "starts_at": _dt_iso(row.starts_at),
        "ends_at": _dt_iso(row.ends_at),
        "timezone": row.timezone,
        "location": row.location,
        "status": row.status,
        "importance": row.importance,
        "reminder_enabled": row.reminder_enabled,
        "reminder_offsets": _json_load(row.reminder_offsets_json),
        "recurrence_rule": row.recurrence_rule,
        "source": row.source,
        "notes": row.notes,
        "valid_to": _dt_iso(row.valid_to),
        "created_at": _dt_iso(row.created_at),
        "updated_at": _dt_iso(row.updated_at),
    }


def list_events(db: Session, user_id: int, upcoming_only: bool = False) -> List[dict]:
    now = datetime.utcnow()
    q = db.query(models.UserEvent).filter(
        models.UserEvent.user_id == user_id,
        (models.UserEvent.valid_to.is_(None)) | (models.UserEvent.valid_to > now),
    )
    if upcoming_only:
        q = q.filter(
            models.UserEvent.starts_at >= now,
            models.UserEvent.status == "scheduled",
        )
    rows = q.order_by(models.UserEvent.starts_at.asc()).all()
    return [_event_dict(r) for r in rows]


def create_event(db: Session, user_id: int, body: EventCreateIn) -> dict:
    if body.doctor_id is not None:
        doc = (
            db.query(models.UserDoctor)
            .filter(models.UserDoctor.id == body.doctor_id, models.UserDoctor.user_id == user_id)
            .first()
        )
        if doc is None:
            raise ValueError("doctor_id not found for user")
    now = datetime.utcnow()
    row = models.UserEvent(
        user_id=user_id,
        doctor_id=body.doctor_id,
        title=body.title.strip(),
        description=body.description,
        event_domain=body.event_domain,
        event_type=body.event_type,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        timezone=body.timezone,
        location=body.location,
        status=body.status,
        importance=body.importance,
        reminder_enabled=body.reminder_enabled,
        reminder_offsets_json=_json_dump(body.reminder_offsets),
        recurrence_rule=body.recurrence_rule,
        source=body.source,
        notes=body.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _event_dict(row)


def update_event(db: Session, user_id: int, event_id: int, body: EventUpdateIn) -> dict:
    row = (
        db.query(models.UserEvent)
        .filter(models.UserEvent.id == event_id, models.UserEvent.user_id == user_id)
        .first()
    )
    if row is None or (row.valid_to and row.valid_to <= datetime.utcnow()):
        raise Gate2NotFoundError()
    if body.doctor_id is not None:
        doc = (
            db.query(models.UserDoctor)
            .filter(models.UserDoctor.id == body.doctor_id, models.UserDoctor.user_id == user_id)
            .first()
        )
        if doc is None:
            raise ValueError("doctor_id not found for user")
        row.doctor_id = body.doctor_id
    for field in (
        "title", "description", "event_domain", "event_type", "starts_at", "ends_at",
        "timezone", "location", "status", "importance", "reminder_enabled", "recurrence_rule", "notes",
    ):
        val = getattr(body, field)
        if val is not None:
            setattr(row, field, val.strip() if field == "title" else val)
    if body.reminder_offsets is not None:
        row.reminder_offsets_json = _json_dump(body.reminder_offsets)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _event_dict(row)


def delete_event(db: Session, user_id: int, event_id: int) -> None:
    row = (
        db.query(models.UserEvent)
        .filter(models.UserEvent.id == event_id, models.UserEvent.user_id == user_id)
        .first()
    )
    if row is None:
        raise Gate2NotFoundError()
    row.valid_to = datetime.utcnow()
    row.status = "cancelled"
    row.updated_at = datetime.utcnow()
    db.commit()


def _lifestyle_event_dict(row: models.UserLifestyleEvent) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "event_type": row.event_type,
        "value": _json_load(row.value_json),
        "occurred_at": _dt_iso(row.occurred_at),
        "source": row.source,
        "notes": row.notes,
        "created_at": _dt_iso(row.created_at),
    }


def list_lifestyle_events(db: Session, user_id: int, limit: int = 50) -> List[dict]:
    rows = (
        db.query(models.UserLifestyleEvent)
        .filter(models.UserLifestyleEvent.user_id == user_id)
        .order_by(models.UserLifestyleEvent.occurred_at.desc())
        .limit(limit)
        .all()
    )
    return [_lifestyle_event_dict(r) for r in rows]


def create_lifestyle_event(db: Session, user_id: int, body: LifestyleEventCreateIn) -> dict:
    now = datetime.utcnow()
    row = models.UserLifestyleEvent(
        user_id=user_id,
        event_type=body.event_type.strip(),
        value_json=_json_dump(body.value),
        occurred_at=body.occurred_at,
        source=body.source,
        notes=body.notes,
        created_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _lifestyle_event_dict(row)


def _care_plan_dict(row: models.UserCarePlanItem) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "title": row.title,
        "description": row.description,
        "category": row.category,
        "status": row.status,
        "scheduled_at": _dt_iso(row.scheduled_at),
        "source": row.source,
        "notes": row.notes,
        "valid_to": _dt_iso(row.valid_to),
        "created_at": _dt_iso(row.created_at),
        "updated_at": _dt_iso(row.updated_at),
    }


def list_care_plan_items(db: Session, user_id: int) -> List[dict]:
    now = datetime.utcnow()
    rows = (
        db.query(models.UserCarePlanItem)
        .filter(
            models.UserCarePlanItem.user_id == user_id,
            (models.UserCarePlanItem.valid_to.is_(None)) | (models.UserCarePlanItem.valid_to > now),
        )
        .order_by(models.UserCarePlanItem.updated_at.desc())
        .all()
    )
    return [_care_plan_dict(r) for r in rows]


def create_care_plan_item(db: Session, user_id: int, body: CarePlanItemCreateIn) -> dict:
    now = datetime.utcnow()
    row = models.UserCarePlanItem(
        user_id=user_id,
        title=body.title.strip(),
        description=body.description,
        category=body.category,
        status=body.status,
        scheduled_at=body.scheduled_at,
        source=body.source,
        notes=body.notes,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _care_plan_dict(row)


def update_care_plan_item(db: Session, user_id: int, item_id: int, body: CarePlanItemUpdateIn) -> dict:
    row = (
        db.query(models.UserCarePlanItem)
        .filter(models.UserCarePlanItem.id == item_id, models.UserCarePlanItem.user_id == user_id)
        .first()
    )
    if row is None or (row.valid_to and row.valid_to <= datetime.utcnow()):
        raise Gate2NotFoundError()
    for field in ("title", "description", "category", "status", "scheduled_at", "notes"):
        val = getattr(body, field)
        if val is not None:
            setattr(row, field, val.strip() if field == "title" else val)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _care_plan_dict(row)


def delete_care_plan_item(db: Session, user_id: int, item_id: int) -> None:
    row = (
        db.query(models.UserCarePlanItem)
        .filter(models.UserCarePlanItem.id == item_id, models.UserCarePlanItem.user_id == user_id)
        .first()
    )
    if row is None:
        raise Gate2NotFoundError()
    row.valid_to = datetime.utcnow()
    row.status = "cancelled"
    row.updated_at = datetime.utcnow()
    db.commit()
