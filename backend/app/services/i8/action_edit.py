"""P8: the user's own edits of a plan item (I8 owns the plan; the user may adjust it from the plan page).

Edits, all owner-scoped and all on a still-ACTIVE action:
- move its time of day (``presentation_json.local_time``, which the I10 coaching worker already reads to time the
  reminder and the "did you do it?" follow-up);
- replace it with another item of the SAME catalogue the composer uses, filtered by the user's own allergies,
  dislikes and limits (alternatives are offered in the page; the composer's rules still decide what is eligible);
- correct its title / note / duration in the user's own words;
- take it out of this week (status ``CANCELLED``, a value of the existing action vocabulary; every projection and the
  coaching worker only read ACTIVE/COMPLETED actions, so it simply disappears).
A small ``user_edit`` marker records that the user — not the composer — changed the item, and Sedi reads those markers
back into the chat context (``plan_changes_hint``), so she knows what the user changed and talks about the NEW plan.
No migration.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models

LOCAL_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_TITLE = 120
MAX_NOTE = 240
DURATION_RANGE = (5, 180)
ALTERNATIVES_LIMIT = 3


class ActionEditError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _load(raw: Optional[str]) -> dict:
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _dump(pres: dict) -> str:
    return json.dumps(pres, ensure_ascii=False, separators=(",", ":"))


def _owned_active(db: Session, actor_user_id: int, action_id: int) -> models.I8OperationalPlanAction:
    action = (
        db.query(models.I8OperationalPlanAction)
        .filter(models.I8OperationalPlanAction.id == int(action_id))
        .first()
    )
    if action is None:
        raise ActionEditError("ACTION_NOT_FOUND")
    if int(action.user_id) != int(actor_user_id):
        raise ActionEditError("ACTION_OWNER_MISMATCH")
    if (action.status or "").upper() != "ACTIVE":
        raise ActionEditError("ACTION_NOT_EDITABLE")
    return action


def _stamp(pres: dict, **marks: str) -> None:
    edit = pres.get("user_edit")
    edit = edit if isinstance(edit, dict) else {}
    edit.update(marks)
    pres["user_edit"] = edit


def _clean(text: Optional[str], limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


# ---------------------------------------------------------------------------------------------------------------------
# time / text / duration / removal
# ---------------------------------------------------------------------------------------------------------------------
def edit_action(
    db: Session,
    *,
    actor_user_id: int,
    action_id: int,
    local_time: Optional[str] = None,
    title: Optional[str] = None,
    note: Optional[str] = None,
    duration_minutes: Optional[int] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Any subset of: new time (HH:MM), the user's own title, the user's own note, a new duration (exercise)."""
    if local_time is None and title is None and note is None and duration_minutes is None:
        raise ActionEditError("NOTHING_TO_UPDATE")
    if local_time is not None and not LOCAL_TIME.match(str(local_time)):
        raise ActionEditError("INVALID_TIME")
    new_title = _clean(title, MAX_TITLE) if title is not None else None
    if title is not None and not new_title:
        raise ActionEditError("INVALID_TITLE")
    if duration_minutes is not None and not (DURATION_RANGE[0] <= int(duration_minutes) <= DURATION_RANGE[1]):
        raise ActionEditError("INVALID_DURATION")
    action = _owned_active(db, actor_user_id, action_id)
    when = now or datetime.now(timezone.utc)
    pres = _load(action.presentation_json)
    marks: dict[str, str] = {}
    out: dict[str, Any] = {"action_id": int(action_id)}
    if local_time is not None:
        pres["local_time"] = local_time
        marks["time_moved_at"] = when.isoformat()
        out["local_time"] = local_time
    if new_title is not None:
        marks["title_edited_at"] = when.isoformat()
        marks["previous_title"] = _clean(action.summary_text, MAX_TITLE)
        pres["title"] = new_title
        if "activity_title" in pres:
            pres["activity_title"] = new_title
        action.summary_text = new_title
        out["title"] = new_title
    if note is not None:
        pres["detail"] = _clean(note, MAX_NOTE)
        marks["note_edited_at"] = when.isoformat()
        out["note"] = pres["detail"]
    if duration_minutes is not None:
        if (action.action_domain or "").lower() != "exercise":
            raise ActionEditError("DURATION_ONLY_FOR_EXERCISE")
        pres["duration_minutes"] = int(duration_minutes)
        marks["duration_edited_at"] = when.isoformat()
        out["duration_minutes"] = int(duration_minutes)
    _stamp(pres, **marks)
    action.presentation_json = _dump(pres)
    action.updated_at = when
    db.commit()
    return out


def move_action_time(
    db: Session, *, actor_user_id: int, action_id: int, local_time: str, now: Optional[datetime] = None
) -> dict:
    return edit_action(db, actor_user_id=actor_user_id, action_id=action_id, local_time=local_time, now=now)


