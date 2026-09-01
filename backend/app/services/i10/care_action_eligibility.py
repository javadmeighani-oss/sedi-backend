"""I10-B15 managed-subject CARE_ACTION eligibility — persisted I8 action only."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app import models

CARE_ACTION_DOMAINS = frozenset(
    {
        "nutrition",
        "exercise",
        "routine",
        "lifestyle",
        "wellbeing",
        "cross_domain",
    }
)


def _normalize_utc(when: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def is_managed_care_action_eligible(
    action: models.I8OperationalPlanAction,
    plan: models.I8OperationalPlan,
    *,
    now: datetime,
) -> bool:
    """Governed I8 validity only — no invention, no completion inference."""
    if plan.status != "ACTIVE" or action.status != "ACTIVE":
        return False
    if action.action_domain not in CARE_ACTION_DOMAINS:
        return False
    if action.safety_state != "SAFE" or action.clarification_required:
        return False
    now_utc = _normalize_utc(now)
    for bound in (action.valid_from, action.valid_until, action.expires_at):
        if bound is not None and bound.tzinfo is None:
            pass
    vf = action.valid_from
    vu = action.valid_until
    ex = action.expires_at
    if vf is not None and vf.tzinfo is None:
        vf = vf.replace(tzinfo=timezone.utc)
    if vu is not None and vu.tzinfo is None:
        vu = vu.replace(tzinfo=timezone.utc)
    if ex is not None and ex.tzinfo is None:
        ex = ex.replace(tzinfo=timezone.utc)
    if vf is not None and now_utc < vf:
        return False
    if vu is not None and now_utc > vu:
        return False
    if ex is not None and now_utc > ex:
        return False
    return True
