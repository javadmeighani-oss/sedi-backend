"""Authenticated I8 reactive operational action routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import User
from backend.app.routers.auth_otp import get_current_user
from backend.app.schemas.i8_action import I8GenerateActionRequest, I8GenerateActionResponse
from backend.app.services.i8.constants import ACTION_DOMAINS
from backend.app.services.i8.unified_core import generate_operational_action

router = APIRouter(prefix="/i8", tags=["I8 Operational Actions"])


@router.post("/actions/generate", response_model=I8GenerateActionResponse)
def generate_i8_action(
    body: I8GenerateActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.domain and body.domain not in ACTION_DOMAINS:
        raise HTTPException(status_code=422, detail="invalid_domain")
    result = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request=body.request,
        domain=body.domain,
        persist=body.persist,
        plan_idempotency_key=body.plan_idempotency_key,
        action_idempotency_key=body.action_idempotency_key,
    )
    return I8GenerateActionResponse(result=result.to_dict())
