"""I3 request-local reminder/event slot readiness (no DB, no LLM).

Bounded deterministic extraction of title/date/time from the current message.
Timezone must be supplied by I1/I2 locale resolution — never guessed here.
Does not own persistence (UserEvent) or notifications (I10).

R-026 (2026-10-26): the parser understands how people really ask in Persian/Arabic/English:
"فردا ساعت ۱۰ صبح یادآوری کن ...", "امشب ساعت ۹", "پس‌فردا ساعت ۱۴", "۲ ساعت دیگه", "۵ آبان ساعت ۸ صبح",
"remind me tomorrow at 10am ...". A reminder asked without an offset fires AT the stated time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.app.services.intelligence.contracts import (
    ClarificationResult,
    FactRequirementOutcome,
    FactRequirementStatus,
    IntentId,
    IntentResult,
    LanguageCode,
    ReadinessResult,
    ReadinessStatus,
    RequestKind,
)
from backend.app.utils.jalali_calendar import (
    JALALI_MONTHS_FA,
    gregorian_to_jalali,
    jalali_month_length,
    jalali_to_gregorian,
)

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

MAX_OFFSET_MINUTES = 7 * 24 * 60

_RECURRENCE = re.compile(
    r"(هر\s*شب|هر\s*روز|هر\s*هفته|every\s+night|every\s+day|daily|weekly|"
    r"کل\s*ل[يی]لة|کل\s*[يی]وم|کل\s*أسبوع|کل\s*شب|کل\s*روز|"
    r"هر\s*(?:صبح|ظهر|عصر)|every\s+(?:morning|evening|afternoon)|كل\s*صباح)",
    re.IGNORECASE,
)

_REMINDER_WORDS = re.compile(
    r"remind|notif\w*|یاد\s*آور[یی]?|یادم\s*(?:بنداز|بیار|بیاور)|خبرم\s*کن|ذ[كک]رن[يی]|تذ[كک][يی]ر|"
    # asking Sedi to SEND a notification is a reminder request too («برام یه نوتیف ارسال کنی ساعت ۹»)
    r"نوتیف(?:یکیشن)?|اعلان|[اإ]شعار|تنبیه",
    re.IGNORECASE,
)

_OFFSET = re.compile(
    r"(?P<n>\d+|نیم)\s*(?P<u>hours?|hrs?|ساعت|ساعة|mins?|minutes?|دق[يی]قه|دق[يی]قة|days?|روز|[يی]وم)\s*"
    r"(?:before|prior|قبل(?:\s*از)?|پیش(?:\s*از)?)",
    re.IGNORECASE,
)
_AT_EVENT_TIME = re.compile(
    r"at\s+(?:the\s+)?event\s+time|on\s+time|سر\s*وقت|دق[يی]قا\s*(?:سر)?\s*ساعت|وقت\s*رو[يی]داد|ف[يی]\s*وقت\s*الحدث",
    re.IGNORECASE,
)

_WORD_NUMBERS = {"یه": 1, "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "نیم": 0.5}

_RELATIVE = re.compile(
    r"(?:(?P<n>\d+|یه|یک|دو|سه|چهار|پنج|شش|نیم)\s*(?P<u>ساعت|دق[يی]قه|hours?|hrs?|minutes?|mins?)\s*(?:دیگه|دیگر|بعد|دیگر)"
    r"|in\s+(?P<n2>\d+|an?|half\s+an)\s*(?P<u2>hours?|hrs?|minutes?|mins?)"
    r"|(?P<half>نیم\s*ساعت)\s*(?:دیگه|دیگر|بعد))",
    re.IGNORECASE,
)

_DAY_AFTER_TOMORROW = re.compile(r"پس\s*فردا|day\s+after\s+tomorrow|بعد\s*غد", re.IGNORECASE)
_DAY_TOMORROW = re.compile(r"(?<![\w])(tomorrow|فردا|غدا|غداً)(?![\w])", re.IGNORECASE)
_DAY_TONIGHT = re.compile(r"(?<![\w])(tonight|امشب|هذه\s*الل[يی]لة)(?![\w])", re.IGNORECASE)
_DAY_TODAY = re.compile(r"(?<![\w])(today|امروز|ال[يی]وم)(?![\w])", re.IGNORECASE)
_IN_N_DAYS = re.compile(r"(\d{1,2})\s*(?:روز|days?)\s*(?:دیگه|دیگر|بعد|later)|in\s+(\d{1,2})\s+days?", re.IGNORECASE)
_NEXT_WEEK = re.compile(r"هفته\s*(?:ی\s*)?(?:بعد|آینده|دیگه|دیگر)|next\s+week|الأسبوع\s*القادم", re.IGNORECASE)
_NOW = re.compile(r"(?<![\w])(?:الان|همین\s*الان|همین\s*حالا|right\s+now|now|immediately|الآن|حالا)(?![\w])", re.IGNORECASE)

_JALALI_DATE = re.compile(
    r"(?<!\d)(?P<d>\d{1,2})\s*(?P<m>" + "|".join(JALALI_MONTHS_FA) + r")(?![\w])(?:\s*(?:ماه))?(?:\s*(?P<y>1[34]\d{2}))?",
)
_NUMERIC_DATE = re.compile(r"(?<!\d)(?P<y>1[34]\d{2}|20\d{2})[/-](?P<m>\d{1,2})[/-](?P<d>\d{1,2})(?!\d)")

# Weekday tokens → Python weekday (Mon=0 … Sun=6); longest token wins (e.g. "سه شنبه" before "شنبه").
_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "دوشنبه": 0,
    "سه شنبه": 1,
    "چهارشنبه": 2,
    "چهار شنبه": 2,
    "پنجشنبه": 3,
    "پنج شنبه": 3,
    "جمعه": 4,
    "شنبه": 5,
    "یکشنبه": 6,
    "یک شنبه": 6,
    "الاثنين": 0,
    "الثلاثاء": 1,
    "الاربعاء": 2,
    "الأربعاء": 2,
    "الخميس": 3,
    "الجمعة": 4,
    "السبت": 5,
    "الاحد": 6,
    "الأحد": 6,
}
_WEEKDAYS = {k.replace("ي", "ی").replace("ك", "ک"): v for k, v in _WEEKDAYS.items()}
_WEEKDAY_TOKENS = sorted(_WEEKDAYS, key=len, reverse=True)

_EVERY_N = re.compile(
    r"هر\s*\d+\s*(?:ساعت|دقیقه)|every\s+\d+\s*(?:hours?|hrs?|minutes?|mins?)|every\s+(?:hour|other)|كل\s*\d+\s*ساع",
    re.IGNORECASE,
)
_WEEKDAY_BYDAY = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
_EVERY_WEEKDAY_PREFIX = re.compile(r"(?:هر|every|each|کل)\s+$", re.IGNORECASE)
_WEEKLY = re.compile(r"هر\s*هفته|every\s+week|weekly|کل\s*أسبوع|اسبوع[يی]ا", re.IGNORECASE)


def _detect_recurrence(text: str, first_local: datetime) -> Optional[str]:
    """DEBT-044: map "هر روز/هر شب/every day/هر دوشنبه/every monday/weekly" to a bounded rule, else None."""
    lowered = text.lower()
    for token in _WEEKDAY_TOKENS:
        for m in re.finditer(r"(?<![\w])" + re.escape(token) + r"(?![\w])", lowered):
            if _EVERY_WEEKDAY_PREFIX.search(lowered[: m.start()]):
                return f"FREQ=WEEKLY;BYDAY={_WEEKDAY_BYDAY[_WEEKDAYS[token]]}"
    if _WEEKLY.search(text):
        return f"FREQ=WEEKLY;BYDAY={_WEEKDAY_BYDAY[first_local.weekday()]}"
    if _RECURRENCE.search(text):
        return "FREQ=DAILY"
    return None


_PM_WORDS = re.compile(
    r"(?<![\w])(?:عصر|بعد از ظهر|بعدازظهر|شب|امشب|مساء|مساءً|pm|evening|night|afternoon|tonight)(?![\w])",
    re.IGNORECASE,
)
_NOON_WORDS = re.compile(r"(?<![\w])(?:ظهر|noon)(?![\w])", re.IGNORECASE)
_AM_WORDS = re.compile(r"(?<![\w])(?:صبح|بامداد|صباح|am|morning)(?![\w])", re.IGNORECASE)

_TIME_AFTER_WORD = re.compile(
    r"(?:ساعت|الساعة|at|around)\s*(?P<h>\d{1,2})(?:[:٫.](?P<min>\d{2}))?"
    r"(?:\s*(?P<half>و\s*نیم))?(?:\s*و\s*(?P<min2>\d{1,2})\s*دق[يی]قه)?(?:\s*(?P<ap>am|pm))?",
    re.IGNORECASE,
)
# «تا ۲۱ و ۲۰ دقیقه» = 21:20 (hour and minutes spoken together, no «ساعت»); not «۲ ساعت و ۳۰ دقیقه دیگه».
_TIME_H_AND_MIN = re.compile(
    r"(?<![\d:])(?P<h>\d{1,2})\s*و\s*(?P<min>\d{1,2})\s*دق[يی]قه(?!\s*(?:دیگه|دیگر|بعد|قبل|پیش))",
)
_TIME_COLON = re.compile(r"(?<!\d)(?P<h>\d{1,2}):(?P<min>\d{2})(?!\d)(?:\s*(?P<ap>am|pm))?", re.IGNORECASE)
_TIME_SUFFIX = re.compile(
    r"(?<![\d/:-])(?P<h>\d{1,2})\s*(?P<ap>am|pm|صبح|ظهر|عصر|شب|بعد\s*از\s*ظهر)(?![\w])",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------------------------------------------------
# R-026 v3 (Javad 2026-10-29): understand the CONCEPT "tell me at that day / time", not a list of keywords.
# «میخوام فردا ساعت ۱۰ بهم نوتیف بدی برای صحبت در مورد شنبه» = a notification at 10 tomorrow; «شنبه» is the TOPIC.
# ---------------------------------------------------------------------------------------------------------------------
_WHEN_TOKENS = (
    _DAY_AFTER_TOMORROW,
    _DAY_TOMORROW,
    _DAY_TONIGHT,
    _DAY_TODAY,
    _IN_N_DAYS,
    _NEXT_WEEK,
    _NOW,
    _NUMERIC_DATE,
    _JALALI_DATE,
    _RELATIVE,
    _TIME_AFTER_WORD,
    _TIME_H_AND_MIN,
    _TIME_COLON,
    _TIME_SUFFIX,
)
_PAST_REFERENCE = re.compile(
    r"دیروز|پریروز|قبلاً|قبلا|\byesterday\b|\bago\b|last\s+(?:night|week)|أمس|البارحة|منذ",
    re.IGNORECASE,
)
# "give / send / ring / message / tell / wake me" in the three languages - the user wants Sedi to reach out.
_NOTIFY_CONCEPT = re.compile(
    r"(?:نوتیف(?:یکیشن)?|اعلان|پیام|پیغام|خبر|زنگ|تماس|یادآور[یی]?|[اإ]شعار|تنبیه)\s*(?:بهم\s*|برام\s*|به\s*من\s*|برای\s*من\s*)?(?:بد[هیو]?|بدید|بزن[یم]?|بفرست[یم]?|بفرستید|ارسال|کن[یم]?|بکن[یم]?)"
    r"|صدا(?:م)?\s*(?:کن|بزن)|بهم\s*(?:بگ[وی]|خبر(?:\s*بد[هی])?|زنگ(?:\s*بزن[یم]?)?|سر\s*بزن[یم]?|پیام(?:\s*بد[هیو]?)?|اطلاع(?:\s*بد[هی])?)|خبرم\s*کن|اطلاع(?:م)?\s*بد[هی]"
    r"|متوجهم\s*کن|بیدارم\s*کن|حالم\s*رو\s*بپرس|یادم\s*(?:بنداز|باشه|بده)|به\s*یادم\s*بیار"
    r"|\b(?:ping|text|message|notify|alert|nudge|wake|call|tell|buzz|ring)\s+me\b"
    r"|\b(?:send|give)\s+me\s+(?:a\s+)?(?:message|note|alert|notification|notice|reminder|ping)\b"
    r"|let\s+me\s+know|check\s+in\s+with\s+me|talk\s+to\s+me"
    r"|(?:أرسل|ارسل|ابعث|أرسل[يی]|ارسل[يی]|ابعث[يی])\s+ل[يی]|نب[ّ]?هن[يی]|ذ[كک]رن[يی]|أخبرن[يی]|اخبرن[يی]|أعلمن[يی]|أشعرن[يی]"
    r"|[كک]لمن[يی]|اتصل\s+ب[يی]|إشعار|اشعار",
    re.IGNORECASE,
)
_TOPIC_MARKERS = {
    "fa": re.compile(r"(?:درباره\s*(?:ی|ء)?|در\s*مورد|راجع\s*به|راجب|پیرامون)\s+(?P<t>.+?)\s*$"),
    "en": re.compile(r"(?:about|regarding|concerning)\s+(?P<t>.+?)\s*$", re.IGNORECASE),
    "ar": re.compile(r"(?:عن|حول|بخصوص|بشأن)\s+(?P<t>.+?)\s*$"),
}
_TALK_WORDS = {
    "fa": re.compile(r"صحبت|حرف|گفتگو|گپ|چت"),
    "en": re.compile(r"\b(?:talk|chat|speak|discuss|conversation)\b", re.IGNORECASE),
    "ar": re.compile(r"الحديث|التحدث|نتحدث|نتكلم|الكلام|محادثة"),
}
_SCHEDULED_WEEKDAY = re.compile(
    r"(?:(?<![\w])(?:on|next|this|every|each|هر|روز|این|يوم|ي[وو]م|كل)\s+)(?:"
    + "|".join(re.escape(tok) for tok in _WEEKDAY_TOKENS)
    + r")(?![\w])",
    re.IGNORECASE,
)
_TALK_TAIL = {
    "fa": re.compile(r"\s*(?:حرف\s*بزن\w*|صحبت\s*کن\w*|صحبت\s*کنیم|بحث\s*کن\w*|گپ\s*بزن\w*|گفتگو\s*کن\w*)\s*$"),
    "en": re.compile(r"\s*(?:to\s+)?(?:talk|chat|speak|discuss)(?:\s+about\s+it)?\s*$", re.IGNORECASE),
    "ar": re.compile(r"\s*(?:نتحدث|نتكلم|نناقش)\s*$"),
}
_TALK_TITLE = {"fa": "صحبت درباره‌ی {t}", "en": "talk about {t}", "ar": "الحديث عن {t}"}


def _split_topic(text: str, lang: str) -> tuple[Optional[str], str]:
    """«… برای صحبت در مورد شنبه» -> («صحبت درباره‌ی شنبه», «… »): the topic phrase is NOT a date or time."""
    marker = _TOPIC_MARKERS.get(lang)
    if marker is None:
        return None, text
    m = marker.search(text)
    if m is None:
        return None, text
    topic = m.group("t")
    cut = len(topic)
    # the topic ends where a date, a time, «on Saturday» / «every Monday» or «بهم خبر بده» begins
    for rx in _WHEN_TOKENS + (_NOTIFY_CONCEPT, _RECURRENCE, _SCHEDULED_WEEKDAY):
        hit = rx.search(topic)
        if hit is not None:
            cut = min(cut, hit.start())
    after = topic[cut:]
    topic = re.sub(r"[.,،؛:!?؟\-_/()\"'«»]+", " ", topic[:cut])
    topic = re.sub(r"\s+", " ", topic).strip()
    if len(topic) < 2:
        return None, text
    tail = _TALK_TAIL[lang].search(topic)
    if tail is not None:
        topic = topic[: tail.start()].strip()
    lead = text[: m.start()]
    talks = tail is not None or _TALK_WORDS[lang].search(lead) is not None
    if not talks or len(topic) < 2:
        return None, text  # «remind me about my meeting on Saturday»: the words stay in the scheduling text
    return _TALK_TITLE[lang].format(t=topic)[:120], f"{lead} {after}".strip()


def looks_like_notify_request(message: str, language: str) -> bool:
    """True when the user asks Sedi to reach out at a stated time/day - whatever words they use for it."""
    text = _normalize(message or "")
    if not text or _PAST_REFERENCE.search(text):
        return False
    lang = language if language in ("fa", "ar", "en") else _guess_language(text, None)
    _topic, rest = _split_topic(text, lang)
    if not _NOTIFY_CONCEPT.search(text):
        return False
    return any(rx.search(rest) for rx in _WHEN_TOKENS)


_EVENT_HINTS = (
    (re.compile(r"آزمایش\s*خون|lab\s*test|تحل[يی]ل\s*دم|آزمایش", re.I), "lab_test", "medical"),
    (re.compile(r"نوبت\s*(?:دکتر|پزشک|دندانپزشک|دندان\s*پزشک)|doctor\s*(?:visit|appointment)|موعد\s*(?:ال)?(?:طب[يی]ب|د[كک]تور)|دکتر|پزشک", re.I), "doctor_visit", "medical"),
    (re.compile(r"امتحان|exam\b|اختبار", re.I), "exam", "education"),
    (re.compile(r"جلسه|meeting|موعد\s*عمل|work\s*meeting", re.I), "work_meeting", "work"),
    (re.compile(r"deadline|مهلت", re.I), "deadline", "work"),
)

_TITLE_DEFAULTS = {
    "lab_test": {"fa": "آزمایش خون", "ar": "تحليل الدم", "en": "Lab test"},
    "doctor_visit": {"fa": "نوبت دکتر", "ar": "موعد الطبيب", "en": "Doctor visit"},
    "exam": {"fa": "امتحان", "ar": "اختبار", "en": "Exam"},
    "work_meeting": {"fa": "جلسه", "ar": "اجتماع", "en": "Meeting"},
    "deadline": {"fa": "مهلت کار", "ar": "موعد التسليم", "en": "Deadline"},
    "other": {"fa": "یادآوری", "ar": "تذكير", "en": "Reminder"},
}


@dataclass(frozen=True)
class ReminderEventDraft:
    title: str
    event_domain: str
    event_type: str
    starts_at_local: datetime
    timezone_name: str
    reminder_enabled: bool
    reminder_offsets: tuple[int, ...]
    importance: str = "normal"
    # R-026: how the time was said (used for the confirmation sentence).
    relative: bool = False
    offsets_defaulted: bool = False
    # DEBT-044: "FREQ=DAILY" or "FREQ=WEEKLY;BYDAY=MO" when asked "every day/week ... remind me".
    recurrence_rule: Optional[str] = None


def _clarification(
    *,
    question_id: str,
    target_key: str,
    template_id: str,
    language: LanguageCode,
) -> ClarificationResult:
    messages = {
        "tpl.reminder.datetime.v1": {
            "en": "When should I remind you? Please tell me the date and time, like “tomorrow at 10 am”.",
            "fa": "کِی یادت بندازم؟ روز و ساعتش رو بگو، مثلاً «فردا ساعت ۱۰ صبح».",
            "ar": "متى أذكّرك؟ أخبرني باليوم والساعة، مثل «غداً الساعة 10 صباحاً».",
        },
        "tpl.reminder.past.v1": {
            "en": "That time has already passed today. Which other time or day should I use?",
            "fa": "این ساعت امروز گذشته. چه ساعت یا روز دیگه‌ای بذارم؟",
            "ar": "هذا الوقت مضى اليوم. أي وقت أو يوم آخر أضع؟",
        },
        "tpl.reminder.timezone.v1": {
            "en": "I need your timezone before I can schedule this. Please set your timezone in Profile.",
            "fa": "برای زمان‌بندی به منطقهٔ زمانی شما نیاز دارم. لطفاً آن را در پروفایل تنظیم کنید.",
            "ar": "أحتاج إلى منطقتك الزمنية قبل الجدولة. يرجى ضبطها في الملف الشخصي.",
        },
        "tpl.reminder.recurrence.v1": {
            "en": "I can repeat a reminder every day or every week, like “every day at 8 remind me to drink water”. Which one would you like?",
            "fa": "می‌تونم یادآور رو هر روز یا هر هفته تکرار کنم، مثلاً «هر روز ساعت ۸ یادم بنداز آب بخورم». کدومشو بذارم؟",
            "ar": "يمكنني تكرار التذكير كل يوم أو كل أسبوع، مثل «كل يوم الساعة 8 ذكّرني بشرب الماء». أيهما تريد؟",
        },
        "tpl.reminder.title.v1": {
            "en": "What should I put on your schedule?",
            "fa": "چه چیزی را در برنامهٔ شما ثبت کنم؟",
            "ar": "ماذا أضع في جدولك؟",
        },
    }
    block = messages.get(template_id, messages["tpl.reminder.datetime.v1"])
    return ClarificationResult(
        question_id=question_id,
        target_key=target_key,
        template_id=template_id,
        localized_message=block.get(language) or block["en"],
    )


# D-130: the first words of Sedi's own "when should I remind you?" questions (datetime / past / title), fa + ar + en.
_CLARIFICATION_OPENINGS = (
    "When should I remind you?",
    "That time has already passed today.",
    "What should I put on your schedule?",
    "کِی یادت بندازم؟",
    "این ساعت امروز گذشته.",
    "چه چیزی را در برنامهٔ شما ثبت کنم؟",
    "متى أذكّرك؟",
    "هذا الوقت مضى اليوم.",
    "ماذا أضع في جدولك؟",
)

_ANSWER_PREFIX = {"fa": "یادم بنداز ", "ar": "ذكرني ", "en": "remind me "}


_DIACRITICS = re.compile(r"[\u064b-\u065f\u0670\u200c\u200e\u200f]")


def _plain(text: str) -> str:
    """Letters only: no Arabic diacritics (کِی = کی), no ZWNJ/direction marks, one Yeh/Kaf, collapsed spaces."""
    t = _DIACRITICS.sub("", text or "").replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", t).strip()


def is_reminder_clarification(sedi_text: Optional[str]) -> bool:
    """True when [sedi_text] is one of Sedi's own reminder questions (so the user's next message is the answer)."""
    t = _plain(sedi_text or "")
    return any(_plain(op) in t for op in _CLARIFICATION_OPENINGS)


def answer_as_reminder_request(answer: str, language: str) -> str:
    """The user's short answer («حدود ۵ دقیقه دیگه») phrased as a full reminder request the parser understands."""
    return _ANSWER_PREFIX.get(language if language in _ANSWER_PREFIX else "en", "remind me ") + (answer or "").strip()


