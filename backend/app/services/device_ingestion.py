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

from backend.app.models import DeviceEvent, User, UserMemoryFact
from backend.app.decision_engine.models import EventDto, CreateHealthAlertAction
from backend.app.decision_engine.service import evaluate_event
from backend.app.services.memory.memory_repository import MemoryRepository
from backend.app.services.notification_engine import DecisionEngine
from backend.app.services.vitals.vital_registry import validate_event, map_to_memory_facts, build_dedupe_key, VitalValidationError

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
    # Validate + normalize payload via registry
    normalized = validate_event(event_type, payload)

    # Rate limit (per device_id only)
    if device_id:
        _check_rate_limit(device_id)
    
    # Create new event
    received_at = datetime.utcnow()
    if recorded_at is None:
        recorded_at = received_at
    
    # Build dedupe key via registry (use recorded_at if present, else received_at)
    # Dedupe is intentionally independent of device_id to avoid circular imports and keep deterministic bucketing.
    dedupe_key = build_dedupe_key(
        user_id=user_id,
        event_type=event_type,  # type: ignore[arg-type]
        recorded_at=recorded_at,
        received_at=received_at,
    )
    
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
    
    # Map to memory facts (schema-driven)
    try:
        repo = MemoryRepository(db)
        updates = map_to_memory_facts(
            user_id=user_id,
            event_type=event_type,  # type: ignore[arg-type]
            normalized_payload=normalized,
            device_id=device_id,
            recorded_at=recorded_at,
        )
        for u in updates:
            repo.upsert_fact(
                user_id=user_id,
                domain=u.domain,
                key=u.key,
                value=u.value,
                confidence=u.confidence,
                source=u.source,
            )
        logger.info(
            f"[DEVICE_INGEST] Mapped to memory user={user_id} type={event_type} facts={len(updates)}"
        )
    except Exception as e:
        logger.exception("[DEVICE_INGEST] Failed to map to memory: %s", e)

    # Unified decision path: Decision Engine evaluates event -> actions -> executor persists
    try:
        event_dto = EventDto(
            user_id=user_id,
            device_id=device_id,
            event_type=event_type,
            payload=normalized,
            recorded_at=recorded_at,
            received_at=received_at,
            event_id=event.id,
        )
        actions = evaluate_event(event_dto)
        _execute_actions(db, actions)
    except Exception as e:
        logger.exception("[DEVICE_INGEST] Failed to evaluate/execute decision actions: %s", e)

    return event, dedupe_key


def _execute_actions(db: Session, actions: list) -> None:
    """Execute Decision Engine actions (e.g. create health_alert notifications). Best-effort per action."""
    engine = DecisionEngine(db)
    for a in actions:
        try:
            if isinstance(a, CreateHealthAlertAction):
                engine.create_health_alert(
                    user_id=a.user_id,
                    alert_code=a.alert_code,
                    alert_reason=a.alert_reason,
                    priority=a.priority,
                )
        except Exception as e:
            logger.exception("[DEVICE_INGEST] Failed to execute action %s: %s", type(a).__name__, e)


## Legacy C1 hardcoded mapping/alerts removed in Release C3 (now registry-driven)
