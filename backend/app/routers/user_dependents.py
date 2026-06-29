"""JWT API for Gate 1 dependent (special) users."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.schemas.gate1 import DependentCreateIn, DependentUpdateIn
from backend.app.routers.auth_otp import get_current_user
from backend.app.routers.jwt_guards import reject_legacy_user_id_query
from backend.app.services.user_dependent_service import (
    DependentAccessDeniedError,
    DependentNotFoundError,
    create_dependent,
    deactivate_dependent,
    get_dependent,
    list_dependents,
    update_dependent,
)

router = APIRouter()


@router.post("/dependents", response_model=APIResponse)
def post_dependent(
    body: DependentCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        item = create_dependent(db, auth_user.id, body)
    except DependentAccessDeniedError as exc:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="DEPENDENT_ACCESS_DENIED", message=str(exc) or "Access denied"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return APIResponse(ok=True, data=item)


@router.get("/dependents", response_model=APIResponse)
def get_dependents(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    items = list_dependents(db, auth_user.id)
    return APIResponse(ok=True, data={"dependents": items})


@router.get("/dependents/{dependent_user_id}", response_model=APIResponse)
def get_dependent_route(
    dependent_user_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        item = get_dependent(db, auth_user.id, dependent_user_id)
    except DependentNotFoundError:
        raise HTTPException(status_code=404, detail="Dependent not found") from None
    return APIResponse(ok=True, data=item)


@router.patch("/dependents/{dependent_user_id}", response_model=APIResponse)
def patch_dependent(
    dependent_user_id: int,
    body: DependentUpdateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    try:
        item = update_dependent(db, auth_user.id, dependent_user_id, body)
    except DependentNotFoundError:
        raise HTTPException(status_code=404, detail="Dependent not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return APIResponse(ok=True, data=item)


@router.delete("/dependents/{dependent_user_id}", response_model=APIResponse)
def delete_dependent_route(
    dependent_user_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Deactivate caregiver↔dependent relationship (soft)."""
    try:
        deactivate_dependent(db, auth_user.id, dependent_user_id)
    except DependentNotFoundError:
        raise HTTPException(status_code=404, detail="Dependent not found") from None
    return APIResponse(ok=True, data={"deleted": True, "dependent_user_id": dependent_user_id, "soft": True})
