"""Build / adjust a plan from the setup sheet (pilot V1 screen 6): the SAME fields chat asks, the SAME composer builds.

The setup answers are stored as the I6 intake facts the composer already reads (goal, allergies, food_preferences,
meal_times, exercise_time) - no second store. A fresh cycle is composed; a plan that already exists is adjusted in place
(meal times moved, items the user now avoids swapped for an eligible alternative) because composing is idempotent per
cycle. Consent-gated like every I6 write; the allergy answer is a hard prerequisite for nutrition (R-008).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i8 import plan_composer as pc
from backend.app.services.i8 import plan_settings as ps

_SLOT_FA = {"breakfast": "صبحانه", "lunch": "ناهار", "dinner": "شام", "snack": "میان‌وعده"}
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_AVOID_CUE = {"fa": "دوست ندارم", "en": "I don't like", "ar": "لا أحب"}
_NO_ALLERGY = {"fa": "ندارم", "en": "none", "ar": "لا يوجد"}


class PlanBuildError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _lang(language: Optional[str]) -> str:
    lang = (language or "fa").split("-")[0].lower()
    return lang if lang in ("fa", "en", "ar") else "en"


def _clean(text: Any, limit: int = 240) -> str:
    return " ".join(str(text or "").split())[:limit]


def _meal_times_text(times: dict) -> str:
    parts = []
    for slot in ("breakfast", "lunch", "dinner", "snack"):
        value = times.get(slot)
        if value is None:
            continue
        if not _HHMM.match(str(value)):
            raise PlanBuildError("MEAL_TIME_INVALID")
        parts.append(f"{_SLOT_FA[slot]} {value}")
    return "، ".join(parts)


def _avoid_text(raw: str, lang: str) -> str:
    """Free text of foods to avoid -> a clause the composer's preference parser reads as an avoid (needs a cue)."""
    text = _clean(raw)
    if not text:
        return ""
    low = text.lower()
    if any(cue in low for cue in pc._NEG_CUES):
        return text
    return f"{text} {_AVOID_CUE[lang]}"


def _write(db: Session, user_id: int, key: str, value: str) -> None:
    from backend.app.services.i6.memory_writes import write_fact

    write_fact(db, user_id, "intake", key, value, commit=True)


def _known_allergies(db: Session, user_id: int) -> bool:
    answers, _ = pc.read_answers(db, user_id)
    return bool(answers.get("allergies") or answers.get("medical_allergies"))


def _cycle_items(db: Session, user_id: int, domain: str) -> list[models.I8OperationalPlanAction]:
    rows = (
        db.query(models.I8OperationalPlanAction)
        .filter(
            models.I8OperationalPlanAction.user_id == int(user_id),
            models.I8OperationalPlanAction.action_domain == domain,
            models.I8OperationalPlanAction.status == "ACTIVE",
        )
        .all()
    )
    import json

    out = []
    for row in rows:
        try:
            pres = json.loads(row.presentation_json or "{}")
        except (TypeError, ValueError):
            continue
        if isinstance(pres, dict) and pres.get("source") == pc.SOURCE_TAG:
            out.append(row)
    return out


def _adjust_existing(db: Session, user_id: int, domain: str, constraints: pc.Constraints) -> dict:
    """Move times and swap now-avoided items on the plan that already exists. Never touches the user's own edits."""
    import json

    from backend.app.services.i8 import action_edit as ae

    moved = swapped = unsafe_fixed = 0
    for row in _cycle_items(db, user_id, domain):
        pres = json.loads(row.presentation_json)
        edit = pres.get("user_edit") if isinstance(pres.get("user_edit"), dict) else {}
        # SAFETY FIRST (R-008): a meal that holds an allergen the user has told us about is replaced by an eligible
        # alternative - or taken out when there is none - even when the user edited it earlier.
        if domain == "nutrition" and constraints.allergens:
            entry = next((m for m in pc.catalog()["meals"] if m["id"] == str(pres.get("item_id") or "")), None)
            if entry and set(entry.get("allergens") or []) & constraints.allergens:
                db.commit()
                try:
                    alts = ae.list_alternatives(db, actor_user_id=int(user_id), action_id=int(row.id), limit=1)
                    if alts:
                        ae.replace_action_item(db, actor_user_id=int(user_id), action_id=int(row.id), item_id=alts[0]["item_id"])
                    else:
                        ae.remove_action(db, actor_user_id=int(user_id), action_id=int(row.id))
                    unsafe_fixed += 1
                except ae.ActionEditError:
                    pass
                continue
        want = (
            constraints.meal_times.get(str(pres.get("meal_slot") or ""))
            if domain == "nutrition"
            else constraints.exercise_time
        )
        if want and want != pres.get("local_time") and not edit.get("time_moved_at") and pres.get("local_time"):
            pres["local_time"] = want
            row.presentation_json = json.dumps(pres, ensure_ascii=False, separators=(",", ":"))
            moved += 1
        if domain == "nutrition" and constraints.avoid_kw and not edit.get("replaced_at"):
            item_id = str(pres.get("item_id") or "")
            entry = next((m for m in pc.catalog()["meals"] if m["id"] == item_id), None)
            keywords = {pc._norm(k) for k in (entry or {}).get("keywords", [])}
            if keywords & {pc._norm(a) for a in constraints.avoid_kw}:
                db.commit()
                try:
                    alts = ae.list_alternatives(db, actor_user_id=int(user_id), action_id=int(row.id), limit=1)
                    if alts:
                        ae.replace_action_item(db, actor_user_id=int(user_id), action_id=int(row.id), item_id=alts[0]["item_id"])
                        swapped += 1
                except ae.ActionEditError:
                    pass
    db.commit()
    changed_days = _adjust_exercise_days(db, user_id, constraints) if domain == "exercise" else 0
    return {"moved": moved, "swapped": swapped, "days_changed": changed_days, "unsafe_fixed": unsafe_fixed}


