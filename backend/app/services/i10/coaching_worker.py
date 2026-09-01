"""I10-B13 bounded I8 operational plan coaching worker — no plan invention."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.coaching_followup_types import resolve_coaching_domain
from backend.app.services.i10.coaching_i10_adapter import (
    build_coaching_occurrence_key,
    enqueue_coaching_followup_notification,
)
from backend.app.services.section10.feature_flags import coaching_followup_enabled

logger = logging.getLogger(__name__)


def _normalize_utc(when: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _load_i7_daily_flag(db: Session, user_id: int) -> bool:
    row = (
        db.query(models.UserPeriodSummary)
        .filter(
            models.UserPeriodSummary.user_id == user_id,
            models.UserPeriodSummary.summary_type == "DAILY",
            models.UserPeriodSummary.status == "active",
            models.UserPeriodSummary.finalized_at.isnot(None),
        )
        .order_by(models.UserPeriodSummary.period_start.desc())
        .limit(1)
        .first()
    )
    return row is not None


def is_action_eligible(
    action: models.I8OperationalPlanAction,
    plan: models.I8OperationalPlan,
    *,
    now: datetime,
) -> bool:
    if plan.status != "ACTIVE" or action.status != "ACTIVE":
        return False
    if action.safety_state != "SAFE" or action.clarification_required:
        return False
    if resolve_coaching_domain(action.action_domain) is None:
        return False
    now_utc = _normalize_utc(now)
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


def list_eligible_coaching_actions(
    db: Session,
    *,
    now: datetime,
    user_id: Optional[int] = None,
) -> list[tuple[models.I8OperationalPlanAction, models.I8OperationalPlan]]:
    when = _normalize_utc(now)
    q = (
        db.query(models.I8OperationalPlanAction, models.I8OperationalPlan)
        .join(
            models.I8OperationalPlan,
            models.I8OperationalPlan.id == models.I8OperationalPlanAction.plan_id,
        )
        .filter(
            models.I8OperationalPlanAction.status == "ACTIVE",
            models.I8OperationalPlan.status == "ACTIVE",
            models.I8OperationalPlanAction.safety_state == "SAFE",
            models.I8OperationalPlanAction.clarification_required.is_(False),
            models.I8OperationalPlanAction.valid_from <= when,
            models.I8OperationalPlanAction.valid_until >= when,
            models.I8OperationalPlanAction.expires_at > when,
        )
    )
    if user_id is not None:
        q = q.filter(models.I8OperationalPlanAction.user_id == user_id)
    rows = q.order_by(models.I8OperationalPlanAction.id.asc()).all()
    return [(action, plan) for action, plan in rows if is_action_eligible(action, plan, now=when)]


def process_single_coaching_action(
    db: Session,
    action: models.I8OperationalPlanAction,
    *,
    now: datetime,
) -> bool:
    occurrence_key = build_coaching_occurrence_key(
        action_id=int(action.id),
        valid_from_iso=action.valid_from.isoformat() if action.valid_from else str(action.id),
    )
    existing = (
        db.query(models.I10NotificationDecision.id)
        .filter(
            models.I10NotificationDecision.candidate_key == occurrence_key,
            models.I10NotificationDecision.recipient_user_id == action.user_id,
            models.I10NotificationDecision.decision == "SEND",
        )
        .first()
    )
    if existing:
        return False
    i7_flag = _load_i7_daily_flag(db, action.user_id)
    notif = enqueue_coaching_followup_notification(
        db, action=action, i7_continuity_available=i7_flag
    )
    return notif is not None


def process_i8_coaching_followups(
    db: Session,
    *,
    now: Optional[datetime] = None,
    user_id: Optional[int] = None,
    force: bool = False,
) -> int:
    """Process due persisted I8 plan actions — no plan invention, no raw chat."""
    if not force and not coaching_followup_enabled():
        return 0
    when = now or datetime.now(timezone.utc)
    processed = 0
    for action, _plan in list_eligible_coaching_actions(db, now=when, user_id=user_id):
        try:
            if process_single_coaching_action(db, action, now=when):
                processed += 1
            db.flush()
        except Exception:
            db.rollback()
            logger.exception("[I10-B13] action=%s processing failed", action.id)
    return processed
