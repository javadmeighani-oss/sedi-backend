"""Lifelong timeline service aggregation. No second canonical event table. No SQL view."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i6.consent_service import PERM_READ, require_permission

PRIVACY_CLASS = "USER_PRIVATE"


def list_lifelong_timeline(
    db: Session,
    user_id: int,
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    require_permission(db, user_id, PERM_READ)
    rows: list[dict[str, Any]] = []
    present = set(inspect(db.bind).get_table_names())

    if "user_events" in present:
      for ev in db.query(models.UserEvent).filter(models.UserEvent.user_id == user_id).all():
        occurred = ev.starts_at
        recorded = ev.created_at
        if start and occurred and occurred < start:
            continue
        if end and occurred and occurred > end:
            continue
        rows.append(
            {
                "event_id": f"user_event:{ev.id}",
                "user_id": user_id,
                "event_family": "life",
                "event_type": ev.event_type,
                "occurred_at": occurred,
                "recorded_at": recorded,
                "source": ev.source,
                "provenance_ref": f"user_events:{ev.id}",
                "timezone": ev.timezone,
                "privacy_class": PRIVACY_CLASS,
                "source_table": "user_events",
            }
        )

    if "user_lifestyle_events" in present:
      for ev in db.query(models.UserLifestyleEvent).filter(models.UserLifestyleEvent.user_id == user_id).all():
        occurred = ev.occurred_at
        if start and occurred and occurred < start:
            continue
        if end and occurred and occurred > end:
            continue
        rows.append(
            {
                "event_id": f"lifestyle:{ev.id}",
                "user_id": user_id,
                "event_family": "lifestyle",
                "event_type": ev.event_type,
                "occurred_at": occurred,
                "recorded_at": ev.created_at,
                "source": ev.source,
                "provenance_ref": f"user_lifestyle_events:{ev.id}",
                "timezone": None,
                "privacy_class": PRIVACY_CLASS,
                "source_table": "user_lifestyle_events",
            }
        )

    if "interaction_events" in present:
      for ev in db.query(models.InteractionEvent).filter(models.InteractionEvent.user_id == user_id).all():
        occurred = ev.created_at
        if start and occurred and occurred < start:
            continue
        if end and occurred and occurred > end:
            continue
        rows.append(
            {
                "event_id": f"interaction:{ev.id}",
                "user_id": user_id,
                "event_family": "interaction",
                "event_type": ev.event_type,
                "occurred_at": occurred,
                "recorded_at": ev.created_at,
                "source": ev.source,
                "provenance_ref": f"interaction_events:{ev.id}",
                "timezone": None,
                "privacy_class": PRIVACY_CLASS,
                "source_table": "interaction_events",
            }
        )

    rows.sort(key=lambda r: (r["occurred_at"] is None, r["occurred_at"] or r["recorded_at"]))
    return rows
