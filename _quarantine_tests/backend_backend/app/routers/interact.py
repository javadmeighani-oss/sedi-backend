"""
Interaction Router - Thin API Layer

RESPONSIBILITY:
- Receives API request
- Calls Conversation Brain
- Returns response
- NO logic, NO decisions
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import uuid

from app.database import get_db
from app.models import User, Memory
from app.core.conversation.brain import ConversationBrain
from app.schemas import InteractionResponse
from app.schemas.chat import ChatRequest
from app.schemas.onboarding import OnboardingRequest

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
async def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Chat endpoint - Thin API layer.
    All conversation logic handled by Conversation Brain.
    
    CRITICAL VALIDATION:
    - message: Required, non-empty (from JSON body)
    - user_id: Required (from JSON body)
    - Language: Detected ONLY from message content (no query params)
    - Name: Retrieved from memory/context (no query params)
    """
    # STEP 3: HARDEN CHAT FLOW - Validate payload
    if not payload.message or not payload.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )
    
    # Extract values from payload
    user_id = payload.user_id
    message = payload.message.strip()
    
    # Validate user_id
    if not user_id or user_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid user_id. Must be a positive integer."
        )
    
    # Find user by user_id (required after onboarding)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with id {user_id} not found. Please check your user_id or start a new conversation."
        )
    
    try:
        # STEP 2: SINGLE SOURCE OF LANGUAGE TRUTH
        # Detect language from user message text ONLY (not IP/locale/query params)
        from app.core.conversation.name_database import detect_language
        detected_lang = detect_language(message)
        
        # Use detected language if valid, otherwise default to "en"
        # NO query parameter fallback - message content is the ONLY source
        if detected_lang in ["en", "fa", "ar"]:
            response_language = detected_lang
        else:
            response_language = "en"  # Default to English
        
        print(f"[CHAT] Language detection: message='{message[:50]}...', detected={detected_lang}, using={response_language}")
        print(f"[CHAT] ✅ Language determined ONLY from message content (no query params)")
        
        # STEP 3: HARDEN CHAT FLOW - Validate message before GPT call
        # This validation is also done in prompts.py, but we validate here too for early failure
        if not isinstance(message, str) or not message.strip():
            raise HTTPException(
                status_code=400,
                detail="Message must be a non-empty string"
            )
        
        # Initialize brain with detected language for response
        # Sedi's internal thinking is ALWAYS English (enforced in prompts)
        print(f"[CHAT] ===== BEFORE GPT CALL =====")
        print(f"[CHAT] User ID: {user.id}")
        print(f"[CHAT] Message: '{message[:100]}...'")
        print(f"[CHAT] Response language: {response_language}")
        print(f"[CHAT] ===== END BEFORE GPT =====")
        
        # Name is retrieved from memory/context by ConversationBrain - not passed as parameter
        brain = ConversationBrain(db, language=response_language)
        result = brain.process_message(user.id, message, None)  # name=None - will be retrieved from memory
        
        print(f"[CHAT] ===== AFTER GPT CALL =====")
        print(f"[CHAT] Response received: {result.get('message', '')[:100]}...")
        print(f"[CHAT] Response language: {result.get('language', 'unknown')}")
        print(f"[CHAT] ===== END AFTER GPT =====")
        
        return InteractionResponse(
            message=result["message"],
            language=result["language"],
            user_id=user.id,
            timestamp=datetime.utcnow(),
            requires_security_check=False,  # Security check handled by brain if needed
            detected_name=result.get("detected_name")
        )
    except HTTPException:
        # Re-raise HTTP exceptions (validation errors, etc.)
        raise
    except ValueError as validation_error:
        # STEP 3: Validation errors from message construction - return 400
        print(f"[CHAT ERROR] Validation error: {validation_error}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "validation_error",
                "detail": str(validation_error)
            }
        )
    except Exception as e:
        # STEP 4: ERROR TRANSPARENCY - Log and return real errors
        print(f"[CHAT ERROR] ===== ERROR PROCESSING MESSAGE =====")
        print(f"[CHAT ERROR] Error: {e}")
        print(f"[CHAT ERROR] Error type: {type(e).__name__}")
        import traceback
        print(f"[CHAT ERROR] Traceback: {traceback.format_exc()}")
        print(f"[CHAT ERROR] Message: '{message[:100]}...'")
        print(f"[CHAT ERROR] User ID: {user_id}")
        print(f"[CHAT ERROR] User found: {user is not None}")
        print(f"[CHAT ERROR] ===== END ERROR =====")
        
        # Check if this is a GPT-related error
        error_str = str(e).lower()
        error_type_name = type(e).__name__.lower()
        is_gpt_error = (
            "openai" in error_str or
            "api key" in error_str or
            "authentication" in error_str or
            "rate limit" in error_str or
            "gpt" in error_str or
            "completion" in error_str or
            "openai" in error_type_name or
            "authenticationerror" in error_type_name or
            "apierror" in error_type_name
        )
        
        if is_gpt_error:
            # STEP 4: Return 502 with real error message (not generic)
            print(f"[CHAT ERROR] GPT-related error detected - returning 502")
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=502,
                content={
                    "error": "gpt_failure",
                    "detail": str(e)[:500]  # Real error message, not generic
                }
            )
        else:
            # Return 500 for other internal errors
            raise HTTPException(
                status_code=500,
                detail=f"Error processing message: {str(e)[:200]}. Please try again."
            )


