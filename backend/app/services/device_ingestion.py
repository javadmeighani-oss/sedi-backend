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
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone
import time
from collections import deque
from sqlalchemy.orm import Session

from backend.app.models import DeviceEvent, User, UserMemoryFact
from backend.app.decision_engine.models import EventDto, CreateHealthAlertAction
from backend.app.decision_engine.service import evaluate_event
from backend.app.services.memory.memory_repository import MemoryRepository
from backend.app.models import Notification
from backend.app.services.notification_engine import DecisionEngine, persist_health_alert_d1
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


def minute_bucket(dt: Optional[datetime]) -> str:
    """
    UTC minute bucket for dedupe_key: YYYYMMDDHHMM.
    If dt is None, uses utcnow().
    """
    if dt is None:
        dt = datetime.utcnow()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%d%H%M")


def parse_recorded_at_utc(payload: Dict[str, Any], fallback: Optional[datetime]) -> Optional[datetime]:
    """
    Parse recorded_at from payload['ts'] if present (ISO with 'Z' = UTC).
    Returns timezone-aware UTC datetime or fallback.
    """
    ts = payload.get("ts")
    if ts is None:
        return fallback
    if isinstance(ts, datetime):
        d = ts
    elif isinstance(ts, str):
        try:
            # Handle Z suffix as UTC (stdlib fromisoformat accepts +00:00)
            s = (ts[:-1] + "+00:00") if ts.endswith("Z") else ts
            d = datetime.fromisoformat(s)
        except (ValueError, TypeError):
            return fallback
    else:
        return fallback
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    else:
        d = d.astimezone(timezone.utc)
    return d


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
) -> Tuple[Optional[DeviceEvent], Optional[str], Dict[str, Any]]:
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
        (DeviceEvent if created, dedupe_key, decision_summary) or (None, dedupe_key, decision_summary) if duplicate.
        decision_summary includes e.g. {"actions_created": n} for debugging.
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
        return None, dedupe_key, {"actions_created": 0}
    
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

    # D1: recorded_at from payload['ts'] if present else device event
    recorded_at_for_dto = parse_recorded_at_utc(payload, event.recorded_at)

    # Unified decision path: Decision Engine evaluates event -> actions -> executor persists
    actions_created = 0
    try:
        event_dto = EventDto(
            user_id=user_id,
            device_id=device_id,
            event_type=event_type,
            payload=normalized,
            recorded_at=recorded_at_for_dto,
            received_at=event.received_at,
            event_id=event.id,
        )
        actions = evaluate_event(event_dto)
        actions_created = _execute_d1_actions(db, event_dto, actions)
    except Exception as e:
        logger.exception("[DEVICE_INGEST] Failed to evaluate/execute decision actions: %s", e)

    decision_summary = {"actions_created": actions_created}
    return event, dedupe_key, decision_summary


def _execute_d1_actions(db: Session, event_dto: EventDto, actions: list) -> int:
    """
    Execute D1 CreateHealthAlertAction: build dedupe_key, skip if exists, else persist.
    Returns count of notifications created.
    """
    created = 0
    for a in actions:
        if not isinstance(a, CreateHealthAlertAction) or not a.rule_id:
            continue
        try:
            bucket = minute_bucket(event_dto.recorded_at)
            dedupe_key = f"alert:{event_dto.event_type}:{event_dto.user_id}:{bucket}:{a.rule_id}"
            existing = (
                db.query(Notification)
                .filter(
                    Notification.user_id == a.user_id,
                    Notification.channel == "health_alert",
                    Notification.dedupe_key == dedupe_key,
                )
                .first()
            )
            if existing:
                continue
            notif = persist_health_alert_d1(
                db=db,
                user_id=a.user_id,
                title=a.title or "هشدار سلامت",
                body=a.body or "هشدار سلامت ثبت شد.",
                dedupe_key=dedupe_key,
                priority=a.priority,
            )
            if notif:
                created += 1
        except Exception as e:
            logger.exception("[DEVICE_INGEST] Failed to execute action %s: %s", type(a).__name__, e)
    return created


## Legacy C1 hardcoded mapping/alerts removed in Release C3 (now registry-driven)