def remove_action(db: Session, *, actor_user_id: int, action_id: int, now: Optional[datetime] = None) -> dict:
    action = _owned_active(db, actor_user_id, action_id)
    when = now or datetime.now(timezone.utc)
    pres = _load(action.presentation_json)
    _stamp(pres, removed_at=when.isoformat(), previous_title=_clean(action.summary_text, MAX_TITLE))
    action.presentation_json = _dump(pres)
    action.status = "CANCELLED"
    action.updated_at = when
    db.commit()
    return {"action_id": int(action_id), "removed": True}


# ---------------------------------------------------------------------------------------------------------------------
# alternatives (same catalogue and the same user constraints as the composer)
# ---------------------------------------------------------------------------------------------------------------------
def _user_lang(db: Session, user_id: int) -> str:
    row = db.query(models.User.preferred_language).filter(models.User.id == user_id).first()
    raw = ((row[0] if row else None) or "fa").strip().lower().split("-")[0]
    return raw if raw in ("fa", "en", "ar") else "en"


def _current_item_id(action: models.I8OperationalPlanAction, pres: dict) -> Optional[str]:
    if pres.get("item_id"):
        return str(pres["item_id"])
    from backend.app.services.i8 import plan_composer as pc

    title = _clean(action.summary_text, MAX_TITLE)
    for item_id, by_lang in pc.catalog()["texts"].items():
        if any(str(v[0]).strip() == title for v in by_lang.values()):
            return str(item_id)
    return None


def _pool(db: Session, action: models.I8OperationalPlanAction, pres: dict) -> list[dict]:
    """Eligible catalogue items for this action, never the item it already is. Allergens are never relaxed."""
    from backend.app.services.i8 import plan_composer as pc

    answers, has_condition = pc.read_answers(db, int(action.user_id))
    constraints = pc.constraints_from_answers(answers, has_condition=has_condition)
    domain = (action.action_domain or "").lower()
    current = _current_item_id(action, pres)
    if domain == "nutrition":
        slot = str(pres.get("meal_slot") or "")
        pool: list[dict] = []
        for relax in (0, 1, 2):  # relax budget / prep time, never allergens and never the user's dislikes (relax 3)
            pool = pc._meal_candidates(slot, constraints, relax)
            if len([it for it in pool if it["id"] != current]) >= ALTERNATIVES_LIMIT:
                break
    elif domain == "exercise":
        pool = [it for it in pc._exercise_candidates(constraints) if it.get("type") != "rest"]
    else:
        raise ActionEditError("ACTION_NOT_REPLACEABLE")
    return [it for it in pool if it["id"] != current]


def _ranked(pool: list[dict], action_id: int) -> list[dict]:
    """Stable, per-action order so the same item shows the same suggestions until the plan changes."""
    return sorted(pool, key=lambda it: hashlib.sha256(f"{action_id}:{it['id']}".encode()).hexdigest())


def list_alternatives(
    db: Session, *, actor_user_id: int, action_id: int, limit: int = ALTERNATIVES_LIMIT
) -> list[dict]:
    from backend.app.services.i8 import plan_composer as pc

    action = _owned_active(db, actor_user_id, action_id)
    pres = _load(action.presentation_json)
    if pres.get("source") != pc.SOURCE_TAG:
        return []  # only composer-built items have a catalogue to choose from
    lang = _user_lang(db, actor_user_id)
    slot = "exercise" if (action.action_domain or "").lower() == "exercise" else str(pres.get("meal_slot") or "")
    out = []
    for it in _ranked(_pool(db, action, pres), int(action.id))[: max(1, min(int(limit), 5))]:
        title, detail = pc.render_item({"item": it, "slot": slot, "why": []}, lang)
        out.append({"item_id": it["id"], "title": title, "detail": detail[:220]})
    return out


def replace_action_item(
    db: Session, *, actor_user_id: int, action_id: int, item_id: str, now: Optional[datetime] = None
) -> dict:
    from backend.app.services.i8 import plan_composer as pc

    action = _owned_active(db, actor_user_id, action_id)
    pres = _load(action.presentation_json)
    if pres.get("source") != pc.SOURCE_TAG:
        raise ActionEditError("ACTION_NOT_REPLACEABLE")
    chosen = next((it for it in _pool(db, action, pres) if it["id"] == str(item_id)), None)
    if chosen is None:
        raise ActionEditError("ITEM_NOT_ELIGIBLE")
    lang = _user_lang(db, actor_user_id)
    domain = (action.action_domain or "").lower()
    slot = "exercise" if domain == "exercise" else str(pres.get("meal_slot") or "")
    title, detail = pc.render_item({"item": chosen, "slot": slot, "why": []}, lang)
    when = now or datetime.now(timezone.utc)
    _stamp(pres, replaced_at=when.isoformat(), previous_title=_clean(action.summary_text, MAX_TITLE))
    pres.update({"title": title, "detail": detail, "item_id": chosen["id"]})
    if domain == "exercise":
        pres.update({"activity_title": title, "activity_type": chosen["type"]})
        minutes = int(chosen.get("minutes", 0) or 0)
        pres["duration_minutes"] = minutes or None
    action.summary_text = title[:256]
    action.presentation_json = _dump(pres)
    action.updated_at = when
    db.commit()
    return {"action_id": int(action_id), "item_id": chosen["id"], "title": title, "detail": detail}


