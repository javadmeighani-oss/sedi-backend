# backend.app.services.notification_runtime.renderer
"""
Notification renderer (Stage 16.6.4).

Deterministic templates per channel with language-aware variants.
Returns {title, body, actions_json}. Conservative phrasing for health alerts.
Supports optional multi-language template.texts via i18n_resolver.
"""

from typing import Dict, Any, Optional, Literal

from backend.app.services.notification_runtime.i18n_resolver import resolve_text_by_user_language

SupportedLanguage = Literal["en", "fa", "ar"]

DEFAULT_ACTIONS_JSON = '[{"id":"like","type":"LIKE"},{"id":"dislike","type":"DISLIKE"},{"id":"open_chat","type":"OPEN_CHAT"}]'


def render(
    channel: str,
    language: str,
    inputs: Optional[Dict[str, Any]] = None,
    priority: str = "normal",
    template: Optional[Dict[str, Any]] = None,
    user_ctx: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """
    Render notification title and body for a channel.

    Args:
        channel: "morning" | "engagement" | "health_alert" | "companion"
        language: "en" | "fa" | "ar" (or locale e.g. "fa-IR"; used for template.texts resolution)
        inputs: optional {user_display_name, last_vitals_summary, last_topic_hint}
        priority: "low" | "normal" | "high" | "critical"
        template: optional dict; if it has "texts" (multilingual blocks), resolve by language and use
                  for title/body; otherwise channel-based rendering is used.
        user_ctx: optional from build_notification_context; preferred_name, goals_items, lifestyle_text, etc.

    Returns:
        {title, body, actions_json}
    """
    inputs = inputs or {}
    user_ctx = user_ctx or {}
    lang = (language or user_ctx.get("language") or "en").strip().lower() if (language or user_ctx.get("language")) else "en"
    if lang not in ("en", "fa", "ar"):
        lang = "en"
    name = (user_ctx.get("preferred_name") or "").strip() or (inputs.get("user_display_name") or "").strip() or None

    # Multi-language template: resolve texts by user language
    if template and isinstance(template.get("texts"), dict):
        resolved = resolve_text_by_user_language(
            template["texts"],
            user_language=language or lang,
            default="en",
        )
        if resolved:
            title = resolved.get("title", "").strip() or "Sedi"
            body = (resolved.get("body") or resolved.get("message") or "").strip() or ""
            if body or title:
                is_companion = channel in ("companion", "morning", "engagement")
                body = _personalize_text(body, lang, user_ctx, is_companion, name)
                return {
                    "title": title,
                    "body": body,
                    "actions_json": template.get("actions_json") or DEFAULT_ACTIONS_JSON,
                }
    # Channel-based rendering (existing behavior)
    if channel == "morning":
        title, body = _render_morning(lang, name, inputs)
    elif channel == "engagement":
        title, body = _render_engagement(lang, name, inputs)
    elif channel == "health_alert":
        title, body = _render_health_alert(lang, name, inputs, priority)
    else:
        title, body = _render_engagement(lang, name, inputs)  # fallback

    is_companion = channel in ("companion", "morning", "engagement")
    body = _append_goals_hint(body, lang, user_ctx, is_companion)

    return {
        "title": title,
        "body": body,
        "actions_json": DEFAULT_ACTIONS_JSON,
    }


def _text_starts_with_name(text: str, name: str) -> bool:
    if not text or not name:
        return False
    t = text.strip()
    n = name.strip()
    return t.lower().startswith(n.lower()) or t.startswith(n)


def _personalize_title(title: str, lang: str, name: Optional[str]) -> str:
    """Prepend name to title gently for companion (short)."""
    if not name or not name.strip():
        return title
    n = name.strip()
    if lang == "fa":
        return f"{n} جان"
    if lang == "ar":
        return f"يا {n}"
    return n


def _personalize_text(
    text: str,
    lang: str,
    user_ctx: Dict[str, Any],
    is_companion: bool,
    preferred_name: Optional[str] = None,
) -> str:
    """
    For companion channels: optionally prepend name and append one short goals/lifestyle hint.
    Keeps message short; no change for non-companion or when user_ctx empty.
    """
    if not is_companion:
        return text
    name = (preferred_name or (user_ctx.get("preferred_name") or "").strip()) or None
    out = text
    if name and out and not _text_starts_with_name(out, name):
        if lang == "fa":
            out = f"{name} جان، {out}"
        elif lang == "ar":
            out = f"يا {name}، {out}"
        else:
            out = f"Hey {name}, {out}"
    hint = _one_goals_lifestyle_hint(lang, user_ctx)
    if hint and out:
        out = f"{out} {hint}"
    return out[:500] if out else out


def _one_goals_lifestyle_hint(lang: str, user_ctx: Dict[str, Any]) -> str:
    """One short supportive clause from goals or lifestyle (max ~60 chars)."""
    goals = user_ctx.get("goals_items") or []
    lifestyle = (user_ctx.get("lifestyle_text") or "").strip()
    if not goals and not lifestyle:
        return ""
    if goals:
        first = str(goals[0])[:30]
        if lang == "fa":
            return f"برای هدفت ({first}) همین قدم‌های کوچک موثره."
        if lang == "ar":
            return "خطوة صغيرة تساعدك."
        return f"Small steps help your {first} goal."
    if lifestyle:
        snippet = lifestyle[:40].rstrip()
        if lang == "fa":
            return "بر اساس سبک زندگیت، همین کارهای کوچک مفیده."
        if lang == "ar":
            return "وفق نمط حياتك، خطوة صغيرة مفيدة."
        return "Small steps help."
    return ""


def _append_goals_hint(body: str, lang: str, user_ctx: Dict[str, Any], is_companion: bool) -> str:
    """Append one short goals/lifestyle hint for companion channel-based body."""
    if not is_companion or not body:
        return body
    hint = _one_goals_lifestyle_hint(lang, user_ctx)
    if not hint:
        return body
    return f"{body} {hint}"[:500]


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
