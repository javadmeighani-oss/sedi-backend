"""Flag-gated bounded eligible-user schedule scan (PD-I8-04B).

Scheduler role: trusted trigger producer only. I8 owns the decision.

Fair progression: in-process keyset cursor per schedule_rule_id (no DB schema).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.models import UserProfileCore
from backend.app.services.i8.feature_flags import (
    I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG,
    i8_proactive_schedule_scan_batch_size,
    i8_proactive_schedule_trigger_enabled,
)
from backend.app.services.i8.local_day import (
    I8InvalidTimezoneError,
    I8TimezoneRequiredError,
    resolve_local_day_window,
)
from backend.app.services.i8.schedule_adapter import adapt_trusted_schedule_trigger
from backend.app.services.i8.schedule_rules import DEFAULT_V1_SCHEDULE_RULE_ID
from backend.app.services.i8.trusted_trigger import (
    TRUSTED_PRODUCER_I8_SCHEDULE_SCAN_V1,
    TrustedTriggerV1,
    trusted_trigger_to_log_fields,
)

logger = logging.getLogger(__name__)

I8_SCHEDULE_SCAN_JOB_ID = "i8_proactive_schedule_scan_v1"

# In-process fair-scan cursors keyed by schedule_rule_id (single-process scheduler).
_scan_cursors: dict[str, int] = {}


def get_schedule_scan_cursor(schedule_rule_id: str) -> int:
    return int(_scan_cursors.get(schedule_rule_id, 0))


def set_schedule_scan_cursor(schedule_rule_id: str, after_user_id: int) -> None:
    _scan_cursors[schedule_rule_id] = int(after_user_id)


def reset_schedule_scan_cursors() -> None:
    """Test helper: clear in-process progression state."""
    _scan_cursors.clear()


@dataclass
class ScheduleScanRunStats:
    flag_enabled: bool
    flag_name: str = I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG
    batch_size: int = 0
    eligible_scanned: int = 0
    trigger_attempts: int = 0
    evaluation_success: int = 0
    action_created: int = 0
    no_action: int = 0
    reused: int = 0
    isolated_failures: int = 0
    completed: bool = False
    after_user_id: Optional[int] = None
    next_after_user_id: Optional[int] = None
    cursor_before: Optional[int] = None
    cursor_after: Optional[int] = None
    cursor_advanced: bool = False
    cursor_wrapped: bool = False
    cursor_unchanged: bool = True
    catastrophic_failure: bool = False
    failure_samples: list[str] = field(default_factory=list)

    def to_log_dict(self) -> dict:
        return {
            "flag_name": self.flag_name,
            "flag_enabled": self.flag_enabled,
            "batch_size": self.batch_size,
            "eligible_scanned": self.eligible_scanned,
            "trigger_attempts": self.trigger_attempts,
            "evaluation_success": self.evaluation_success,
            "action_created": self.action_created,
            "no_action": self.no_action,
            "reused": self.reused,
            "isolated_failures": self.isolated_failures,
            "completed": self.completed,
            "after_user_id": self.after_user_id,
            "next_after_user_id": self.next_after_user_id,
            "cursor_before": self.cursor_before,
            "cursor_after": self.cursor_after,
            "cursor_advanced": self.cursor_advanced,
            "cursor_wrapped": self.cursor_wrapped,
            "cursor_unchanged": self.cursor_unchanged,
            "catastrophic_failure": self.catastrophic_failure,
        }


def iter_eligible_schedule_user_ids(
    db: Session,
    *,
    after_user_id: int = 0,
    limit: int,
) -> list[int]:
    """Keyset page of users eligible for V1 schedule path.

    Eligibility (no new schema): UserProfileCore with non-empty timezone.
    Unbounded ``.all()`` over users is forbidden.
    """
    if limit < 1:
        return []
    rows = (
        db.query(UserProfileCore.user_id)
        .filter(
            UserProfileCore.user_id > int(after_user_id),
            UserProfileCore.timezone.isnot(None),
            UserProfileCore.timezone != "",
        )
        .order_by(UserProfileCore.user_id.asc())
        .limit(int(limit))
        .all()
    )
    return [int(r[0]) for r in rows]


def run_i8_proactive_schedule_scan(
    db: Session,
    *,
    after_user_id: int = 0,
    batch_size: int | None = None,
    schedule_rule_id: str = DEFAULT_V1_SCHEDULE_RULE_ID,
    now_utc: datetime | None = None,
) -> ScheduleScanRunStats:
    """One bounded scan tick. Flag OFF → zero work (no query)."""
    enabled = i8_proactive_schedule_trigger_enabled()
    size = int(batch_size) if batch_size is not None else i8_proactive_schedule_scan_batch_size()
    stats = ScheduleScanRunStats(
        flag_enabled=enabled,
        batch_size=size,
        after_user_id=int(after_user_id),
        cursor_before=int(after_user_id),
        cursor_after=int(after_user_id),
    )
    if not enabled:
        stats.completed = True
        stats.cursor_unchanged = True
        logger.info("i8_schedule_scan_skipped_flag_off %s", stats.to_log_dict())
        return stats

    scan_batch_id = str(uuid.uuid4())
    try:
        user_ids = iter_eligible_schedule_user_ids(db, after_user_id=after_user_id, limit=size)
    except Exception:
        stats.catastrophic_failure = True
        stats.completed = False
        stats.cursor_unchanged = True
        logger.exception(
            "i8_schedule_scan_catastrophic_query_failure after_user_id=%s",
            after_user_id,
        )
        raise

    stats.eligible_scanned = len(user_ids)
    if user_ids:
        stats.next_after_user_id = user_ids[-1]

    for user_id in user_ids:
        try:
            window = resolve_local_day_window(db, user_id, now_utc=now_utc)
            trigger = TrustedTriggerV1(
                producer_id=TRUSTED_PRODUCER_I8_SCHEDULE_SCAN_V1,
                user_id=user_id,
                trigger_family="schedule",
                schedule_rule_id=schedule_rule_id,
                user_local_date=window.user_local_date,
                producer_attempt_id=f"{scan_batch_id}:{user_id}",
                bounded_metadata={
                    "timezone_snapshot": window.timezone_snapshot,
                    "scan_batch_id": scan_batch_id,
                    "job_id": I8_SCHEDULE_SCAN_JOB_ID,
                },
            )
            stats.trigger_attempts += 1
            result = adapt_trusted_schedule_trigger(db, trigger)
            stats.evaluation_success += 1
            if result.reused:
                stats.reused += 1
            elif result.outcome == "ACTION_CREATED" or result.status == "ACTION_CREATED":
                stats.action_created += 1
            elif result.outcome == "NO_ACTION" or result.status == "NO_ACTION":
                stats.no_action += 1
            logger.info(
                "i8_schedule_trigger_ok %s status=%s outcome=%s reused=%s",
                trusted_trigger_to_log_fields(trigger),
                result.status,
                result.outcome,
                result.reused,
            )
        except (I8TimezoneRequiredError, I8InvalidTimezoneError) as exc:
            stats.isolated_failures += 1
            if len(stats.failure_samples) < 5:
                stats.failure_samples.append(f"user={user_id}:tz:{type(exc).__name__}")
            logger.warning(
                "i8_schedule_trigger_isolated_failure user_id=%s err=%s",
                user_id,
                type(exc).__name__,
            )
        except Exception as exc:  # noqa: BLE001 — isolate per user; continue batch
            stats.isolated_failures += 1
            if len(stats.failure_samples) < 5:
                stats.failure_samples.append(f"user={user_id}:{type(exc).__name__}")
            logger.exception(
                "i8_schedule_trigger_isolated_failure user_id=%s err=%s",
                user_id,
                type(exc).__name__,
            )

    stats.completed = True
    logger.info("i8_schedule_scan_completed %s", stats.to_log_dict())
    return stats


def apply_schedule_scan_cursor_progression(
    *,
    schedule_rule_id: str,
    stats: ScheduleScanRunStats,
) -> ScheduleScanRunStats:
    """Advance / wrap in-process cursor from a completed scan result.

    Rules:
    - flag OFF / incomplete / catastrophic → no change
    - empty page → wrap to 0
    - non-empty page → advance to last scanned user_id (partial failures OK)
    """
    before = get_schedule_scan_cursor(schedule_rule_id)
    stats.cursor_before = before
    if (
        not stats.flag_enabled
        or not stats.completed
        or stats.catastrophic_failure
    ):
        stats.cursor_after = before
        stats.cursor_unchanged = True
        stats.cursor_advanced = False
        stats.cursor_wrapped = False
        return stats

    if stats.eligible_scanned == 0:
        set_schedule_scan_cursor(schedule_rule_id, 0)
        stats.cursor_after = 0
        stats.cursor_wrapped = True
        stats.cursor_advanced = before != 0
        stats.cursor_unchanged = before == 0
        return stats

    nxt = int(stats.next_after_user_id or before)
    set_schedule_scan_cursor(schedule_rule_id, nxt)
    stats.cursor_after = nxt
    stats.cursor_advanced = nxt != before
    stats.cursor_wrapped = False
    stats.cursor_unchanged = nxt == before
    return stats


def run_i8_proactive_schedule_scan_job(
    *,
    schedule_rule_id: str = DEFAULT_V1_SCHEDULE_RULE_ID,
) -> ScheduleScanRunStats:
    """APScheduler entrypoint: fair bounded tick using in-process cursor."""
    from backend.app.database import get_db

    cursor_before = get_schedule_scan_cursor(schedule_rule_id)
    try:
        with next(get_db()) as db:
            stats = run_i8_proactive_schedule_scan(
                db,
                after_user_id=cursor_before,
                schedule_rule_id=schedule_rule_id,
                now_utc=datetime.now(timezone.utc),
            )
    except Exception:
        # Catastrophic failure: do not advance cursor.
        logger.exception(
            "i8_schedule_scan_job_catastrophic_failure cursor_before=%s rule=%s",
            cursor_before,
            schedule_rule_id,
        )
        raise

    return apply_schedule_scan_cursor_progression(
        schedule_rule_id=schedule_rule_id,
        stats=stats,
    )