def _outcome(req_id: str, key: str, status: FactRequirementStatus, priority: int) -> FactRequirementOutcome:
    return FactRequirementOutcome(
        requirement_id=req_id,
        canonical_key=key,
        status=status,
        priority=priority,
    )


def _normalize(text: str) -> str:
    t = (text or "").translate(_DIGITS)
    t = t.replace("‌", " ").replace("ي", "ی").replace("ك", "ک").replace("ـ", "")
    return re.sub(r"\s+", " ", t).strip()


def _parse_offsets(text: str) -> tuple[bool, tuple[int, ...], bool]:
    """Return (reminder_requested, offsets, defaulted).

    R-026: a reminder asked without an offset fires AT the stated time (offset 0).
    An explicit offset ("1 hour before", "نیم ساعت قبل") is honoured for any value up to 7 days.
    """
    t = _normalize(text)
    requested = bool(
        _REMINDER_WORDS.search(t) or _NOTIFY_CONCEPT.search(t) or _OFFSET.search(t) or _AT_EVENT_TIME.search(t)
    )
    if not requested:
        return False, (), False
    if _AT_EVENT_TIME.search(t):
        return True, (0,), False
    m = _OFFSET.search(t)
    if not m:
        return True, (0,), True
    raw = m.group("n")
    n = 0.5 if raw == "نیم" else float(raw)
    unit = (m.group("u") or "").lower()
    if unit.startswith(("hour", "hr", "ساعت", "ساعة")):
        mins = int(n * 60)
    elif unit.startswith(("min", "دقیقه", "دقيقة")):
        mins = int(n)
    else:
        mins = int(n * 1440)
    if mins < 0 or mins > MAX_OFFSET_MINUTES:
        return True, (0,), True
    return True, (mins,), False


