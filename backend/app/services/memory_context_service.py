"""Gate 2 unified memory context read aggregation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.app.services.gate2_data_service import (
    list_care_plan_items,
    list_doctors,
    list_events,
    list_goals,
    list_habits,
    list_lifestyle_events,
    list_restrictions,
)
from backend.app.services.memory import MemoryRepository
from backend.app.services.user_context import UserContextService
from backend.app.services.user_profile_fact_service import list_profile_facts


def _medical_conditions(db: Session, user_id: int, limit: int = 10) -> List[str]:
    try:
        from backend.app import models

        rows = (
            db.query(models.MedicalCondition.name)
            .join(models.UserCondition, models.UserCondition.condition_id == models.MedicalCondition.id)
            .filter(models.UserCondition.user_id == user_id)
            .distinct()
            .limit(limit)
            .all()
        )
        return [r[0] for r in rows if r and r[0]]
    except Exception:
        return []


def _medications_summary(db: Session, user_id: int, limit: int = 10) -> List[str]:
    try:
        from backend.app.services.rag_context.rag_context_builder import _get_user_medications_for_context

        return _get_user_medications_for_context(db, user_id)[:limit]
    except Exception:
        return []


def _memory_facts_summary(db: Session, user_id: int, limit_per_domain: int = 5) -> Dict[str, Any]:
    repo = MemoryRepository(db)
    out: Dict[str, Any] = {}
    for domain in ("lifestyle", "routines", "preferences", "goals"):
        facts = repo.get_facts_by_domain(user_id, domain)[:limit_per_domain]
        if not facts:
            continue
        domain_items = []
        for f in facts:
            try:
                import json
                val = json.loads(f.value_json)
            except Exception:
                val = f.value_json
            domain_items.append({"key": f.key, "value": val})
        if domain_items:
            out[domain] = domain_items
    return out


def build_memory_context(db: Session, user_id: int) -> Dict[str, Any]:
    """Unified read-only memory context for API and RAG assembly."""
    pack = UserContextService(db).get_user_context(user_id)
    upcoming = list_events(db, user_id, upcoming_only=True)[:5]
    return {
        "user_id": user_id,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "profile_core": {
            "birth_year": pack.birth_year,
            "sex": pack.sex,
            "timezone": pack.timezone,
            "addressing_preference": pack.addressing_preference,
            "preferred_name": pack.preferred_name,
            "language": pack.language,
        },
        "profile_facts": list_profile_facts(db, user_id)[:10],
        "memory_facts": _memory_facts_summary(db, user_id),
        "lifestyle_events_recent": list_lifestyle_events(db, user_id, limit=10),
        "habits": list_habits(db, user_id)[:5],
        "goals": list_goals(db, user_id)[:5],
        "restrictions": list_restrictions(db, user_id)[:5],
        "doctors": list_doctors(db, user_id)[:3],
        "upcoming_events": upcoming,
        "care_plan_items": list_care_plan_items(db, user_id)[:5],
        "medications": _medications_summary(db, user_id),
        "conditions": _medical_conditions(db, user_id),
        "daily_summary": pack.daily_memory_summary,
        "lifestyle_summary": (pack.lifestyle.text[:300] if pack.lifestyle and pack.lifestyle.text else None),
    }
