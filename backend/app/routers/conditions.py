# app/routers/conditions.py
"""
Conditions Router - Medical Condition Management

Optional endpoints for listing and assigning user conditions.
This router provides basic CRUD operations for medical conditions.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List

from backend.app.database import get_db
from backend.app.models import User, UserCondition
from backend.app.schemas import APIResponse, ErrorInfo
from backend.app.schemas.medical import (
    MedicalConditionResponse,
    UserConditionAssignRequest,
    UserConditionResponse,
)
from backend.app.services.medical import MedicalService
from backend.app.routers.auth_otp import get_current_user

router = APIRouter()


def _reject_legacy_user_id_query(request: Request) -> None:
    """Reject legacy user_id query param; identity comes from JWT only."""
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


def _build_user_condition_responses(
    medical_service: MedicalService,
    user_conditions: List[UserCondition],
) -> List[UserConditionResponse]:
    condition_list = []
    for uc in user_conditions:
        condition = medical_service.get_condition_by_id(uc.condition_id)
        if condition:
            condition_list.append(
                UserConditionResponse(
                    id=uc.id,
                    user_id=uc.user_id,
                    condition_id=uc.condition_id,
                    diagnosed_date=uc.diagnosed_date,
                    severity=uc.severity,
                    notes=uc.notes,
                    embedding_id=uc.embedding_id,
                    created_at=uc.created_at,
                    condition=MedicalConditionResponse(
                        id=condition.id,
                        name=condition.name,
                        description=condition.description,
                        category=condition.category,
                        embedding_id=condition.embedding_id,
                        created_at=condition.created_at,
                    ),
                )
            )
    return condition_list


# -------------------- GET /conditions --------------------
@router.get("", response_model=APIResponse)
@router.get("/", response_model=APIResponse)
def get_all_conditions(db: Session = Depends(get_db)):
    """
    Get all available medical conditions.

    Returns a list of all medical conditions in the system.
    """
    medical_service = MedicalService(db)
    conditions = medical_service.get_all_conditions()

    condition_list = [
        MedicalConditionResponse(
            id=cond.id,
            name=cond.name,
            description=cond.description,
            category=cond.category,
            embedding_id=cond.embedding_id,
            created_at=cond.created_at,
        )
        for cond in conditions
    ]

    return APIResponse(
        ok=True,
        data={"conditions": [c.dict() for c in condition_list]},
    )


# -------------------- GET /conditions/user --------------------
@router.get("/user", response_model=APIResponse)
def get_user_conditions(
    auth_user: User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """
    Get all conditions assigned to the authenticated user.

    Requires Bearer JWT; user identity is derived from the token only.
    """
    medical_service = MedicalService(db)
    user_conditions = medical_service.get_user_conditions(auth_user.id)
    condition_list = _build_user_condition_responses(medical_service, user_conditions)

    return APIResponse(
        ok=True,
        data={"user_conditions": [c.dict() for c in condition_list]},
    )


# -------------------- POST /conditions/assign --------------------
@router.post("/assign", response_model=APIResponse)
def assign_condition(
    payload: UserConditionAssignRequest,
    auth_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Assign a medical condition to the authenticated user.

    Requires Bearer JWT; user identity is derived from the token only.
    """
    medical_service = MedicalService(db)
    condition = medical_service.get_condition_by_id(payload.condition_id)
    if not condition:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="CONDITION_NOT_FOUND", message="Medical condition not found."),
        )

    user_condition = medical_service.assign_condition_to_user(
        user_id=auth_user.id,
        condition_id=payload.condition_id,
        diagnosed_date=payload.diagnosed_date,
        severity=payload.severity,
        notes=payload.notes,
    )

    response = UserConditionResponse(
        id=user_condition.id,
        user_id=user_condition.user_id,
        condition_id=user_condition.condition_id,
        diagnosed_date=user_condition.diagnosed_date,
        severity=user_condition.severity,
        notes=user_condition.notes,
        embedding_id=user_condition.embedding_id,
        created_at=user_condition.created_at,
        condition=MedicalConditionResponse(
            id=condition.id,
            name=condition.name,
            description=condition.description,
            category=condition.category,
            embedding_id=condition.embedding_id,
            created_at=condition.created_at,
        ),
    )

    return APIResponse(
        ok=True,
        data=response.dict(),
    )


# -------------------- DELETE /conditions/user/condition/{condition_id} --------------------
@router.delete("/user/condition/{condition_id}", response_model=APIResponse)
def remove_user_condition(
    condition_id: int,
    auth_user: User = Depends(get_current_user),
    _: None = Depends(_reject_legacy_user_id_query),
    db: Session = Depends(get_db),
):
    """
    Remove a condition assignment from the authenticated user.

    Requires Bearer JWT; user identity is derived from the token only.
    """
    medical_service = MedicalService(db)
    removed = medical_service.remove_user_condition(auth_user.id, condition_id)

    if removed:
        return APIResponse(
            ok=True,
            data={"message": "Condition removed from user successfully."},
        )
    return APIResponse(
        ok=False,
        error=ErrorInfo(code="CONDITION_NOT_ASSIGNED", message="Condition is not assigned to this user."),
    )
