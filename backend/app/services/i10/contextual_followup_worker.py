"""I10-B12 bounded CareFollowUpTask worker — due_at eligibility, no raw chat reads."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.contextual_followup_i10_adapter import (
    build_followup_occurrence_key,
    enqueue_contextual_followup_notification,
)
from backend.app.services.i10.contextual_followup_task_meta import (
    BoundedFollowUpMeta,
    pack_description,
    with_notification_id,
)
from backend.app.services.i10.contextual_followup_types import (
    FollowUpTaskSource,
    FollowUpTaskStatus,
)
from backend.app.services.i10.event_reminder_i10_adapter import evaluate_post_event_follow_up_eligible
from backend.app.services.section10.feature_flags import contextual_followup_enabled

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({
    FollowUpTaskStatus.DONE.value,
    FollowUpTaskStatus.CANCELLED.value,
    FollowUpTaskStatus.NOTIFIED.value,
})


def is_task_eligible(task: models.CareFollowUpTask, now: datetime) -> bool:
    if task.status in TERMINAL_STATUSES:
        return False
    if task.status != FollowUpTaskStatus.OPEN.value:
        return False
    if task.due_at is None:
        return False
    due = task.due_at
    if due.tzinfo is not None:
        due = due.replace(tzinfo=None)
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now
    return now_naive >= due


def create_structured_follow_up_task(
    db: Session,
    *,
    user_id: int,
    title: str,
    due_at: datetime,
    source: FollowUpTaskSource,
    follow_up_kind: str,
    description: Optional[str] = None,
    user_event_id: Optional[int] = None,
    source_notification_id: Optional[int] = None,
) -> models.CareFollowUpTask:
    """Persist governed follow-up task with bounded metadata."""
    now = datetime.utcnow()
    meta = BoundedFollowUpMeta(
        follow_up_kind=follow_up_kind,
        user_event_id=user_event_id,
        source_notification_id=source_notification_id,
    )
    row = models.CareFollowUpTask(
        user_id=user_id,
        title=title.strip()[:256],
        description=pack_description(description, meta),
        status=FollowUpTaskStatus.OPEN.value,
        due_at=due_at,
        source=source.value,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def create_post_event_follow_up_task(
    db: Session,
    *,
    user_id: int,
    event: models.UserEvent,
    due_at: datetime,
    source_notification_id: Optional[int] = None,
) -> Optional[models.CareFollowUpTask]:
    """Bounded post-event handoff — does not assert attendance."""
    if not evaluate_post_event_follow_up_eligible(event, due_at):
        return None
    title = (event.title or "Medical appointment")[:256]
    return create_structured_follow_up_task(
        db,
        user_id=user_id,
        title=title,
        due_at=due_at,
        source=FollowUpTaskSource.POST_EVENT,
        follow_up_kind="post_event",
        user_event_id=event.id,
        source_notification_id=source_notification_id,
    )


def process_single_follow_up_task(
    db: Session,
    task: models.CareFollowUpTask,
    *,
    now: datetime,
) -> bool:
    if not is_task_eligible(task, now):
        return False
    occurrence_key = build_followup_occurrence_key(task_id=task.id)
    existing = (
        db.query(models.I10NotificationDecision.id)
        .filter(
            models.I10NotificationDecision.candidate_key == occurrence_key,
            models.I10NotificationDecision.recipient_user_id == task.user_id,
            models.I10NotificationDecision.decision == "SEND",
        )
        .first()
    )
    if existing:
        if task.status == FollowUpTaskStatus.OPEN.value:
            task.status = FollowUpTaskStatus.NOTIFIED.value
            task.updated_at = datetime.utcnow()
        return False

    notif = enqueue_contextual_followup_notification(db, task=task)
    if notif is None:
        return False

    task.status = FollowUpTaskStatus.NOTIFIED.value
    task.description = with_notification_id(task.description, notif.id)
    task.updated_at = datetime.utcnow()
    return True


def process_due_follow_up_tasks(db: Session, *, now: Optional[datetime] = None) -> int:
    """Process open CareFollowUpTask rows whose due_at has passed."""
    if not contextual_followup_enabled():
        return 0
    when = now or datetime.utcnow()
    rows = (
        db.query(models.CareFollowUpTask)
        .filter(
            models.CareFollowUpTask.status == FollowUpTaskStatus.OPEN.value,
            models.CareFollowUpTask.due_at.isnot(None),
            models.CareFollowUpTask.due_at <= when,
        )
        .order_by(models.CareFollowUpTask.due_at.asc())
        .all()
    )
    processed = 0
    for task in rows:
        try:
            if process_single_follow_up_task(db, task, now=when):
                processed += 1
            db.flush()
        except Exception:
            db.rollback()
            logger.exception("[I10-B12] task=%s processing failed", task.id)
    return processed
