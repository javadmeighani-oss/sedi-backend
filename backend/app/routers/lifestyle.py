# app/routers/lifestyle.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel, Field

from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo
from app.services.memory import MemoryRepository, build_memory_context


router = APIRouter()


# -------------------- Request/Response Models --------------------

class LifestyleEntry(BaseModel):
    """Single lifestyle fact entry"""
    domain: str = Field(..., description="Memory domain (e.g., 'lifestyle')")
    key: str = Field(..., description="Fact key (e.g., 'sleep_duration_hours')")
    value: Any = Field(..., description="Fact value (will be stored as JSON)")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Confidence score")
    source: str = Field(default="manual", description="Source: 'chat' | 'device' | 'manual'")


class LifestyleUpdateRequest(BaseModel):
    """Request model for lifestyle update"""
    user_id: int = Field(..., description="User ID")
    entries: List[LifestyleEntry] = Field(..., description="List of lifestyle facts to update")


# -------------------- Endpoints --------------------

@router.post("/update", response_model=APIResponse)
def update_lifestyle(
    request: LifestyleUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Update lifestyle facts for a user.
    
    Upserts facts into UserMemoryFact (domain+key unique per user).
    
    Example payload:
    {
        "user_id": 1,
        "entries": [
            {
                "domain": "lifestyle",
                "key": "sleep_duration_hours",
                "value": 6.5,
                "confidence": 0.8,
                "source": "manual"
            },
            {
                "domain": "lifestyle",
                "key": "hydration_ml",
                "value": 1200,
                "confidence": 0.7,
                "source": "manual"
            }
        ]
    }
    """
    # Verify user exists
    user = db.query(models.User).filter(models.User.id == request.user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))
    
    # Upsert facts
    repo = MemoryRepository(db)
    updated_facts = []
    errors = []
    
    for entry in request.entries:
        try:
            fact = repo.upsert_fact(
                user_id=request.user_id,
                domain=entry.domain,
                key=entry.key,
                value=entry.value,
                confidence=entry.confidence,
                source=entry.source
            )
            updated_facts.append({
                "domain": fact.domain,
                "key": fact.key,
                "fact_id": fact.id
            })
        except ValueError as e:
            errors.append(f"Invalid entry ({entry.domain}/{entry.key}): {str(e)}")
        except Exception as e:
            errors.append(f"Error updating {entry.domain}/{entry.key}: {str(e)}")
    
    if errors:
        return APIResponse(
            ok=False,
            error=ErrorInfo(
                code="UPDATE_ERROR",
                message=f"Some entries failed: {', '.join(errors)}"
            ),
            data={"updated": updated_facts, "errors": errors}
        )
    
    return APIResponse(
        ok=True,
        data={
            "updated_count": len(updated_facts),
            "facts": updated_facts
        }
    )


@router.get("/context", response_model=APIResponse)
def get_lifestyle_context(
    user_id: int = Query(..., description="User ID"),
    db: Session = Depends(get_db)
):
    """
    Get compact memory context for a user.
    
    Returns a MemoryContext built from UserMemoryFact (sleep/hydration/activity/mood/preferences if available).
    """
    # Verify user exists
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))
    
    # Build memory context
    context = build_memory_context(db, user_id)
    
    return APIResponse(
        ok=True,
        data=context.to_dict()
    )
