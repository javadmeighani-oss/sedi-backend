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

SupportedLanguage = Literal["en", "fa", "ar"]


def generate_fallback_text(
    payload: NotificationPayload,
    language: SupportedLanguage,
    user_name: Optional[str] = None,
    memory_context: Optional[MemoryContext] = None
) -> str:
    """
    Generate deterministic fallback text in user's language with motherly-care tone (Release B2.1).
    
    Args:
        payload: NotificationPayload with type, metadata, etc.
        language: User's effective language ("en" | "fa" | "ar")
        user_name: Optional user name (from User.name)
        memory_context: Optional MemoryContext for personalization
    
    Returns:
        Non-empty text string in the specified language. Never raises.
    """
    # Resolve greeting name based on language
    if language == "fa":
        greeting_name = user_name or "عزیزم"
    elif language == "ar":
        greeting_name = user_name or "عزيزي"
    else:  # en
        greeting_name = user_name or "dear"
    
    if payload.type == "morning_brief":
        return _generate_morning_brief(greeting_name, language, memory_context)
    elif payload.type == "connection_ping":
        return _generate_connection_ping(greeting_name, language, memory_context)
    elif payload.type == "health_alert":
        return _generate_health_alert(greeting_name, language, payload.metadata)
    elif payload.type == "device_disconnected":
        return _generate_device_disconnected(greeting_name, language, payload.metadata)
    else:
        # Fallback for unknown types
        return _get_fallback_greeting(greeting_name, language)


def _generate_morning_brief(
    greeting_name: str,
    language: SupportedLanguage,
    memory_context: Optional[MemoryContext]
) -> str:
    """Generate morning brief notification text in specified language"""
    
    if language == "fa":
        base = f"صبح بخیر {greeting_name} 🌅"
        hints = []
        
        if memory_context:
            if memory_context.has_sleep_data() and memory_context.sleep_duration_hours is not None:
                if memory_context.sleep_duration_hours < 6:
                    hints.append("امشب بیشتر استراحت کن")
                elif memory_context.sleep_duration_hours >= 7:
                    hints.append("خواب خوبی داشتی")
            
            if memory_context.has_hydration_data() and memory_context.hydration_ml is not None:
                if memory_context.hydration_ml < 1500:
                    hints.append("یادت نره آب بخوری")
            
            if memory_context.has_activity_data():
                if memory_context.steps_count and memory_context.steps_count > 5000:
                    hints.append("فعالیت خوبی داشتی")
        
        if hints:
            hint_text = "، ".join(hints[:2])
            return f"{base} {hint_text}."
        else:
            return f"{base} روز خوبی داشته باشی."
    
    elif language == "ar":
        base = f"صباح الخير {greeting_name} 🌅"
        hints = []
        
        if memory_context:
            if memory_context.has_sleep_data() and memory_context.sleep_duration_hours is not None:
                if memory_context.sleep_duration_hours < 6:
                    hints.append("احصل على مزيد من الراحة الليلة")
                elif memory_context.sleep_duration_hours >= 7:
                    hints.append("كان نومك جيداً")
            
            if memory_context.has_hydration_data() and memory_context.hydration_ml is not None:
                if memory_context.hydration_ml < 1500:
                    hints.append("لا تنس شرب الماء")
            
            if memory_context.has_activity_data():
                if memory_context.steps_count and memory_context.steps_count > 5000:
                    hints.append("كان نشاطك جيداً")
        
        if hints:
            hint_text = "، ".join(hints[:2])
            return f"{base} {hint_text}."
        else:
            return f"{base} أتمنى لك يوماً جميلاً."
    
    else:  # en
        base = f"Good morning {greeting_name} 🌅"
        hints = []
        
        if memory_context:
            if memory_context.has_sleep_data() and memory_context.sleep_duration_hours is not None:
                if memory_context.sleep_duration_hours < 6:
                    hints.append("try to get more rest tonight")
                elif memory_context.sleep_duration_hours >= 7:
                    hints.append("you had good sleep")
            
            if memory_context.has_hydration_data() and memory_context.hydration_ml is not None:
                if memory_context.hydration_ml < 1500:
                    hints.append("remember to drink water")
            
            if memory_context.has_activity_data():
                if memory_context.steps_count and memory_context.steps_count > 5000:
                    hints.append("you had good activity")
        
        if hints:
            hint_text = ", ".join(hints[:2])
            return f"{base} {hint_text}."
        else:
            return f"{base} Have a wonderful day."