def _next_weekday(local_now: datetime, weekday: int) -> datetime:
    days = (weekday - local_now.weekday()) % 7
    if days == 0:
        days = 7  # next occurrence if same weekday name without "today"
    return local_now + timedelta(days=days)


def _jalali_year_and_today(local_now: datetime) -> tuple[int, int, int]:
    return gregorian_to_jalali(local_now.year, local_now.month, local_now.day)


def _resolve_date(text: str, local_now: datetime) -> Optional[datetime]:
    """Day-level resolution (time of day is applied by the caller)."""
    if _DAY_AFTER_TOMORROW.search(text):
        return local_now + timedelta(days=2)
    if _DAY_TOMORROW.search(text):
        return local_now + timedelta(days=1)
    if _DAY_TONIGHT.search(text) or _DAY_TODAY.search(text):
        return local_now
    m = _IN_N_DAYS.search(text)
    if m:
        n = int(m.group(1) or m.group(2))
        if 0 < n <= 90:
            return local_now + timedelta(days=n)
    m = _NUMERIC_DATE.search(text)
    if m:
        y, mo, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
        try:
            if y < 1700:  # Jalali year
                if not (1 <= mo <= 12 and 1 <= d <= jalali_month_length(y, mo)):
                    return None
                gy, gm, gd = jalali_to_gregorian(y, mo, d)
            else:
                gy, gm, gd = y, mo, d
            return local_now.replace(year=gy, month=gm, day=gd)
        except ValueError:
            return None
    m = _JALALI_DATE.search(text)
    if m:
        d = int(m.group("d"))
        mo = JALALI_MONTHS_FA.index(m.group("m")) + 1
        jy_now, jm_now, jd_now = _jalali_year_and_today(local_now)
        y = int(m.group("y")) if m.group("y") else jy_now
        if not (1 <= d <= jalali_month_length(y, mo)):
            return None
        if not m.group("y") and (mo, d) < (jm_now, jd_now):
            y += 1  # no year said and the date already passed this year -> next year
            if d > jalali_month_length(y, mo):
                return None
        gy, gm, gd = jalali_to_gregorian(y, mo, d)
        return local_now.replace(year=gy, month=gm, day=gd)
    lowered = text.lower()
    for token in _WEEKDAY_TOKENS:
        if re.search(r"(?<![\w])" + re.escape(token) + r"(?![\w])", lowered):
            target = _next_weekday(local_now, _WEEKDAYS[token])
            return target + timedelta(days=7) if _NEXT_WEEK.search(text) else target
    return None


