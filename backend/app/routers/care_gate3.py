"""Gate 3 care intelligence API (/care/*)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse
from backend.app.schemas.gate3 import (
    CareAnalyzeIn,
    FollowUpCreateIn,
    FollowUpUpdateIn,
    RecommendationCreateIn,
    RecommendationPatchIn,
    SafetyCheckIn,
)
from backend.app.routers.auth_otp import get_current_user
from backend.app.routers.jwt_guards import reject_legacy_user_id_query
from backend.app.services.gate3.care_intelligence import (
    Gate3NotFoundError,
    analyze_message,
    build_care_context,
    create_follow_up,
    delete_follow_up,
    generate_recommendations,
    list_follow_ups,
    list_recommendations,
    patch_recommendation,
    update_follow_up,
)
from backend.app.services.gate3.safety_core import RiskClassifier, SafetyPolicy, persist_risk_assessment

router = APIRouter()


def _not_found():
    raise HTTPException(status_code=404, detail="Not found")


@router.get("/context", response_model=APIResponse)
def get_care_context(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data=build_care_context(db, auth_user.id))


@router.post("/safety-check", response_model=APIResponse)
def post_safety_check(
    body: SafetyCheckIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    result = RiskClassifier().classify(body.message, "fa")
    assessment = persist_risk_assessment(db, auth_user.id, result, body.message)
    policy = SafetyPolicy().evaluate(result.risk_level)
    template = SafetyPolicy().response_for_level(result.risk_level, "fa")
    return APIResponse(
        ok=True,
        data={
            "assessment": assessment,
            "policy": policy,
            "template": template,
        },
    )


@router.post("/analyze", response_model=APIResponse)
def post_analyze(
    body: CareAnalyzeIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    lang = body.language or "fa"
    data = analyze_message(db, auth_user.id, body.message, lang)
    persist_risk_assessment(db, auth_user.id, RiskClassifier().classify(body.message, lang), body.message)
    return APIResponse(ok=True, data=data)


@router.get("/recommendations", response_model=APIResponse)
def get_recommendations(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data={"recommendations": list_recommendations(db, auth_user.id)})


@router.post("/recommendations", response_model=APIResponse)
def post_recommendations(
    body: RecommendationCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    msg = body.trigger_message or ""
    recs = generate_recommendations(db, auth_user.id, msg, "fa", body)
    return APIResponse(ok=True, data={"recommendations": recs})


@router.patch("/recommendations/{rec_id}", response_model=APIResponse)
def patch_recommendation_route(
    rec_id: int,
    body: RecommendationPatchIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    if body.status is None:
        raise HTTPException(status_code=422, detail="status required")
    try:
        return APIResponse(ok=True, data=patch_recommendation(db, auth_user.id, rec_id, body.status))
    except Gate3NotFoundError:
        _not_found()


@router.get("/follow-ups", response_model=APIResponse)
def get_follow_ups(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data={"follow_ups": list_follow_ups(db, auth_user.id)})


@router.post("/follow-ups", response_model=APIResponse)
def post_follow_up(
    body: FollowUpCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    return APIResponse(ok=True, data=create_follow_up(db, auth_user.id, body))


@router.patch("/follow-ups/{task_id}", response_model=APIResponse)
def patch_follow_up(
    task_id: int,
    body: FollowUpUpdateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        return APIResponse(ok=True, data=update_follow_up(db, auth_user.id, task_id, body))
    except Gate3NotFoundError:
        _not_found()


@router.delete("/follow-ups/{task_id}", response_model=APIResponse)
def delete_follow_up_route(
    task_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        delete_follow_up(db, auth_user.id, task_id)
    except Gate3NotFoundError:
        _not_found()
    return APIResponse(ok=True, data={"deleted": True, "id": task_id})
