"""A3 Profile read-only summary projection — I6 + I8 authority reuse only.

No I7/I9. No IDs/reason codes. No mutation. Schema-free.
Frontend localizes row keys + status codes; does not infer from raw rows.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.app.services.i6.consent_service import get_memory_consent_status
from backend.app.services.i8.action_completion import CANONICAL_TERMINAL_ACTION_STATUS
from backend.app.services.i8.local_day import (
    I8InvalidTimezoneError,
    I8TimezoneRequiredError,
    resolve_local_day_window,
)
from backend.app.services.i8.repository import I8OperationalRepository

_REPO = I8OperationalRepository()


def _consent_row(consent: dict[str, Any]) -> dict[str, str]:
    raw = (consent.get("status") or "none").lower()
    if consent.get("granted") and raw == "active":
        status = "granted"
    elif raw in ("revoked", "expired"):
        status = raw
    else:
        status = "not_granted"
    return {"key": "memory_consent", "status": status}


def _perm_row(key: str, allowed: bool) -> dict[str, str]:
    return {"key": key, "status": "allowed" if allowed else "denied"}


def _i8_rows(db: Session, user_id: int) -> list[dict[str, str]]:
    try:
        window = resolve_local_day_window(db, user_id)
    except (I8TimezoneRequiredError, I8InvalidTimezoneError):
        return [
            {"key": "daily_plan", "status": "unavailable"},
            {"key": "plan_actions", "status": "unavailable"},
        ]

    plan = _REPO.get_active_plan(
        db, user_id=user_id, user_local_date=window.user_local_date
    )
    if plan is None:
        return [
            {"key": "daily_plan", "status": "none"},
            {"key": "plan_actions", "status": "none"},
        ]

    actions = _REPO.list_actions_for_plan(db, user_id=user_id, plan_id=int(plan.id))
    if not actions:
        return [
            {"key": "daily_plan", "status": "active"},
            {"key": "plan_actions", "status": "no_actions"},
        ]

    active = sum(1 for a in actions if (a.status or "").upper() == "ACTIVE")
    completed = sum(
        1
        for a in actions
        if (a.status or "").upper() == CANONICAL_TERMINAL_ACTION_STATUS
    )
    if active > 0:
        action_status = "in_progress"
    elif completed == len(actions):
        action_status = "completed"
    else:
        action_status = "partial"

    return [
        {"key": "daily_plan", "status": "active"},
        {"key": "plan_actions", "status": action_status},
    ]


def build_a3_profile_summary(db: Session, user_id: int) -> dict[str, Any]:
    """Compact user-facing rows for Gate3 Profile summary table."""
    consent = get_memory_consent_status(db, int(user_id))
    perms = consent.get("permissions") or {}
    rows: list[dict[str, str]] = [
        _consent_row(consent),
        _perm_row("memory_write", bool(perms.get("memory.write"))),
        _perm_row("memory_read", bool(perms.get("memory.read"))),
    ]
    rows.extend(_i8_rows(db, int(user_id)))
    # Fail-closed shape: only key/status strings; never IDs or internals.
    safe_rows = [
        {"key": str(r["key"]), "status": str(r["status"])}
        for r in rows
        if r.get("key") and r.get("status")
    ]
    return {"rows": safe_rows}