def _apply_period(h: int, minute: int, text: str, explicit_ap: str) -> Optional[tuple[int, int, int]]:
    """Return (hour24, minute, day_shift) or None when invalid."""
    ap = (explicit_ap or "").lower()
    day_shift = 0
    pm = ap == "pm" or bool(_PM_WORDS.search(ap)) if ap else False
    noon = bool(_NOON_WORDS.search(ap)) if ap else False
    am = ap == "am" or bool(_AM_WORDS.search(ap)) if ap else False
    if not ap:
        # Period word elsewhere in the sentence ("ساعت ۸ شب", "10 صبح").
        if _PM_WORDS.search(text):
            pm = True
        elif _NOON_WORDS.search(text):
            noon = True
        elif _AM_WORDS.search(text):
            am = True
    if pm:
        if h == 12 and re.search(r"شب|night|مساء", ap or text):
            h, day_shift = 0, 1  # "۱۲ شب" = midnight starting the next day
        elif 1 <= h <= 11:
            if re.search(r"شب|night|مساء", ap or text) and h <= 5:
                pass  # "ساعت ۲ شب" is after midnight, spoken as night
            else:
                h += 12
    elif noon:
        if 1 <= h <= 4:
            h += 12
    elif am:
        if h == 12:
            h = 0
    elif 1 <= h <= 6 and re.search(r"ساعت|الساعة", text):
        # FA/AR wall-clock without a period word: early hours are afternoon ("ساعت ۵ جلسه" → 17:00).
        h += 12
    if h > 23 or minute > 59:
        return None
    return h, minute, day_shift


