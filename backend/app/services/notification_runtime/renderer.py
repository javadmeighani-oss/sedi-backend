# backend.app.services.notification_runtime.renderer
"""
Notification renderer (Stage 16.6.4).

Deterministic templates per channel with language-aware variants.
Returns {title, body, actions_json}. Conservative phrasing for health alerts.
"""

from typing import Dict, Any, Optional, Literal

SupportedLanguage = Literal["en", "fa", "ar"]

DEFAULT_ACTIONS_JSON = '[{"id":"like","type":"LIKE"},{"id":"dislike","type":"DISLIKE"},{"id":"open_chat","type":"OPEN_CHAT"}]'


def render(
    channel: str,
    language: str,
    inputs: Optional[Dict[str, Any]] = None,
    priority: str = "normal",
) -> Dict[str, str]:
    """
    Render notification title and body for a channel.

    Args:
        channel: "morning" | "engagement" | "health_alert"
        language: "en" | "fa" | "ar"
        inputs: optional {user_display_name, last_vitals_summary, last_topic_hint}
        priority: "low" | "normal" | "high" | "critical"

    Returns:
        {title, body, actions_json}
    """
    inputs = inputs or {}
    lang = language if language in ("en", "fa", "ar") else "en"
    name = (inputs.get("user_display_name") or "").strip() or None

    if channel == "morning":
        title, body = _render_morning(lang, name, inputs)
    elif channel == "engagement":
        title, body = _render_engagement(lang, name, inputs)
    elif channel == "health_alert":
        title, body = _render_health_alert(lang, name, inputs, priority)
    else:
        title, body = _render_engagement(lang, name, inputs)  # fallback

    return {
        "title": title,
        "body": body,
        "actions_json": DEFAULT_ACTIONS_JSON,
    }


def _render_morning(lang: str, name: Optional[str], inputs: Dict[str, Any]) -> tuple:
    greeting = _morning_greeting(lang, name)
    hints = []
    for key in ("sleep_hint", "hydration_hint", "activity_hint"):
        h = (inputs.get(key) or "").strip()
        if h and len(h) < 50:
            hints.append(h)
    if hints:
        line = " ".join(hints[:2]) + "."
    else:
        line = _morning_cta(lang)
    return _morning_title(lang), f"{greeting} {line}"


def _morning_title(lang: str) -> str:
    return {"fa": "صبح بخیر", "ar": "صباح الخير", "en": "Good Morning"}.get(lang, "Good Morning")


def _morning_greeting(lang: str, name: Optional[str]) -> str:
    n = name or ({"fa": "عزیزم", "ar": "عزيزي", "en": "dear"}.get(lang, "dear"))
    return {"fa": f"صبح بخیر {n} 🌅", "ar": f"صباح الخير {n} 🌅", "en": f"Good morning {n} 🌅"}.get(lang, f"Good morning {n} 🌅")


def _morning_cta(lang: str) -> str:
    return {"fa": " روز خوبی داشته باشی.", "ar": " أتمنى لك يوماً جميلاً.", "en": " Have a wonderful day."}.get(lang, " Have a wonderful day.")


def _render_engagement(lang: str, name: Optional[str], inputs: Dict[str, Any]) -> tuple:
    topic = (inputs.get("last_topic_hint") or "").strip()
    if topic and len(topic) < 60:
        body = _engagement_with_topic(lang, name, topic)
    else:
        body = _engagement_short(lang, name)
    title = {"fa": "سلام", "ar": "مرحباً", "en": "Hello"}.get(lang, "Hello")
    return title, body


def _engagement_short(lang: str, name: Optional[str]) -> str:
    n = name or ({"fa": "عزیزم", "ar": "عزيزي", "en": "dear"}.get(lang, "dear"))
    texts = {
        "fa": f"سلام {n}، همه چی خوبه؟ 🌿",
        "ar": f"مرحباً {n}، هل كل شيء على ما يرام؟ 🌿",
        "en": f"Hello {n}, how are you? 🌿",
    }
    return texts.get(lang, texts["en"])


def _engagement_with_topic(lang: str, name: Optional[str], topic: str) -> str:
    n = name or ({"fa": "عزیزم", "ar": "عزيزي", "en": "dear"}.get(lang, "dear"))
    if lang == "fa":
        return f"سلام {n}، درباره «{topic[:40]}» چطوره؟ 🌿"
    if lang == "ar":
        return f"مرحباً {n}، ماذا عن «{topic[:40]}»؟ 🌿"
    return f"Hello {n}, how about «{topic[:40]}»? 🌿"


def _render_health_alert(lang: str, name: Optional[str], inputs: Dict[str, Any], priority: str) -> tuple:
    """Conservative phrasing: unusual reading, no diagnosis. CTA to open Sedi. Critical adds emergency disclaimer."""
    title = {"fa": "هشدار سلامت", "ar": "تنبيه صحي", "en": "Health Alert"}.get(lang, "Health Alert")
    reason = (inputs.get("last_vitals_summary") or inputs.get("alert_reason") or "").strip()
    if reason and len(reason) < 100:
        base = _health_unusual(lang)
        body = f"{base} {reason}"
    else:
        body = _health_unusual(lang)
    body += " " + _health_cta(lang)
    if priority == "critical":
        body += " " + _health_emergency_disclaimer(lang)
    return title, body


def _health_unusual(lang: str) -> str:
    return {
        "fa": "یک قرائت غیرمعمول ثبت شد.",
        "ar": "تم تسجيل قراءة غير عادية.",
        "en": "An unusual reading was detected.",
    }.get(lang, "An unusual reading was detected.")


def _health_cta(lang: str) -> str:
    return {
        "fa": "برای بررسی، صدی رو باز کن.",
        "ar": "افتح التطبيق للمراجعة.",
        "en": "Open Sedi to review.",
    }.get(lang, "Open Sedi to review.")


def _health_emergency_disclaimer(lang: str) -> str:
    return {
        "fa": "اگر وضعیت جدی است، به پزشک مراجعه کنید.",
        "ar": "إذا كان الأمر عاجلاً، استشر طبيباً.",
        "en": "If urgent, seek professional care.",
    }.get(lang, "If urgent, seek professional care.")
