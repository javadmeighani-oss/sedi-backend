"""I5-IMPL-W2-P03 — admin review API surfaces for KU / gap / safety / conflict.

Extends the W1-P02 health stub with human-in-the-loop review endpoints.
Authorization follows repository convention: X-Admin-Token when ADMIN_TOKEN is set.
Does not mount crawler activation or source enablement.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas.i5_core import MANAGEMENT_ALIAS, PACKAGE_ID, PACKAGE_TITLE
from backend.app.services.i5 import admin_review_service as ars
from backend.app.services.i5.knowledge_unit_service import (
    build_canonical_hash,
    build_deduplication_key,
    evaluate_runtime_eligibility,
)
from backend.app.services.i5.provenance_service import is_provenance_complete

router = APIRouter(prefix="/i5/admin", tags=["i5-admin"])


def _require_admin(request: Request) -> None:
    """Require X-Admin-Token when ADMIN_TOKEN env is set. 404 if unset; 401 if mismatch."""
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=404, detail="Not Found")
    header_token = (request.headers.get("X-Admin-Token") or "").strip()
    if header_token != token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _map_service_error(exc: ars.AdminReviewServiceError) -> HTTPException:
    msg = str(exc)
    if "NOT_FOUND" in msg:
        return HTTPException(status_code=404, detail=msg)
    return HTTPException(status_code=400, detail=msg)


class StartSafetyReviewBody(BaseModel):
    queue_item_id: str = Field(..., min_length=1, max_length=64)
    actor_reference: str = Field(..., min_length=1, max_length=512)


class CloseSafetyReviewBody(BaseModel):
    queue_item_id: str = Field(..., min_length=1, max_length=64)
    closed_status: str = Field(..., min_length=1, max_length=32)
    decision_id: int = Field(..., gt=0)
    reason: str = Field(..., min_length=1, max_length=4000)
    actor_reference: str = Field(..., min_length=1, max_length=512)


class ResolveConflictBody(BaseModel):
    conflict_key: str = Field(..., min_length=1, max_length=64)
    resolution_note: str = Field(..., min_length=1, max_length=4000)
    actor_reference: str = Field(..., min_length=1, max_length=512)


class TriageGapBody(BaseModel):
    gap_id: int = Field(..., gt=0)
    new_status: str = Field(..., min_length=1, max_length=32)
    reviewer_reference: str = Field(..., min_length=1, max_length=512)
    reason: Optional[str] = Field(None, max_length=2000)


@router.get("/package")
def admin_package_identity(request: Request) -> dict[str, object]:
    """Canonical W2-P03 / P05 identity (read)."""
    _require_admin(request)
    return {
        "ok": True,
        "package_id": PACKAGE_ID,
        "management_alias": MANAGEMENT_ALIAS,
        "title": PACKAGE_TITLE,
        "crawler_activation": False,
        "source_activation": False,
    }


@router.get("/knowledge-units/health")
def knowledge_units_health() -> dict[str, object]:
    """Legacy W1-P02 placeholder health (no auth; no DB)."""
    dedupe = build_deduplication_key(
        "health", "placeholder", "general", "ZZ", "canonical-placeholder"
    )
    canon = build_canonical_hash(
        "placeholder statement",
        "health",
        "FACT",
        language="en",
    )
    eligibility = evaluate_runtime_eligibility(
        {"provenance_complete": False, "runtime_eligibility": "ELIGIBLE"}
    )
    return {
        "ok": True,
        "package": PACKAGE_ID,
        "deduplication_key_len": len(dedupe),
        "canonical_hash_len": len(canon),
        "eligibility": eligibility.value,
    }


@router.get("/provenance/health")
def provenance_health() -> dict[str, object]:
    """Legacy W1-P02 placeholder health (no auth; no DB)."""
    complete = is_provenance_complete(
        {
            "knowledge_unit_id": 1,
            "source_profile_id": 1,
            "retrieval_method": "ADMIN_HEALTH_CHECK",
        }
    )
    incomplete = is_provenance_complete(
        {"knowledge_unit_id": None, "source_profile_id": 1, "retrieval_method": ""}
    )
    return {
        "ok": True,
        "package": PACKAGE_ID,
        "complete_probe": complete,
        "incomplete_probe": incomplete,
    }


@router.get("/safety-reviews")
def list_safety_reviews(
    request: Request,
    status: Optional[str] = Query(None),
    knowledge_unit_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_admin(request)
    try:
        items = ars.list_safety_reviews(
            db, status=status, knowledge_unit_id=knowledge_unit_id
        )
    except ars.AdminReviewServiceError as exc:
        raise _map_service_error(exc) from exc
    return {
        "ok": True,
        "package_id": PACKAGE_ID,
        "count": len(items),
        "items": [item.__dict__ for item in items],
    }


@router.post("/safety-reviews/start")
def start_safety_review(
    request: Request,
    body: StartSafetyReviewBody,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_admin(request)
    try:
        item = ars.start_safety_review(
            db,
            queue_item_id=body.queue_item_id,
            actor_reference=body.actor_reference,
        )
    except ars.AdminReviewServiceError as exc:
        raise _map_service_error(exc) from exc
    return {"ok": True, "item": item.__dict__}


@router.post("/safety-reviews/close")
def close_safety_review(
    request: Request,
    body: CloseSafetyReviewBody,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_admin(request)
    try:
        item = ars.close_safety_review(
            db,
            queue_item_id=body.queue_item_id,
            closed_status=body.closed_status,
            decision_id=body.decision_id,
            reason=body.reason,
            actor_reference=body.actor_reference,
        )
    except ars.AdminReviewServiceError as exc:
        raise _map_service_error(exc) from exc
    return {"ok": True, "item": item.__dict__}


@router.get("/conflicts")
def list_conflicts(
    request: Request,
    conflict_state: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_admin(request)
    try:
        items = ars.list_conflicts(db, conflict_state=conflict_state)
    except ars.AdminReviewServiceError as exc:
        raise _map_service_error(exc) from exc
    return {
        "ok": True,
        "package_id": PACKAGE_ID,
        "count": len(items),
        "items": [item.__dict__ for item in items],
    }


@router.post("/conflicts/resolve")
def resolve_conflict(
    request: Request,
    body: ResolveConflictBody,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_admin(request)
    try:
        item = ars.resolve_conflict_review(
            db,
            conflict_key=body.conflict_key,
            resolution_note=body.resolution_note,
            actor_reference=body.actor_reference,
        )
    except ars.AdminReviewServiceError as exc:
        raise _map_service_error(exc) from exc
    return {"ok": True, "item": item.__dict__}


@router.get("/knowledge-gaps")
def list_knowledge_gaps(
    request: Request,
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_admin(request)
    try:
        items = ars.list_knowledge_gaps(db, status=status, priority=priority)
    except ars.AdminReviewServiceError as exc:
        raise _map_service_error(exc) from exc
    return {
        "ok": True,
        "package_id": PACKAGE_ID,
        "count": len(items),
        "items": [item.__dict__ for item in items],
    }


@router.post("/knowledge-gaps/triage")
def triage_knowledge_gap(
    request: Request,
    body: TriageGapBody,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    _require_admin(request)
    try:
        item = ars.triage_knowledge_gap(
            db,
            gap_id=body.gap_id,
            new_status=body.new_status,
            reviewer_reference=body.reviewer_reference,
            reason=body.reason,
        )
    except ars.AdminReviewServiceError as exc:
        raise _map_service_error(exc) from exc
    return {"ok": True, "item": item.__dict__}
