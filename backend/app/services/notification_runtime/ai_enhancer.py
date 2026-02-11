# app/services/notification_runtime/ai_enhancer.py
"""
Safe AI Enhancement Wrapper (Release B - Part B1)

Safely enhances notification text with AI if enabled.
Never breaks notification creation - always returns payload unchanged on any error.
"""

import os
from typing import Optional
import logging

from backend.app.schemas.notification import NotificationPayload

logger = logging.getLogger(__name__)

# Environment flag for AI enhancement (default: False)
NOTIF_AI_ENHANCE = os.getenv("NOTIF_AI_ENHANCE", "false").lower() in ("true", "1", "yes")


def enhance_with_ai(payload: NotificationPayload) -> NotificationPayload:
    """
    Safely enhance notification payload with AI if enabled (Stage 16.6.4).

    Guardrails: health_alert with priority high/critical -> no AI.
    Never changes medical meaning; tone only; bounded length.
    """
    if not NOTIF_AI_ENHANCE:
        return payload

    # Stage 16.6.4: Health alerts - AI disabled unless priority=normal
    if payload.type == "health_alert" and payload.priority in ("high", "critical"):
        return payload

    try:
        # Import AI text engine (may not exist in all environments)
        from backend.app.core.ai_text_engine import generate_notification_text
        
        # Map notification types to AI engine types
        ai_type_map = {
            "morning_brief": "morning_summary",
            "connection_ping": "inactive_ping",
            "health_alert": "health_check"
        }
        
        ai_type = ai_type_map.get(payload.type, "health_check")
        
        # Get user name from database (optional)
        user_name = "عزیزم"  # Default fallback
        try:
            from sqlalchemy.orm import Session
            from backend.app.models import User
            # Note: We don't have db session here, so we'll use default
            # In practice, user_name should be passed from caller
        except Exception:
            pass
        
        # Extract context from metadata if available
        health_summary = None
        hours_since = None
        
        if payload.metadata:
            health_summary = payload.metadata.get("health_summary")
            hours_since = payload.metadata.get("hours_since_last_talk")
        
        # Call AI text engine
        enhanced_body = generate_notification_text(
            language="fa",  # Persian
            notification_type=ai_type,
            user_name=user_name,
            health_summary=health_summary,
            hours_since_last_talk=hours_since
        )
        
        # Stage 16.6.4: Bounded length - max 1 short sentence extra (~80 chars)
        max_extra = 80
        orig_len = len(payload.body.strip())
        if enhanced_body and len(enhanced_body.strip()) > 0:
            trimmed = enhanced_body.strip()[: orig_len + max_extra]
            if len(trimmed) < 5:
                return payload
            # Update metadata to track AI enhancement
            enhanced_metadata = payload.metadata.copy() if payload.metadata else {}
            enhanced_metadata["ai_enhanced"] = True

            # Create new payload with enhanced body
            return NotificationPayload(
                user_id=payload.user_id,
                type=payload.type,
                title=payload.title,
                body=trimmed,
                priority=payload.priority,
                scheduled_for=payload.scheduled_for,
                dedupe_key=payload.dedupe_key,
                metadata=enhanced_metadata
            )
        
        # If AI returned empty, mark as not enhanced and return original
        if payload.metadata is None:
            payload.metadata = {}
        payload.metadata["ai_enhanced"] = False
        return payload
        
    except ImportError:
        # AI engine not available
        logger.debug("[AI Enhancer] AI text engine not available, using fallback")
        return payload
    except Exception as e:
        # Any other error (401, 429, timeout, etc.) - return unchanged
        logger.warning(f"[AI Enhancer] Error enhancing notification: {e}, using fallback")
        return payload
