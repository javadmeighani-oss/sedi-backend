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
    user_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Introduce user with secret key.
    If user_id provided, upgrade anonymous user to authenticated.
    """
    user = None
    
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.secret_key = secret_key
            db.commit()
    
    if not user:
        new_user = User(
            secret_key=secret_key,
            preferred_language=lang
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        user = new_user
    
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
    user_id: Optional[int] = Query(None),
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
    is_anonymous = False
    
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with id {user_id} not found. Please check your user_id or start a new conversation."
            )
    
    if not user and secret_key:
        user = db.query(User).filter(User.secret_key == secret_key).first()
    
    if not user:
        is_anonymous = True
        new_user = User(
            secret_key=str(uuid.uuid4()),
            preferred_language=lang
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        user = new_user
    
    try:
        brain = ConversationBrain(db, language=lang)
        result = brain.process_message(user.id, message, name)
        
        return InteractionResponse(
            message=result["message"],
            language=result["language"],
            user_id=user.id,
            timestamp=datetime.utcnow(),
            requires_security_check=requires_security_check,
            detected_name=result.get("detected_name")
        )
    except Exception as e:
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
    Handles ALL possible errors gracefully.
    """
    # Step 1: Validate password
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    # Step 2: Ensure tables exist (create if needed)
    try:
        from app.database import Base, engine
        Base.metadata.create_all(bind=engine)
        print(f"[ONBOARDING] Tables ensured to exist")
    except Exception as table_error:
        print(f"[ONBOARDING] ⚠️ Warning: Could not ensure tables exist: {table_error}")
        import traceback
        print(f"[ONBOARDING] Table creation error traceback: {traceback.format_exc()}")
        # Continue anyway - tables might already exist
    
    # Step 3: Create user - with comprehensive error handling
    new_user = None
    user_id = None
    
    try:
        print(f"[ONBOARDING] Step 1: Creating user - password length: {len(password)}, language: {language}")
        print(f"[ONBOARDING] Password value (first 3 chars): {password[:3]}...")
        
        # Create user object with explicit values
        new_user = User(
            secret_key=password,
            preferred_language=language or "en"  # Ensure language is never None
        )
        print(f"[ONBOARDING] Step 2: User object created successfully")
        print(f"[ONBOARDING] User object: secret_key length={len(new_user.secret_key)}, language={new_user.preferred_language}")
        
        db.add(new_user)
        print(f"[ONBOARDING] Step 3: User added to session")
        
        # Try to flush first to catch any constraint errors early
        try:
            db.flush()
            print(f"[ONBOARDING] Step 3.5: Flush successful - no constraint errors detected")
        except Exception as flush_error:
            print(f"[ONBOARDING] ❌ FLUSH ERROR (before commit): {flush_error}")
            print(f"[ONBOARDING] Flush error type: {type(flush_error).__name__}")
            import traceback
            print(f"[ONBOARDING] Flush error traceback: {traceback.format_exc()}")
            db.rollback()
            raise  # Re-raise to be caught by outer except
        
        db.commit()
        print(f"[ONBOARDING] Step 4: Transaction committed successfully")
        
        db.refresh(new_user)
        user_id = new_user.id
        print(f"[ONBOARDING] Step 5: User refreshed - user_id: {user_id}")
        
    except Exception as e:
        print(f"[ONBOARDING] ❌ ERROR in user creation: {e}")
        print(f"[ONBOARDING] Error type: {type(e).__name__}")
        print(f"[ONBOARDING] Error class: {e.__class__.__name__}")
        print(f"[ONBOARDING] Error module: {e.__class__.__module__}")
        import traceback
        print(f"[ONBOARDING] Full traceback:\n{traceback.format_exc()}")
        
        try:
            db.rollback()
            print(f"[ONBOARDING] Transaction rolled back successfully")
        except Exception as rollback_error:
            print(f"[ONBOARDING] ⚠️ Rollback error: {rollback_error}")
        
        # Determine specific error message with more detailed analysis
        error_str = str(e).lower()
        error_detail = "Error creating account. Please try again."
        
        # Check error type first
        error_type_name = type(e).__name__.lower()
        error_module = e.__class__.__module__.lower()
        
        print(f"[ONBOARDING] Error analysis - type: {error_type_name}, module: {error_module}, str: {error_str[:200]}")
        
        if "integrityerror" in error_type_name or "integrity" in error_module:
            # This is a constraint violation
            if "unique" in error_str or "duplicate" in error_str or "already exists" in error_str:
                error_detail = "A user with this password already exists. Please use a different password."
            elif "foreign key" in error_str or "fk_" in error_str:
                error_detail = "Database foreign key constraint error. Please contact support."
            elif "check" in error_str:
                error_detail = "Database check constraint error. Please contact support."
            elif "not null" in error_str or "null value" in error_str:
                error_detail = "Required field is missing. Please contact support."
            else:
                # Generic constraint error - provide more info
                error_detail = f"Database constraint error: {error_str[:100]}. Please contact support."
        elif "operationalerror" in error_type_name or "operational" in error_module:
            if "connection" in error_str or "connect" in error_str or "could not connect" in error_str:
                error_detail = "Cannot connect to database. Please check if the database server is running."
            elif "timeout" in error_str:
                error_detail = "Database connection timeout. Please try again."
            else:
                error_detail = "Database operation error. Please try again."
        elif "programmingerror" in error_type_name or "programming" in error_module:
            if "relation" in error_str and "does not exist" in error_str:
                error_detail = "Database table not found. Please run database migrations."
            elif "column" in error_str and "does not exist" in error_str:
                error_detail = "Database column not found. Please run database migrations."
            else:
                error_detail = "Database schema error. Please contact support."
        elif "connection" in error_str or "connect" in error_str or "could not connect" in error_str:
            error_detail = "Cannot connect to database. Please check if the database server is running."
        elif "relation" in error_str and "does not exist" in error_str:
            error_detail = "Database table not found. Please run database migrations."
        elif "unique" in error_str or "duplicate" in error_str or "already exists" in error_str:
            error_detail = "A user with this password already exists. Please use a different password."
        elif "permission" in error_str or "access" in error_str:
            error_detail = "Database permission error. Please contact support."
        elif "timeout" in error_str:
            error_detail = "Database connection timeout. Please try again."
        
        print(f"[ONBOARDING] Final error detail: {error_detail}")
        raise HTTPException(status_code=500, detail=error_detail)
    
    # Step 4: Generate greeting message - NEVER FAILS
    initial_message = ""
    
    if user_id:
        try:
            print(f"[ONBOARDING] Step 6: Generating greeting from GPT for user_id: {user_id}")
            brain = ConversationBrain(db, language=language)
            initial_message = brain.get_initial_message(user_id, None, language)
            print(f"[ONBOARDING] Step 7: GPT greeting generated successfully")
        except Exception as gpt_error:
            print(f"[ONBOARDING] ⚠️ GPT failed (non-critical), using fallback: {gpt_error}")
            # GPT failure is NOT critical - use fallback
            if language == "fa":
                initial_message = "سلام! من صدی هستم، دستیار مراقبت سلامت شما. خوش آمدید!"
            elif language == "ar":
                initial_message = "مرحباً! أنا صدي، مساعد رعاية صحية الخاص بك. أهلاً بك!"
            else:
                initial_message = "Hello! I'm Sedi, your health care assistant. Welcome!"
            print(f"[ONBOARDING] Step 7: Using fallback greeting")
    else:
        # Fallback if user_id is None (shouldn't happen, but just in case)
        print(f"[ONBOARDING] ⚠️ WARNING: user_id is None, using fallback greeting")
        if language == "fa":
            initial_message = "سلام! من صدی هستم، دستیار مراقبت سلامت شما. خوش آمدید!"
        elif language == "ar":
            initial_message = "مرحباً! أنا صدي، مساعد رعاية صحية الخاص بك. أهلاً بك!"
        else:
            initial_message = "Hello! I'm Sedi, your health care assistant. Welcome!"
    
    # Step 5: Return success - ALWAYS with user_id
    if user_id is None:
        print(f"[ONBOARDING] ❌ CRITICAL: user_id is None after user creation!")
        raise HTTPException(
            status_code=500,
            detail="User created but could not retrieve user ID. Please try again."
        )
    
    print(f"[ONBOARDING] ✅ SUCCESS - Returning response with user_id: {user_id}")
    return {
        "user_id": user_id,
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