def _resolve_time(text: str) -> Optional[tuple[int, int, int]]:
    m = _TIME_AFTER_WORD.search(text)
    if m:
        minute = int(m.group("min") or m.group("min2") or (30 if m.group("half") else 0))
        return _apply_period(int(m.group("h")), minute, text, m.group("ap") or "")
    m = _TIME_H_AND_MIN.search(text)
    if m:
        return _apply_period(int(m.group("h")), int(m.group("min")), text, "")
    m = _TIME_COLON.search(text)
    if m:
        return _apply_period(int(m.group("h")), int(m.group("min")), text, m.group("ap") or "")
    m = _TIME_SUFFIX.search(text)
    if m:
        return _apply_period(int(m.group("h")), 0, text, m.group("ap") or "")
    return None


def _resolve_relative(text: str, local_now: datetime) -> Optional[datetime]:
    m = _RELATIVE.search(text)
    if not m:
        return None
    if m.group("half"):
        return local_now + timedelta(minutes=30)
    raw = m.group("n") or m.group("n2") or ""
    unit = (m.group("u") or m.group("u2") or "").lower()
    if raw in ("a", "an"):
        n = 1.0
    elif raw.startswith("half"):
        n = 0.5
    elif raw.isdigit():
        n = float(raw)
    else:
        n = float(_WORD_NUMBERS.get(raw, 0))
    if n <= 0:
        return None
    mins = n * 60 if unit.startswith(("ساعت", "hour", "hr")) else n
    if mins <= 0 or mins > 24 * 60:
        return None
    return local_now + timedelta(minutes=mins)