# ---------------- Onboarding - Setup User ---------------- 
@router.post("/onboarding")
def setup_onboarding(
    payload: OnboardingRequest,
    db: Session = Depends(get_db)
):
    """
    SIMPLE ONBOARDING: Create user and return success.
    Handles ALL possible errors gracefully.
    
    CRITICAL:
    - name is REQUIRED (from JSON body)
    - password is REQUIRED (from JSON body)
    - language is optional (default: "fa")
    - User.name is ALWAYS saved (non-empty, stripped)
    """
    # Step 1: Validate payload
    password = payload.password.strip()
    name = payload.name.strip()
    language = payload.language.strip() if payload.language else "fa"
    
    # Validate name (REQUIRED, non-empty)
    if not name or len(name) == 0:
        raise HTTPException(
            status_code=400,
            detail="Name is required and cannot be empty"
        )
    
    # Validate password
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    # Step 2: Ensure tables exist (create if needed) - with explicit User table
    # NOTE: create_all does NOT modify existing tables - it only creates if missing
    # If schema mismatch exists, you need to run fix_schema.py
    try:
        from app.database import Base, engine
        from app.models import User
        # Explicitly create User table to ensure schema matches
        # This will only create if table doesn't exist - won't modify existing schema
        Base.metadata.create_all(bind=engine, tables=[User.__table__])
        print(f"[ONBOARDING] User table ensured to exist")
        print(f"[ONBOARDING] NOTE: If schema mismatch exists, run 'python fix_schema.py'")
    except Exception as table_error:
        print(f"[ONBOARDING] ⚠️ Warning: Could not ensure User table exists: {table_error}")
        import traceback
        print(f"[ONBOARDING] Table creation error traceback: {traceback.format_exc()}")
        # Continue anyway - table might already exist
    
    # Step 3: Create user - with comprehensive error handling
    new_user = None
    user_id = None
    
    try:
        print(f"[ONBOARDING] ========== USER CREATION START ==========")
        print(f"[ONBOARDING] Step 1: Input validation")
        print(f"[ONBOARDING]   - Name: '{name}' (length: {len(name)})")
        print(f"[ONBOARDING]   - Password length: {len(password)}")
        print(f"[ONBOARDING]   - Password (first 3): {password[:3]}...")
        print(f"[ONBOARDING]   - Language: '{language}'")
        
        # Ensure language is valid (handle None case)
        user_language = (language.strip() if language and language.strip() else "en")
        print(f"[ONBOARDING]   - Language from request: '{language}'")
        print(f"[ONBOARDING]   - Final language: '{user_language}'")
        
        # Step 2: Create user object - ensure ALL required fields are set
        print(f"[ONBOARDING] Step 2: Creating User object...")
        print(f"[ONBOARDING]   - secret_key: length={len(password)}, value (first 3): {password[:3]}...")
        print(f"[ONBOARDING]   - preferred_language: '{user_language}'")
        
        # Create user with explicit values for ALL fields
        from datetime import datetime
        import time
        
        # Ensure password is not empty
        if not password or not password.strip():
            raise ValueError("Password cannot be empty")
        
        # Ensure language is not empty
        if not user_language or not user_language.strip():
            user_language = "en"
        
        # Create timestamp explicitly
        now = datetime.utcnow()
        
        print(f"[ONBOARDING] Creating User with:")
        print(f"[ONBOARDING]   - name: '{name}' (length: {len(name)})")
        print(f"[ONBOARDING]   - secret_key: '{password[:3]}...' (length: {len(password)})")
        print(f"[ONBOARDING]   - preferred_language: '{user_language}'")
        print(f"[ONBOARDING]   - created_at: {now}")
        
        new_user = User(
            name=name.strip(),  # STEP 2: ALWAYS save user name (required, non-empty, stripped)
            secret_key=password.strip(),  # Ensure no whitespace
            preferred_language=user_language.strip(),  # Ensure no whitespace
            created_at=now  # Explicitly set created_at
        )
        
        print(f"[ONBOARDING] ✅ User object created")
        print(f"[ONBOARDING]   - secret_key: length={len(new_user.secret_key)}, value (first 3): '{new_user.secret_key[:3]}...'")
        print(f"[ONBOARDING]   - preferred_language: '{new_user.preferred_language}'")
        print(f"[ONBOARDING]   - created_at: {new_user.created_at}")
        
        # Verify all required fields are set and not None
        if not new_user.name or not new_user.name.strip():
            raise ValueError("name cannot be empty or whitespace")
        if not new_user.secret_key or not new_user.secret_key.strip():
            raise ValueError("secret_key cannot be empty or whitespace")
        if not new_user.preferred_language or not new_user.preferred_language.strip():
            raise ValueError("preferred_language cannot be empty or whitespace")
        if new_user.created_at is None:
            raise ValueError("created_at cannot be None")
        
        print(f"[ONBOARDING] ✅ All required fields verified and not None")
        
        # Step 3: Add to session
        print(f"[ONBOARDING] Step 3: Adding to session...")
        db.add(new_user)
        print(f"[ONBOARDING] ✅ User added to session")
        
        # Step 4: Flush to catch constraint errors early
        print(f"[ONBOARDING] Step 4: Flushing (checking constraints)...")
        try:
            db.flush()
            print(f"[ONBOARDING] ✅ Flush successful - no constraint errors")
        except Exception as flush_error:
            print(f"[ONBOARDING] ❌ FLUSH ERROR: {flush_error}")
            print(f"[ONBOARDING] Flush error type: {type(flush_error).__name__}")
            print(f"[ONBOARDING] Flush error class: {flush_error.__class__.__name__}")
            print(f"[ONBOARDING] Flush error module: {flush_error.__class__.__module__}")
            import traceback
            print(f"[ONBOARDING] Flush error traceback:\n{traceback.format_exc()}")
            try:
                db.rollback()
                print(f"[ONBOARDING] Rolled back after flush error")
            except:
                pass
            raise  # Re-raise to be caught by outer except
        
        # Step 5: Commit transaction
        print(f"[ONBOARDING] Step 5: Committing transaction...")
        db.commit()
        print(f"[ONBOARDING] ✅ Transaction committed successfully")
        
        # Step 6: Refresh to get ID
        print(f"[ONBOARDING] Step 6: Refreshing user to get ID...")
        db.refresh(new_user)
        user_id = new_user.id
        print(f"[ONBOARDING] ✅ User refreshed - user_id: {user_id}")
        print(f"[ONBOARDING] ========== USER CREATION SUCCESS ==========")
        
    except Exception as e:
        print(f"[ONBOARDING] ========== USER CREATION ERROR ==========")
        print(f"[ONBOARDING] ❌ ERROR: {e}")
        print(f"[ONBOARDING] Error type: {type(e).__name__}")
        print(f"[ONBOARDING] Error class: {e.__class__.__name__}")
        print(f"[ONBOARDING] Error module: {e.__class__.__module__}")
        import traceback
        print(f"[ONBOARDING] Full traceback:\n{traceback.format_exc()}")
        
        try:
            db.rollback()
            print(f"[ONBOARDING] ✅ Transaction rolled back")
        except Exception as rollback_error:
            print(f"[ONBOARDING] ⚠️ Rollback error: {rollback_error}")
        
        # Determine specific error message with detailed analysis
        error_str = str(e).lower()
        error_detail = "Error creating account. Please try again."
        
        # Check error type first (most reliable)
        error_type_name = type(e).__name__.lower()
        error_module = e.__class__.__module__.lower()
        
        print(f"[ONBOARDING] Error analysis:")
        print(f"[ONBOARDING]   - Type name: {error_type_name}")
        print(f"[ONBOARDING]   - Module: {error_module}")
        print(f"[ONBOARDING]   - Error string (first 200 chars): {error_str[:200]}")
        
        if "integrityerror" in error_type_name or "integrity" in error_module:
            # This is a constraint violation
            print(f"[ONBOARDING] Detected: IntegrityError (constraint violation)")
            if "unique" in error_str or "duplicate" in error_str or "already exists" in error_str:
                error_detail = "A user with this password already exists. Please use a different password."
            elif "foreign key" in error_str or "fk_" in error_str or "references" in error_str:
                error_detail = "Database foreign key constraint error. Please contact support."
            elif "check" in error_str or "check constraint" in error_str:
                error_detail = "Database check constraint error. Please contact support."
            elif "not null" in error_str or "null value" in error_str or "null constraint" in error_str:
                error_detail = "Required field is missing. Please contact support."
            else:
                # Generic constraint error - extract more info from error
                constraint_name = ""
                if "constraint" in error_str:
                    # Try to extract constraint name
                    import re
                    match = re.search(r'constraint\s+["\']?(\w+)["\']?', error_str, re.IGNORECASE)
                    if match:
                        constraint_name = match.group(1)
                if constraint_name:
                    error_detail = f"Database constraint error ({constraint_name}). Please contact support."
                else:
                    error_detail = f"Database constraint error: {error_str[:150]}. Please contact support."
        elif "operationalerror" in error_type_name or "operational" in error_module:
            print(f"[ONBOARDING] Detected: OperationalError")
            if "connection" in error_str or "connect" in error_str or "could not connect" in error_str:
                error_detail = "Cannot connect to database. Please check if the database server is running."
            elif "timeout" in error_str:
                error_detail = "Database connection timeout. Please try again."
            else:
                error_detail = "Database operation error. Please try again."
        elif "programmingerror" in error_type_name or "programming" in error_module:
            print(f"[ONBOARDING] Detected: ProgrammingError")
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
        print(f"[ONBOARDING] ========== END ERROR ANALYSIS ==========")
        raise HTTPException(status_code=500, detail=error_detail)
    
    # Step 4: Generate greeting message - NEVER FAILS
    initial_message = ""
    
    if user_id:
        try:
            print(f"[ONBOARDING] Step 7: Generating greeting from GPT for user_id: {user_id}")
            print(f"[ONBOARDING] User name from payload: '{name}'")
            # STEP 2: Use name from payload (always available, required)
            user_name_for_gpt = name.strip()
            # CRITICAL: Initial greeting is ALWAYS in English (for context)
            # User's preferred language will be used for subsequent responses
            brain = ConversationBrain(db, language="en")  # Use English for initial greeting
            initial_message = brain.get_initial_message(user_id, user_name_for_gpt, "en")  # Always English for initial message
            print(f"[ONBOARDING] ✅ GPT greeting generated successfully")
        except Exception as gpt_error:
            print(f"[ONBOARDING] ⚠️ GPT failed (non-critical), using fallback: {gpt_error}")
            # GPT failure is NOT critical - use fallback
            if language == "fa":
                initial_message = "سلام! من صدی هستم، دستیار مراقبت سلامت شما. خوش آمدید!"
            elif language == "ar":
                initial_message = "مرحباً! أنا صدي، مساعد رعاية صحية الخاص بك. أهلاً بك!"
            else:
                initial_message = "Hello! I'm Sedi, your health care assistant. Welcome!"
            print(f"[ONBOARDING] ✅ Using fallback greeting")
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
    name: Optional[str] = Query(None),  # Optional: name from frontend (for GPT personalization)
    db: Session = Depends(get_db)
):
    """
    Get personalized greeting for user.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    print(f"[GREETING] Getting greeting for user_id: {user_id}, name: '{name}', lang: {lang}")
    
    brain = ConversationBrain(db, language=lang)
    # Pass name to get_greeting if provided
    greeting_result = brain.get_greeting(user_id, user_name=name)
    
    # get_greeting returns dict with message
    greeting_message = greeting_result.get("message", "") if isinstance(greeting_result, dict) else str(greeting_result)
    
    print(f"[GREETING] Greeting generated: '{greeting_message[:50]}...'")
    
    return {
        "message": greeting_message,
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
