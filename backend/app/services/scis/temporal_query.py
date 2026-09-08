"""Phase2-A CASE_05 — deterministic temporal query-intent parser (fa/en/ar).

No LLM. No invented dates. Relative forms require explicit reference_time + timezone.
Temporal parsing never grants access to personal historical health data.
PERSONAL != GOVERNED.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.app.services.scis.normalize import normalize_for_language

TEMPORAL_KIND_NONE = "none"
TEMPORAL_KIND_TODAY = "today"
TEMPORAL_KIND_YESTERDAY = "yesterday"
TEMPORAL_KIND_LAST_WEEK = "last_week"
TEMPORAL_KIND_SINCE = "since"
TEMPORAL_KIND_BEFORE = "before"
TEMPORAL_KIND_AFTER = "after"
TEMPORAL_KIND_AMBIGUOUS = "ambiguous"

STATE_NONE = "NONE"
STATE_RESOLVED = "RESOLVED"
STATE_AMBIGUOUS = "AMBIGUOUS"

_DATE_RE = re.compile(
    r"(?P<y>\d{4})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})"
    r"|(?P<d2>\d{1,2})[-/](?P<m2>\d{1,2})[-/](?P<y2>\d{4})"
)

# Bounded surface forms (no synonym inference beyond listed literals).
_TODAY = {
    "en": ("today", "this day"),
    "fa": ("امروز", "امروز"),
    "ar": ("اليوم", "هذا اليوم"),
}
_YESTERDAY = {
    "en": ("yesterday",),
    "fa": ("دیروز", "ديروز"),
    "ar": ("امس", "الامس", "أمس"),
}
_LAST_WEEK = {
    "en": ("last week", "past week"),
    "fa": ("هفته گذشته", "هفته قبل"),
    "ar": ("الاسبوع الماضي", "الأسبوع الماضي", "اسبوع الماضي"),
}
_SINCE = {
    "en": ("since",),
    "fa": ("از تاریخ",),
    "ar": ("منذ", "من تاريخ"),
}
_BEFORE = {
    "en": ("before", "prior to"),
    "fa": ("قبل از", "پیش از"),
    "ar": ("قبل من", "قبل تاريخ"),
}
_AFTER = {
    "en": ("after", "following"),
    "fa": ("بعد از", "پس از"),
    "ar": ("بعد من", "بعد تاريخ"),
}
# Short FA particle "از" only when immediately followed by an explicit date.
_FA_SINCE_DATE_RE = re.compile(
    r"از\s+(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})"
)

# Personal-history markers — routing only; never invent personal vitals.
_PERSONAL_POSSESSIVE = {
    "en": ("my ", " my", "i had", "i measured"),
    "fa": ("فشار خونم", "ضربانم", "من دیروز", "سلامتی من", "نتیجه من"),
    "ar": ("ضغط دمي", "نبضي", "صحتي", "نتيجتي"),
}
_HEALTH_METRIC = {
    "en": (
        "blood pressure",
        "heart rate",
        "glucose",
        "weight",
        "vital",
        "lab result",
        "medication",
    ),
    "fa": ("فشار خون", "ضربان", "قند", "وزن", "علائم حیاتی", "نتیجه آزمایش", "دارو"),
    "ar": ("ضغط الدم", "نبض", "سكر", "وزن", "علامات حيوية", "نتيجة", "دواء"),
}


@dataclass(frozen=True)
class TemporalQueryIntent:
    kind: str
    start: Optional[date]
    end: Optional[date]
    timezone: Optional[str]
    source_expression: Optional[str]
    deterministic_state: str
    clarification_required: bool
    personal_history_intent: bool
    authority_note: str = "TEMPORAL_PARSE_ONLY_NOT_PERSONAL_DATA_ACCESS"

    def to_audit_dict(self) -> dict:
        return {
            "kind": self.kind,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "timezone": self.timezone,
            "source_expression": self.source_expression,
            "deterministic_state": self.deterministic_state,
            "clarification_required": self.clarification_required,
            "personal_history_intent": self.personal_history_intent,
            "authority_note": self.authority_note,
            "TEMPORAL_RESOLUTION": self.deterministic_state,
            "CLARIFICATION_REQUIRED": self.clarification_required,
        }


def _lang_root(language: Optional[str]) -> str:
    lang = (language or "en").strip().lower()
    if lang.startswith("fa") or lang in {"persian", "farsi"}:
        return "fa"
    if lang.startswith("ar") or lang in {"arabic"}:
        return "ar"
    return "en"


def _contains_any(hay: str, needles: tuple[str, ...]) -> Optional[str]:
    for n in needles:
        if n and n in hay:
            return n
    return None


def _parse_explicit_date(text: str) -> Optional[date]:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    try:
        if m.group("y"):
            return date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
        return date(int(m.group("y2")), int(m.group("m2")), int(m.group("d2")))
    except ValueError:
        return None


def _resolve_tz(tz_name: Optional[str]) -> Optional[ZoneInfo]:
    if not tz_name or not str(tz_name).strip():
        return None
    try:
        return ZoneInfo(str(tz_name).strip())
    except ZoneInfoNotFoundError:
        return None


def detect_personal_history_intent(query: str, *, language: Optional[str] = "en") -> bool:
    """True when query asks for the user's own historical health values."""
    root = _lang_root(language)
    norm = normalize_for_language(query or "", language)
    lower = (query or "").casefold()
    hay = f"{norm} {lower}"
    has_personal = _contains_any(hay, _PERSONAL_POSSESSIVE[root]) is not None
    if root == "en":
        has_personal = has_personal or bool(re.search(r"\bmy\b", hay))
    has_metric = _contains_any(hay, _HEALTH_METRIC[root]) is not None
    return bool(has_personal and has_metric)


