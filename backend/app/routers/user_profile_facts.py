"""JWT CRUD for Gate 1 structured profile facts."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse
from backend.app.schemas.gate1 import ProfileFactCreateIn, ProfileFactUpdateIn
from backend.app.routers.auth_otp import get_current_user
from backend.app.routers.jwt_guards import reject_legacy_user_id_query
from backend.app.services.user_profile_fact_service import (
    ProfileFactNotFoundError,
    create_profile_fact,
    delete_profile_fact,
    list_profile_facts,
    update_profile_fact,
)

router = APIRouter()


@router.get("/profile-facts", response_model=APIResponse)
def get_profile_facts(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    items = list_profile_facts(db, auth_user.id)
    return APIResponse(ok=True, data={"profile_facts": items})


@router.post("/profile-facts", response_model=APIResponse)
def post_profile_fact(
    body: ProfileFactCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        item = create_profile_fact(db, auth_user.id, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return APIResponse(ok=True, data=item)


@router.patch("/profile-facts/{fact_id}", response_model=APIResponse)
def patch_profile_fact(
    fact_id: int,
    body: ProfileFactUpdateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        item = update_profile_fact(db, auth_user.id, fact_id, body)
    except ProfileFactNotFoundError:
        raise HTTPException(status_code=404, detail="Profile fact not found") from None
    return APIResponse(ok=True, data=item)


@router.delete("/profile-facts/{fact_id}", response_model=APIResponse)
def delete_profile_fact_route(
    fact_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        delete_profile_fact(db, auth_user.id, fact_id)
    except ProfileFactNotFoundError:
        raise HTTPException(status_code=404, detail="Profile fact not found") from None
    return APIResponse(ok=True, data={"deleted": True, "id": fact_id})
