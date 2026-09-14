"""Notification + I10 decision retention foundation (G1).

Policy (LOCKED):
- FULL_NOTIFICATION_CONTENT_RETENTION_DAYS = 180
- I10_DECISION_AUDIT_RETENTION_DAYS = 365

Automatic production scheduling is OFF by default.
FK behavior (models):
- notification_feedback.notification_id → CASCADE
- interaction_events.source_notification_id → SET NULL
- medication_dose_occurrences.source_notification_id → SET NULL
- i10_notification_decisions.notification_id → SET NULL
- caregiver_notification_intents.notification_id → SET NULL
- notifications.i10_policy_decision_id → SET NULL on decision delete
- caregiver_notification_intents.i10_decision_id → SET NULL
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.app.models import I10NotificationDecision, Notification

logger = logging.getLogger(__name__)

FULL_NOTIFICATION_CONTENT_RETENTION_DAYS = int(
    os.getenv("SEDI_NOTIFICATION_CONTENT_RETENTION_DAYS", "180")
)
I10_DECISION_AUDIT_RETENTION_DAYS = int(
    os.getenv("SEDI_I10_DECISION_AUDIT_RETENTION_DAYS", "365")
)
DEFAULT_BATCH_SIZE = int(os.getenv("SEDI_RETENTION_BATCH_SIZE", "200"))

# Production scheduler activation is NOT authorized in G1.
RETENTION_PRUNE_ENABLED = os.getenv("SEDI_NOTIFICATION_RETENTION_PRUNE_ENABLED", "").lower() in (
    "1",
    "true",
    "yes",
)


@dataclass(frozen=True)
class RetentionCutoffs:
    content_cutoff: datetime
    decision_cutoff: datetime


@dataclass(frozen=True)
class RetentionPruneResult:
    notifications_deleted: int
    decisions_deleted: int
    dry_run: bool
    enabled: bool
    content_cutoff: datetime
    decision_cutoff: datetime


def retention_cutoffs(now: Optional[datetime] = None) -> RetentionCutoffs:
    ref = now or datetime.utcnow()
    return RetentionCutoffs(
        content_cutoff=ref - timedelta(days=FULL_NOTIFICATION_CONTENT_RETENTION_DAYS),
        decision_cutoff=ref - timedelta(days=I10_DECISION_AUDIT_RETENTION_DAYS),
    )


def _expired_notification_filter(cut: datetime):
    """Prefer sent_at age when present; fall back to created_at for never-sent rows."""
    return or_(
        and_(Notification.sent_at.isnot(None), Notification.sent_at < cut),
        and_(Notification.sent_at.is_(None), Notification.created_at < cut),
    )


def count_expired_notifications(db: Session, *, now: Optional[datetime] = None) -> int:
    cut = retention_cutoffs(now).content_cutoff
    return db.query(Notification).filter(_expired_notification_filter(cut)).count()


def count_expired_decisions(db: Session, *, now: Optional[datetime] = None) -> int:
    cut = retention_cutoffs(now).decision_cutoff
    return (
        db.query(I10NotificationDecision)
        .filter(I10NotificationDecision.created_at < cut)
        .count()
    )


def prune_expired_notification_content(
    db: Session,
    *,
    now: Optional[datetime] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = True,
    force: bool = False,
) -> RetentionPruneResult:
    """
    Bounded batch prune. Default dry_run=True and enabled=False.

    Callers must pass force=True for explicit test/admin invocation when the
    env activation flag is off. Production scheduler must remain OFF in G1.
    """
    cuts = retention_cutoffs(now)
    enabled = RETENTION_PRUNE_ENABLED or force
    if not enabled:
        return RetentionPruneResult(
            notifications_deleted=0,
            decisions_deleted=0,
            dry_run=dry_run,
            enabled=False,
            content_cutoff=cuts.content_cutoff,
            decision_cutoff=cuts.decision_cutoff,
        )

    notif_q = (
        db.query(Notification.id)
        .filter(_expired_notification_filter(cuts.content_cutoff))
        .order_by(Notification.id.asc())
        .limit(max(1, int(batch_size)))
    )
    notif_ids = [row[0] for row in notif_q.all()]

    dec_q = (
        db.query(I10NotificationDecision.id)
        .filter(I10NotificationDecision.created_at < cuts.decision_cutoff)
        .order_by(I10NotificationDecision.id.asc())
        .limit(max(1, int(batch_size)))
    )
    dec_ids = [row[0] for row in dec_q.all()]

    deleted_n = 0
    deleted_d = 0
    if dry_run:
        deleted_n = len(notif_ids)
        deleted_d = len(dec_ids)
    else:
        if notif_ids:
            deleted_n = (
                db.query(Notification)
                .filter(Notification.id.in_(notif_ids))
                .delete(synchronize_session=False)
            )
        if dec_ids:
            deleted_d = (
                db.query(I10NotificationDecision)
                .filter(I10NotificationDecision.id.in_(dec_ids))
                .delete(synchronize_session=False)
            )
        db.commit()

    logger.info(
        "[RETENTION] prune dry_run=%s notif=%s decisions=%s content_cutoff=%s decision_cutoff=%s",
        dry_run,
        deleted_n,
        deleted_d,
        cuts.content_cutoff.isoformat(),
        cuts.decision_cutoff.isoformat(),
    )
    return RetentionPruneResult(
        notifications_deleted=int(deleted_n or 0),
        decisions_deleted=int(deleted_d or 0),
        dry_run=dry_run,
        enabled=True,
        content_cutoff=cuts.content_cutoff,
        decision_cutoff=cuts.decision_cutoff,
    )