def _guess_language(text: str, language: Optional[str]) -> str:
    if language in ("fa", "ar", "en"):
        return language
    if re.search(r"[پچژگیک]", text):  # Persian-only letters (U+06CC ی, U+06A9 ک, پ چ ژ گ)
        return "fa"
    if re.search(r"[؀-ۿ]", text):
        return "ar"
    return "en"


def _resolve_event_meta(text: str, lang: str) -> tuple[str, str, str]:
    etype, domain = "other", "lifestyle"
    for pat, t, d in _EVENT_HINTS:
        if pat.search(text):
            etype, domain = t, d
            break
    cleaned = _clean_title(text)
    if cleaned:
        return cleaned[:120], domain, etype
    return _TITLE_DEFAULTS.get(etype, _TITLE_DEFAULTS["other"])[lang], domain, etype


_TITLE_NOISE = (
    _RECURRENCE,
    _NOTIFY_CONCEPT,
    _REMINDER_WORDS,
    _OFFSET,
    _AT_EVENT_TIME,
    _RELATIVE,
    _DAY_AFTER_TOMORROW,
    _DAY_TOMORROW,
    _DAY_TONIGHT,
    _DAY_TODAY,
    _IN_N_DAYS,
    _NEXT_WEEK,
    _NOW,
    _NUMERIC_DATE,
    _JALALI_DATE,
    _TIME_AFTER_WORD,
    _TIME_H_AND_MIN,
    _TIME_COLON,
    _TIME_SUFFIX,
)
_FILLER = re.compile(
    r"(?<![\w])(?:لطفا|لطفاً|please|کن|کنی|کنید|بکن|بده|بهم|به من|برام|برای من|برایم|بگو|که|تا|برای|را|رو|"
    r"that|me|set|reminder|دارم|دارید|هست|ساعت|صبح|ظهر|عصر|شب|am|pm|before|prior|"
    r"هر|every|each|نوتیف|نوتیفیکیشن|اعلان|بفرست|ارسال|یه|یک|میخوام|میخواهم|کنم|حدود|تقریبا|تقریباً|about|around|صباحا|صباحاً|مساء|مساءً|ظهرا)(?![\w])",
    re.IGNORECASE,
)


