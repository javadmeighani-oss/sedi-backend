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
        
        # Normal chat message (pass name from frontend)
        result = brain.process_message(user.id, message, user_name=name)
        
        return InteractionResponse(
            message=result["message"],
            language=result["language"],
            user_id=user.id,
            timestamp=datetime.utcnow(),
            requires_security_check=requires_security_check,
            detected_name=result.get("detected_name")  # Name detected from conversation
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
    
    CRITICAL: This endpoint MUST always return 200 with user_id, even if GPT fails.
    Only validation errors (400) should prevent user creation.
    
    COMPREHENSIVE ERROR HANDLING:
    - Validates database connection
    - Checks if users table exists
    - Handles all database errors gracefully
    - Provides specific error messages
    """
    from sqlalchemy import text, inspect
    from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
    
    # Step 1: Validate password (only validation that can fail)
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    print(f"[ONBOARDING] ========== START ONBOARDING ==========")
    print(f"[ONBOARDING] Password length: {len(password)}, Language: {language}")
    
    # Step 2: Comprehensive database checks
    try:
        # Check 1: Database connection
        print(f"[ONBOARDING] Check 1: Testing database connection...")
        try:
            db.execute(text("SELECT 1"))
            print(f"[ONBOARDING] ✅ Database connection: OK")
        except Exception as conn_error:
            print(f"[ONBOARDING] ❌ Database connection failed: {conn_error}")
            import traceback
            print(f"[ONBOARDING] Connection error traceback: {traceback.format_exc()}")
            raise HTTPException(
                status_code=503,
                detail="Database connection failed. Please check if the database server is running."
            )
        
        # Check 2: Verify users table exists
        print(f"[ONBOARDING] Check 2: Verifying users table exists...")
        try:
            inspector = inspect(db.bind)
            tables = inspector.get_table_names()
            if 'users' not in tables:
                print(f"[ONBOARDING] ❌ Table 'users' does not exist!")
                print(f"[ONBOARDING] Available tables: {tables}")
                # Try to create tables
                print(f"[ONBOARDING] Attempting to create tables...")
                from app.database import Base, engine
                Base.metadata.create_all(bind=engine)
                print(f"[ONBOARDING] ✅ Tables created successfully")
            else:
                print(f"[ONBOARDING] ✅ Table 'users' exists")
        except Exception as table_error:
            print(f"[ONBOARDING] ⚠️ Error checking/creating tables: {table_error}")
            import traceback
            print(f"[ONBOARDING] Table error traceback: {traceback.format_exc()}")
            # Continue anyway - might be a permission issue, but table might still exist
        
        # Check 3: Verify users table structure
        print(f"[ONBOARDING] Check 3: Verifying users table structure...")
        try:
            inspector = inspect(db.bind)
            columns = {col['name']: col for col in inspector.get_columns('users')}
            required_columns = ['id', 'secret_key', 'preferred_language', 'created_at']
            missing_columns = [col for col in required_columns if col not in columns]
            if missing_columns:
                print(f"[ONBOARDING] ❌ Missing columns in users table: {missing_columns}")
                print(f"[ONBOARDING] Available columns: {list(columns.keys())}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Database schema error: Missing columns {missing_columns}. Please run database migrations."
                )
            print(f"[ONBOARDING] ✅ Users table structure: OK")
        except HTTPException:
            raise
        except Exception as struct_error:
            print(f"[ONBOARDING] ⚠️ Error checking table structure: {struct_error}")
            # Continue anyway
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as check_error:
        print(f"[ONBOARDING] ❌ Database check failed: {check_error}")
        import traceback
        print(f"[ONBOARDING] Check error traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=503,
            detail="Database configuration error. Please contact support."
        )
    
    # Step 3: Create user - this MUST succeed
    new_user = None
    try:
        print(f"[ONBOARDING] Step 3: Creating user object...")
        
        # Create user object
        new_user = User(
            secret_key=password,
            preferred_language=language
        )
        print(f"[ONBOARDING] ✅ User object created")
        
        # Add to session
        print(f"[ONBOARDING] Step 4: Adding user to session...")
        db.add(new_user)
        print(f"[ONBOARDING] ✅ User added to session")
        
        # Commit transaction
        print(f"[ONBOARDING] Step 5: Committing transaction...")
        db.commit()
        print(f"[ONBOARDING] ✅ Transaction committed")
        
        # Refresh to get ID
        print(f"[ONBOARDING] Step 6: Refreshing user to get ID...")
        db.refresh(new_user)
        print(f"[ONBOARDING] ✅ Step 3 SUCCESS: User created - user_id: {new_user.id}")
        
    except IntegrityError as integrity_error:
        # Handle constraint violations (unique, foreign key, etc.)
        print(f"[ONBOARDING] ❌ IntegrityError: {integrity_error}")
        import traceback
        print(f"[ONBOARDING] IntegrityError traceback: {traceback.format_exc()}")
        db.rollback()
        
        error_msg = str(integrity_error).lower()
        if "unique" in error_msg or "duplicate" in error_msg:
            raise HTTPException(
                status_code=409,
                detail="A user with this password already exists. Please use a different password."
            )
        elif "foreign key" in error_msg or "constraint" in error_msg:
            raise HTTPException(
                status_code=500,
                detail="Database constraint error. Please contact support."
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Database integrity error. Please try again."
            )
            
    except OperationalError as op_error:
        # Handle connection/operational errors
        print(f"[ONBOARDING] ❌ OperationalError: {op_error}")
        import traceback
        print(f"[ONBOARDING] OperationalError traceback: {traceback.format_exc()}")
        db.rollback()
        
        error_msg = str(op_error).lower()
        if "connection" in error_msg or "connect" in error_msg:
            raise HTTPException(
                status_code=503,
                detail="Database connection lost. Please try again."
            )
        elif "server closed" in error_msg:
            raise HTTPException(
                status_code=503,
                detail="Database server closed the connection. Please try again."
            )
        else:
            raise HTTPException(
                status_code=503,
                detail="Database operation failed. Please try again later."
            )
            
    except ProgrammingError as prog_error:
        # Handle SQL syntax/schema errors
        print(f"[ONBOARDING] ❌ ProgrammingError: {prog_error}")
        import traceback
        print(f"[ONBOARDING] ProgrammingError traceback: {traceback.format_exc()}")
        db.rollback()
        
        error_msg = str(prog_error).lower()
        if "relation" in error_msg and "does not exist" in error_msg:
            raise HTTPException(
                status_code=500,
                detail="Database table not found. Please run database migrations."
            )
        elif "column" in error_msg and "does not exist" in error_msg:
            raise HTTPException(
                status_code=500,
                detail="Database schema error. Please run database migrations."
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Database schema error. Please contact support."
            )
            
    except HTTPException:
        # Re-raise HTTP exceptions
        db.rollback()
        raise
        
    except Exception as e:
        # Handle any other unexpected errors
        print(f"[ONBOARDING] ❌ Unexpected error: {e}")
        print(f"[ONBOARDING] Error type: {type(e).__name__}")
        import traceback
        print(f"[ONBOARDING] Unexpected error traceback: {traceback.format_exc()}")
        
        # Rollback transaction
        try:
            db.rollback()
            print(f"[ONBOARDING] ✅ Transaction rolled back")
        except Exception as rollback_error:
            print(f"[ONBOARDING] ⚠️ Rollback failed: {rollback_error}")
        
        # Generic error message
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while creating your account. Please try again."
        )
    
    # Step 3: Generate greeting message (GPT or fallback - never fails)
    initial_message = None
    try:
        print(f"[ONBOARDING] Step 2: Generating greeting message from GPT...")
        brain = ConversationBrain(db, language=language)
        initial_message = brain.get_initial_message(new_user.id, None, language)
        print(f"[ONBOARDING] ✅ Step 2 SUCCESS: GPT message generated")
    except Exception as e:
        print(f"[ONBOARDING] ⚠️ Step 2 WARNING: GPT failed, using fallback - {e}")
        # GPT failure is NOT critical - use fallback
        if language == "fa":
            initial_message = "سلام! من صدی هستم، دستیار مراقبت سلامت شما. خوش آمدید!"
        elif language == "ar":
            initial_message = "مرحباً! أنا صدي، مساعد رعاية صحية الخاص بك. أهلاً بك!"
        else:
            initial_message = "Hello! I'm Sedi, your health care assistant. Welcome!"
        print(f"[ONBOARDING] ✅ Step 2 FALLBACK: Using fallback message")
    
    # Step 4: Return success response - ALWAYS 200 with user_id
    response_data = {
        "user_id": new_user.id,  # CRITICAL: Always present
        "message": initial_message,  # Always present (GPT or fallback)
        "language": language  # Always present
    }
    print(f"[ONBOARDING] ✅ Step 3: Returning success - user_id: {response_data['user_id']}, message: {response_data['message'][:50]}...")
    return response_data


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
