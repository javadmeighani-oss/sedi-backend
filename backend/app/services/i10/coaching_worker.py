"""I10-B13 bounded I8 operational plan coaching worker — no plan invention."""

from __future__ import annotations

import logging
import os
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

# In-process fair cursor for optional scheduler progression mode.
_coaching_after_action_id: int = 0


def reset_coaching_scan_cursor() -> None:
    """Test helper: clear in-process coaching progression."""
    global _coaching_after_action_id
    _coaching_after_action_id = 0


def get_coaching_scan_cursor() -> int:
    return int(_coaching_after_action_id)


def coaching_scan_batch_size() -> int:
    raw = (os.getenv("I10_COACHING_SCAN_BATCH_SIZE") or "").strip()
    if not raw:
        return 100
    try:
        n = int(raw)
    except ValueError:
        return 100
    return max(1, min(500, n))


def coaching_scan_max_per_tick() -> int:
    raw = (os.getenv("I10_COACHING_SCAN_MAX_PER_TICK") or "").strip()
    if not raw:
        return 1000
    try:
        n = int(raw)
    except ValueError:
        return 1000
    return max(1, min(5000, n))


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
    after_action_id: int = 0,
    limit: Optional[int] = None,
) -> list[tuple[models.I8OperationalPlanAction, models.I8OperationalPlan]]:
    """List eligible actions. Optional keyset bound for capacity scans.

    Eligibility predicates unchanged. ``limit=None`` keeps prior behavior for
    callers that expect a full filtered result set (typically small / tests).
    """
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
            models.I8OperationalPlanAction.id > int(after_action_id),
        )
    )
    if user_id is not None:
        q = q.filter(models.I8OperationalPlanAction.user_id == user_id)
    q = q.order_by(models.I8OperationalPlanAction.id.asc())
    if limit is not None:
        q = q.limit(int(limit))
    rows = q.all()
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


def _advance_coaching_cursor(*, page_last_id: Optional[int], page_len: int, limit: int) -> None:
    global _coaching_after_action_id
    before = _coaching_after_action_id
    if page_len == 0:
        _coaching_after_action_id = 0
        logger.info(
            "i10_coaching_scan_cursor cursor_before=%s cursor_after=0 cursor_wrapped=true batch_size=%s",
            before,
            limit,
        )
        return
    nxt = int(page_last_id or before)
    _coaching_after_action_id = nxt
    logger.info(
        "i10_coaching_scan_cursor cursor_before=%s cursor_after=%s cursor_advanced=%s batch_size=%s page_len=%s",
        before,
        nxt,
        nxt != before,
        limit,
        page_len,
    )


def _process_pairs(db: Session, pairs, when: datetime) -> int:
    processed = 0
    for action, _plan in pairs:
        try:
            if process_single_coaching_action(db, action, now=when):
                processed += 1
            db.flush()
        except Exception:
            db.rollback()
            logger.exception("[I10-B13] action=%s processing failed", action.id)
    return processed


def process_i8_coaching_followups(
    db: Session,
    *,
    now: Optional[datetime] = None,
    user_id: Optional[int] = None,
    force: bool = False,
    after_action_id: Optional[int] = None,
    limit: Optional[int] = None,
    use_inprocess_cursor: bool = False,
) -> int:
    """Process due persisted I8 plan actions — no plan invention, no raw chat.

    Default full-population path: same-tick keyset pages up to max_per_tick.
    Optional ``use_inprocess_cursor=True`` enables cross-tick fair progression
    (SAFE_ONLY_SINGLE_BACKGROUND_PROCESS).
    """
    if not force and not coaching_followup_enabled():
        return 0
    when = now or datetime.now(timezone.utc)

    if user_id is not None:
        pairs = list_eligible_coaching_actions(db, now=when, user_id=user_id)
        return _process_pairs(db, pairs, when)

    batch = int(limit) if limit is not None else coaching_scan_batch_size()
    single_page = use_inprocess_cursor or after_action_id is not None or limit is not None

    if single_page:
        cursor = (
            int(after_action_id)
            if after_action_id is not None
            else (get_coaching_scan_cursor() if use_inprocess_cursor else 0)
        )
        when_n = _normalize_utc(when)
        raw_rows = (
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
                models.I8OperationalPlanAction.valid_from <= when_n,
                models.I8OperationalPlanAction.valid_until >= when_n,
                models.I8OperationalPlanAction.expires_at > when_n,
                models.I8OperationalPlanAction.id > cursor,
            )
            .order_by(models.I8OperationalPlanAction.id.asc())
            .limit(batch)
            .all()
        )
        raw_page_len = len(raw_rows)
        page_last_id = int(raw_rows[-1][0].id) if raw_rows else None
        if use_inprocess_cursor and after_action_id is None:
            _advance_coaching_cursor(
                page_last_id=page_last_id,
                page_len=raw_page_len,
                limit=batch,
            )
        pairs = [
            (action, plan)
            for action, plan in raw_rows
            if is_action_eligible(action, plan, now=when)
        ]
        processed = _process_pairs(db, pairs, when)
        logger.info(
            "i10_coaching_scan_completed mode=single_page eligible=%s processed=%s raw_page_len=%s",
            len(pairs),
            processed,
            raw_page_len,
        )
        return processed

    # Same-tick multi-page (default)
    after = 0
    scanned = 0
    processed = 0
    max_per_tick = coaching_scan_max_per_tick()
    while scanned < max_per_tick:
        page_limit = min(batch, max_per_tick - scanned)
        when_n = _normalize_utc(when)
        raw_rows = (
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
                models.I8OperationalPlanAction.valid_from <= when_n,
                models.I8OperationalPlanAction.valid_until >= when_n,
                models.I8OperationalPlanAction.expires_at > when_n,
                models.I8OperationalPlanAction.id > after,
            )
            .order_by(models.I8OperationalPlanAction.id.asc())
            .limit(page_limit)
            .all()
        )
        if not raw_rows:
            break
        scanned += len(raw_rows)
        after = int(raw_rows[-1][0].id)
        pairs = [
            (action, plan)
            for action, plan in raw_rows
            if is_action_eligible(action, plan, now=when)
        ]
        processed += _process_pairs(db, pairs, when)
        if len(raw_rows) < page_limit:
            break

    logger.info(
        "i10_coaching_scan_completed mode=same_tick scanned=%s processed=%s max_per_tick=%s",
        scanned,
        processed,
        max_per_tick,
    )
    return processed