def _clean_title(text: str) -> str:
    t = _normalize(text)
    for rx in _TITLE_NOISE:
        t = rx.sub(" ", t)
    for token in _WEEKDAY_TOKENS:
        t = re.sub(r"(?<![\w])" + re.escape(token) + r"(?![\w])", " ", t, flags=re.IGNORECASE)
    t = _FILLER.sub(" ", t)
    t = re.sub(r"[\d]+", " ", t)
    t = re.sub(r"^\s*to\s+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[.,،؛:!?؟\-_/()\"'«»]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def parse_reminder_event_draft(
    *,
    message: str,
    timezone_name: Optional[str],
    now_utc: Optional[datetime] = None,
    language: Optional[str] = None,
) -> tuple[Optional[ReminderEventDraft], Optional[str]]:
    """
    Returns (draft, missing_slot_key).
    missing_slot_key in {timezone, recurrence, datetime, past, title} or None when ready.
    """
    raw = (message or "").strip()
    if not raw:
        return None, "title"
    text = _normalize(raw)
    lang = _guess_language(raw, language)
    topic_title, text = _split_topic(text, lang)  # the topic («شنبه» in «درباره‌ی شنبه») is never a date

    if _EVERY_N.search(text):
        return None, "recurrence"  # sub-daily repetition is not supported
    recurring = _detect_recurrence(text, datetime.now()) is not None
    if recurring and not _REMINDER_WORDS.search(text):
        return None, "recurrence"  # a habit statement ("هر شب ساعت ۱۱ می‌خوابم") is not a reminder request

    if not timezone_name or not str(timezone_name).strip():
        return None, "timezone"

    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return None, "timezone"

    effective = now_utc or datetime.now(timezone.utc)
    if effective.tzinfo is None:
        effective = effective.replace(tzinfo=timezone.utc)
    local_now = effective.astimezone(tz)

    if recurring and (_resolve_relative(text, local_now) is not None or _NOW.search(text)):
        return None, "recurrence"  # "every 2 hours" is not a supported pattern

    relative_dt = None if recurring else _resolve_relative(text, local_now)
    if not recurring and relative_dt is None and _NOW.search(text) and _resolve_time(text) is None and _resolve_date(text, local_now) is None:
        relative_dt = local_now + timedelta(minutes=2)  # "send it now": the next scheduler tick
    relative = relative_dt is not None
    recurrence_rule: Optional[str] = None
    if recurring:
        time_hm = _resolve_time(text)
        if time_hm is None:
            return None, "datetime"
        hour, minute, day_shift = time_hm
        no_weekday = text.lower()
        for token in _WEEKDAY_TOKENS:
            no_weekday = re.sub(r"(?<![\w])" + re.escape(token) + r"(?![\w])", " ", no_weekday)
        day = _resolve_date(no_weekday, local_now) or local_now
        starts_local = day.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=day_shift)
        recurrence_rule = _detect_recurrence(text, starts_local)
        if recurrence_rule and recurrence_rule.startswith("FREQ=WEEKLY;BYDAY="):
            target = _WEEKDAY_BYDAY.index(recurrence_rule.rsplit("=", 1)[1])
            starts_local += timedelta(days=(target - starts_local.weekday()) % 7)
        if starts_local <= local_now:
            starts_local += timedelta(days=7 if (recurrence_rule or "").startswith("FREQ=WEEKLY") else 1)
    elif relative_dt is not None:
        starts_local = relative_dt.replace(second=0, microsecond=0)
    else:
        day = _resolve_date(text, local_now)
        time_hm = _resolve_time(text)
        implicit_day = day is None and time_hm is not None and bool(_REMINDER_WORDS.search(text) or _NOTIFY_CONCEPT.search(text))
        if implicit_day:
            day = local_now  # «تا ۲۱:۲۰ یادم بنداز»: no day said -> the next time that clock shows
        if day is None or time_hm is None:
            return None, "datetime"
        hour, minute, day_shift = time_hm
        starts_local = day.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=day_shift)
        if starts_local <= local_now:
            if not implicit_day:
                return None, "past"
            starts_local += timedelta(days=1)

    title, domain, etype = _resolve_event_meta(text, lang)
    if topic_title:
        title = topic_title
    if not title.strip():
        return None, "title"

    rem_req, offsets, defaulted = _parse_offsets(text)
    if not rem_req:
        # A stated appointment/plan without reminder words: Sedi still reminds, one hour ahead by default.
        offsets, defaulted = (60,), True
    if relative:
        offsets = (0,)

    return (
        ReminderEventDraft(
            title=title[:256],
            event_domain=domain,
            event_type=etype,
            starts_at_local=starts_local.replace(tzinfo=None),
            timezone_name=timezone_name,
            reminder_enabled=True,
            reminder_offsets=offsets,
            relative=relative,
            offsets_defaulted=defaulted,
            recurrence_rule=recurrence_rule,
        ),
        None,
    )