def _generate_connection_ping(
    greeting_name: str,
    language: SupportedLanguage,
    memory_context: Optional[MemoryContext]
) -> str:
    """Generate connection ping notification text in specified language"""
    
    if language == "fa":
        base = f"سلام {greeting_name}"
        if memory_context and memory_context.has_activity_data():
            check_in = "چطوره؟ یه کم حرکت کنی خوبه"
        else:
            check_in = "همه چی خوبه؟"
        return f"{base}، {check_in} 🌿"
    
    elif language == "ar":
        base = f"مرحباً {greeting_name}"
        if memory_context and memory_context.has_activity_data():
            check_in = "كيف حالك؟ القليل من الحركة سيكون جيداً"
        else:
            check_in = "هل كل شيء على ما يرام؟"
        return f"{base}، {check_in} 🌿"
    
    else:  # en
        base = f"Hello {greeting_name}"
        if memory_context and memory_context.has_activity_data():
            check_in = "how are you? a little movement would be good"
        else:
            check_in = "is everything okay?"
        return f"{base}, {check_in} 🌿"


def _generate_health_alert(
    greeting_name: str,
    language: SupportedLanguage,
    metadata: Optional[Dict[str, Any]]
) -> str:
    """Generate health alert notification text in specified language"""
    
    # Extract alert reason from metadata
    alert_code = None
    alert_reason = None
    
    if metadata:
        alert_code = metadata.get("alert_code")
        alert_reason = metadata.get("alert_reason")
    
    if language == "fa":
        base = f"سلام {greeting_name}، یه نکته مهم"
        
        if alert_reason:
            return f"{base}: {alert_reason} 🌿"
        elif alert_code:
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
    
    elif language == "ar":
        base = f"مرحباً {greeting_name}، ملاحظة مهمة"
        
        if alert_reason:
            return f"{base}: {alert_reason} 🌿"
        elif alert_code:
            alert_messages = {
                "high_heart_rate": "نبضك مرتفع",
                "low_heart_rate": "نبضك منخفض",
                "low_spo2": "الأكسجين في دمك منخفض",
                "high_temperature": "درجة حرارتك مرتفعة",
                "irregular": "تم ملاحظة تغيير في حالتك الصحية"
            }
            reason = alert_messages.get(alert_code, "تم ملاحظة تغيير في حالتك الصحية")
            return f"{base}: {reason}. من الأفضل أن تتحقق 🌿"
        else:
            return f"{base}: من الأفضل أن تتحقق من حالتك الصحية 🌿"
    
    else:  # en
        base = f"Hello {greeting_name}, an important note"
        
        if alert_reason:
            return f"{base}: {alert_reason} 🌿"
        elif alert_code:
            alert_messages = {
                "high_heart_rate": "your heart rate is elevated",
                "low_heart_rate": "your heart rate is low",
                "low_spo2": "your blood oxygen is low",
                "high_temperature": "your temperature is elevated",
                "irregular": "a change in your health status was detected"
            }
            reason = alert_messages.get(alert_code, "a change in your health status was detected")
            return f"{base}: {reason}. you should check 🌿"
        else:
            return f"{base}: you should check your health status 🌿"


def _generate_device_disconnected(
    greeting_name: str,
    language: SupportedLanguage,
    metadata: Optional[Dict[str, Any]]
) -> str:
    """Generate device disconnected notification text in specified language"""
    device_id = (metadata or {}).get("device_id", "device")
    if language == "fa":
        return f"سلام {greeting_name}، اتصال دستگاه ({device_id}) قطع شده. وقتی می‌تونی دوباره وصلش کن 🌿"
    elif language == "ar":
        return f"مرحباً {greeting_name}، انقطع اتصال الجهاز ({device_id}). أعد الاتصال عندما تستطيع 🌿"
    else:  # en
        return f"Hello {greeting_name}, your device ({device_id}) has been disconnected. Reconnect when you can 🌿"


def _get_fallback_greeting(greeting_name: str, language: SupportedLanguage) -> str:
    """Get fallback greeting for unknown notification types"""
    if language == "fa":
        return f"سلام {greeting_name}، امیدوارم حالت خوب باشه 🌿"
    elif language == "ar":
        return f"مرحباً {greeting_name}، أتمنى أن تكون بخير 🌿"
    else:  # en
        return f"Hello {greeting_name}, I hope you're doing well 🌿"
