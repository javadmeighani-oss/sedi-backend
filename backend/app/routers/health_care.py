"""Gate 3 health Q&A and symptoms API (mounted at /health)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse
from backend.app.schemas.gate3 import HealthQuestionIn, SymptomReportIn, SymptomReportPatchIn
from backend.app.routers.auth_otp import get_current_user
from backend.app.routers.jwt_guards import reject_legacy_user_id_query
from backend.app.services.gate3.care_intelligence import Gate3NotFoundError, get_vitals_summary
from backend.app.services.gate3.health_care_services import (
    answer_health_question,
    create_symptom_report,
    get_health_education,
    list_health_questions,
    list_symptom_reports,
    update_symptom_report,
)

router = APIRouter()


def _not_found():
    raise HTTPException(status_code=404, detail="Not found")


@router.post("/questions", response_model=APIResponse)
def post_health_question(
    body: HealthQuestionIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data=answer_health_question(db, auth_user.id, body))


@router.get("/questions", response_model=APIResponse)
def get_health_questions(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data={"questions": list_health_questions(db, auth_user.id)})


@router.get("/education", response_model=APIResponse)
def get_education(
    topic: str,
    language: Optional[str] = "fa",
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    if not topic or not topic.strip():
        raise HTTPException(status_code=422, detail="topic required")
    return APIResponse(ok=True, data=get_health_education(db, topic.strip(), language or "fa", auth_user.id))


@router.post("/symptoms", response_model=APIResponse)
def post_symptom(
    body: SymptomReportIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data=create_symptom_report(db, auth_user.id, body))


@router.get("/symptoms", response_model=APIResponse)
def get_symptoms(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data={"symptoms": list_symptom_reports(db, auth_user.id)})


@router.patch("/symptoms/{report_id}", response_model=APIResponse)
def patch_symptom(
    report_id: int,
    body: SymptomReportPatchIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse(ok=True, data=update_symptom_report(db, auth_user.id, report_id, body))
    except Gate3NotFoundError:
        _not_found()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/vitals-summary", response_model=APIResponse)
def get_vitals_summary_route(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data=get_vitals_summary(db, auth_user.id))
