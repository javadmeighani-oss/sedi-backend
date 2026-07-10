"""Gate 4-compatible medication stock notification intent foundation."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.section10 import feature_flags
from backend.app.services.section10.medication_stock_service import StockLevel, classify_medication_stock


def _dedupe_key(user_id: int, medication_id: int, stock_level: str, bucket: str) -> str:
    return f"med_stock:{user_id}:{medication_id}:{stock_level}:{bucket}"


def maybe_create_stock_notification(
    db: Session,
    um: models.UserMedication,
    *,
    bucket: str,
) -> Optional[models.Notification]:
    if not feature_flags.medication_stock_notifications_enabled():
        return None

    level = classify_medication_stock(um)
    if level not in {StockLevel.LOW, StockLevel.EMPTY}:
        return None

    notif_type = "medication_low_stock" if level == StockLevel.LOW else "medication_empty"
    dedupe = _dedupe_key(um.user_id, um.id, level.value, bucket)
    existing = (
        db.query(models.Notification)
        .filter(models.Notification.dedupe_key == dedupe)
        .first()
    )
    if existing is not None:
        return existing

    row = models.Notification(
        user_id=um.user_id,
        type=notif_type,
        title="Medication stock",
        body="Your medication supply may need attention.",
        template_key=notif_type,
        dedupe_key=dedupe,
        status="queued",
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
