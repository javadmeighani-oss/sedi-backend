"""Non-clinical medication low-stock classification."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from backend.app import models


class StockLevel(str, Enum):
    UNKNOWN = "unknown"
    SUFFICIENT = "sufficient"
    LOW = "low"
    EMPTY = "empty"


def classify_medication_stock(um: models.UserMedication) -> StockLevel:
    qty = um.remaining_quantity
    threshold = um.refill_threshold
    if qty is None:
        return StockLevel.UNKNOWN
    if qty <= 0:
        return StockLevel.EMPTY
    if threshold is not None and qty <= threshold:
        return StockLevel.LOW
    return StockLevel.SUFFICIENT


def stock_level_for_medication(um: models.UserMedication) -> dict:
    level = classify_medication_stock(um)
    return {
        "stock_level": level.value,
        "remaining_quantity": um.remaining_quantity,
        "quantity_unit": um.quantity_unit,
        "refill_threshold": um.refill_threshold,
        "estimated_end_at": um.estimated_end_at.isoformat() + "Z" if um.estimated_end_at else None,
    }
