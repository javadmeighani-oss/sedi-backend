# app/services/notification_runtime/ai_enhancer.py
"""
Safe AI Enhancement Wrapper (Release B - Part B1)

Safely enhances notification text with AI if enabled.
Never breaks notification creation - always returns payload unchanged on any error.
Correctness of localized notifications must not depend on this enhancer.
"""

import os
import logging

from backend.app.schemas.notification import NotificationPayload

logger = logging.getLogger(__name__)

# Environment flag for AI enhancement (default: False)
NOTIF_AI_ENHANCE = os.getenv("NOTIF_AI_ENHANCE", "false").lower() in ("true", "1", "yes")

# Canonical V1 Smart Notification types — never free-form AI rewritten.
_V1_CANONICAL_NO_AI_TYPES = frozenset(
    {
        "connection_ping",
        "morning_brief",
        "engagement_nudge",
    }
)


def _payload_language(payload: NotificationPayload) -> str:
    """Prefer persisted payload language; never hard-code FA."""
    meta = payload.metadata or {}
    raw = str(meta.get("language") or "").strip().lower().split("-")[0]
    if raw in ("en", "fa", "ar"):
        return raw
    return "en"


def _is_canonical_v1_push(payload: NotificationPayload) -> bool:
    """True when payload is a V1 smart-notification path that must keep deterministic copy."""
    if payload.type in _V1_CANONICAL_NO_AI_TYPES:
        return True
    meta = payload.metadata or {}
    if str(meta.get("alert_code") or "").strip() == "daily_wellness_digest":
        return True
    if str(getattr(payload, "template_key", None) or "").strip() == "daily_wellness_digest":
        return True
    return False


def enhance_with_ai(payload: NotificationPayload) -> NotificationPayload:
    """
    Safely enhance notification payload with AI if enabled (Stage 16.6.4).

    Guardrails: health_alert with priority high/critical -> no AI.
    Canonical V1 smart notifications (daily digest / presence / legacy morning
    & engagement nudge) are never rewritten even when NOTIF_AI_ENHANCE=true.
    Never changes medical meaning; tone only; bounded length.
    Language follows payload metadata (en/fa/ar) — not hard-coded FA.
    """
    if not NOTIF_AI_ENHANCE:
        return payload

    if _is_canonical_v1_push(payload):
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
            "health_alert": "health_check",
        }

        ai_type = ai_type_map.get(payload.type, "health_check")
        language = _payload_language(payload)

        # Neutral default — never عزیزم / dear / عزيزي.
        user_name = "friend"

        health_summary = None
        hours_since = None

        if payload.metadata:
            health_summary = payload.metadata.get("health_summary")
            hours_since = payload.metadata.get("hours_since_last_talk")

        enhanced_body = generate_notification_text(
            language=language,
            notification_type=ai_type,
            user_name=user_name,
            health_summary=health_summary,
            hours_since_last_talk=hours_since,
        )

        # Stage 16.6.4: Bounded length - max 1 short sentence extra (~80 chars)
        max_extra = 80
        orig_len = len(payload.body.strip())
        if enhanced_body and len(enhanced_body.strip()) > 0:
            trimmed = enhanced_body.strip()[: orig_len + max_extra]
            if len(trimmed) < 5:
                return payload
            enhanced_metadata = payload.metadata.copy() if payload.metadata else {}
            enhanced_metadata["ai_enhanced"] = True

            return NotificationPayload(
                user_id=payload.user_id,
                type=payload.type,
                title=payload.title,
                body=trimmed,
                priority=payload.priority,
                scheduled_for=payload.scheduled_for,
                dedupe_key=payload.dedupe_key,
                metadata=enhanced_metadata,
            )

        if payload.metadata is None:
            payload.metadata = {}
        payload.metadata["ai_enhanced"] = False
        return payload

    except ImportError:
        logger.debug("[AI Enhancer] AI text engine not available, using fallback")
        return payload
    except Exception as e:
        logger.warning(f"[AI Enhancer] Error enhancing notification: {e}, using fallback")
        return payload
