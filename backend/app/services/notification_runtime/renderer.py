# backend.app.services.notification_runtime.renderer
"""
Notification renderer (Stage 16.6.4).

Deterministic templates per channel with language-aware variants.
Returns {title, body, actions_json}. Conservative phrasing for health alerts.
Supports optional multi-language template.texts via i18n_resolver.
"""

import hashlib
from datetime import date
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
            return f"یادم نرفته دنبال «{first}» هستی؛ قدم‌های کوچیک هم حساب می‌شه."
        if lang == "ar":
            return f"لم أنسَ أنك تسعى إلى «{first}»؛ الخطوات الصغيرة تُحسب أيضاً."
        return f"I haven't forgotten you're working on {first}; small steps count too."
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
    """Calm morning greeting — no default pet-name, no decorative emoji."""
    n = (name or "").strip()
    if lang == "fa":
        return f"صبح بخیر {n}".strip()
    if lang == "ar":
        return f"صباح الخير {n}".strip()
    return f"Good morning {n}".strip() if n else "Good morning"


def _morning_cta(lang: str) -> str:
    return {
        "fa": " روز خوبی داشته باشی.",
        "ar": " أتمنى لك يوماً جميلاً.",
        "en": " Have a good day.",
    }.get(lang, " Have a good day.")


# R-011 (2026-10-20): the A4 tone contract changed to a warm, human, friend-like voice. Copy is still
# deterministic and code-owned (no free-form AI rewrite), but rotates so the same words never repeat two days
# in a row. Pairs are (title, body); "{p}" is the optional "<name> جان، " / "<name>, " prefix.
_ENGAGEMENT_PAIRS: Dict[str, tuple] = {
    "fa": (
        ("سلام از صدی", "{p}امروز چطوری؟ دلم می‌خواست یه احوالی ازت بپرسم. هر وقت حال داشتی، با هم حرف بزنیم."),
        ("یه سر زدم", "{p}فقط اومدم بگم کنارتم. اگه دلت می‌خواد، برام تعریف کن امروز چه خبر."),
        ("حالت چطوره؟", "{p}حس کردم یه مدتیه ازت خبر ندارم. همه‌چیز خوبه؟ من همین‌جام."),
        ("صدی کنارته", "{p}هر وقت دلت خواست درد و دل کنی یا فقط یکی گوش بده، من اینجام."),
    ),
    "ar": (
        ("تحية من صدی", "{p}كيف حالك اليوم؟ أحببت أن أطمئن عليك. متى ما رغبت، لنتحدث معاً."),
        ("مررتُ لأطمئن", "{p}أردت فقط أن أقول إني بجانبك. إن شئت، احكِ لي كيف كان يومك."),
        ("كيف حالك؟", "{p}شعرتُ أنني لم أسمع منك منذ فترة. هل كل شيء بخير؟ أنا هنا."),
        ("صدی بجانبك", "{p}متى أردت أن تفضفض أو تجد من يُصغي، أنا هنا."),
    ),
    "en": (
        ("Hello from Sedi", "{p}how is your day going? I wanted to check in on you. Whenever you feel like it, let's talk."),
        ("Just dropping by", "{p}I only wanted to say I'm right here with you. Tell me about your day if you like."),
        ("How are you?", "{p}it's been a little while since I heard from you. Is everything okay? I'm here."),
        ("Sedi is with you", "{p}whenever you want to talk it out, or just have someone listen, I'm here."),
    ),
}

# Used instead of the rotating pairs when the user's recent days looked low (I7 derived, consent-gated).
_ENGAGEMENT_LOW_PAIRS: Dict[str, tuple] = {
    "fa": (("فکرم پیشته", "{p}این روزها شاید کمی سخت می‌گذره. اگه دوست داری درباره‌اش حرف بزنیم، من گوش می‌دم و کنارتم."),),
    "ar": (("أفكر بك", "{p}ربما تمرّ عليك أيام ثقيلة. إن أحببت أن نتحدث عنها، أنا أُصغي وبجانبك."),),
    "en": (("Thinking of you", "{p}these days may be a bit heavy. If you'd like to talk about it, I'm listening and I'm with you."),),
}

_ENGAGEMENT_TOPIC_BODY: Dict[str, str] = {
    "fa": "{p}آخرین بار درباره‌ی {t} حرف می‌زدیم و فکرم پیشت بود. حالت چطوره؟ دوست داری ادامه بدیم؟",
    "ar": "{p}آخر مرة تحدثنا عن {t} وكنتُ أفكر بك. كيف حالك؟ هل تحب أن نكمل؟",
    "en": "{p}last time we talked about {t} and you stayed on my mind. How are you? Want to pick it up again?",
}


def _engagement_prefix(lang: str, name: Optional[str]) -> str:
    n = (name or "").strip()
    if not n:
        return ""
    if lang == "fa":
        return f"{n} جان، "
    if lang == "ar":
        return f"يا {n}، "
    return f"{n}, "


def _rotation_index(n_variants: int, name: Optional[str], salt: str) -> int:
    """Deterministic per user-name/day: a different variant than yesterday whenever there is more than one."""
    if n_variants <= 1:
        return 0
    offset = int(hashlib.sha256(f"{(name or '').strip()}:{salt}".encode("utf-8")).hexdigest()[:8], 16) % n_variants
    return (offset + date.today().toordinal()) % n_variants


def _render_engagement(lang: str, name: Optional[str], inputs: Dict[str, Any]) -> tuple:
    prefix = _engagement_prefix(lang, name)
    pairs = _ENGAGEMENT_PAIRS.get(lang, _ENGAGEMENT_PAIRS["en"])
    if inputs.get("wellbeing_trend") == "low" and not inputs.get("simple_copy"):
        pairs = _ENGAGEMENT_LOW_PAIRS.get(lang, _ENGAGEMENT_LOW_PAIRS["en"])
    # "unclear" feedback -> the plainest wording (first pair) instead of the rotating variants.
    idx = 0 if inputs.get("simple_copy") else _rotation_index(len(pairs), name, "engagement")
    title, short_body = pairs[idx]
    topic = (inputs.get("last_topic_hint") or "").strip()
    if topic and len(topic) < 60 and inputs.get("wellbeing_trend") != "low":
        body = _engagement_with_topic(lang, name, topic)
    else:
        body = short_body.format(p=prefix)
        if lang == "en" and not prefix:
            body = body[:1].upper() + body[1:]
    return title, body


def _engagement_short(lang: str, name: Optional[str]) -> str:
    """Presence re-engagement body (warm, human; rotates daily)."""
    pairs = _ENGAGEMENT_PAIRS.get(lang, _ENGAGEMENT_PAIRS["en"])
    body = pairs[_rotation_index(len(pairs), name, "engagement")][1].format(p=_engagement_prefix(lang, name))
    if lang == "en" and not _engagement_prefix(lang, name):
        body = body[:1].upper() + body[1:]
    return body


def _engagement_with_topic(lang: str, name: Optional[str], topic: str) -> str:
    """Natural continuation with a privacy-safe coarse topic only (never raw chat)."""
    tpl = _ENGAGEMENT_TOPIC_BODY.get(lang, _ENGAGEMENT_TOPIC_BODY["en"])
    body = tpl.format(p=_engagement_prefix(lang, name), t=topic[:40])
    if lang == "en" and not _engagement_prefix(lang, name):
        body = body[:1].upper() + body[1:]
    return body


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
