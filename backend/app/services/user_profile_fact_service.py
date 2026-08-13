"""Gate 1 structured profile facts CRUD."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.gate1 import ProfileFactCreateIn, ProfileFactUpdateIn


class ProfileFactNotFoundError(Exception):
    pass


def _serialize_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps({"value": value.strip()}, ensure_ascii=False)
    return json.dumps({"value": value}, ensure_ascii=False, default=str)


def _deserialize_value(value_json: str) -> Any:
    try:
        data = json.loads(value_json)
        if isinstance(data, dict) and "value" in data:
            return data["value"]
        return data
    except json.JSONDecodeError:
        return value_json


def _row_to_dict(row: models.UserProfileFact) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "fact_type": row.fact_type,
        "value": _deserialize_value(row.value_json),
        "source": row.source,
        "confidence": row.confidence,
        "verified_at": row.verified_at,
        "valid_from": row.valid_from,
        "valid_to": row.valid_to,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_profile_facts(db: Session, user_id: int) -> List[dict]:
    now = datetime.utcnow()
    rows = (
        db.query(models.UserProfileFact)
        .filter(
            models.UserProfileFact.user_id == user_id,
            (models.UserProfileFact.valid_to.is_(None))
            | (models.UserProfileFact.valid_to > now),
        )
        .order_by(models.UserProfileFact.updated_at.desc())
        .all()
    )
    return [_row_to_dict(r) for r in rows]


def create_profile_fact(db: Session, user_id: int, body: ProfileFactCreateIn) -> dict:
    from backend.app.services.i6.legacy_fact_freeze import assert_legacy_write_allowed

    assert_legacy_write_allowed("user_profile_facts")
    now = datetime.utcnow()
    row = models.UserProfileFact(
        user_id=user_id,
        fact_type=body.fact_type,
        value_json=_serialize_value(body.value),
        source=body.source,
        confidence=body.confidence,
        valid_from=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def update_profile_fact(
    db: Session,
    user_id: int,
    fact_id: int,
    body: ProfileFactUpdateIn,
) -> dict:
    from backend.app.services.i6.legacy_fact_freeze import assert_legacy_write_allowed

    assert_legacy_write_allowed("user_profile_facts")
    row = (
        db.query(models.UserProfileFact)
        .filter(
            models.UserProfileFact.id == fact_id,
            models.UserProfileFact.user_id == user_id,
        )
        .first()
    )
    if row is None:
        raise ProfileFactNotFoundError()
    if body.value is not None:
        row.value_json = _serialize_value(body.value)
    if body.confidence is not None:
        row.confidence = body.confidence
    if body.verified is True:
        row.verified_at = datetime.utcnow()
    elif body.verified is False:
        row.verified_at = None
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def delete_profile_fact(db: Session, user_id: int, fact_id: int) -> None:
    row = (
        db.query(models.UserProfileFact)
        .filter(
            models.UserProfileFact.id == fact_id,
            models.UserProfileFact.user_id == user_id,
        )
        .first()
    )
    if row is None:
        raise ProfileFactNotFoundError()
    row.valid_to = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()


def get_profile_facts_for_context(db: Session, user_id: int, limit: int = 10) -> List[str]:
    """Concise strings for RAG stable_facts (no caregiver internals)."""
    items = list_profile_facts(db, user_id)[:limit]
    out: List[str] = []
    for item in items:
        val = item.get("value")
        if val is None:
            continue
        text = str(val).strip()
        if not text:
            continue
        out.append(f"{item['fact_type']}: {text[:120]}")
    return out
