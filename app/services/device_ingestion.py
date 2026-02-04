# app/services/device_ingestion.py
"""
Device Ingestion Service (Release C1)

Handles ingestion of device events (vital signs) with:
- Deduplication
- Memory fact mapping
- Rule-based health alerts
"""

import os
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import time
from collections import deque
from sqlalchemy.orm import Session

from app.models import DeviceEvent, User, UserMemoryFact
from app.services.memory.memory_repository import MemoryRepository
from app.services.notification_engine import DecisionEngine

logger = logging.getLogger(__name__)

# Heart rate thresholds (configurable via env, defaults to safe ranges)
HEART_RATE_MIN_SAFE = int(os.getenv("HEART_RATE_MIN_SAFE", "60"))
HEART_RATE_MAX_SAFE = int(os.getenv("HEART_RATE_MAX_SAFE", "100"))

# Rate limiting (Release C2)
DEVICE_RATE_LIMIT_PER_MINUTE = int(os.getenv("DEVICE_RATE_LIMIT_PER_MINUTE", "30"))
_rate_buckets: Dict[str, "deque[float]"] = {}


class DeviceRateLimitExceeded(Exception):
    pass


def _check_rate_limit(device_id: str) -> None:
    """
    In-memory sliding-window rate limit per device_id (no external deps).
    Limitation: per-process only (not shared across workers).
    """
    if DEVICE_RATE_LIMIT_PER_MINUTE <= 0:
        return

    now = time.time()
    window_start = now - 60.0
    q = _rate_buckets.get(device_id)
    if q is None:
        q = deque()
        _rate_buckets[device_id] = q

    while q and q[0] < window_start:
        q.popleft()

    if len(q) >= DEVICE_RATE_LIMIT_PER_MINUTE:
        raise DeviceRateLimitExceeded(f"Rate limit exceeded for device_id={device_id}")

    q.append(now)


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


def ingest_event(
    db: Session,
    user_id: int,
    event_type: str,
    payload: Dict[str, Any],
    device_id: Optional[str] = None,
    recorded_at: Optional[datetime] = None
) -> tuple[Optional[DeviceEvent], Optional[str]]:
    """
    Ingest a device event with deduplication and memory mapping.
    
    Args:
        db: Database session
        user_id: User ID
        event_type: Event type (e.g., "heart_rate")
        payload: Event payload (must contain required fields for event_type)
        device_id: Optional device identifier
        recorded_at: Optional timestamp from device
    
    Returns:
        (DeviceEvent if created, dedupe_key) or (None, dedupe_key) if duplicate
    """
    # Validate event_type
    if event_type != "heart_rate":
        raise ValueError(f"Unsupported event_type: {event_type}. Supported: ['heart_rate']")
    
    # Validate payload is not empty
    if not payload:
        raise ValueError("Payload must not be empty")

    # Rate limit (per device_id only)
    if device_id:
        _check_rate_limit(device_id)
    
    # Create new event
    received_at = datetime.utcnow()
    if recorded_at is None:
        recorded_at = received_at
    
    # Build dedupe key (use recorded_at if present, else received_at)
    dedupe_key = build_dedupe_key(event_type, user_id, recorded_at, received_at)
    
    # Check for existing event with same dedupe_key
    existing = (
        db.query(DeviceEvent)
        .filter(
            DeviceEvent.user_id == user_id,
            DeviceEvent.dedupe_key == dedupe_key
        )
        .first()
    )
    
    if existing:
        logger.info(
            f"[DEVICE_INGEST] DUPLICATE user={user_id} type={event_type} "
            f"dedupe={dedupe_key} existing_id={existing.id}"
        )
        return None, dedupe_key
    
    event = DeviceEvent(
        user_id=user_id,
        device_id=device_id,
        event_type=event_type,
        payload_json=json.dumps(payload),
        recorded_at=recorded_at,
        received_at=received_at,
        dedupe_key=dedupe_key,
        embedding_id=None  # RAG-ready, not active
    )
    
    db.add(event)
    db.commit()
    db.refresh(event)
    
    logger.info(
        f"[DEVICE_INGEST] CREATED user={user_id} type={event_type} "
        f"dedupe={dedupe_key} event_id={event.id}"
    )
    
    # Map to memory fact
    try:
        _map_to_memory_fact(db, user_id, event_type, payload, device_id, recorded_at)
    except Exception as e:
        logger.error(f"[DEVICE_INGEST] Failed to map to memory: {e}", exc_info=True)
        # Don't fail ingestion if memory mapping fails
    
    # Check for health alerts (rule-based, no AI)
    try:
        _check_health_alerts(db, user_id, event_type, payload)
    except Exception as e:
        logger.error(f"[DEVICE_INGEST] Failed to check health alerts: {e}", exc_info=True)
        # Don't fail ingestion if alert check fails
    
    return event, dedupe_key


