"""P10: Sedi notices that the user's gadget has gone quiet and asks, once, whether it is still on their wrist.

A SELF producer on the existing I10 seam (``enqueue_i10_notification``): one candidate per quiet episode, so the dedupe key is
the day of the last reading and a gap is mentioned once. The copy is warm and lock-screen safe — it names the gadget, never a
value, a rhythm or a condition. Reactions adapt later sends through the normal I10 policy (R-023); this producer adds no
timer of its own: the existing scheduler calls ``run_hr_data_gap_scan`` and the whole thing is OFF unless
``SEDI_I10_HR_DATA_GAP_ENABLED`` is set (Tier 2).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.gate4.notification_context import (
    NotificationCategory,
    NotificationRiskLevel,
    NotificationSourceType,
    sanitize_notification_context,
)
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.intake import enqueue_i10_notification
from backend.app.services.i10.policy_types import (
    I10DecisionValue,
    I10NotificationScope,
    I10PrivacyClass,
    I10SemanticFamily,
)
from backend.app.services.i10.self_producer_adapter import resolve_or_ensure_self_health_subject_id

logger = logging.getLogger(__name__)

PRODUCER_OWNER = "I10_HR_DATA_GAP"
TEMPLATE_KEY = "hr_data_gap"
# Quiet for at least this long = a gap worth one friendly question; older than the window = the user has moved on.
GAP_AFTER = timedelta(hours=20)
GAP_WINDOW = timedelta(days=7)

_COPY = {
    "fa": ("گجتت", "{who}یه مدته خبری از گجتت نیست. روی دستته و بلوتوث روشنه؟"),
    "en": ("Your gadget", "{who}I have not heard from your gadget for a while. Is it on your wrist and is Bluetooth on?"),
    "ar": ("جهازك", "{who}مضى وقت دون أخبار من جهازك. هل هو على معصمك والبلوتوث يعمل؟"),
}


def build_occurrence_key(*, user_id: int, last_reading_day: str) -> str:
    return f"i10:self:hr_data_gap:{int(user_id)}:{last_reading_day}"


def render_copy(db: Session, user_id: int) -> tuple[str, str]:
    row = db.query(models.User.preferred_language, models.User.name).filter(models.User.id == user_id).first()
    lang = ((row[0] if row else None) or "fa").strip().lower().split("-")[0]
    lang = lang if lang in _COPY else "en"
    name = ((row[1] if row else None) or "").strip()[:64]
    who = (f"{name}، " if lang != "en" else f"{name}, ") if name else ""
    title, body = _COPY[lang]
    return title, body.format(who=who)


def enqueue_hr_data_gap_notification(
    db: Session, *, user_id: int, last_reading_at: datetime
) -> Optional[models.Notification]:
    last = last_reading_at if last_reading_at.tzinfo else last_reading_at.replace(tzinfo=timezone.utc)
    occurrence = build_occurrence_key(user_id=user_id, last_reading_day=last.astimezone(timezone.utc).date().isoformat())
    subject_id = resolve_or_ensure_self_health_subject_id(db, user_id)
    if subject_id is None:
        return None
    title, body = render_copy(db, user_id)
    payload = NotificationPayload(
        user_id=user_id,
        type="connection_ping",
        title=title,
        body=body,
        priority="normal",
        dedupe_key=occurrence,
        metadata={"alert_code": "hr_data_gap"},
        category=NotificationCategory.DEVICE_ALERT.value,
        source_type=NotificationSourceType.SYSTEM_SCHEDULER.value,
        source_id=str(user_id),
        risk_level=NotificationRiskLevel.INFORMATIONAL.value,
        template_key=TEMPLATE_KEY,
        context=sanitize_notification_context(
            {"template_key": TEMPLATE_KEY, "trigger_reason": "hr_data_gap", "source_summary_key": "i9_hr_gap"}
        ),
        privacy_class=I10PrivacyClass.PRIVATE.value,
    )
    candidate = I10NotificationCandidate(
        candidate_key=occurrence,
        health_subject_id=int(subject_id),
        recipient_user_id=user_id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
        source_owner=PRODUCER_OWNER,
        source_type="i9_hr_gap_scan",
        source_id=str(user_id),
        semantic_family=I10SemanticFamily.DEVICE_STATUS,
        privacy_hint=I10PrivacyClass.PRIVATE,
        provenance_refs=(f"i9_heart_rate_last_reading:{last.isoformat()}",),
    )
    result = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)
    if result.decision != I10DecisionValue.SEND or result.notification_id is None:
        logger.info("[I10-HR-GAP] suppressed user=%s reason=%s", user_id, result.reason_code)
        return None
    return db.query(models.Notification).filter(models.Notification.id == result.notification_id).one()


def run_hr_data_gap_scan(db: Session, *, now: Optional[datetime] = None, limit: int = 100) -> dict:
    """Users whose gadget was reporting and has been silent for 20 h .. 7 days get ONE gentle question per episode."""
    from backend.app.services.section10.feature_flags import i10_hr_data_gap_enabled

    if not i10_hr_data_gap_enabled():
        return {"processed": 0, "sent": 0, "dormant": True}
    moment = now or datetime.now(timezone.utc)
    last_at = func.max(models.PhysiologicalMeasurement.received_at)
    rows = (
        db.query(models.PhysiologicalMeasurement.user_id, last_at)
        .filter(
            models.PhysiologicalMeasurement.measurement_type == "heart_rate",
            models.PhysiologicalMeasurement.ingestion_status == "accepted",
        )
        .group_by(models.PhysiologicalMeasurement.user_id)
        .having(last_at < moment - GAP_AFTER, last_at > moment - GAP_WINDOW)
        .order_by(models.PhysiologicalMeasurement.user_id.asc())
        .limit(max(1, min(int(limit), 500)))
        .all()
    )
    summary = {"processed": 0, "sent": 0, "dormant": False}
    for user_id, last_reading in rows:
        summary["processed"] += 1
        try:
            if enqueue_hr_data_gap_notification(db, user_id=int(user_id), last_reading_at=last_reading) is not None:
                summary["sent"] += 1
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("[I10-HR-GAP] failed user=%s", user_id)
    return summary
