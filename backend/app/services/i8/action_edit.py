"""P8: the user's own edits of a plan item (I8 owns the plan; the user may adjust it from the plan page).

Two edits only, both owner-scoped and both on a still-ACTIVE action:
- move its time of day (``presentation_json.local_time``, which the I10 coaching worker already reads to time the
  reminder and the "did you do it?" follow-up);
- take it out of this week (status ``CANCELLED``, a value of the existing action vocabulary; every projection and the
  coaching worker only read ACTIVE/COMPLETED actions, so it simply disappears).
A small ``user_edit`` marker records that the user — not the composer — changed the item. No migration.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models

LOCAL_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


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


def _stamp(pres: dict, key: str, when: datetime) -> None:
    edit = pres.get("user_edit")
    edit = edit if isinstance(edit, dict) else {}
    edit[key] = when.isoformat()
    pres["user_edit"] = edit


def move_action_time(
    db: Session, *, actor_user_id: int, action_id: int, local_time: str, now: Optional[datetime] = None
) -> dict:
    if not LOCAL_TIME.match(str(local_time or "")):
        raise ActionEditError("INVALID_TIME")
    action = _owned_active(db, actor_user_id, action_id)
    when = now or datetime.now(timezone.utc)
    pres = _load(action.presentation_json)
    pres["local_time"] = local_time
    _stamp(pres, "time_moved_at", when)
    action.presentation_json = json.dumps(pres, ensure_ascii=False, separators=(",", ":"))
    action.updated_at = when
    db.commit()
    return {"action_id": int(action_id), "local_time": local_time}


def remove_action(db: Session, *, actor_user_id: int, action_id: int, now: Optional[datetime] = None) -> dict:
    action = _owned_active(db, actor_user_id, action_id)
    when = now or datetime.now(timezone.utc)
    pres = _load(action.presentation_json)
    _stamp(pres, "removed_at", when)
    action.presentation_json = json.dumps(pres, ensure_ascii=False, separators=(",", ":"))
    action.status = "CANCELLED"
    action.updated_at = when
    db.commit()
    return {"action_id": int(action_id), "removed": True}
