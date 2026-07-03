"""
Interaction Router - Thin API Layer

RESPONSIBILITY:
- Receives API request
- Calls Conversation Brain
- Returns response
- NO logic, NO decisions
"""

from fastapi import APIRouter, HTTPException, Query, Depends, Request, Response
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import os
import uuid

from backend.app.database import get_db
from backend.app.models import User, Memory
from backend.app.core.conversation.brain import ConversationBrain, _is_gpt_related_error, _redact_secrets
from backend.app.schemas import InteractionResponse
from backend.app.schemas.chat import ChatRequest
from backend.app.schemas.onboarding import OnboardingRequest
from backend.app.routers.auth_otp import get_current_user

router = APIRouter()


def _legacy_onboarding_enabled() -> bool:
    v = os.getenv("SEDI_LEGACY_ONBOARDING_ENABLED", "true").strip().lower()
    return v not in ("0", "false", "no", "off")


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
    request: Request,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Chat endpoint - Thin API layer.
    All conversation logic handled by Conversation Brain.
    
    CRITICAL VALIDATION:
    - message: Required, non-empty (from JSON body)
    - user_id: Optional in body; JWT is source of truth when omitted
    - Language: Detected ONLY from message content (no query params)
    - Name: Retrieved from memory/context (no query params)
    """
    # STEP 3: HARDEN CHAT FLOW - Validate payload
    if not payload.message or not payload.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )
    
    message = payload.message.strip()

    # JWT is source of truth; body user_id is kept for contract compatibility only.
    if payload.user_id and payload.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="user_id does not match authenticated user",
        )
    user_id = user.id

    chat_reminder_result = None
    try:
        from backend.app.services.gate4.user_chat_reminder import create_user_chat_reminder

        chat_reminder_result = create_user_chat_reminder(
            db,
            user_id=user_id,
            message=message,
            conversation_id=payload.conversation_id,
        )
        if chat_reminder_result.get("reason") == "needs_clarification":
            clarification = chat_reminder_result.get("clarification_message")
            if clarification:
                from backend.app.schemas.interaction import InteractionResponse

                return InteractionResponse(
                    reply=clarification,
                    user_id=user_id,
                    conversation_id=payload.conversation_id,
                )
    except Exception:
        pass

    notification_context = None
    continued_from_notification = False
    response_source_notification_id = None
    response_conversation_id = None

    if payload.source_notification_id is not None:
        from backend.app.services.gate4.interaction_event_service import (
            create_chat_message_event,
            verify_notification_belongs_to_user,
        )
        from backend.app.services.gate4.notification_chat_context import build_safe_chat_context

        try:
            notification = verify_notification_belongs_to_user(
                db,
                user_id=user_id,
                notification_id=payload.source_notification_id,
            )
        except LookupError:
            raise HTTPException(status_code=404, detail="Notification not found")
        except PermissionError:
            raise HTTPException(
                status_code=403,
                detail="Notification does not belong to user",
            )

        notification_context = build_safe_chat_context(notification)
        create_chat_message_event(
            db,
            user_id=user_id,
            source_notification_id=payload.source_notification_id,
            conversation_id=payload.conversation_id,
            thread_id=payload.thread_id,
            interaction_source=payload.interaction_source,
            metadata={"message_length": len(message)},
        )
        db.flush()
        continued_from_notification = True
        response_source_notification_id = payload.source_notification_id
        response_conversation_id = payload.conversation_id
    
    try:
        # STEP 2: SINGLE SOURCE OF LANGUAGE TRUTH
        # Detect language from user message text ONLY (not IP/locale/query params)
        from backend.app.core.conversation.name_database import detect_language
        detected_lang = detect_language(message)
        
        # Use detected language if valid, otherwise default to "en"
        # NO query parameter fallback - message content is the ONLY source
        if detected_lang in ["en", "fa", "ar"]:
            response_language = detected_lang
        else:
            response_language = "en"  # Default to English
        
        # V1 language policy: UI language is driven by Accept-Language or user preference (preferred_language).
        # Do not rely on message-language detection as the primary source.
        from backend.app.services.i18n.request_lang import resolve_request_lang
        response_language = resolve_request_lang(request, db=db, user_id=user.id)

        print(f"[CHAT] Language detection: message='{message[:50]}...', detected={detected_lang}, resolved={response_language}")
        print(f"[CHAT] ✅ Language determined by request/user preference (V1 policy)")
        
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
        
        # Stage 16.6.5: Try notification settings commands first (no GPT)
        from backend.app.services.chat_commands import detect_and_handle_user_settings_command
        from backend.app.core.conversation.memory import ConversationMemory

        override = detect_and_handle_user_settings_command(user.id, message, db, language=response_language)
        if override is not None:
            mem_obj = None
            try:
                mem = ConversationMemory(db)
                mem_obj = mem.save_conversation(user.id, message, override.assistant_message, response_language)
            except Exception as mem_err:
                print(f"[CHAT WARNING] Could not save command response to memory (non-critical): {mem_err}")
            try:
                from backend.app.services.knowledge.conversation_extraction_service import process_message as kc_process_message
                kc_process_message(
                    db=db,
                    user_id=user.id,
                    text=message,
                    language=response_language or "fa",
                    source_message_id=str(mem_obj.id) if mem_obj else None,
                )
            except Exception:
                pass
            return InteractionResponse(
                message=override.assistant_message,
                language=response_language,
                user_id=user.id,
                timestamp=datetime.utcnow(),
                requires_security_check=False,
                detected_name=None,
                continued_from_notification=continued_from_notification or None,
                source_notification_id=response_source_notification_id,
                conversation_id=response_conversation_id,
            )

        # Name is retrieved from memory/context by ConversationBrain - not passed as parameter
        brain = ConversationBrain(db, language=response_language)
        result = brain.process_message(
            user.id,
            message,
            None,
            notification_context=notification_context,
        )  # name=None - will be retrieved from memory

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
            detected_name=result.get("detected_name"),
            continued_from_notification=continued_from_notification or None,
            source_notification_id=response_source_notification_id,
            conversation_id=response_conversation_id,
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
        print(f"[CHAT ERROR] Error type: {type(e).__name__}")
        print(f"[CHAT ERROR] Error message: {_redact_secrets(str(e))[:300]}")
        import traceback
        print(f"[CHAT ERROR] Traceback: {traceback.format_exc()}")
        print(f"[CHAT ERROR] Message: '{message[:100]}...'")
        print(f"[CHAT ERROR] User ID: {user_id}")
        print(f"[CHAT ERROR] User found: {user is not None}")
        print(f"[CHAT ERROR] ===== END ERROR =====")
        
        if _is_gpt_related_error(e):
            print(
                f"[CHAT ERROR] GPT-related error detected - returning 502 gpt_failure "
                f"(error_type={type(e).__name__})"
            )
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=502,
                content={
                    "error": "gpt_failure",
                    "detail": "AI service is temporarily unavailable. Please try again.",
                },
            )
        else:
            # Return 500 for other internal errors
            raise HTTPException(
                status_code=500,
                detail=f"Error processing message: {str(e)[:200]}. Please try again."
            )


# ---------------- Onboarding - Setup User ----------------
# DEPRECATED (Phase V1.1A): Prefer JWT PATCH /auth/me for unified profile updates.
# Kept for backward compatibility with legacy frontend onboarding flow.
@router.post("/onboarding")
def setup_onboarding(
    request: Request,
    payload: OnboardingRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    DEPRECATED legacy onboarding (no JWT). Prefer OTP auth + PATCH /auth/me.
    Disabled when SEDI_LEGACY_ONBOARDING_ENABLED=false (returns 410).
    """
    if not _legacy_onboarding_enabled():
        raise HTTPException(
            status_code=410,
            detail="Legacy onboarding is disabled. Use OTP authentication and PATCH /auth/me.",
        )
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</auth/me>; rel="successor-version"'
    # Step 1: Validate payload
    name = payload.name.strip()
    
    # Validate name (REQUIRED, non-empty) - ONLY validation needed
    if not name or len(name) == 0:
        raise HTTPException(
            status_code=400,
            detail="Name is required and cannot be empty"
        )
    
    # Step 2: Ensure tables exist and remove UNIQUE constraint on name if it exists
    try:
        from backend.app.database import Base, engine
        from backend.app.models import User
        from sqlalchemy import text
        
        # Explicitly create User table to ensure schema matches
        # This will only create if table doesn't exist - won't modify existing schema
        Base.metadata.create_all(bind=engine, tables=[User.__table__])
        print(f"[ONBOARDING] User table ensured to exist")
        
        # Remove UNIQUE constraint on name if it exists (safe migration)
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_name_key"))
                conn.commit()
                print(f"[ONBOARDING] ✅ Removed UNIQUE constraint on users.name (if it existed)")
        except Exception as constraint_error:
            # If constraint doesn't exist or can't be dropped, continue anyway
            print(f"[ONBOARDING] ⚠️ Could not drop constraint (may not exist): {constraint_error}")
            # Continue - constraint might already be removed
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
        
        # Step 2: Create user object - password removed, using dummy value for secret_key
        print(f"[ONBOARDING] Step 2: Creating User object...")
        print(f"[ONBOARDING]   - name: '{name}'")
        print(f"[ONBOARDING]   - secret_key: '<ignored>' (password removed, using placeholder)")
        print(f"[ONBOARDING]   - preferred_language: 'en' (default)")
        
        # Create user with explicit values
        from datetime import datetime
        
        # Set default language
        user_language = "en"
        
        # Create timestamp explicitly
        now = datetime.utcnow()
        
        print(f"[ONBOARDING] Creating User with:")
        print(f"[ONBOARDING]   - name: '{name}' (length: {len(name)})")
        print(f"[ONBOARDING]   - secret_key: '<ignored>' (placeholder, not used)")
        print(f"[ONBOARDING]   - preferred_language: '{user_language}'")
        print(f"[ONBOARDING]   - created_at: {now}")
        
        # Create user - secret_key is set to placeholder since column exists but is ignored
        new_user = User(
            name=name.strip(),  # ALWAYS save user name (required, non-empty, stripped)
            secret_key="<ignored>",  # Placeholder - password removed, column ignored
            preferred_language=user_language,  # Default to English
            created_at=now  # Explicitly set created_at
        )
        
        print(f"[ONBOARDING] ✅ User object created")
        print(f"[ONBOARDING]   - name: '{new_user.name}'")
        print(f"[ONBOARDING]   - preferred_language: '{new_user.preferred_language}'")
        print(f"[ONBOARDING]   - created_at: {new_user.created_at}")
        
        # Verify required fields are set and not None
        if not new_user.name or not new_user.name.strip():
            raise ValueError("name cannot be empty or whitespace")
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
            # Check if it's a unique constraint on name - this should not happen after migration
            if "users_name_key" in error_str or ("unique" in error_str and "name" in error_str):
                print(f"[ONBOARDING] ⚠️ UNIQUE constraint on name still exists - attempting to remove...")
                # Try to remove constraint and retry user creation
                try:
                    from backend.app.database import engine
                    from sqlalchemy import text
                    with engine.connect() as conn:
                        conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_name_key"))
                        conn.commit()
                        print(f"[ONBOARDING] ✅ Removed constraint, but user creation already failed")
                except Exception as drop_error:
                    print(f"[ONBOARDING] ⚠️ Could not remove constraint: {drop_error}")
                # Return generic error - don't leak constraint details
                error_detail = "Registration failed. Please try again."
            elif "foreign key" in error_str or "fk_" in error_str or "references" in error_str:
                error_detail = "Database foreign key constraint error. Please contact support."
            elif "check" in error_str or "check constraint" in error_str:
                error_detail = "Database check constraint error. Please contact support."
            elif "not null" in error_str or "null value" in error_str or "null constraint" in error_str:
                error_detail = "Required field is missing. Please contact support."
            else:
                # Generic constraint error - don't leak details
                error_detail = "Registration failed. Please try again."
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
            # Multiple users with same name are allowed - this should not happen
            error_detail = "Database constraint error. Please try again."
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
            # V1 language policy: default English, but fully support fa/ar via Accept-Language or user preference.
            from backend.app.services.i18n.request_lang import resolve_request_lang

            greeting_lang = resolve_request_lang(request, db=db, user_id=user_id)
            brain = ConversationBrain(db, language=greeting_lang)
            initial_message = brain.get_initial_message(user_id, user_name_for_gpt, greeting_lang)
            print(f"[ONBOARDING] ✅ GPT greeting generated successfully")
        except Exception as gpt_error:
            print(f"[ONBOARDING] ⚠️ GPT failed (non-critical), using fallback: {gpt_error}")
            # GPT failure is NOT critical - use fallback
            from backend.app.services.i18n.request_lang import resolve_request_lang
            greeting_lang = resolve_request_lang(request, db=db, user_id=user_id)
            if greeting_lang == "fa":
                initial_message = "سلام! من صدی هستم، دستیار مراقبت سلامت شما. خوش آمدید!"
            elif greeting_lang == "ar":
                initial_message = "مرحباً! أنا صدي، مساعد رعاية صحية الخاص بك. أهلاً بك!"
            else:
                initial_message = "Hello! I'm Sedi, your health care assistant. Welcome!"
            print(f"[ONBOARDING] ✅ Using fallback greeting")
    else:
        # Fallback if user_id is None (shouldn't happen, but just in case)
        print(f"[ONBOARDING] ⚠️ WARNING: user_id is None, using fallback greeting")
        # Use default English greeting
        initial_message = "Hello! I'm Sedi, your health care assistant. Welcome!"
    
    # Step 5: Return success - ALWAYS with user_id
    if user_id is None:
        print(f"[ONBOARDING] ❌ CRITICAL: user_id is None after user creation!")
        raise HTTPException(
            status_code=500,
            detail="User created but could not retrieve user ID. Please try again."
        )
    
    print(f"[ONBOARDING] ✅ SUCCESS - Returning response with user_id: {user_id}")
    from backend.app.services.i18n.request_lang import resolve_request_lang
    response_lang = resolve_request_lang(request, db=db, user_id=user_id)
    return {
        "user_id": user_id,
        "message": initial_message,
        "language": response_lang
    }