def _adjust_exercise_days(db: Session, user_id: int, constraints: pc.Constraints) -> int:
    """The user chose other workout weekdays: take workouts off the days she dropped, put one on the days she added.
    Only open, future-or-today items; reviewed or user-edited items are never touched."""
    import json
    from datetime import date

    from backend.app.services.i8 import action_edit as ae
    from backend.app.services.i8.action_review import review_of

    chosen = constraints.workout_weekdays
    if not chosen:
        return 0
    changed = 0
    from datetime import datetime, timezone

    from backend.app.services.i8.local_day import local_today_for_user

    _tz, today = local_today_for_user(db, int(user_id))
    # a workout this adjustment took off a day earlier comes back when the user chooses that day again
    for row in (
        db.query(models.I8OperationalPlanAction)
        .filter(
            models.I8OperationalPlanAction.user_id == int(user_id),
            models.I8OperationalPlanAction.action_domain == "exercise",
            models.I8OperationalPlanAction.status == "CANCELLED",
        )
        .all()
    ):
        try:
            back = json.loads(row.presentation_json or "{}")
            local = date.fromisoformat(str(back.get("local_date")))
        except (TypeError, ValueError):
            continue
        if back.get("source") == pc.SOURCE_TAG and back.get("auto_removed") == "days" and local >= today and local.isoweekday() in chosen:
            back.pop("auto_removed", None)
            row.presentation_json = json.dumps(back, ensure_ascii=False, separators=(",", ":"))
            row.status = "ACTIVE"
            changed += 1
    db.commit()
    for row in _cycle_items(db, user_id, "exercise"):
        pres = json.loads(row.presentation_json)
        edit = pres.get("user_edit") if isinstance(pres.get("user_edit"), dict) else {}
        try:
            local = date.fromisoformat(str(pres.get("local_date")))
        except ValueError:
            continue
        if local < today or review_of(row) or edit:
            continue
        is_rest = pres.get("activity_type") == "rest"
        wanted = local.isoweekday() in chosen
        try:
            if wanted and is_rest:
                alts = ae.list_alternatives(db, actor_user_id=int(user_id), action_id=int(row.id), limit=1)
                if not alts:
                    continue
                ae.replace_action_item(db, actor_user_id=int(user_id), action_id=int(row.id), item_id=alts[0]["item_id"])
                db.refresh(row)
                pres = json.loads(row.presentation_json)
                pres["local_time"] = constraints.exercise_time
                row.presentation_json = json.dumps(pres, ensure_ascii=False, separators=(",", ":"))
                db.commit()
                changed += 1
            elif not wanted and not is_rest:
                pres["auto_removed"] = "days"  # marked so that choosing the day again restores it
                row.presentation_json = json.dumps(pres, ensure_ascii=False, separators=(",", ":"))
                row.status = "CANCELLED"
                row.updated_at = datetime.now(timezone.utc)
                db.commit()
                changed += 1
        except ae.ActionEditError:
            continue
    return changed


