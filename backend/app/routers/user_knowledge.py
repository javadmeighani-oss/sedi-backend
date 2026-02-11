# app/routers/user_knowledge.py
"""User Knowledge API: profile baseline (1 row per user) + facts (key-value per user)."""
import os
from typing import List
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.schemas.user_knowledge import (
    UserProfileKnowledgeRead,
    UserProfileKnowledgeUpsert,
    UserFactRead,
    UserFactUpsert,
)

router = APIRouter()


def _ensure_user(db: Session, user_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _require_admin(request: Request) -> None:
    """Admin-only: require ADMIN_TOKEN env and X-Admin-Token header. 404 if no token set; 401 if mismatch."""
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=404, detail="Not Found")
    header_token = (request.headers.get("X-Admin-Token") or "").strip()
    if header_token != token:
        raise HTTPException(status_code=401, detail="Unauthorized")


# -------------------- GET /user/knowledge --------------------
@router.get("/knowledge", response_model=UserProfileKnowledgeRead)
def get_knowledge(
    user_id: int = Query(..., description="User ID"),
    db: Session = Depends(get_db),
):
    """Get user profile knowledge (baseline). Returns 404 if user or row missing."""
    _ensure_user(db, user_id)
    row = (
        db.query(models.UserProfileKnowledge)
        .filter(models.UserProfileKnowledge.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No profile knowledge found for this user.")
    return row


# -------------------- PUT /user/knowledge --------------------
@router.put("/knowledge", response_model=UserProfileKnowledgeRead)
def upsert_knowledge(
    payload: UserProfileKnowledgeUpsert,
    db: Session = Depends(get_db),
):
    """Upsert user profile knowledge (1 row per user)."""
    _ensure_user(db, payload.user_id)
    row = (
        db.query(models.UserProfileKnowledge)
        .filter(models.UserProfileKnowledge.user_id == payload.user_id)
        .first()
    )
    if row:
        row.display_name = payload.display_name if payload.display_name is not None else row.display_name
        row.language = payload.language if payload.language is not None else row.language
        row.baseline_summary = payload.baseline_summary if payload.baseline_summary is not None else row.baseline_summary
        row.goals_json = payload.goals_json if payload.goals_json is not None else row.goals_json
        row.constraints_json = payload.constraints_json if payload.constraints_json is not None else row.constraints_json
        row.preferences_json = payload.preferences_json if payload.preferences_json is not None else row.preferences_json
        row.updated_at = datetime.utcnow()
    else:
        row = models.UserProfileKnowledge(
            user_id=payload.user_id,
            display_name=payload.display_name,
            language=payload.language,
            baseline_summary=payload.baseline_summary,
            goals_json=payload.goals_json,
            constraints_json=payload.constraints_json,
            preferences_json=payload.preferences_json,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


# -------------------- GET /user/facts --------------------
@router.get("/facts", response_model=List[UserFactRead])
def get_facts(
    user_id: int = Query(..., description="User ID"),
    db: Session = Depends(get_db),
):
    """Get all facts for a user. Strictly filtered by user_id."""
    _ensure_user(db, user_id)
    rows = (
        db.query(models.UserFact)
        .filter(models.UserFact.user_id == user_id)
        .order_by(models.UserFact.updated_at.desc())
        .all()
    )
    return list(rows)


# -------------------- POST /user/facts --------------------
@router.post("/facts", response_model=UserFactRead)
def upsert_fact(
    payload: UserFactUpsert,
    db: Session = Depends(get_db),
):
    """Upsert a fact by (user_id, key). value_json stored as-is (plain text). SAFE: query by (user_id, key) then update or insert to enforce uniqueness at application level."""
    _ensure_user(db, payload.user_id)
    source = (payload.source or "manual").strip()
    if source not in ("chat", "manual", "device"):
        source = "manual"
    # Uniqueness: always query by (user_id, key) first; update if exists, insert only if missing.
    row = (
        db.query(models.UserFact)
        .filter(
            models.UserFact.user_id == payload.user_id,
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
            user_id=payload.user_id,
            key=payload.key,
            value_json=payload.value_json,
            source=source,
            confidence=payload.confidence if payload.confidence is not None else 0.7,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


# -------------------- POST /user/facts/cleanup (admin-only) --------------------
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


# ---------------------------------------------------------------------------
# curl examples (backend at http://localhost:8000)
# ---------------------------------------------------------------------------
#
# PUT /user/knowledge (upsert profile baseline)
#   curl -s -X PUT "http://localhost:8000/user/knowledge" \
#     -H "Content-Type: application/json" \
#     -d '{"user_id":1,"baseline_summary":"User prefers Persian. Focus on gentle reminders."}'
#
# GET /user/knowledge
#   curl -s "http://localhost:8000/user/knowledge?user_id=1"
#
# POST /user/facts (upsert one fact)
#   curl -s -X POST "http://localhost:8000/user/facts" \
#     -H "Content-Type: application/json" \
#     -d '{"user_id":1,"key":"diet","value_json":"low sodium","source":"manual"}'
#
# GET /user/facts
#   curl -s "http://localhost:8000/user/facts?user_id=1"
#
# POST /user/facts/cleanup (admin-only; set ADMIN_TOKEN in env)
#   Dry run:
#   curl -s -X POST "http://localhost:8000/user/facts/cleanup?dry_run=true" -H "X-Admin-Token: <ADMIN_TOKEN>"
#   Execute:
#   curl -s -X POST "http://localhost:8000/user/facts/cleanup?dry_run=false" -H "X-Admin-Token: <ADMIN_TOKEN>"
#
# Verify injection: set baseline_summary to "User prefers Persian", then
# POST /interact/chat with user_id=1 and a question; response should align
# with that preference (e.g. Persian or acknowledgment of preference).
