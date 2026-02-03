# app/services/notification_engine/fallback_generator.py
"""
Deterministic Fallback Text Generator (Release B - Part B1)

Generates Persian notification text with motherly-care tone.
Always returns non-empty text. Never raises exceptions.
"""

from typing import Optional, Dict, Any
from datetime import datetime

from app.services.memory.memory_context import MemoryContext
from app.schemas.notification import NotificationPayload


def generate_fallback_text(
    payload: NotificationPayload,
    user_name: Optional[str] = None,
    memory_context: Optional[MemoryContext] = None
) -> str:
    """
    Generate deterministic fallback text in Persian with motherly-care tone.
    
    Args:
        payload: NotificationPayload with type, metadata, etc.
        user_name: Optional user name (from User.name)
        memory_context: Optional MemoryContext for personalization
    
    Returns:
        Non-empty Persian text string. Never raises.
    """
    # Default greeting name
    greeting_name = user_name or "عزیزم"
    
    if payload.type == "morning_brief":
        return _generate_morning_brief(greeting_name, memory_context)
    elif payload.type == "connection_ping":
        return _generate_connection_ping(greeting_name, memory_context)
    elif payload.type == "health_alert":
        return _generate_health_alert(greeting_name, payload.metadata)
    else:
        # Fallback for unknown types
        return f"سلام {greeting_name}، امیدوارم حالت خوب باشه 🌿"


def _generate_morning_brief(
    greeting_name: str,
    memory_context: Optional[MemoryContext]
) -> str:
    """Generate morning brief notification text"""
    base = f"صبح بخیر {greeting_name} 🌅"
    
    hints = []
    
    # Add personalized hints from memory context
    if memory_context:
        # Sleep hint
        if memory_context.has_sleep_data() and memory_context.sleep_duration_hours is not None:
            if memory_context.sleep_duration_hours < 6:
                hints.append("امشب بیشتر استراحت کن")
            elif memory_context.sleep_duration_hours >= 7:
                hints.append("خواب خوبی داشتی")
        
        # Hydration hint
        if memory_context.has_hydration_data() and memory_context.hydration_ml is not None:
            if memory_context.hydration_ml < 1500:
                hints.append("یادت نره آب بخوری")
        
        # Activity hint
        if memory_context.has_activity_data():
            if memory_context.steps_count and memory_context.steps_count > 5000:
                hints.append("فعالیت خوبی داشتی")
    
    # Combine base with hints
    if hints:
        # Use first 1-2 hints
        selected_hints = hints[:2]
        hint_text = "، ".join(selected_hints)
        return f"{base} {hint_text}."
    else:
        return f"{base} روز خوبی داشته باشی."


def _generate_connection_ping(
    greeting_name: str,
    memory_context: Optional[MemoryContext]
) -> str:
    """Generate connection ping notification text"""
    base = f"سلام {greeting_name}"
    
    # Gentle check-in message
    check_in = "همه چی خوبه؟"
    
    # Add context if available
    if memory_context and memory_context.has_activity_data():
        check_in = "چطوره؟ یه کم حرکت کنی خوبه"
    
    return f"{base}، {check_in} 🌿"


def _generate_health_alert(
    greeting_name: str,
    metadata: Optional[Dict[str, Any]]
) -> str:
    """Generate health alert notification text"""
    base = f"سلام {greeting_name}، یه نکته مهم"
    
    # Extract alert reason from metadata
    alert_code = None
    alert_reason = None
    
    if metadata:
        alert_code = metadata.get("alert_code")
        alert_reason = metadata.get("alert_reason")
    
    # Build alert message
    if alert_reason:
        return f"{base}: {alert_reason} 🌿"
    elif alert_code:
        # Map common alert codes to Persian messages
        alert_messages = {
            "high_heart_rate": "ضربان قلبت بالاست",
            "low_heart_rate": "ضربان قلبت پایینه",
            "low_spo2": "اکسیژن خونت پایینه",
            "high_temperature": "دمای بدنت بالاست",
            "irregular": "یه تغییر در وضعیت سلامتت دیده شده"
        }
        reason = alert_messages.get(alert_code, "یه تغییر در وضعیت سلامتت دیده شده")
        return f"{base}: {reason}. بهتره بررسی کنی 🌿"
    else:
        return f"{base}: بهتره وضعیت سلامتت رو بررسی کنی 🌿"