def build_plan(db: Session, user_id: int, domain: str, setup: dict, language: Optional[str] = None) -> dict[str, Any]:
    """Apply the setup and build (or adjust) this cycle's plan. Raises PlanBuildError / PlanSettingsError / ConsentDenied."""
    if domain not in ps.DOMAINS:
        raise PlanBuildError("DOMAIN_INVALID")
    lang = _lang(language)
    goal = _clean(setup.get("goal"), 120)
    if goal:
        _write(db, user_id, "goal", goal)
    if domain == "nutrition":
        if setup.get("no_allergies") is True:
            _write(db, user_id, "allergies", _NO_ALLERGY[lang])
        elif _clean(setup.get("allergies")):
            _write(db, user_id, "allergies", _clean(setup.get("allergies")))
        avoid = _avoid_text(setup.get("avoid") or "", lang)
        if avoid:
            _write(db, user_id, "food_preferences", avoid)
        times = setup.get("meal_times")
        if isinstance(times, dict) and times:
            text = _meal_times_text(times)
            if text:
                _write(db, user_id, "meal_times", text)
    else:
        exercise_time = setup.get("exercise_time")
        if exercise_time:
            if not _HHMM.match(str(exercise_time)):
                raise PlanBuildError("EXERCISE_TIME_INVALID")
            _write(db, user_id, "exercise_time", str(exercise_time))
    settings = ps.save_plan_settings(db, user_id, domain, dict(setup.get("settings") or {}), language)

    if domain == "nutrition" and not _known_allergies(db, user_id):
        return {"status": "NEEDS_INFO", "needs": ["allergies"], "settings": settings, "created": 0}

    answers, has_condition = pc.read_answers(db, user_id)
    constraints = pc.constraints_from_answers(answers, has_condition=has_condition)
    if domain == "exercise":
        constraints.workout_weekdays = pc._chosen_workout_days(db, user_id)
    existing = bool(_cycle_items(db, user_id, domain))
    adjusted = _adjust_existing(db, user_id, domain, constraints) if existing else {"moved": 0, "swapped": 0}
    result = pc.compose_week_plan(db, user_id=user_id, domain=domain, language=lang, constraints=constraints)
    if result.status != "ACTION_PERSISTED":
        return {"status": result.status, "settings": settings, "created": 0}
    ps.apply_settings_to_actions(db, user_id, domain, settings)
    return {
        "status": "BUILT" if result.created else "UPDATED",
        "created": result.created,
        "adjusted": adjusted,
        "settings": settings,
        "today": [{"slot": s, "local_time": t, "title": title, "detail": d} for s, t, title, d in result.today],
    }


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def free_exercise_time(meal_times: dict, preferred: Optional[str] = None) -> str:
    """A workout time at least an hour away from every meal, so the two plans do not collide."""
    meals = [_minutes(v) for v in meal_times.values() if _HHMM.match(str(v))]
    candidates = [c for c in ([preferred] if preferred else []) + ["17:00", "18:00", "19:00", "07:00", "06:30", "18:30"] if c and _HHMM.match(c)]
    for cand in candidates:
        if all(abs(_minutes(cand) - m) >= 60 for m in meals):
            return cand
    return candidates[0] if candidates else "17:00"


def build_pro(db: Session, user_id: int, setup: dict, language: Optional[str] = None) -> dict[str, Any]:
    """The professional plan: nutrition AND exercise from one set of answers - same goal, same reminder lead and review
    day, a workout time that does not collide with a meal. Allergies come first (nutrition NEEDS_INFO stops both)."""
    meal_times = dict(pc.parse_meal_times(_meal_times_text(setup.get("meal_times") or {})) if setup.get("meal_times") else pc._DEFAULT_MEAL_TIMES)
    nutrition = build_plan(db, user_id, "nutrition", dict(setup), language)
    if nutrition["status"] in ("NEEDS_INFO", "CONSENT_REQUIRED"):
        return {**nutrition, "mode": "pro"}
    settings = dict(setup.get("settings") or {})
    exercise_days = setup.get("exercise_days")
    ex_settings = {k: v for k, v in settings.items() if k != "days"}
    if exercise_days:
        ex_settings["days"] = exercise_days
    exercise = build_plan(
        db,
        user_id,
        "exercise",
        {
            "goal": setup.get("goal"),
            "exercise_time": free_exercise_time(meal_times, setup.get("exercise_time")),
            "settings": ex_settings,
        },
        language,
    )
    ok = nutrition["status"] in ("BUILT", "UPDATED") and exercise["status"] in ("BUILT", "UPDATED")
    return {"status": "BUILT" if ok else exercise["status"], "mode": "pro", "nutrition": nutrition, "exercise": exercise, "created": nutrition.get("created", 0) + exercise.get("created", 0)}
