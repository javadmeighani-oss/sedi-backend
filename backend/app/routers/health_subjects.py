"""Health Subject management routes (I9 foundation)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import User
from backend.app.routers.auth_otp import get_current_user
from backend.app.schemas.health_subject import (
    HealthSubjectApiResponse,
    ManagedHealthSubjectCreate,
)
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)

router = APIRouter()


@router.post("/self", response_model=HealthSubjectApiResponse)
def ensure_self_health_subject(
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ensure account holder has a SELF health subject."""
    subject = ensure_self_subject_for_account(db, auth_user.id)
    return HealthSubjectApiResponse(
        ok=True,
        data={
            "health_subject_id": subject.id,
            "display_name": subject.display_name,
            "linked_user_id": subject.linked_user_id,
            "subject_kind": subject.subject_kind,
        },
    )


@router.post("/managed", response_model=HealthSubjectApiResponse)
def create_managed_health_subject(
    body: ManagedHealthSubjectCreate,
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a managed health subject without a linked Sedi account."""
    subject = create_managed_subject_without_account(
        db,
        account_user_id=auth_user.id,
        display_name=body.display_name,
        access_role=body.access_role,
    )
    return HealthSubjectApiResponse(
        ok=True,
        data={
            "health_subject_id": subject.id,
            "display_name": subject.display_name,
            "linked_user_id": subject.linked_user_id,
            "subject_kind": subject.subject_kind,
            "access_role": body.access_role,
        },
    )