_WEEKDAY_NAME_FA = ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه")
_WEEKDAY_NAME_AR = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")


def _two(n: int) -> str:
    return f"{n:02d}"


def describe_when(draft: ReminderEventDraft, lang: str, now_utc: Optional[datetime] = None) -> str:
    """Natural phrase for the confirmation: «فردا ساعت ۱۰:۰۰» / "tomorrow at 10:00" (user's own timezone)."""
    try:
        tz = ZoneInfo(draft.timezone_name)
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    effective = now_utc or datetime.now(timezone.utc)
    if effective.tzinfo is None:
        effective = effective.replace(tzinfo=timezone.utc)
    today = effective.astimezone(tz).date()
    d: date = draft.starts_at_local.date()
    hhmm = f"{_two(draft.starts_at_local.hour)}:{_two(draft.starts_at_local.minute)}"
    delta = (d - today).days
    rule = draft.recurrence_rule or ""
    if rule:
        if lang == "fa":
            digits = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
            day_txt = "هر هفته " + _WEEKDAY_NAME_FA[d.weekday()] if rule.startswith("FREQ=WEEKLY") else "هر روز"
            return f"{day_txt} ساعت {hhmm}".translate(digits)
        if lang == "ar":
            day_txt = "كل أسبوع " + _WEEKDAY_NAME_AR[d.weekday()] if rule.startswith("FREQ=WEEKLY") else "كل يوم"
            return f"{day_txt} الساعة {hhmm}"
        day_txt = f"every {d.strftime('%A')}" if rule.startswith("FREQ=WEEKLY") else "every day"
        return f"{day_txt} at {hhmm}"
    if lang == "fa":
        digits = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        if delta == 0:
            day_txt = "امروز"
        elif delta == 1:
            day_txt = "فردا"
        elif delta == 2:
            day_txt = "پس‌فردا"
        else:
            jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
            day_txt = f"{jd} {JALALI_MONTHS_FA[jm - 1]}"
        return f"{day_txt} ساعت {hhmm}".translate(digits)
    if lang == "ar":
        if delta == 0:
            day_txt = "اليوم"
        elif delta == 1:
            day_txt = "غداً"
        elif delta == 2:
            day_txt = "بعد غد"
        else:
            day_txt = d.strftime("%Y-%m-%d")
        return f"{day_txt} الساعة {hhmm}"
    if delta == 0:
        day_txt = "today"
    elif delta == 1:
        day_txt = "tomorrow"
    else:
        day_txt = d.strftime("%b %d")
    return f"{day_txt} at {hhmm}"


def evaluate_reminder_event_readiness(
    *,
    message: str,
    language: LanguageCode,
    intent: IntentResult,
    timezone_name: Optional[str],
    now_utc: Optional[datetime] = None,
) -> ReadinessResult:
    """I3 readiness for REMINDER/ACTION using request-local slots only."""
    draft, missing = parse_reminder_event_draft(
        message=message, timezone_name=timezone_name, now_utc=now_utc, language=str(getattr(language, "value", language))
    )
    if missing is None and draft is not None:
        return ReadinessResult(
            status=ReadinessStatus.READY,
            intent_id=intent.intent_id,
            request_kind=intent.request_kind,
            outcomes=(
                _outcome("rem.datetime", "request.local.datetime", FactRequirementStatus.PRESENT, 10),
                _outcome("rem.timezone", "profile.timezone", FactRequirementStatus.PRESENT, 20),
                _outcome("rem.title", "request.local.title", FactRequirementStatus.PRESENT, 30),
            ),
            missing_fact_keys=(),
            clarification=None,
        )

    key_map = {
        "timezone": ("rem.timezone", "profile.timezone", "tpl.reminder.timezone.v1", 20),
        "recurrence": ("rem.recurrence", "request.local.recurrence", "tpl.reminder.recurrence.v1", 5),
        "datetime": ("rem.datetime", "request.local.datetime", "tpl.reminder.datetime.v1", 10),
        "past": ("rem.datetime", "request.local.datetime", "tpl.reminder.past.v1", 10),
        "title": ("rem.title", "request.local.title", "tpl.reminder.title.v1", 30),
    }
    req_id, ckey, tpl, prio = key_map.get(
        missing or "datetime", key_map["datetime"]
    )
    outcome = _outcome(req_id, ckey, FactRequirementStatus.MISSING, prio)
    return ReadinessResult(
        status=ReadinessStatus.NEEDS_CLARIFICATION,
        intent_id=intent.intent_id,
        request_kind=intent.request_kind or RequestKind.ACTION,
        outcomes=(outcome,),
        missing_fact_keys=(ckey,),
        clarification=_clarification(
            question_id=f"i3.q.{req_id}.v1",
            target_key=ckey,
            template_id=tpl,
            language=language,
        ),
    )


def is_reminder_intent(intent: Optional[IntentResult]) -> bool:
    return intent is not None and intent.intent_id is IntentId.REMINDER
