"""A3 Lifestyle schedule — compact I8 active-action projection. No IDs. Schema-free."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.app.services.i8.action_completion import CANONICAL_TERMINAL_ACTION_STATUS
from backend.app.services.i8.local_day import (
    I8InvalidTimezoneError,
    I8TimezoneRequiredError,
    resolve_local_day_window,
)
from backend.app.services.i8.repository import I8OperationalRepository

_REPO = I8OperationalRepository()

_STATUS_MAP = {
    "ACTIVE": "upcoming",
    "COMPLETED": "done",
    CANONICAL_TERMINAL_ACTION_STATUS: "done",
    "SUPERSEDED": "cancelled",
    "EXPIRED": "cancelled",
    "CANCELLED": "cancelled",
    "FAILED": "cancelled",
}


def build_lifestyle_i8_schedule_projection(db: Session, user_id: int) -> dict[str, Any]:
    """Read-only governed I8 actions for My Schedule (distinct from UserEvent)."""
    try:
        window = resolve_local_day_window(db, int(user_id))
    except (I8TimezoneRequiredError, I8InvalidTimezoneError):
        return {"items": [], "plan_state": "unavailable"}

    plan = _REPO.get_active_plan(
        db, user_id=int(user_id), user_local_date=window.user_local_date
    )
    if plan is None:
        return {"items": [], "plan_state": "none"}

    actions = _REPO.list_actions_for_plan(db, user_id=int(user_id), plan_id=int(plan.id))
    items: list[dict[str, str]] = []
    for a in actions:
        raw = (a.status or "").upper()
        items.append(
            {
                "source": "i8_action",
                "title": (a.summary_text or a.action_type or "Action")[:256],
                "status": _STATUS_MAP.get(raw, "upcoming"),
                "domain": (a.action_domain or "lifestyle")[:32],
            }
        )
    return {"items": items, "plan_state": "active"}
