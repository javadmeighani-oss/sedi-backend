"""Long-term memory governance — conflict resolution and poisoning protection."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app import models

FACT_STATUSES = frozenset({"active", "superseded", "expired", "rejected", "needs_confirmation"})

_POISON_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.I),
    re.compile(r"system\s+prompt", re.I),
    re.compile(r"you\s+are\s+now", re.I),
    re.compile(r"disregard\s+safety", re.I),
    re.compile(r"api[_\s]?key", re.I),
    re.compile(r"password\s*[:=]", re.I),
]

_CONFLICT_KEYS = {
    "preferred_language",
    "medication",
    "doctor",
    "exercise_goal",
    "caregiver",
}


def is_poison_candidate(text: str) -> bool:
    if not text or len(text.strip()) < 4:
        return True
    for pat in _POISON_PATTERNS:
        if pat.search(text):
            return True
    return False


def supersede_conflicting_facts(
    db: Session,
    user_id: int,
    domain: str,
    key: str,
    *,
    exclude_id: Optional[int] = None,
) -> int:
    conflict_key = f"{domain}.{key}"
    base_key = key.split(".")[-1] if "." in key else key
    if base_key not in _CONFLICT_KEYS and conflict_key not in _CONFLICT_KEYS:
        return 0

    q = db.query(models.UserMemoryFact).filter(
        models.UserMemoryFact.user_id == user_id,
        models.UserMemoryFact.domain == domain,
        models.UserMemoryFact.key == key,
        models.UserMemoryFact.fact_status == "active",
    )
    if exclude_id is not None:
        q = q.filter(models.UserMemoryFact.id != exclude_id)
    rows = q.all()
    count = 0
    for row in rows:
        row.fact_status = "superseded"
        row.updated_at = datetime.utcnow()
        count += 1
    if count:
        db.commit()
    return count


def store_governed_fact(
    db: Session,
    user_id: int,
    domain: str,
    key: str,
    value: Any,
    *,
    provenance: str = "chat",
    source_interaction_id: Optional[int] = None,
    confidence: float = 0.7,
    requires_confirmation: bool = False,
) -> Optional[models.UserMemoryFact]:
    value_str = json.dumps(value, ensure_ascii=False)
    if is_poison_candidate(value_str):
        return None

    supersede_conflicting_facts(db, user_id, domain, key)
    now = datetime.utcnow()
    status = "needs_confirmation" if requires_confirmation or domain == "medical" else "active"
    row = models.UserMemoryFact(
        user_id=user_id,
        domain=domain,
        key=key,
        value_json=value_str,
        confidence=confidence,
        source=provenance,
        provenance=provenance,
        source_interaction_id=source_interaction_id,
        extracted_at=now,
        valid_from=now,
        fact_status=status,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def invalidate_fact(db: Session, user_id: int, fact_id: int) -> bool:
    row = (
        db.query(models.UserMemoryFact)
        .filter(models.UserMemoryFact.id == fact_id, models.UserMemoryFact.user_id == user_id)
        .first()
    )
    if row is None:
        return False
    row.fact_status = "rejected"
    row.valid_until = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()
    return True


def list_active_facts(db: Session, user_id: int, domain: Optional[str] = None) -> List[dict]:
    q = db.query(models.UserMemoryFact).filter(
        models.UserMemoryFact.user_id == user_id,
        models.UserMemoryFact.fact_status == "active",
    )
    if domain:
        q = q.filter(models.UserMemoryFact.domain == domain)
    rows = q.order_by(models.UserMemoryFact.updated_at.desc()).all()
    return [
        {
            "id": r.id,
            "domain": r.domain,
            "key": r.key,
            "value": r.value_json,
            "provenance": r.provenance,
            "confidence": r.confidence,
            "status": r.fact_status,
        }
        for r in rows
    ]
