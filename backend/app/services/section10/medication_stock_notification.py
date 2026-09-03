"""I10-B19: medication stock alerts are retired from the I10 writer surface.

Not one of the 12 frozen I10 families. Path remains flag-gated and unwired;
creation is quarantined so no duplicate/legacy Notification ORM write occurs
from this module in the I10 freeze.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.section10 import feature_flags
from backend.app.services.section10.medication_stock_state import StockLevel

logger = logging.getLogger(__name__)


def _dedupe_key(user_id: int, medication_id: int, level: str, bucket: str) -> str:
    return f"med_stock:{user_id}:{medication_id}:{level}:{bucket}"


def maybe_create_medication_stock_notification(
    db: Session,
    um: models.UserMedication,
    level: StockLevel,
    *,
    bucket: str,
) -> Optional[models.Notification]:
    """Quarantined — I10-B19 RETIRED writer. No Notification ORM write."""
    logger.info(
        "[I10-B19] medication_stock_notification retired user=%s med=%s level=%s flag=%s",
        um.user_id,
        um.id,
        level.value,
        feature_flags.medication_stock_notifications_enabled(),
    )
    return None