def parse_temporal_query_intent(
    query: str,
    *,
    language: Optional[str] = "en",
    reference_time: Optional[datetime] = None,
    timezone_name: Optional[str] = None,
) -> TemporalQueryIntent:
    """Parse bounded temporal intent. Never invent dates.

    Relative kinds require both reference_time and a resolvable timezone_name.
    """
    root = _lang_root(language)
    norm = normalize_for_language(query or "", language)
    personal = detect_personal_history_intent(query, language=language)

    def _ambiguous(src: Optional[str]) -> TemporalQueryIntent:
        return TemporalQueryIntent(
            kind=TEMPORAL_KIND_AMBIGUOUS,
            start=None,
            end=None,
            timezone=timezone_name,
            source_expression=src,
            deterministic_state=STATE_AMBIGUOUS,
            clarification_required=True,
            personal_history_intent=personal,
        )

    def _none() -> TemporalQueryIntent:
        return TemporalQueryIntent(
            kind=TEMPORAL_KIND_NONE,
            start=None,
            end=None,
            timezone=timezone_name,
            source_expression=None,
            deterministic_state=STATE_NONE,
            clarification_required=False,
            personal_history_intent=personal,
        )

    # Absolute since/before/after with explicit date (no relative clock needed).
    for kind, forms in (
        (TEMPORAL_KIND_SINCE, _SINCE[root]),
        (TEMPORAL_KIND_BEFORE, _BEFORE[root]),
        (TEMPORAL_KIND_AFTER, _AFTER[root]),
    ):
        hit = _contains_any(norm, forms) or _contains_any((query or "").casefold(), forms)
        if not hit and kind == TEMPORAL_KIND_SINCE and root == "fa":
            if _FA_SINCE_DATE_RE.search(norm) or _FA_SINCE_DATE_RE.search(query or ""):
                hit = "از"
        if not hit:
            continue
        explicit = _parse_explicit_date(query or "") or _parse_explicit_date(norm)
        if explicit is None:
            return _ambiguous(hit)
        if kind == TEMPORAL_KIND_SINCE:
            start, end = explicit, None
        elif kind == TEMPORAL_KIND_BEFORE:
            start, end = None, explicit
        else:
            start, end = explicit, None
        return TemporalQueryIntent(
            kind=kind,
            start=start,
            end=end,
            timezone=timezone_name,
            source_expression=hit,
            deterministic_state=STATE_RESOLVED,
            clarification_required=False,
            personal_history_intent=personal,
        )

    relative_specs = (
        (TEMPORAL_KIND_TODAY, _TODAY[root]),
        (TEMPORAL_KIND_YESTERDAY, _YESTERDAY[root]),
        (TEMPORAL_KIND_LAST_WEEK, _LAST_WEEK[root]),
    )
    relative_hit: Optional[tuple[str, str]] = None
    for kind, forms in relative_specs:
        hit = _contains_any(norm, forms) or _contains_any((query or "").casefold(), forms)
        if hit:
            relative_hit = (kind, hit)
            break

    if relative_hit is None:
        return _none()

    kind, src = relative_hit
    if reference_time is None or timezone_name is None:
        return _ambiguous(src)
    tz = _resolve_tz(timezone_name)
    if tz is None:
        return _ambiguous(src)

    # Normalize reference into the explicit timezone (fail closed if naive without tz).
    ref = reference_time
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=tz)
    else:
        ref = ref.astimezone(tz)
    local_day = ref.date()

    if kind == TEMPORAL_KIND_TODAY:
        start = end = local_day
    elif kind == TEMPORAL_KIND_YESTERDAY:
        start = end = local_day - timedelta(days=1)
    else:  # last_week — previous 7 calendar days ending yesterday
        end = local_day - timedelta(days=1)
        start = end - timedelta(days=6)

    return TemporalQueryIntent(
        kind=kind,
        start=start,
        end=end,
        timezone=timezone_name,
        source_expression=src,
        deterministic_state=STATE_RESOLVED,
        clarification_required=False,
        personal_history_intent=personal,
    )


def utc_now_for_tests() -> datetime:
    """Helper for tests only — production callers must pass explicit reference_time."""
    return datetime.now(timezone.utc)
