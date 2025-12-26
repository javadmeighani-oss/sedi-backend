# app/routers/interact.py
"""
Interaction Router - Thin API Layer

RESPONSIBILITY:
- Receives API request
- Calls Conversation Brain
- Returns response
- NO logic, NO decisions
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Memory
from app.core.conversation.brain import ConversationBrain
from app.schemas import InteractionResponse
from datetime import datetime
from fastapi import Depends
from typing import Optional

router = APIRouter()

# ---------------- Introduce User ----------------
@router.post("/introduce", response_model=InteractionResponse)
def introduce_user(
    name: str = Query(...),
    secret_key: str = Query(...),
    lang: str = Query("en"),
    db: Session = Depends(get_db)
):
    """
    Create new user account.
    Returns greeting from Conversation Brain.
    """
    existing_user = db.query(User).filter(User.name == name).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = User(name=name, secret_key=secret_key, preferred_language=lang)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Use Conversation Brain for greeting
    brain = ConversationBrain(db, language=lang)
    greeting = brain.get_greeting(new_user.id)

    return InteractionResponse(
        message=greeting["message"],
        language=lang,
        user_id=new_user.id,
        timestamp=datetime.utcnow()
    )


# ---------------- Chat with Sedi ----------------
@router.post("/chat", response_model=InteractionResponse)
def chat_with_sedi(
    message: str = Query(...),
    lang: str = Query("en"),
    name: Optional[str] = Query(None),
    secret_key: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Chat endpoint - Thin API layer.
    All conversation logic handled by Conversation Brain.
    """
    user = None
    requires_security_check = False
    
    # If credentials provided, try to find user
    if name and secret_key:
        user = db.query(User).filter(
            User.name == name,
            User.secret_key == secret_key
        ).first()
        
        if not user:
            requires_security_check = True
    
    # If no user found, return error (user must be authenticated)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User authentication required. Please provide valid name and secret_key."
        )
    
    # Use Conversation Brain to process message
    brain = ConversationBrain(db, language=lang)
    result = brain.process_message(user.id, message)
    
    return InteractionResponse(
        message=result["message"],
        language=result["language"],
        user_id=user.id,
        timestamp=datetime.utcnow(),
        requires_security_check=requires_security_check
    )


# ---------------- Get Greeting ----------------
@router.get("/greeting")
def get_greeting(
    user_id: int = Query(...),
    lang: str = Query("en"),
    db: Session = Depends(get_db)
):
    """
    Get greeting message from Conversation Brain.
    Used when user opens chat.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    brain = ConversationBrain(db, language=lang)
    greeting = brain.get_greeting(user_id)
    
    return {
        "message": greeting["message"],
        "language": greeting["language"],
        "stage": greeting["stage"],
        "metadata": greeting.get("metadata", {})
    }


# ------------------ Memory History ------------------
@router.get("/history")
def get_user_history(
    name: str = Query(...),
    secret_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Get conversation history for user.
    """
    user = db.query(User).filter(
        User.name == name,
        User.secret_key == secret_key
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    history = db.query(Memory).filter(Memory.user_id == user.id).all()

    if not history:
        return {"message": "No conversations found for this user."}

    return [
        {
            "user_message": h.user_message,
            "sedi_response": h.sedi_response,
            "language": h.language,
            "timestamp": h.created_at
        }
        for h in history
    ]