def _map_to_memory_fact(
    db: Session,
    user_id: int,
    event_type: str,
    payload: Dict[str, Any],
    device_id: Optional[str],
    recorded_at: Optional[datetime]
):
    """Map device event to UserMemoryFact with source='device'"""
    repo = MemoryRepository(db)
    
    if event_type == "heart_rate":
        # Extract BPM from payload
        bpm = payload.get("bpm")
        if bpm is None:
            logger.warning(f"[DEVICE_INGEST] Missing 'bpm' in heart_rate payload: {payload}")
            return
        
        # Build value_json
        value = {
            "bpm": float(bpm),
            "recorded_at": recorded_at.isoformat() if recorded_at else None,
            "device_id": device_id,
        }
        
        # Include any additional fields from payload
        if "quality" in payload:
            value["quality"] = payload["quality"]
        if "confidence" in payload:
            value["confidence"] = payload["confidence"]
        
        # Upsert memory fact
        repo.upsert_fact(
            user_id=user_id,
            domain="vitals",
            key="heart_rate_bpm",
            value=value,
            confidence=0.9,  # High confidence for device data
            source="device"
        )
        
        logger.info(
            f"[DEVICE_INGEST] Mapped to memory user={user_id} "
            f"domain=vitals key=heart_rate_bpm bpm={bpm}"
        )


def _check_health_alerts(
    db: Session,
    user_id: int,
    event_type: str,
    payload: Dict[str, Any]
):
    """Check for health alerts based on rule-based thresholds (no AI)"""
    if event_type != "heart_rate":
        return
    
    bpm = payload.get("bpm")
    if bpm is None:
        return
    
    bpm_float = float(bpm)
    alert_code = None
    alert_reason = None
    priority = "normal"
    
    # Check thresholds
    if bpm_float > HEART_RATE_MAX_SAFE:
        alert_code = "high_heart_rate"
        alert_reason = f"Heart rate is elevated: {bpm_float:.0f} bpm (normal: {HEART_RATE_MIN_SAFE}-{HEART_RATE_MAX_SAFE})"
        priority = "high"
    elif bpm_float < HEART_RATE_MIN_SAFE:
        alert_code = "low_heart_rate"
        alert_reason = f"Heart rate is low: {bpm_float:.0f} bpm (normal: {HEART_RATE_MIN_SAFE}-{HEART_RATE_MAX_SAFE})"
        priority = "high"
    
    if alert_code:
        # Use DecisionEngine to create health alert (respects dedupe/rate limits)
        decision_engine = DecisionEngine(db)
        notif = decision_engine.create_health_alert(
            user_id=user_id,
            alert_code=alert_code,
            alert_reason=alert_reason,
            priority=priority
        )
        
        if notif:
            logger.info(
                f"[DEVICE_INGEST] ALERT CREATED user={user_id} "
                f"code={alert_code} bpm={bpm_float} notif_id={notif.id}"
            )
        else:
            logger.info(
                f"[DEVICE_INGEST] ALERT SUPPRESSED user={user_id} "
                f"code={alert_code} bpm={bpm_float} reason=dedupe"
            )