# ---------------------------------------------------------------------------------------------------------------------
# Sedi reads the user's plan edits back (chat context)
# ---------------------------------------------------------------------------------------------------------------------
def recent_user_plan_edits(
    db: Session, user_id: int, *, now: Optional[datetime] = None, days: int = 3, limit: int = 6
) -> list[dict]:
    since = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    rows = (
        db.query(models.I8OperationalPlanAction)
        .filter(
            models.I8OperationalPlanAction.user_id == int(user_id),
            models.I8OperationalPlanAction.updated_at >= since,
            models.I8OperationalPlanAction.presentation_json.like('%"user_edit"%'),
        )
        .order_by(models.I8OperationalPlanAction.updated_at.desc())
        .limit(40)
        .all()
    )
    out: list[dict] = []
    for r in rows:
        pres = _load(r.presentation_json)
        edit = pres.get("user_edit") if isinstance(pres.get("user_edit"), dict) else {}
        kinds = [k for k in ("replaced_at", "title_edited_at", "note_edited_at", "time_moved_at", "duration_edited_at", "removed_at") if edit.get(k)]
        if not kinds:
            continue
        out.append(
            {
                "domain": (r.action_domain or "").lower(),
                "title": _clean(r.summary_text, 80),
                "previous_title": _clean(edit.get("previous_title"), 80),
                "slot": str(pres.get("meal_slot") or ""),
                "local_time": str(pres.get("local_time") or ""),
                "removed": "removed_at" in kinds,
                "replaced": "replaced_at" in kinds or "title_edited_at" in kinds,
                "moved": "time_moved_at" in kinds,
                "note": "note_edited_at" in kinds,
                "duration": pres.get("duration_minutes") if "duration_edited_at" in kinds else None,
            }
        )
        if len(out) >= limit:
            break
    return out


def plan_changes_hint(db: Session, user_id: int, language: Optional[str], *, now: Optional[datetime] = None) -> str:
    """One bounded prompt line: what the user changed in their plan themselves. '' when nothing / on any problem."""
    try:
        edits = recent_user_plan_edits(db, user_id, now=now)
    except Exception:
        return ""
    if not edits:
        return ""
    lang = (language or "fa").strip().lower().split("-")[0]
    lang = lang if lang in ("fa", "en", "ar") else "en"
    parts: list[str] = []
    for e in edits:
        t = f"«{e['title']}»"
        if e["removed"]:
            parts.append({"fa": f"{t} را از برنامه حذف کرد", "ar": f"حذف {t} من الخطة", "en": f"removed {t} from the plan"}[lang])
        elif e["replaced"] and e["previous_title"] and e["previous_title"] != e["title"]:
            old = f"«{e['previous_title']}»"
            parts.append({"fa": f"{old} را با {t} عوض کرد", "ar": f"استبدل {old} بـ {t}", "en": f"replaced {old} with {t}"}[lang])
        elif e["moved"] and e["local_time"]:
            parts.append({"fa": f"ساعت {t} را به {e['local_time']} برد", "ar": f"نقل وقت {t} إلى {e['local_time']}", "en": f"moved {t} to {e['local_time']}"}[lang])
        elif e["duration"]:
            parts.append({"fa": f"مدت {t} را {e['duration']} دقیقه کرد", "ar": f"جعل مدة {t} {e['duration']} دقيقة", "en": f"set {t} to {e['duration']} minutes"}[lang])
        else:
            parts.append({"fa": f"{t} را اصلاح کرد", "ar": f"عدّل {t}", "en": f"edited {t}"}[lang])
    joined = "؛ ".join(parts) if lang != "en" else "; ".join(parts)
    if lang == "fa":
        return (
            f"[تغییرهای_برنامه_توسط_کاربر] کاربر خودش در صفحه‌ی برنامه این تغییرها را داده: {joined}. "
            "نسخه‌ی جدید برنامه معتبر است؛ بر همان اساس حرف بزن، تغییرها را بدون نقد بپذیر و چیزی را که حذف یا عوض کرده دوباره پیشنهاد نکن."
        )
    if lang == "ar":
        return (
            f"[تغييرات_الخطة_من_المستخدم] أجرى المستخدم بنفسه في صفحة الخطة هذه التغييرات: {joined}. "
            "النسخة الجديدة هي المعتمدة؛ تحدثي على أساسها وتقبّلي التغييرات ولا تقترحي ما حذفه أو استبدله."
        )
    return (
        f"[USER_PLAN_CHANGES] The user changed their plan themselves on the plan page: {joined}. "
        "The new version is the valid one; talk from it, accept the changes without second-guessing and do not suggest what they removed or replaced."
    )
