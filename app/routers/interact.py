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
import uuid

router = APIRouter()

# ---------------- Introduce User ----------------
@router.post("/introduce", response_model=InteractionResponse)
def introduce_user(
    name: str = Query(...),
    secret_key: str = Query(...),
    lang: str = Query("en"),
    user_id: Optional[int] = Query(None),  # Optional: for upgrading anonymous users
    db: Session = Depends(get_db)
):
    """
    Create new user account or upgrade anonymous user to registered user.
    
    If user_id is provided, upgrades existing anonymous user.
    Otherwise, creates new user account.
    Returns greeting from Conversation Brain.
    """
    # If user_id provided, try to upgrade anonymous user
    if user_id:
        existing_user = db.query(User).filter(User.id == user_id).first()
        if existing_user:
            # Check if it's an anonymous user (can be upgraded)
            if existing_user.name.startswith("anonymous_") and existing_user.secret_key.startswith("temp_"):
                # Check if new name is already taken
                name_taken = db.query(User).filter(
                    User.name == name,
                    User.id != user_id
                ).first()
                if name_taken:
                    raise HTTPException(status_code=400, detail="User name already exists")
                
                # Upgrade anonymous user to registered user
                existing_user.name = name
                existing_user.secret_key = secret_key
                existing_user.preferred_language = lang
                db.commit()
                db.refresh(existing_user)
                
                # Use Conversation Brain for greeting
                brain = ConversationBrain(db, language=lang)
                greeting = brain.get_greeting(existing_user.id)
                
                return InteractionResponse(
                    message=greeting["message"],
                    language=lang,
                    user_id=existing_user.id,
                    timestamp=datetime.utcnow()
                )
    
    # Check if name already exists
    existing_user = db.query(User).filter(User.name == name).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    # Create new user
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
    
    Supports both authenticated users and new anonymous users.
    For new users without credentials, creates a temporary anonymous user.
    """
    user = None
    requires_security_check = False
    is_anonymous = False
    
    # If credentials provided, try to find user
    if name and secret_key:
        user = db.query(User).filter(
            User.name == name,
            User.secret_key == secret_key
        ).first()
        
        if not user:
            requires_security_check = True
    
    # If no user found and no credentials, create anonymous user for new users
    if not user and (not name or not secret_key):
        # Check if this is a greeting request (special marker)
        is_greeting = message.strip() == "__GREETING__"
        
        # Create temporary anonymous user for new users
        # Use UUID to ensure uniqueness
        anonymous_name = f"anonymous_{uuid.uuid4().hex[:12]}"
        anonymous_secret = "temp_" + uuid.uuid4().hex[:12]
        
        # Check if anonymous user already exists (shouldn't happen, but safety check)
        existing_anonymous = db.query(User).filter(
            User.name.like("anonymous_%"),
            User.secret_key.like("temp_%")
        ).first()
        
        if existing_anonymous:
            user = existing_anonymous
        else:
            # Create new anonymous user
            user = User(
                name=anonymous_name,
                secret_key=anonymous_secret,
                preferred_language=lang
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            is_anonymous = True
    
    # If still no user (shouldn't happen), return error
    if not user:
        raise HTTPException(
            status_code=500,
            detail="Failed to create or find user account."
        )
    
    # Use Conversation Brain to process message
    brain = ConversationBrain(db, language=lang)
    
    # If this is a greeting request, use get_greeting instead
    if message.strip() == "__GREETING__":
        greeting = brain.get_greeting(user.id)
        return InteractionResponse(
            message=greeting["message"],
            language=greeting["language"],
            user_id=user.id,
            timestamp=datetime.utcnow(),
            requires_security_check=requires_security_check
        )
    
    # Normal chat message
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
