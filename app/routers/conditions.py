# app/routers/conditions.py
"""
Conditions Router - Medical Condition Management

Optional endpoints for listing and assigning user conditions.
This router provides basic CRUD operations for medical conditions.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models import User, MedicalCondition, UserCondition
from app.schemas import APIResponse, ErrorInfo
from app.schemas.medical import (
    MedicalConditionResponse,
    UserConditionCreate,
    UserConditionResponse
)
from app.services.medical import MedicalService

router = APIRouter()


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
            created_at=cond.created_at
        )
        for cond in conditions
    ]
    
    return APIResponse(
        ok=True,
        data={"conditions": [c.dict() for c in condition_list]}
    )


# -------------------- GET /conditions/user/{user_id} --------------------
@router.get("/user/{user_id}", response_model=APIResponse)
def get_user_conditions(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all conditions assigned to a user.
    
    Returns a list of user's medical conditions with details.
    """
    # Validate user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )
    
    medical_service = MedicalService(db)
    user_conditions = medical_service.get_user_conditions(user_id)
    
    # Build response with condition details
    condition_list = []
    for uc in user_conditions:
        condition = medical_service.get_condition_by_id(uc.condition_id)
        if condition:
            condition_list.append(UserConditionResponse(
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
                    created_at=condition.created_at
                )
            ))
    
    return APIResponse(
        ok=True,
        data={"user_conditions": [c.dict() for c in condition_list]}
    )


# -------------------- POST /conditions/assign --------------------
@router.post("/assign", response_model=APIResponse)
def assign_condition(
    payload: UserConditionCreate,
    db: Session = Depends(get_db)
):
    """
    Assign a medical condition to a user.
    
    Request body:
    {
        "user_id": 1,
        "condition_id": 2,
        "diagnosed_date": "2024-01-01T00:00:00",  # optional
        "severity": "moderate",  # optional
        "notes": "Diagnosed by Dr. Smith"  # optional
    }
    """
    # Validate user exists
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )
    
    # Validate condition exists
    medical_service = MedicalService(db)
    condition = medical_service.get_condition_by_id(payload.condition_id)
    if not condition:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="CONDITION_NOT_FOUND", message="Medical condition not found.")
        )
    
    # Assign condition to user
    user_condition = medical_service.assign_condition_to_user(
        user_id=payload.user_id,
        condition_id=payload.condition_id,
        diagnosed_date=payload.diagnosed_date,
        severity=payload.severity,
        notes=payload.notes
    )
    
    # Build response
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
            created_at=condition.created_at
        )
    )
    
    return APIResponse(
        ok=True,
        data=response.dict()
    )


# -------------------- DELETE /conditions/user/{user_id}/condition/{condition_id} --------------------
@router.delete("/user/{user_id}/condition/{condition_id}", response_model=APIResponse)
def remove_user_condition(
    user_id: int,
    condition_id: int,
    db: Session = Depends(get_db)
):
    """
    Remove a condition assignment from a user.
    
    Removes the association between user and condition.
    """
    # Validate user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )
    
    medical_service = MedicalService(db)
    removed = medical_service.remove_user_condition(user_id, condition_id)
    
    if removed:
        return APIResponse(
            ok=True,
            data={"message": "Condition removed from user successfully."}
        )
    else:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="CONDITION_NOT_ASSIGNED", message="Condition is not assigned to this user.")
        )
