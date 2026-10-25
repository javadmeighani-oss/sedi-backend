"""Promote accepted KC candidates into canonical Gate 2 stores."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.gate1 import GATE1_PROFILE_FACT_TYPES, ProfileFactCreateIn
from backend.app.schemas.gate2 import (
    EventCreateIn,
    GoalCreateIn,
    HabitCreateIn,
    RestrictionCreateIn,
)
from backend.app.services.gate2_data_service import create_event, create_goal, create_habit, create_restriction
from backend.app.services.memory.memory_contract import MemoryContract
from backend.app.services.i6.consent_service import ConsentDenied
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.user_profile_fact_service import create_profile_fact

logger = logging.getLogger(__name__)

# fact_type -> (target_kind, extra)
LIFESTYLE_SCALAR_MAP: Dict[str, Tuple[str, str]] = {
    "sleep_quality": ("lifestyle", "sleep_quality"),
    "stress_level": ("lifestyle", "stress_level"),
    "mood": ("lifestyle", "mood"),
    "activity_level": ("lifestyle", "activity_level"),
    "sleep_duration_hours": ("lifestyle", "sleep_duration_hours"),
    "hydration_ml": ("lifestyle", "hydration_ml"),
    "food_habits": ("lifestyle", "food_habits"),
    "diet_notes": ("lifestyle", "diet_notes"),
    "wake_time": ("routines", "wake_time"),
    "bedtime": ("routines", "bedtime"),
    "exercise_schedule": ("routines", "exercise_schedule"),
    "response_length": ("preferences", "response_length"),
    # CR-04F.2 — missing SUPPORTED_TARGET I6 mappings for RD confirm→promote.
    "interests": ("preferences", "interests"),
    "communication_style": ("preferences", "communication_style"),
    "listen_before_advice": ("preferences", "listen_before_advice"),
    "work_schedule": ("work", "work_schedule"),
    "time_constraints": ("barriers", "time_constraints"),
    "daily_walk_minutes": ("lifestyle", "exercise_minutes"),
    # R-014 second memory: user-stated facts (I6-canonical; consent-gated by write_fact).
    "health_concerns": ("medical", "health_concerns"),
    "family_history": ("medical", "family_history"),
    "occupation_stated": ("work", "occupation"),  # key differs: "occupation" is a frozen legacy profile-fact type
    "household_context": ("social", "household_context"),
    # R-021 / M2: intake facts the user stated in free chat (same I6 keys the friendly intake loop uses).
    "intake_allergies": ("intake", "allergies"),
    "intake_goal": ("intake", "goal"),
    "intake_food_preferences": ("intake", "food_preferences"),
    "intake_exercise_preferences": ("intake", "exercise_preferences"),
}

# Keys whose value is a growing list: a new statement is merged into the active fact, never replaces it.
LIST_MERGE_KEYS = frozenset({
    ("medical", "health_concerns"),
    ("medical", "family_history"),
    ("preferences", "interests"),
    ("intake", "allergies"),
    ("intake", "food_preferences"),
    ("intake", "exercise_preferences"),
})


def _merge_list_value(db: Session, user_id: int, domain: str, key: str, value: Any) -> Any:
    """Union of the already-remembered list and the new statement (order kept, duplicates dropped)."""
    new_items = list(value) if isinstance(value, (list, tuple)) else [value]
    try:
        from backend.app.services.i6.memory_writes import _active_fact

        existing = _active_fact(db, user_id, domain, key)
        old = json.loads(existing.value_json) if existing is not None else []
    except Exception:
        old = []
    merged: list = []
    for item in (list(old) if isinstance(old, list) else [old]) + new_items:
        text = str(item).strip()
        if text and text not in [str(x).strip() for x in merged]:
            merged.append(item)
    return merged

PROFILE_FACT_TYPES = frozenset(GATE1_PROFILE_FACT_TYPES)

# Low-risk keys eligible for auto-promote without user confirm (still via KC candidate)
AUTO_PROMOTE_LOW_RISK = frozenset({"sleep_quality", "mood", "stress_level"})


def _parse_value(value_json: str) -> Any:
    try:
        return json.loads(value_json)
    except json.JSONDecodeError:
        return value_json


def _unwrap_value(raw: Any) -> Any:
    if isinstance(raw, dict) and "value" in raw and len(raw) == 1:
        return raw["value"]
    return raw


def promote_kc_candidate(db: Session, candidate: models.KcFactCandidate) -> Dict[str, Any]:
    """
    Promote an accepted KC candidate into the canonical store.
    Returns {"target": str, "id": optional int}.
    """
    fact_type = (candidate.fact_type or "").strip()
    value = _unwrap_value(_parse_value(candidate.value_json))
    user_id = candidate.user_id
    source = "conversation"

    if fact_type in PROFILE_FACT_TYPES:
        ft = fact_type if fact_type in GATE1_PROFILE_FACT_TYPES else "other_identity"
        if fact_type == "medical_history_note":
            ft = "medical_history_note"
        item = create_profile_fact(
            db,
            user_id,
            ProfileFactCreateIn(fact_type=ft, value=value, source="conversation", confidence=candidate.confidence),
        )
        return {"target": "user_profile_facts", "id": item.get("id")}

    if fact_type in LIFESTYLE_SCALAR_MAP:
        domain, key = LIFESTYLE_SCALAR_MAP[fact_type]
        valid, err = MemoryContract.validate_fact(domain, key)
        if not valid:
            logger.debug("promote skip invalid memory fact %s/%s: %s", domain, key, err)
            return {"target": "skipped", "reason": err}
        if (domain, key) in LIST_MERGE_KEYS:
            value = _merge_list_value(db, user_id, domain, key, value)
        try:
            write_fact(
                db,
                user_id,
                domain,
                key,
                value,
                source="chat",
                provenance_class="USER_CONFIRMED",
                commit=True,
            )
        except ConsentDenied:
            return {"target": "skipped", "reason": "CONSENT_DENIED"}
        return {"target": "user_memory_facts", "domain": domain, "key": key}

    if fact_type in ("habit", "user_habit"):
        title = str(value).strip() if value is not None else "habit"
        item = create_habit(db, user_id, HabitCreateIn(name=title[:128], source=source))
        return {"target": "user_habits", "id": item.get("id")}

    if fact_type in ("goal", "health_goal", "lifestyle_goal", "health_goals"):
        title = str(value).strip() if value is not None else "goal"
        category = "health" if "health" in fact_type else "lifestyle"
        item = create_goal(db, user_id, GoalCreateIn(category=category, title=title[:256], source=source))
        return {"target": "user_goals", "id": item.get("id")}

    if fact_type in ("restriction", "diet_restriction", "exercise_restriction"):
        title = str(value).strip() if value is not None else "restriction"
        rtype = "diet" if "diet" in fact_type else ("exercise" if "exercise" in fact_type else "other")
        item = create_restriction(db, user_id, RestrictionCreateIn(restriction_type=rtype, title=title[:256], source=source))
        return {"target": "user_restrictions", "id": item.get("id")}

    if fact_type in (
        "user_event", "event", "appointment", "deadline", "doctor_visit", "lab_test", "exam",
        "work_meeting", "birthday", "surgery", "imaging", "physiotherapy", "care_followup",
        "nursing_visit", "medication_review", "important_day",
    ):
        payload = value if isinstance(value, dict) else {"title": str(value)}
        starts_at = payload.get("starts_at")
        if isinstance(starts_at, str):
            starts_at = datetime.fromisoformat(starts_at.replace("Z", "+00:00")).replace(tzinfo=None)
        if not isinstance(starts_at, datetime):
            starts_at = datetime.utcnow() + timedelta(days=1)
        domain = payload.get("event_domain") or _infer_event_domain(fact_type)
        etype = payload.get("event_type") or fact_type
        if etype == "appointment":
            etype = "doctor_visit"
        if fact_type == "user_event" and isinstance(value, dict):
            domain = value.get("event_domain") or domain
            etype = value.get("event_type") or etype
        item = create_event(
            db,
            user_id,
            EventCreateIn(
                title=str(payload.get("title") or "Event")[:256],
                event_domain=domain,
                event_type=etype,
                starts_at=starts_at,
                source=source,
                description=payload.get("description"),
                location=payload.get("location"),
            ),
        )
        return {"target": "user_events", "id": item.get("id")}

    if fact_type in ("care_plan_item", "care_plan"):
        from backend.app.schemas.gate2 import CarePlanItemCreateIn
        from backend.app.services.gate2_data_service import create_care_plan_item

        title = str(value).strip() if not isinstance(value, dict) else str(value.get("title", "care plan"))
        item = create_care_plan_item(db, user_id, CarePlanItemCreateIn(title=title[:256], source=source))
        return {"target": "user_care_plan_items", "id": item.get("id")}

    if fact_type == "care_checkin_event":
        return _promote_care_checkin(db, user_id, str(value).strip().lower())

    if fact_type in ("medications", "medications_list", "medication"):
        # Do not duplicate into memory facts — leave for structured meds flow (Gate 2: pending/suggest only)
        return {"target": "user_medications", "action": "suggest_only", "value": str(value)[:120]}

    if fact_type in ("medical_conditions", "conditions"):
        return {"target": "user_conditions", "action": "suggest_only", "value": str(value)[:120]}

    # Fallback: try lifestyle scalar if key exists in contract goals/preferences
    if fact_type in ("health_goals", "fitness_goals", "lifestyle_goals"):
        domain, key = "goals", fact_type
        valid, _ = MemoryContract.validate_fact(domain, key)
        if valid:
            try:
                write_fact(
                    db,
                    user_id,
                    domain,
                    key,
                    value,
                    source="chat",
                    provenance_class="USER_CONFIRMED",
                    commit=True,
                )
            except ConsentDenied:
                return {"target": "skipped", "reason": "CONSENT_DENIED"}
            return {"target": "user_memory_facts", "domain": domain, "key": key}

    logger.info("promote_kc_candidate unmapped fact_type=%s user_id=%s", fact_type, user_id)
    return {"target": "unmapped", "fact_type": fact_type}


def _infer_event_domain(fact_type: str) -> str:
    if fact_type in ("doctor_visit", "lab_test", "imaging", "surgery", "physiotherapy", "medication_review"):
        return "medical"
    if fact_type in ("work_meeting", "deadline"):
        return "work"
    if fact_type in ("exam",):
        return "education"
    if fact_type in ("birthday",):
        return "family"
    if fact_type in ("care_followup", "nursing_visit"):
        return "care"
    return "other"


def promote_after_accept(db: Session, candidate_id: int) -> Optional[Dict[str, Any]]:
    cand = db.query(models.KcFactCandidate).filter(models.KcFactCandidate.id == candidate_id).first()
    if cand is None or cand.status != "accepted":
        return None
    return promote_kc_candidate(db, cand)


# R-018: a significant life event the user stated (loss, job loss, separation, surgery, accident) schedules ONE gentle
# check-in through the existing I10-B12 CareFollowUpTask (no new scheduler). Only the event KIND is stored.
_CARE_CHECKIN_DELAY_DAYS = {"loss": 2, "job_loss": 3, "separation": 3, "surgery": 2, "accident": 2}
CARE_CHECKIN_TITLE_PREFIX = "care_checkin:"


def _promote_care_checkin(db: Session, user_id: int, kind: str) -> Dict[str, Any]:
    if kind not in _CARE_CHECKIN_DELAY_DAYS:
        return {"target": "skipped", "reason": "UNKNOWN_CARE_EVENT"}
    from backend.app.services.i6.consent_service import PERM_WRITE, has_permission

    if not has_permission(db, user_id, PERM_WRITE):
        return {"target": "skipped", "reason": "CONSENT_DENIED"}
    now = datetime.utcnow()
    try:  # R-021: the same fact also lands on the user's life timeline (I7); never blocks the check-in
        from backend.app.services.i7.life_events import record_life_event

        record_life_event(db, user_id, kind=kind, source="conversation")
    except Exception:
        logger.debug("life event record skipped", exc_info=True)
    recent = (
        db.query(models.CareFollowUpTask.id)
        .filter(
            models.CareFollowUpTask.user_id == user_id,
            models.CareFollowUpTask.title.like(f"{CARE_CHECKIN_TITLE_PREFIX}%"),
            models.CareFollowUpTask.created_at >= now - timedelta(days=7),
        )
        .first()
    )
    if recent:
        return {"target": "skipped", "reason": "CARE_CHECKIN_RECENT"}
    from backend.app.services.i10.contextual_followup_types import FollowUpTaskSource
    from backend.app.services.i10.contextual_followup_worker import create_structured_follow_up_task

    task = create_structured_follow_up_task(
        db,
        user_id=user_id,
        title=f"{CARE_CHECKIN_TITLE_PREFIX}{kind}",
        due_at=now + timedelta(days=_CARE_CHECKIN_DELAY_DAYS[kind]),
        source=FollowUpTaskSource.GENERAL_CONTEXTUAL,
        follow_up_kind="care_checkin",
    )
    db.commit()
    return {"target": "care_follow_up_tasks", "id": task.id}
