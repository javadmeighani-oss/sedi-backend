# backend/app/behavior/models.py
"""Behavior Layer V1: domain enums and value types (DB model lives in backend.app.models)."""
from enum import Enum
from typing import Any, Dict, Optional


class BehaviorMode(str, Enum):
    """Engagement mode derived from user score (deterministic mapping)."""
    low = "low"        # minimal lead-in, fewer pings
    normal = "normal"  # default caring tone
    high = "high"      # slightly warmer, can add lead-in more often


def score_to_mode(score: float) -> BehaviorMode:
    """
    Map numeric score to BehaviorMode. Deterministic for tests.
    Score typically 0.0–1.0; out of range clamped.
    """
    if score >= 0.7:
        return BehaviorMode.high
    if score >= 0.3:
        return BehaviorMode.normal
    return BehaviorMode.low


def behavior_profile_to_dict(
    user_id: int,
    score: float,
    mode: str,
    daily_initiated_count: int,
    last_initiated_at: Optional[Any],
    last_interaction_at: Optional[Any],
    updated_at: Optional[Any],
) -> Dict[str, Any]:
    """Serialize profile for logging/tests; datetimes as ISO strings."""
    return {
        "user_id": user_id,
        "score": score,
        "mode": mode,
        "daily_initiated_count": daily_initiated_count,
        "last_initiated_at": last_initiated_at.isoformat() if hasattr(last_initiated_at, "isoformat") else last_initiated_at,
        "last_interaction_at": last_interaction_at.isoformat() if hasattr(last_interaction_at, "isoformat") else last_interaction_at,
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else updated_at,
    }
