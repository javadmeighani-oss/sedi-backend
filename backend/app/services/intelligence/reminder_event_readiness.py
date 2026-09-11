"""I3 request-local reminder/event slot readiness (no DB, no LLM).

Bounded deterministic extraction of title/date/time from the current message.
Timezone must be supplied by I1/I2 locale resolution — never guessed.
Does not own persistence (UserEvent) or notifications (I10).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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

_RECURRENCE = re.compile(
    r"(هر\s*شب|هر\s*روز|هر\s*هفته|every\s+night|every\s+day|daily|weekly|"
    r"كل\s*ليلة|كل\s*يوم|كل\s*أسبوع)",
    re.IGNORECASE,
)

_REMINDER_OFFSET = re.compile(
    r"(?:remind\s+me\s+)?(?P<n>\d+)\s*(?:hour|hours|hr|hrs|ساعت|ساعة)s?\s*(?:before|قبل)|"
    r"(?:remind\s+me\s+)?(?P<m>\d+)\s*(?:min|mins|minute|minutes|دقیقه|دقيقة)s?\s*(?:before|قبل)|"
    r"(?:remind\s+me\s+)?(?P<d>\d+)\s*(?:day|days|روز|يوم)s?\s*(?:before|قبل)|"
    r"(?:at\s+event\s+time|وقت\s*رویداد|في\s*وقت\s*الحدث)",
    re.IGNORECASE,
)

_TIME = re.compile(
    r"(?:ساعت|at|الساعة)?\s*(?P<h>\d{1,2})(?::(?P<min>\d{2}))?(?:\s*(?P<ampm>am|pm))?",
    re.IGNORECASE,
)

_DAY_TODAY = re.compile(r"\b(today|امروز|اليوم)\b", re.IGNORECASE)
_DAY_TOMORROW = re.compile(r"\b(tomorrow|فردا|غدا|غداً)\b", re.IGNORECASE)

# Weekday tokens → Python weekday (Mon=0 … Sun=6)
_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "دوشنبه": 0,
    "سه‌شنبه": 1,
    "سه شنبه": 1,
    "چهارشنبه": 2,
    "پنجشنبه": 3,
    "پنج‌شنبه": 3,
    "جمعه": 4,
    "شنبه": 5,
    "یکشنبه": 6,
    "يكشنبه": 6,
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

_EVENT_HINTS = (
    (re.compile(r"آزمایش\s*خون|lab\s*test|تحليل\s*دم", re.I), "lab_test", "medical", "Lab test"),
    (re.compile(r"نوبت\s*دکتر|doctor\s*(?:visit|appointment)|موعد\s*(?:طبيب|الدكتور)", re.I), "doctor_visit", "medical", "Doctor visit"),
    (re.compile(r"امتحان|exam\b|اختبار", re.I), "exam", "education", "Exam"),
    (re.compile(r"جلسه|meeting|موعد\s*عمل|work\s*meeting", re.I), "work_meeting", "work", "Meeting"),
    (re.compile(r"deadline|مهلت", re.I), "deadline", "work", "Deadline"),
)


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


def _clarification(
    *,
    question_id: str,
    target_key: str,
    template_id: str,
    language: LanguageCode,
) -> ClarificationResult:
    messages = {
        "tpl.reminder.datetime.v1": {
            "en": "When is this scheduled? Please include a clear date and time.",
            "fa": "این برنامه چه زمانی است؟ لطفاً تاریخ و ساعت را مشخص بگویید.",
            "ar": "متى هذا الموعد؟ يرجى ذكر التاريخ والوقت بوضوح.",
        },
        "tpl.reminder.timezone.v1": {
            "en": "I need your timezone before I can schedule this. Please set your timezone in Profile.",
            "fa": "برای زمان‌بندی به منطقهٔ زمانی شما نیاز دارم. لطفاً آن را در پروفایل تنظیم کنید.",
            "ar": "أحتاج إلى منطقتك الزمنية قبل الجدولة. يرجى ضبطها في الملف الشخصي.",
        },
        "tpl.reminder.recurrence.v1": {
            "en": "I can schedule a single event, but not a repeating routine yet. Please give one date and time.",
            "fa": "فعلاً فقط یک رویداد تکی را می‌توانم ثبت کنم، نه برنامهٔ تکراری. یک تاریخ و ساعت بگویید.",
            "ar": "يمكنني جدولة حدث واحد فقط حالياً وليس روتيناً متكرراً. أعطني تاريخاً ووقتاً واحداً.",
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


def _outcome(req_id: str, key: str, status: FactRequirementStatus, priority: int) -> FactRequirementOutcome:
    return FactRequirementOutcome(
        requirement_id=req_id,
        canonical_key=key,
        status=status,
        priority=priority,
    )


def _parse_offsets(text: str) -> tuple[bool, tuple[int, ...]]:
    """Return (reminder_requested, offsets). Unsupported → empty offsets with requested True for fail-closed upstream."""
    lowered = text.lower()
    if not re.search(
        r"remind|یادآور|یادم\s*بنداز|تذكير|ذكرني|before|قبل",
        text,
        re.IGNORECASE,
    ):
        return False, ()

    if re.search(r"at\s+event\s+time|وقت\s*رویداد|في\s*وقت\s*الحدث", text, re.I):
        return True, (0,)

    m = _REMINDER_OFFSET.search(text)
    if not m:
        # Reminder words present but offset unclear → treat as incomplete offset (caller clarifies via datetime/title path or defaults off)
        return True, ()

    if m.groupdict().get("n"):
        hours = int(m.group("n"))
        mins = hours * 60
    elif m.groupdict().get("m"):
        mins = int(m.group("m"))
    elif m.groupdict().get("d"):
        mins = int(m.group("d")) * 1440
    else:
        return True, ()

    allowed = {0, 15, 30, 60, 1440}
    if mins not in allowed:
        return True, ()  # unsupported → fail closed (no invent)
    return True, (mins,)


def _next_weekday(local_now: datetime, weekday: int) -> datetime:
    days = (weekday - local_now.weekday()) % 7
    if days == 0:
        days = 7  # next occurrence if same weekday name without "today"
    return local_now + timedelta(days=days)


def _resolve_day(text: str, local_now: datetime) -> Optional[datetime]:
    if _DAY_TODAY.search(text):
        return local_now
    if _DAY_TOMORROW.search(text):
        return local_now + timedelta(days=1)
    lowered = text.lower()
    for token, wd in _WEEKDAYS.items():
        if token in lowered or token in text:
            # If phrase also says today, today wins (already handled).
            return _next_weekday(local_now, wd)
    return None


def _resolve_time(text: str) -> Optional[tuple[int, int]]:
    # Prefer explicit hour markers
    candidates = list(_TIME.finditer(text))
    if not candidates:
        # Persian digits ۱۰
        fa = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
        candidates = list(_TIME.finditer(fa))
    if not candidates:
        return None
    # Prefer match near ساعت/at
    chosen = candidates[-1]
    for c in candidates:
        start = max(0, c.start() - 8)
        window = text[start : c.end() + 2]
        if re.search(r"ساعت|at|الساعة", window, re.I):
            chosen = c
            break
    h = int(chosen.group("h"))
    minute = int(chosen.group("min") or 0)
    ampm = (chosen.group("ampm") or "").lower()
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    # FA/AR wall-clock without am/pm: early afternoon hours are commonly spoken
    # as 1–6 (e.g. "ساعت ۵ جلسه" → 17:00). Morning medical hours like ۱۰ stay 10.
    if not ampm and 1 <= h <= 6 and re.search(r"ساعت|الساعة", text):
        h += 12
    if h > 23 or minute > 59:
        return None
    return h, minute


def _resolve_event_meta(text: str) -> tuple[str, str, str]:
    for pat, etype, domain, title in _EVENT_HINTS:
        if pat.search(text):
            return title, domain, etype
    # Reminder-only body
    cleaned = re.sub(
        r"(remind\s+me|set\s+a?\s*reminder|یادآوری\s*کن|یادم\s*بنداز|ذكرني|تذكير)",
        "",
        text,
        flags=re.I,
    ).strip(" .،,")
    title = cleaned[:120] if cleaned else "Reminder"
    return title, "lifestyle", "other"


def parse_reminder_event_draft(
    *,
    message: str,
    timezone_name: Optional[str],
    now_utc: Optional[datetime] = None,
) -> tuple[Optional[ReminderEventDraft], Optional[str]]:
    """
    Returns (draft, missing_slot_key).
    missing_slot_key in {timezone, recurrence, datetime, title} or None when ready.
    """
    text = (message or "").strip()
    if not text:
        return None, "title"

    if _RECURRENCE.search(text):
        return None, "recurrence"

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

    day = _resolve_day(text, local_now)
    time_hm = _resolve_time(text)
    if day is None or time_hm is None:
        return None, "datetime"

    hour, minute = time_hm
    starts_local = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # Keep "today" even if time already passed — do not auto-roll to tomorrow.
    title, domain, etype = _resolve_event_meta(text)
    if not title.strip():
        return None, "title"

    rem_req, offsets = _parse_offsets(text)
    if rem_req and not offsets:
        # Explicit reminder without supported offset → fail closed to clarification
        return None, "datetime"

    return (
        ReminderEventDraft(
            title=title[:256],
            event_domain=domain,
            event_type=etype,
            starts_at_local=starts_local.replace(tzinfo=None),
            timezone_name=timezone_name,
            reminder_enabled=bool(rem_req and offsets),
            reminder_offsets=offsets if rem_req else (),
        ),
        None,
    )


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
        message=message, timezone_name=timezone_name, now_utc=now_utc
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
