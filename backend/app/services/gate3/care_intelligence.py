"""Gate 3 care context, vitals, recommendations, follow-ups."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.gate2_data_service import (
    list_care_plan_items,
    list_doctors,
    list_events,
    list_goals,
    list_habits,
    list_restrictions,
)
from backend.app.services.memory_context_service import build_memory_context
from backend.app.services.gate3.safety_core import RiskClassifier, SafetyPolicy
from backend.app.schemas.gate3 import FollowUpCreateIn, FollowUpUpdateIn, RecommendationCreateIn
from backend.app.services.i5.runtime_knowledge_retrieval import (
    PACKAGE_ID as W4P01_PACKAGE_ID,
    retrieve_knowledge_context,
)


class Gate3NotFoundError(Exception):
    pass


from backend.app.services.gate3.vitals_summary_v1 import build_vitals_summary_v1


def get_vitals_summary(db: Session, user_id: int) -> Dict[str, Any]:
    """Unified read from health_data + device_events with stable V1 contract."""
    return build_vitals_summary_v1(db, user_id)


def build_care_context(db: Session, user_id: int, language: str = "fa", query_hint: Optional[str] = None) -> Dict[str, Any]:
    """Build CARE_CONTEXT with Knowledge-Database-First retrieval (I5-IMPL-W4-P01).

    Medical knowledge context uses KU/Memory filters via runtime_knowledge_retrieval.
    Interim Gate3 search_knowledge is not used as an ungoverned medical substitute.
    Final answer synthesis / reference rendering remain outside this function (W4-P02).
    """
    base = build_memory_context(db, user_id)
    base["vitals_summary"] = get_vitals_summary(db, user_id)
    base["care_plan_interpretation"] = interpret_care_plan(db, user_id)
    if query_hint:
        # Risk classification retained for care policy surfaces; not a knowledge substitute.
        RiskClassifier().classify(query_hint, language)
        retrieval = retrieve_knowledge_context(
            db,
            query_hint,
            user_id=user_id,
            language=language,
            limit=3,
            enqueue_gap_on_empty=True,
        )
        envelope = retrieval.to_dict()
        base["i5_knowledge_retrieval"] = envelope
        base["knowledge_snippets"] = envelope.get("knowledge_snippets") or []
        base["i5_retrieval_status"] = retrieval.status
        base["no_base_model_fallback"] = True
        base["knowledge_db_first_package"] = W4P01_PACKAGE_ID
    return base


def interpret_care_plan(db: Session, user_id: int) -> List[str]:
    items = list_care_plan_items(db, user_id)[:5]
    return [f"{i['title']}: data-only care plan item (follow your care team guidance)" for i in items if i.get("status") == "active"]


def list_recommendations(db: Session, user_id: int) -> List[dict]:
    now = datetime.utcnow()
    rows = (
        db.query(models.CareRecommendation)
        .filter(
            models.CareRecommendation.user_id == user_id,
            (models.CareRecommendation.valid_to.is_(None)) | (models.CareRecommendation.valid_to > now),
            models.CareRecommendation.status == "active",
        )
        .order_by(models.CareRecommendation.created_at.desc())
        .all()
    )
    return [_rec_dict(r) for r in rows]


def _rec_dict(row: models.CareRecommendation) -> dict:
    return {
        "id": row.id,
        "category": row.category,
        "title": row.title,
        "body": row.body,
        "safety_level": row.safety_level,
        "status": row.status,
        "source_refs": json.loads(row.source_refs_json) if row.source_refs_json else [],
        "created_at": row.created_at.isoformat() + "Z",
    }


def generate_recommendations(
    db: Session,
    user_id: int,
    message: Optional[str] = None,
    language: str = "fa",
    body: Optional[RecommendationCreateIn] = None,
) -> List[dict]:
    risk = RiskClassifier().classify(message or "", language)
    policy = SafetyPolicy().evaluate(risk.risk_level)
    if policy["template_key"]:
        return []

    created = []
    upcoming = list_events(db, user_id, upcoming_only=True)[:3]
    for ev in upcoming:
        if ev.get("event_type") in ("lab_test", "doctor_visit", "surgery", "exam"):
            title = f"Preparation reminder: {ev.get('title')}"
            text = (
                "This is general educational preparation guidance only, not medical orders. "
                "Follow your clinician's instructions for this appointment or test."
            )
            if ev.get("event_type") == "lab_test":
                text = (
                    "General lab preparation tips may include fasting only if your doctor instructed it. "
                    "Confirm instructions with your clinician."
                )
            row = _save_recommendation(db, user_id, "preparation", title, text, risk.risk_level)
            created.append(_rec_dict(row))

    if not created and (body and body.title or message):
        title = (body.title if body else None) or "General wellness guidance"
        text = (
            "I can offer general supportive wellness guidance. For personal medical decisions, please consult your clinician."
        )
        row = _save_recommendation(db, user_id, body.category if body else "general", title, text, risk.risk_level)
        created.append(_rec_dict(row))
    return created


def _save_recommendation(db: Session, user_id: int, category: str, title: str, body: str, safety_level: str) -> models.CareRecommendation:
    now = datetime.utcnow()
    row = models.CareRecommendation(
        user_id=user_id,
        category=category[:64],
        title=title[:256],
        body=body,
        safety_level=safety_level,
        status="active",
        source="system",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def patch_recommendation(db: Session, user_id: int, rec_id: int, status: str) -> dict:
    row = db.query(models.CareRecommendation).filter(
        models.CareRecommendation.id == rec_id,
        models.CareRecommendation.user_id == user_id,
    ).first()
    if not row:
        raise Gate3NotFoundError()
    row.status = status
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _rec_dict(row)


def analyze_message(db: Session, user_id: int, message: str, language: str = "fa") -> Dict[str, Any]:
    risk = RiskClassifier().classify(message, language)
    policy = SafetyPolicy().evaluate(risk.risk_level)
    ctx = build_care_context(db, user_id, language, query_hint=message)
    recs = []
    if not policy["template_key"]:
        recs = generate_recommendations(db, user_id, message, language)
    return {
        "risk_level": risk.risk_level,
        "reasons": risk.reasons,
        "policy": policy,
        "context_summary": {
            "goals_count": len(ctx.get("goals") or []),
            "upcoming_events_count": len(ctx.get("upcoming_events") or []),
        },
        "recommendations": recs,
        "template": SafetyPolicy().response_for_level(risk.risk_level, language),
    }


# --- Follow-up tasks ---

def list_follow_ups(db: Session, user_id: int) -> List[dict]:
    rows = (
        db.query(models.CareFollowUpTask)
        .filter(models.CareFollowUpTask.user_id == user_id)
        .order_by(models.CareFollowUpTask.created_at.desc())
        .all()
    )
    return [_task_dict(r) for r in rows]


def _task_dict(row: models.CareFollowUpTask) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description,
        "status": row.status,
        "due_at": row.due_at.isoformat() + "Z" if row.due_at else None,
        "linked_recommendation_id": row.linked_recommendation_id,
        "created_at": row.created_at.isoformat() + "Z",
    }


def create_follow_up(db: Session, user_id: int, body: FollowUpCreateIn) -> dict:
    now = datetime.utcnow()
    row = models.CareFollowUpTask(
        user_id=user_id,
        title=body.title.strip(),
        description=body.description,
        status="open",
        due_at=body.due_at,
        linked_recommendation_id=body.linked_recommendation_id,
        source="manual",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _task_dict(row)


def update_follow_up(db: Session, user_id: int, task_id: int, body: FollowUpUpdateIn) -> dict:
    row = db.query(models.CareFollowUpTask).filter(
        models.CareFollowUpTask.id == task_id,
        models.CareFollowUpTask.user_id == user_id,
    ).first()
    if not row:
        raise Gate3NotFoundError()
    if body.title is not None:
        row.title = body.title.strip()
    if body.description is not None:
        row.description = body.description
    if body.status is not None:
        row.status = body.status
    if body.due_at is not None:
        row.due_at = body.due_at
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _task_dict(row)


def delete_follow_up(db: Session, user_id: int, task_id: int) -> None:
    row = db.query(models.CareFollowUpTask).filter(
        models.CareFollowUpTask.id == task_id,
        models.CareFollowUpTask.user_id == user_id,
    ).first()
    if not row:
        raise Gate3NotFoundError()
    db.delete(row)
    db.commit()
