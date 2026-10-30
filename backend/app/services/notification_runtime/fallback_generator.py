# app/services/notification_runtime/fallback_generator.py
"""
Deterministic Fallback Text Generator (Release B2.1)

Generates notification text with motherly-care tone in user's language.
Supports: English (en), Persian (fa), Arabic (ar)
Always returns non-empty text. Never raises exceptions.
"""

from typing import Optional, Dict, Any, Literal
from datetime import datetime

from backend.app.services.memory.memory_context import MemoryContext
from backend.app.schemas.notification import NotificationPayload
from backend.app import sedi_copy

SupportedLanguage = Literal["en", "fa", "ar"]


def generate_fallback_text(
    payload: NotificationPayload,
    language: Optional[SupportedLanguage] = None,
    user_name: Optional[str] = None,
    memory_context: Optional[MemoryContext] = None
) -> str:
    """
    Generate deterministic fallback text in user's language with motherly-care tone (Release B2.1).
    
    Args:
        payload: NotificationPayload with type, metadata, etc.
        language: User's effective language ("en" | "fa" | "ar"). Optional: uses payload.metadata["language"] if present, else "fa" (project default).
        user_name: Optional user name (from User.name)
        memory_context: Optional MemoryContext for personalization
    
    Returns:
        Non-empty text string in the specified language. Never raises.
    """
    try:
        # Resolve language: explicit arg > payload.metadata > default "fa" (project default per knowledge router)
        if language and str(language).strip().lower() in ("en", "fa", "ar"):
            lang: SupportedLanguage = str(language).strip().lower()  # type: ignore
        elif payload.metadata and isinstance(payload.metadata.get("language"), str):
            raw = str(payload.metadata["language"]).strip().lower()
            if raw in ("en", "fa", "ar"):
                lang = raw  # type: ignore
            else:
                lang = "fa"
        else:
            lang = "fa"

        # Prefer real name; never default to عزیزم / dear / عزيزي.
        greeting_name = (user_name or "").strip() or (
            "friend" if lang == "en" else ""
        )

        if payload.type == "morning_brief":
            return _generate_morning_brief(greeting_name, lang, memory_context)
        elif payload.type == "connection_ping":
            return _generate_connection_ping(greeting_name, lang, memory_context)
        elif payload.type == "health_alert":
            return _generate_health_alert(greeting_name, lang, payload.metadata)
        elif payload.type == "device_disconnected":
            return _generate_device_disconnected(greeting_name, lang, payload.metadata)
        else:
            return _get_fallback_greeting(greeting_name, lang)
    except Exception:
        return "Hello."


def _lang3(language: str) -> str:
    return language if language in ("fa", "ar") else "en"


def _generate_morning_brief(
    greeting_name: str,
    language: SupportedLanguage,
    memory_context: Optional[MemoryContext]
) -> str:
    """Generate morning brief notification text in specified language"""
    lang = _lang3(language)
    base = sedi_copy.t("fallback.morning.base", lang, name=greeting_name)
    hints = []

    if memory_context:
        if memory_context.has_sleep_data() and memory_context.sleep_duration_hours is not None:
            if memory_context.sleep_duration_hours < 6:
                hints.append(sedi_copy.t("fallback.hint.sleep_low", lang))
            elif memory_context.sleep_duration_hours >= 7:
                hints.append(sedi_copy.t("fallback.hint.sleep_ok", lang))

        if memory_context.has_hydration_data() and memory_context.hydration_ml is not None:
            if memory_context.hydration_ml < 1500:
                hints.append(sedi_copy.t("fallback.hint.water", lang))

        if memory_context.has_activity_data():
            if memory_context.steps_count and memory_context.steps_count > 5000:
                hints.append(sedi_copy.t("fallback.hint.activity", lang))

    if hints:
        hint_text = sedi_copy.t("fallback.joiner", lang).join(hints[:2])
        return f"{base} {hint_text}."
    return f"{base} {sedi_copy.t('fallback.morning.cta', lang)}"


def _generate_connection_ping(
    greeting_name: str,
    language: SupportedLanguage,
    memory_context: Optional[MemoryContext]
) -> str:
    """Generate connection ping notification text in specified language"""
    lang = _lang3(language)
    name = (greeting_name or "").strip()
    prefix = sedi_copy.t("address.companion", lang, name=name) if name else ""
    if memory_context and memory_context.has_activity_data():
        check_in = sedi_copy.t("fallback.ping.activity", lang)
    else:
        check_in = sedi_copy.t("fallback.ping.plain", lang)
    body = f"{prefix}{check_in}."
    return body[:1].upper() + body[1:] if lang == "en" else body


def _generate_health_alert(
    greeting_name: str,
    language: SupportedLanguage,
    metadata: Optional[Dict[str, Any]]
) -> str:
    """Generate health alert notification text in specified language"""
    lang = _lang3(language)

    # Extract alert reason from metadata
    alert_code = None
    alert_reason = None

    if metadata:
        alert_code = metadata.get("alert_code")
        alert_reason = metadata.get("alert_reason")

    base = sedi_copy.t("fallback.health.base", lang, name=greeting_name)
    if alert_reason:
        return f"{base}: {alert_reason}"
    if alert_code:
        aliases = {"high_heart_rate": "heart_rate_high", "low_heart_rate": "heart_rate_low", "high_temperature": "temperature_high"}
        code = aliases.get(alert_code, alert_code)
        reason_key = f"fallback.health.reason.{code}"
        if not sedi_copy.has(reason_key):
            reason_key = "fallback.health.reason.irregular"
        return f"{base}: {sedi_copy.t(reason_key, lang)}. {sedi_copy.t('fallback.health.check', lang)}"
    return f"{base}: {sedi_copy.t('fallback.health.check_status', lang)}"


def _generate_device_disconnected(
    greeting_name: str,
    language: SupportedLanguage,
    metadata: Optional[Dict[str, Any]]
) -> str:
    """Generate device disconnected notification text in specified language"""
    device_id = (metadata or {}).get("device_id", "device")
    return sedi_copy.t("fallback.device.disconnected", _lang3(language), name=greeting_name, device=device_id)


def _get_fallback_greeting(greeting_name: str, language: SupportedLanguage) -> str:
    """Get fallback greeting for unknown notification types"""
    return sedi_copy.t("fallback.greeting", _lang3(language), name=greeting_name)
