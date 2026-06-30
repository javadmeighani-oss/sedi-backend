# app/routers/user_knowledge.py
"""User Knowledge API: profile baseline (1 row per user) + facts (key-value per user)."""
import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas.user_knowledge import (
    UserProfileKnowledgeRead,
    UserProfileKnowledgeUpsertRequest,
    UserFactRead,
    UserFactUpsertRequest,
)
from backend.app.routers.auth_otp import get_current_user

router = APIRouter()


def _parse_json_list(raw):
    import json
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [str(raw).strip()] if str(raw).strip() else []
    if isinstance(data, list):
        return [str(x).strip() for x in data if x and str(x).strip()]
    if isinstance(data, str) and data.strip():
        return [data.strip()]
    return []


def _mirror_goals_json_to_user_goals(db: Session, user_id: int, goals_json: str) -> None:
    from backend.app.schemas.gate2 import GoalCreateIn
    from backend.app.services.gate2_data_service import create_goal, list_goals

    existing_titles = {g["title"].strip().lower() for g in list_goals(db, user_id)}
    for title in _parse_json_list(goals_json):
        norm = title.strip().lower()
        if not norm or norm in existing_titles:
            continue
        create_goal(db, user_id, GoalCreateIn(title=title[:256], source="system", category="lifestyle"))
        existing_titles.add(norm)


def _mirror_constraints_json_to_restrictions(db: Session, user_id: int, constraints_json: str) -> None:
    from backend.app.schemas.gate2 import RestrictionCreateIn
    from backend.app.services.gate2_data_service import create_restriction, list_restrictions

    existing_titles = {r["title"].strip().lower() for r in list_restrictions(db, user_id)}
    for title in _parse_json_list(constraints_json):
        norm = title.strip().lower()
        if not norm or norm in existing_titles:
            continue
        create_restriction(
            db, user_id,
            RestrictionCreateIn(restriction_type="other", title=title[:256], source="system"),
        )
        existing_titles.add(norm)


def _reject_legacy_user_id_query(request: Request) -> None:
    """Reject legacy user_id query param; identity comes from JWT only."""
    if request.query_params.get("user_id") is not None:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "type": "extra_forbidden",
                    "loc": ["query", "user_id"],
                    "msg": "Extra inputs are not permitted",
                    "input": request.query_params.get("user_id"),
                }
            ],
        )


def _require_admin(request: Request) -> None:
    """Admin-only: require ADMIN_TOKEN env and X-Admin-Token header. 404 if no token set; 401 if mismatch."""
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=404, detail="Not Found")
    header_token = (request.headers.get("X-Admin-Token") or "").strip()
    if header_token != token:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/knowledge", response_model=UserProfileKnowledgeRead)
def get_knowledge(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Get user profile knowledge (baseline). Requires Bearer JWT."""
    row = (
        db.query(models.UserProfileKnowledge)
        .filter(models.UserProfileKnowledge.user_id == auth_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No profile knowledge found for this user.")
    return row


@router.put("/knowledge", response_model=UserProfileKnowledgeRead)
def upsert_knowledge(
    payload: UserProfileKnowledgeUpsertRequest,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upsert user profile knowledge (1 row per user). Requires Bearer JWT."""
    user_id = auth_user.id
    row = (
        db.query(models.UserProfileKnowledge)
        .filter(models.UserProfileKnowledge.user_id == user_id)
        .first()
    )
    if row:
        row.display_name = payload.display_name if payload.display_name is not None else row.display_name
        row.language = payload.language if payload.language is not None else row.language
        row.baseline_summary = payload.baseline_summary if payload.baseline_summary is not None else row.baseline_summary
        # Gate 2: goals_json/constraints_json read-compat; mirror into canonical tables when written
        if payload.goals_json is not None:
            row.goals_json = payload.goals_json
            _mirror_goals_json_to_user_goals(db, user_id, payload.goals_json)
        if payload.constraints_json is not None:
            row.constraints_json = payload.constraints_json
            _mirror_constraints_json_to_restrictions(db, user_id, payload.constraints_json)
        row.preferences_json = payload.preferences_json if payload.preferences_json is not None else row.preferences_json
        row.updated_at = datetime.utcnow()
    else:
        row = models.UserProfileKnowledge(
            user_id=user_id,
            display_name=payload.display_name,
            language=payload.language,
            baseline_summary=payload.baseline_summary,
            goals_json=payload.goals_json,
            constraints_json=payload.constraints_json,
            preferences_json=payload.preferences_json,
        )
        db.add(row)
        db.flush()
        if payload.goals_json:
            _mirror_goals_json_to_user_goals(db, user_id, payload.goals_json)
        if payload.constraints_json:
            _mirror_constraints_json_to_restrictions(db, user_id, payload.constraints_json)
    db.commit()
    db.refresh(row)
    return row


@router.get("/facts", response_model=List[UserFactRead])
def get_facts(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Get all facts for the authenticated user. Requires Bearer JWT."""
    rows = (
        db.query(models.UserFact)
        .filter(models.UserFact.user_id == auth_user.id)
        .order_by(models.UserFact.updated_at.desc())
        .all()
    )
    return list(rows)


@router.post("/facts", response_model=UserFactRead)
def upsert_fact(
    payload: UserFactUpsertRequest,
    auth_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upsert a fact by key for the authenticated user. Requires Bearer JWT."""
    user_id = auth_user.id
    source = (payload.source or "manual").strip()
    if source not in ("chat", "manual", "device"):
        source = "manual"
    row = (
        db.query(models.UserFact)
        .filter(
            models.UserFact.user_id == user_id,
            models.UserFact.key == payload.key,
        )
        .first()
    )
    if row:
        row.value_json = payload.value_json if payload.value_json is not None else row.value_json
        row.source = source
        row.confidence = payload.confidence if payload.confidence is not None else row.confidence
        row.updated_at = datetime.utcnow()
    else:
        row = models.UserFact(
            user_id=user_id,
            key=payload.key,
            value_json=payload.value_json,
            source=source,
            confidence=payload.confidence if payload.confidence is not None else 0.7,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/facts/cleanup")
def cleanup_duplicate_facts(
    request: Request,
    dry_run: bool = Query(True, description="If true, only report; if false, delete duplicates"),
    db: Session = Depends(get_db),
):
    """Admin-only. Find (user_id, key) duplicate groups; keep row with latest updated_at (tie: highest id), delete rest. Requires X-Admin-Token header."""
    _require_admin(request)
    duplicate_pairs = (
        db.query(models.UserFact.user_id, models.UserFact.key)
        .group_by(models.UserFact.user_id, models.UserFact.key)
        .having(func.count(models.UserFact.id) > 1)
        .all()
    )
    duplicate_groups = len(duplicate_pairs)
    rows_to_delete = 0
    to_delete = []
    for (uid, key) in duplicate_pairs:
        rows = (
            db.query(models.UserFact)
            .filter(
                models.UserFact.user_id == uid,
                models.UserFact.key == key,
            )
            .order_by(models.UserFact.updated_at.desc(), models.UserFact.id.desc())
            .all()
        )
        if len(rows) > 1:
            to_delete.extend(rows[1:])
            rows_to_delete += len(rows) - 1
    deleted_rows = 0
    if not dry_run and to_delete:
        for row in to_delete:
            db.delete(row)
        db.commit()
        deleted_rows = len(to_delete)
    return {
        "dry_run": dry_run,
        "duplicate_groups": duplicate_groups,
        "rows_to_delete": rows_to_delete,
        "deleted_rows": deleted_rows,
        "kept_rows": duplicate_groups,
    }
