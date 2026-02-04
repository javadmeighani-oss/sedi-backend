# app/services/vitals/dedupe.py
"""
Deduplication Key Builder (Release C1/C3)

Builds deterministic dedupe keys for device events using 5-minute time buckets.
Extracted to avoid circular imports between device_ingestion and vital_registry.
"""

from datetime import datetime
from typing import Optional


def build_dedupe_key(
    event_type: str,
    user_id: int,
    recorded_at: Optional[datetime] = None,
    received_at: Optional[datetime] = None
) -> str:
    """
    Build deterministic dedupe key for device events using 5-minute time buckets.
    
    Format: {event_type}:{user_id}:{YYYY-MM-DDTHH}:{bucket_min:02d}
    Uses 5-minute buckets: rounds down minute to nearest 5 (0, 5, 10, 15, ..., 55).
    
    Examples:
    - 06:44 -> bucket 06:40
    - 06:40 -> bucket 06:40 (same bucket)
    - 06:45 -> bucket 06:45 (different bucket)
    
    Args:
        event_type: Event type (e.g., "heart_rate")
        user_id: User ID
        recorded_at: Timestamp from device (preferred if present)
        received_at: Server timestamp (fallback if recorded_at is None)
    
    Returns:
        Dedupe key string (e.g., "heart_rate:1:2026-02-03T06:40")
    """
    # Use recorded_at if present, else received_at, else now
    if recorded_at is not None:
        timestamp = recorded_at
    elif received_at is not None:
        timestamp = received_at
    else:
        timestamp = datetime.utcnow()
    
    # Round down to 5-minute bucket (0, 5, 10, 15, ..., 55)
    bucket_minute = (timestamp.minute // 5) * 5
    bucket_time = timestamp.replace(minute=bucket_minute, second=0, microsecond=0)
    
    # Format: heart_rate:1:2026-02-03T06:40 (explicit 2-digit minute)
    return f"{event_type}:{user_id}:{bucket_time.strftime('%Y-%m-%dT%H:%M')}"
