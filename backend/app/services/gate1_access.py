"""Gate 1 shared helpers: timezone validation, caregiver ACL."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from backend.app import models

DEFAULT_DEPENDENT_PERMISSIONS: Dict[str, bool] = {
    "can_manage_profile": True,
    "can_register_device": True,
}


def validate_iana_timezone(value: Optional[str]) -> Optional[str]:
    """Return normalized IANA timezone or raise ValueError."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    try:
        ZoneInfo(trimmed)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid IANA timezone: {trimmed}") from exc
    return trimmed


def parse_permissions_json(raw: Optional[str]) -> Dict[str, Any]:
    if not raw or not str(raw).strip():
        return dict(DEFAULT_DEPENDENT_PERMISSIONS)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else dict(DEFAULT_DEPENDENT_PERMISSIONS)
    except json.JSONDecodeError:
        return dict(DEFAULT_DEPENDENT_PERMISSIONS)


def caregiver_can_manage_dependent(
    db: Session,
    caregiver_user_id: int,
    dependent_user_id: int,
    *,
    require_device: bool = False,
) -> bool:
    """True if an active care relationship grants management (and optionally device) permission."""
    rel = (
        db.query(models.UserCareRelationship)
        .filter(
            models.UserCareRelationship.caregiver_user_id == caregiver_user_id,
            models.UserCareRelationship.dependent_user_id == dependent_user_id,
            models.UserCareRelationship.is_active == True,  # noqa: E712
        )
        .first()
    )
    if rel is None:
        return False
    perms = parse_permissions_json(rel.permissions_json)
    if require_device:
        return bool(perms.get("can_register_device") or perms.get("can_manage_profile"))
    return bool(perms.get("can_manage_profile"))


def get_active_dependent_ids(db: Session, caregiver_user_id: int) -> list[int]:
    rows = (
        db.query(models.UserCareRelationship.dependent_user_id)
        .filter(
            models.UserCareRelationship.caregiver_user_id == caregiver_user_id,
            models.UserCareRelationship.is_active == True,  # noqa: E712
        )
        .all()
    )
    return [r[0] for r in rows]
