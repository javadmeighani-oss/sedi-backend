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
    Introduce user with secret key.
    If user_id provided, upgrade anonymous user to authenticated.
    """
    user = None
    
    # If user_id provided, try to find and upgrade user
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            # Update secret key
            user.secret_key = secret_key
            db.commit()
    
    # If no user found, create new one
    if not user:
        new_user = User(
            secret_key=secret_key,
            preferred_language=lang
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        user = new_user
    
    # Get greeting
    brain = ConversationBrain(db, language=lang)
    greeting = brain.get_greeting(user.id)
    
    return InteractionResponse(
        message=greeting,
        language=lang,
        user_id=user.id,
        timestamp=datetime.utcnow()
    )


# ---------------- Chat with Sedi ----------------  
@router.post("/chat", response_model=InteractionResponse)
def chat_with_sedi(
    message: str = Query(...),
    lang: str = Query("en"),
    user_id: Optional[int] = Query(None),  # CRITICAL: Frontend must send user_id from previous response
    name: Optional[str] = Query(None),  # User's name from frontend (stored locally)
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
        user = db.query(User).filter(User.secret_key == secret_key).first()
        if user:
            print(f"[ROUTER DEBUG] Found user by secret_key: id={user.id}")
    
    # PRIORITY 3: Create anonymous user if no user found
    if not user:
        print(f"[ROUTER DEBUG] No user found - creating anonymous user")
        is_anonymous = True
        new_user = User(
            secret_key=str(uuid.uuid4()),  # Random UUID for anonymous users
            preferred_language=lang
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        user = new_user
        print(f"[ROUTER DEBUG] Created anonymous user: id={user.id}")
    
    # Process message with Conversation Brain
    try:
        brain = ConversationBrain(db, language=lang)
        result = brain.process_message(user.id, message, name)  # Pass name from frontend
        
        return InteractionResponse(
            message=result["message"],
            language=result["language"],
            user_id=user.id,
            timestamp=datetime.utcnow(),
            requires_security_check=requires_security_check,
            detected_name=result.get("detected_name")
        )
    except Exception as e:
        print(f"[ROUTER ERROR] Error processing message: {e}")
        import traceback
        print(f"[ROUTER ERROR] Traceback: {traceback.format_exc()}")
        
        # Return user-friendly error message
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
    SIMPLE ONBOARDING: Create user and return success.
    """
    # Validate password
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    # Create user - SIMPLE with detailed error logging
    new_user = None
    try:
        print(f"[ONBOARDING] Creating user with password length: {len(password)}, language: {language}")
        new_user = User(
            secret_key=password,
            preferred_language=language
        )
        print(f"[ONBOARDING] User object created")
        db.add(new_user)
        print(f"[ONBOARDING] User added to session")
        db.commit()
        print(f"[ONBOARDING] Transaction committed")
        db.refresh(new_user)
        print(f"[ONBOARDING] User refreshed - user_id: {new_user.id}")
    except Exception as e:
        print(f"[ONBOARDING] ❌ ERROR creating user: {e}")
        print(f"[ONBOARDING] Error type: {type(e).__name__}")
        import traceback
        print(f"[ONBOARDING] Traceback: {traceback.format_exc()}")
        try:
            db.rollback()
            print(f"[ONBOARDING] Transaction rolled back")
        except Exception as rollback_error:
            print(f"[ONBOARDING] Rollback error: {rollback_error}")
        
        # Provide more specific error message
        error_detail = "Error creating account. Please try again."
        error_str = str(e).lower()
        
        if "connection" in error_str or "connect" in error_str:
            error_detail = "Database connection error. Please check if the database server is running."
        elif "relation" in error_str and "does not exist" in error_str:
            error_detail = "Database table not found. Please run database migrations."
        elif "unique" in error_str or "duplicate" in error_str:
            error_detail = "A user with this password already exists. Please use a different password."
        elif "constraint" in error_str:
            error_detail = "Database constraint error. Please contact support."
        
        raise HTTPException(
            status_code=500,
            detail=error_detail
        )
    
    # Generate greeting (GPT or fallback)
    try:
        print(f"[ONBOARDING] Generating greeting from GPT...")
        brain = ConversationBrain(db, language=language)
        initial_message = brain.get_initial_message(new_user.id, None, language)
        print(f"[ONBOARDING] GPT greeting generated")
    except Exception as gpt_error:
        print(f"[ONBOARDING] GPT failed, using fallback: {gpt_error}")
        if language == "fa":
            initial_message = "سلام! من صدی هستم، دستیار مراقبت سلامت شما. خوش آمدید!"
        elif language == "ar":
            initial_message = "مرحباً! أنا صدي، مساعد رعاية صحية الخاص بك. أهلاً بك!"
        else:
            initial_message = "Hello! I'm Sedi, your health care assistant. Welcome!"
        print(f"[ONBOARDING] Using fallback message")
    
    # Return success
    print(f"[ONBOARDING] ✅ SUCCESS - Returning user_id: {new_user.id}")
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
    Get personalized greeting for user.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    brain = ConversationBrain(db, language=lang)
    greeting = brain.get_greeting(user_id)
    
    return {
        "message": greeting,
        "language": lang,
        "user_id": user_id
    }


# ---------------- Get User History ----------------
@router.get("/history")
def get_user_history(
    user_id: int = Query(...),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get conversation history for user.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    memories = (
        db.query(Memory)
        .filter(Memory.user_id == user_id)
        .order_by(Memory.created_at.desc())
        .limit(limit)
        .all()
    )
    
    return {
        "user_id": user_id,
        "messages": [
            {
                "id": m.id,
                "user_message": m.user_message,
                "sedi_response": m.sedi_response,
                "language": m.language,
                "created_at": m.created_at.isoformat()
            }
            for m in memories
        ]
    }
