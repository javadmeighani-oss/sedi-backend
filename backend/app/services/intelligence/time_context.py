# backend.app.services.intelligence.time_context
"""R-017: the user's local part of day / weekday as a tiny system hint, so Sedi sounds like a person who knows it is
late evening or Friday morning (warmth, sleep care, gentle pacing). Pure helpers + one fail-open DB-backed builder.
No new storage: the timezone comes from the existing I8/gate4 resolver (profile -> I6 -> default)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

_DAYS = {
    "fa": ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "ar": ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"),
}
_PARTS = {
    "fa": {"night": "دل شب", "morning": "صبح", "noon": "نزدیک ظهر", "afternoon": "بعدازظهر", "evening": "عصر", "late": "شب"},
    "en": {"night": "the middle of the night", "morning": "morning", "noon": "around noon", "afternoon": "afternoon", "evening": "evening", "late": "late evening"},
    "ar": {"night": "منتصف الليل", "morning": "الصباح", "noon": "قرابة الظهر", "afternoon": "بعد الظهر", "evening": "المساء", "late": "الليل"},
}


def part_of_day(hour: int) -> str:
    if hour < 5:
        return "night"
    if hour < 11:
        return "morning"
    if hour < 14:
        return "noon"
    if hour < 17:
        return "afternoon"
    if hour < 20:
        return "evening"
    return "late"


def format_time_hint(local_now: datetime, language: str) -> str:
    lang = language if language in _DAYS else "en"
    part = _PARTS[lang][part_of_day(local_now.hour)]
    day = _DAYS[lang][local_now.weekday()]
    if lang == "fa":
        return (
            f"[زمان_محلی_کاربر] الان برای کاربر {part} است و روز {day}. اگر طبیعی بود، در لحن (نه الزاماً در متن) رعایتش کن: "
            "آخر شب آرام‌تر و با فکر به خواب، صبح انرژی‌بخش‌تر؛ هر پاسخ را با ساعت یا روز شروع نکن."
        )
    if lang == "ar":
        return (
            f"[الوقت_المحلي] الآن عند المستخدم {part} ويوم {day}. راعِ ذلك في النبرة إن كان طبيعياً: "
            "هدوء وتفكير بالنوم في آخر الليل، وحيوية في الصباح؛ ولا تبدئي كل رد بذكر الوقت."
        )
    return (
        f"[USER_LOCAL_TIME] It is {part} on a {day} for the user. If natural, let it shape your tone (not necessarily the "
        "words): calmer and sleep-minded late at night, energising in the morning; never open every reply with the time."
    )


def build_time_context(db, user_id: int, language: Optional[str], *, now_utc: Optional[datetime] = None) -> str:
    """Fail-open: '' when the timezone cannot be resolved."""
    try:
        from backend.app.services.i8.local_day import _local_now_from_utc, resolve_i8_timezone

        tz_name = resolve_i8_timezone(db, user_id)
        local_now = _local_now_from_utc(now_utc or datetime.now(timezone.utc), tz_name)
        return format_time_hint(local_now, (language or "fa").split("-")[0].lower())
    except Exception:
        return ""
