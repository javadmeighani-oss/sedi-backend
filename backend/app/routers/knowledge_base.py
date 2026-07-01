"""Gate 3 curated knowledge base API (/knowledge-base/*)."""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas import APIResponse
from backend.app.schemas.gate3 import (
    KnowledgeDocumentCreateIn,
    KnowledgeDocumentUpdateIn,
    KnowledgeIngestIn,
    KnowledgeSearchIn,
    KnowledgeSourceCreateIn,
    KnowledgeSourceUpdateIn,
    IngestionRejectIn,
)
from backend.app.routers.auth_otp import get_current_user
from backend.app.routers.jwt_guards import reject_legacy_user_id_query
from backend.app import models
from backend.app.services.gate3.fetch_security import FetchSecurityError
from backend.app.services.gate3.knowledge_base_service import (
    Gate3NotFoundError,
    create_document,
    create_source,
    ingest_content,
    list_documents,
    list_sources,
    update_document,
    update_source,
)
from backend.app.services.gate3.knowledge_retrieval_service import search_knowledge
from backend.app.services.gate3.knowledge_update_service import KnowledgeUpdateService
from backend.app.services.gate3.robots_checker import RobotsBlockedError
from backend.app.services.gate3.safety_core import RiskClassifier

router = APIRouter()


def _require_admin(request: Request) -> None:
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=404, detail="Not Found")
    header_token = (request.headers.get("X-Admin-Token") or "").strip()
    if header_token != token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _not_found():
    raise HTTPException(status_code=404, detail="Not found")


@router.get("/sources", response_model=APIResponse)
def get_sources(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    return APIResponse(ok=True, data={"sources": list_sources(db)})


@router.post("/sources", response_model=APIResponse)
def post_source(request: Request, body: KnowledgeSourceCreateIn, db: Session = Depends(get_db)):
    _require_admin(request)
    return APIResponse(ok=True, data=create_source(db, body))


@router.patch("/sources/{source_id}", response_model=APIResponse)
def patch_source(request: Request, source_id: int, body: KnowledgeSourceUpdateIn, db: Session = Depends(get_db)):
    _require_admin(request)
    try:
        return APIResponse(ok=True, data=update_source(db, source_id, body))
    except Gate3NotFoundError:
        _not_found()


@router.get("/documents", response_model=APIResponse)
def get_documents(request: Request, source_id: Optional[int] = None, db: Session = Depends(get_db)):
    _require_admin(request)
    return APIResponse(ok=True, data={"documents": list_documents(db, source_id)})


@router.post("/documents", response_model=APIResponse)
def post_document(request: Request, body: KnowledgeDocumentCreateIn, db: Session = Depends(get_db)):
    _require_admin(request)
    try:
        return APIResponse(ok=True, data=create_document(db, body))
    except Gate3NotFoundError:
        _not_found()


@router.patch("/documents/{document_id}", response_model=APIResponse)
def patch_document(request: Request, document_id: int, body: KnowledgeDocumentUpdateIn, db: Session = Depends(get_db)):
    _require_admin(request)
    try:
        return APIResponse(ok=True, data=update_document(db, document_id, body))
    except Gate3NotFoundError:
        _not_found()


@router.post("/ingest", response_model=APIResponse)
def post_ingest(request: Request, body: KnowledgeIngestIn, db: Session = Depends(get_db)):
    _require_admin(request)
    try:
        return APIResponse(ok=True, data=ingest_content(db, body, run_by="admin"))
    except Gate3NotFoundError:
        _not_found()


@router.post("/sources/{source_id}/fetch", response_model=APIResponse)
def post_source_fetch(request: Request, source_id: int, db: Session = Depends(get_db)):
    _require_admin(request)
    try:
        data = KnowledgeUpdateService().fetch_source(db, source_id, run_by="admin")
        return APIResponse(ok=True, data=data)
    except Gate3NotFoundError:
        _not_found()
    except (FetchSecurityError, RobotsBlockedError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ingestion-runs", response_model=APIResponse)
def get_ingestion_runs(
    request: Request,
    source_id: Optional[int] = None,
    review_status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    _require_admin(request)
    svc = KnowledgeUpdateService()
    return APIResponse(ok=True, data={"runs": svc.list_runs(db, source_id=source_id, review_status=review_status)})


@router.get("/ingestion-runs/{run_id}", response_model=APIResponse)
def get_ingestion_run(request: Request, run_id: int, db: Session = Depends(get_db)):
    _require_admin(request)
    try:
        return APIResponse(ok=True, data=KnowledgeUpdateService().get_run(db, run_id))
    except Gate3NotFoundError:
        _not_found()


@router.post("/ingestion-runs/{run_id}/approve", response_model=APIResponse)
def post_ingestion_approve(request: Request, run_id: int, db: Session = Depends(get_db)):
    _require_admin(request)
    try:
        data = KnowledgeUpdateService().approve_run(db, run_id, approved_by="admin")
        return APIResponse(ok=True, data=data)
    except Gate3NotFoundError:
        _not_found()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ingestion-runs/{run_id}/reject", response_model=APIResponse)
def post_ingestion_reject(
    request: Request,
    run_id: int,
    body: IngestionRejectIn,
    db: Session = Depends(get_db),
):
    _require_admin(request)
    try:
        data = KnowledgeUpdateService().reject_run(db, run_id, reason=body.reason, rejected_by="admin")
        return APIResponse(ok=True, data=data)
    except Gate3NotFoundError:
        _not_found()


@router.get("/search", response_model=APIResponse)
def get_search(
    request: Request,
    q: str,
    category: Optional[str] = None,
    locale: Optional[str] = None,
    limit: int = 5,
    db: Session = Depends(get_db),
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
):
    """JWT user search with SafetyPolicy."""
    risk = RiskClassifier().classify(q, locale or "fa")
    data = search_knowledge(db, q, category=category, locale=locale, limit=limit, risk_level=risk.risk_level)
    return APIResponse(ok=True, data=data)
