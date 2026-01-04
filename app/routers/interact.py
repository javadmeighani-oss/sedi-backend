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
            if existing_user.secret_key.startswith("temp_"):
                # Upgrade anonymous user to registered user
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
    
    # Create new user (no name field)
    new_user = User(secret_key=secret_key, preferred_language=lang)
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
    user_id: Optional[int] = Query(None),  # CRITICAL: Frontend must send user_id from previous response
    secret_key: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Chat endpoint - Thin API layer.
    All conversation logic handled by Conversation Brain.
    
    Supports both authenticated users and new anonymous users.
    For new users without credentials, creates a temporary anonymous user.
    
    CRITICAL: Frontend should send user_id from previous response to maintain conversation continuity.
    """
    user = None
    requires_security_check = False
    is_anonymous = False
    
    # PRIORITY 1: If user_id provided, use it directly (maintains conversation continuity)
    # EXPERIENCE STABILITY: If user_id is provided, we MUST use it or return error
    # Creating new user when user_id is invalid causes conversation reset
    if user_id:
        print(f"[ROUTER DEBUG] user_id provided: {user_id}")
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            print(f"[ROUTER DEBUG] Found user: id={user.id}")
        else:
            # EXPERIENCE STABILITY FIX: Invalid user_id = error, don't create new user
            # This prevents conversation reset when frontend sends invalid user_id
            print(f"[ROUTER DEBUG] ERROR: Invalid user_id provided - returning error to prevent conversation reset")
            raise HTTPException(
                status_code=404,
                detail=f"User with id {user_id} not found. Please check your user_id or start a new conversation."
            )
    
    # PRIORITY 2: If credentials provided, try to find user
    if not user and secret_key:
        user = db.query(User).filter(
            User.secret_key == secret_key
        ).first()
        
        if not user:
            requires_security_check = True
    
    # PRIORITY 3: If no user found and no credentials, create anonymous user for new users
    if not user and not secret_key:
        # TEMP DEBUG: Log anonymous user creation
        print(f"[ROUTER DEBUG] No user_id/credentials provided - creating anonymous user")
        
        # Create temporary anonymous user for new users
        # Use UUID to ensure uniqueness - always create new to avoid conflicts
        anonymous_secret = "temp_" + uuid.uuid4().hex[:12]
        
        # Create new anonymous user (don't reuse existing - each session gets unique user_id)
        user = User(
            secret_key=anonymous_secret,
            preferred_language=lang
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        is_anonymous = True
        print(f"[ROUTER DEBUG] Created anonymous user - user_id={user.id}")
    
    # If still no user (shouldn't happen), return error
    if not user:
        raise HTTPException(
            status_code=500,
            detail="Failed to create or find user account."
        )
    
    # Use Conversation Brain to process message
    try:
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
    except Exception as e:
        # Log the error for debugging
        print(f"[ROUTER ERROR] Exception in chat endpoint: {e}")
        print(f"[ROUTER ERROR] Exception type: {type(e).__name__}")
        import traceback
        print(f"[ROUTER ERROR] Traceback: {traceback.format_exc()}")
        
        # Return a user-friendly error message instead of crashing
        error_messages = {
            "en": "I'm sorry, I encountered an error processing your message. Please try again.",
            "fa": "متاسفم، در پردازش پیام شما خطایی رخ داد. لطفاً دوباره تلاش کنید.",
            "ar": "عذراً، حدث خطأ في معالجة رسالتك. يرجى المحاولة مرة أخرى."
        }
        
        error_message = error_messages.get(lang, error_messages["en"])
        
        return InteractionResponse(
            message=error_message,
            language=lang,
            user_id=user.id,
            timestamp=datetime.utcnow(),
            requires_security_check=requires_security_check
        )


# ---------------- Onboarding - Setup User ----------------
@router.post("/onboarding")
def setup_onboarding(
    password: str = Query(...),
    language: str = Query("fa"),
    db: Session = Depends(get_db)
):
    """
    Setup user onboarding: create user with password and language.
    Returns user_id and initial greeting message.
    Note: Name is no longer stored in database.
    """
    # Validate password requirements
    # Only check minimum length (6 characters), any characters allowed
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    # Create new user (no name field)
    new_user = User(
        secret_key=password,
        preferred_language=language
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Generate initial greeting using GPT with Sedi's knowledge base
    brain = ConversationBrain(db, language=language)
    initial_message = brain.get_initial_message(new_user.id, None, language)
    
    return {
        "user_id": new_user.id,
        "message": initial_message,
        "language": language
    }


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
    secret_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Get conversation history for user.
    """
    user = db.query(User).filter(
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
