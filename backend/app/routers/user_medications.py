"""JWT-protected user medication CRUD (Phase V1.1B)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app import models
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.schemas.medical import UserMedicationCreateIn, UserMedicationUpdateIn
from backend.app.routers.auth_otp import get_current_user
from backend.app.services.user_medication_service import (
    DuplicateUserMedicationError,
    UserMedicationNotFoundError,
    create_user_medication,
    delete_user_medication,
    list_user_medications,
    update_user_medication,
)

router = APIRouter()


def _reject_legacy_user_id_query(request: Request) -> None:
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


@router.get("/medications", response_model=APIResponse)
def get_user_medications(
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """List medications for the authenticated user."""
    items = list_user_medications(db, auth_user.id)
    return APIResponse(ok=True, data={"medications": items})


@router.post("/medications", response_model=APIResponse, status_code=200)
def post_user_medication(
    body: UserMedicationCreateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Add a medication assignment with optional daily reminder times."""
    try:
        item = create_user_medication(db, auth_user.id, body)
    except DuplicateUserMedicationError:
        return APIResponse(
            ok=False,
            error=ErrorInfo(
                code="MEDICATION_ALREADY_ASSIGNED",
                message="This medication is already assigned to your profile.",
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return APIResponse(ok=True, data=item)


@router.patch("/medications/{medication_assignment_id}", response_model=APIResponse)
def patch_user_medication(
    medication_assignment_id: int,
    body: UserMedicationUpdateIn,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Update user-specific medication fields and reminder schedule."""
    try:
        item = update_user_medication(db, auth_user.id, medication_assignment_id, body)
    except UserMedicationNotFoundError:
        raise HTTPException(status_code=404, detail="Medication not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return APIResponse(ok=True, data=item)


@router.delete("/medications/{medication_assignment_id}", response_model=APIResponse)
def delete_user_medication_route(
    medication_assignment_id: int,
    auth_user: models.User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """Remove a medication assignment (stops reminders)."""
    try:
        delete_user_medication(db, auth_user.id, medication_assignment_id)
    except UserMedicationNotFoundError:
        raise HTTPException(status_code=404, detail="Medication not found") from None
    return APIResponse(ok=True, data={"deleted": True, "id": medication_assignment_id})