# ---------------- Get Greeting ----------------
@router.get("/greeting")
def get_greeting(
    auth_user: User = Depends(get_current_user),
    user_id: Optional[int] = Query(None),
    lang: str = Query("en"),
    name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Get personalized greeting for user. Requires Bearer JWT.
    user_id query is optional (defaults to authenticated user); if provided must match JWT.
    """
    effective_user_id = user_id if user_id is not None else auth_user.id
    if effective_user_id != auth_user.id:
        raise HTTPException(
            status_code=403,
            detail="user_id does not match authenticated user",
        )

    print(f"[GREETING] Getting greeting for user_id: {auth_user.id}, name: '{name}', lang: {lang}")

    brain = ConversationBrain(db, language=lang)
    greeting_result = brain.get_greeting(auth_user.id, user_name=name)
    
    # get_greeting returns dict with message
    greeting_message = greeting_result.get("message", "") if isinstance(greeting_result, dict) else str(greeting_result)
    
    print(f"[GREETING] Greeting generated: '{greeting_message[:50]}...'")
    
    return {
        "message": greeting_message,
        "language": lang,
        "user_id": auth_user.id
    }


# ---------------- Get User History ----------------
@router.get("/history")
def get_user_history(
    user: User = Depends(get_current_user),
    user_id: Optional[int] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """
    Get conversation history for user. Requires Bearer JWT.
    user_id query is optional (defaults to authenticated user); if provided must match JWT.
    """
    effective_user_id = user_id if user_id is not None else user.id
    if effective_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="user_id does not match authenticated user",
        )

    memories = (
        db.query(Memory)
        .filter(Memory.user_id == user.id)
        .order_by(Memory.created_at.desc())
        .limit(limit)
        .all()
    )
    
    return {
        "user_id": user.id,
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
