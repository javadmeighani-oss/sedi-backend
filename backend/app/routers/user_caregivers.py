"""JWT CRUD for Gate 1 caregiver contact registry."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse
from backend.app.schemas.gate1 import CaregiverCreateIn, CaregiverUpdateIn
from backend.app.routers.auth_otp import get_current_user
from backend.app.routers.jwt_guards import reject_legacy_user_id_query
from backend.app.services.user_caregiver_service import (
    CaregiverNotFoundError,
    create_caregiver,
    deactivate_caregiver,
    list_caregivers,
    update_caregiver,
)

router = APIRouter()


@router.get("/caregivers", response_model=APIResponse)
def get_caregivers(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    items = list_caregivers(db, auth_user.id)
    return APIResponse(ok=True, data={"caregivers": items})


@router.post("/caregivers", response_model=APIResponse)
def post_caregiver(
    body: CaregiverCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    item = create_caregiver(db, auth_user.id, body)
    return APIResponse(ok=True, data=item)


@router.patch("/caregivers/{caregiver_id}", response_model=APIResponse)
def patch_caregiver(
    caregiver_id: int,
    body: CaregiverUpdateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        item = update_caregiver(db, auth_user.id, caregiver_id, body)
    except CaregiverNotFoundError:
        raise HTTPException(status_code=404, detail="Caregiver not found") from None
    return APIResponse(ok=True, data=item)


@router.delete("/caregivers/{caregiver_id}", response_model=APIResponse)
def delete_caregiver_route(
    caregiver_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Soft-deactivate caregiver contact (is_active=false)."""
    try:
        deactivate_caregiver(db, auth_user.id, caregiver_id)
    except CaregiverNotFoundError:
        raise HTTPException(status_code=404, detail="Caregiver not found") from None
    return APIResponse(ok=True, data={"deleted": True, "id": caregiver_id, "soft": True})
