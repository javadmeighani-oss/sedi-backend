"""CR-03 / CR-03.2 — One-shot relationship-discovery answer binding into I6.

Deterministic. No LLM/network. Structured relationship path only.
Marker: kc_fatigue_policy last_question_type = relationship_discovery:<target_key>

CR-03.2 adds pure target-aware classification (no writes during classify).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.services.i6.consent_service import ConsentDenied, PERM_WRITE, has_permission
from backend.app.services.i6.memory_writes import _active_fact, write_fact
from backend.app.services.intelligence.contracts import LanguageCode
from backend.app.services.intelligence.psychological_interaction import (
    detect_discovery_skip_reject,
    looks_substantive_discovery_answer,
)
from backend.app.services.memory.memory_contract import MemoryContract

MARKER_PREFIX = "relationship_discovery:"

# Direct-write targets only (CR-03). No social/values/barriers.
SUPPORTED_TARGETS: frozenset[str] = frozenset(
    {
        "routines.bedtime",
        "routines.wake_time",
        "lifestyle.sleep_quality",
        "lifestyle.food_habits",
        "lifestyle.activity_level",
        "routines.exercise_schedule",
        "preferences.response_length",
    }
)

_OPEN_TEXT_TARGETS: frozenset[str] = frozenset(
    {
        "lifestyle.sleep_quality",
        "lifestyle.food_habits",
        "lifestyle.activity_level",
        "routines.exercise_schedule",
    }
)

_AMBIGUOUS_ACKNOWLEDGEMENTS: frozenset[str] = frozenset(
    {
        "yes",
        "no",
        "yep",
        "nope",
        "unsure",
        "don't know",
        "dont know",
        "do not know",
        "بله",
        "آره",
        "نه",
        "نمی‌دانم",
        "نمیدانم",
        "نمیدونم",
        "نمی دانم",
        "نعم",
        "لا",
        "لا أعرف",
        "لا اعرف",
        "مش عارف",
        "ok",
        "okay",
        "k",
        "thanks",
        "thank you",
        "hi",
        "hello",
        "hey",
        "سلام",
        "مرسی",
        "ممنون",
        "حسنا",
        "شكرا",
    }
)

_MAX_BOUNDED_TEXT = 200
_MAX_TIME_TEXT = 32

_BRIEF_TOKENS = frozenset(
    {
        "brief",
        "short",
        "concise",
        "shorter",
        "quick",
        "کوتاه",
        "مختصر",
        "مختصرة",
        "مختصرًا",
        "قصیر",
        "قصير",
    }
)
_DETAILED_TOKENS = frozenset(
    {
        "detailed",
        "detail",
        "more detail",
        "longer",
        "full",
        "مفصل",
        "مفصل‌تر",
        "مفصل تر",
        "تفصیل",
        "تفصيلا",
        "تفصيلاً",
        "أكثر تفصيلا",
        "اكثر تفصيلا",
    }
)

_TIME_RE = re.compile(
    r"(?P<t>\b(?:[01]?\d|2[0-3])(?::[0-5]\d)?\s*(?:am|pm|a\.m\.|p\.m\.)?\b|"
    r"\b(?:[۱-۹]|1[۰-۲]|٠?[١-٩]|١[٠-٢])\s*(?:صبح|شب|عصر|ظهر)?\b)",
    re.IGNORECASE,
)

# Explicit new-request / topic-shift cues (not relationship answers).
_UNRELATED_REQUEST_CUES: tuple[str, ...] = (
    "create a meal plan",
    "meal plan for me",
    "make me a meal plan",
    "make a meal plan",
    "plan a diet for me",
    "remind me",
    "set a reminder",
    "reminder to",
    "schedule a reminder",
    "برنامه غذایی",
    "برنامه غذایی بساز",
    "یک برنامه غذایی",
    "یادآوری کن",
    "یادآوری",
    "بهم یادآوری",
    "ذكرني",
    "ذكرنى",
    "ذكرني أن",
    "خطة وجبات",
    "اصنع لي خطة",
    "اعمل لي خطة",
)

# CR-03.5: explicit current-need / new-request cues (boundary-safe).
# Do NOT treat bare "please" as new-request evidence.
_EXPLICIT_NEW_REQUEST_CUES: tuple[str, ...] = (
    # EN interrogatives / request verbs
    "what",
    "how",
    "why",
    "when",
    "where",
    "who",
    "can you",
    "could you",
    "would you",
    "should i",
    "do i",
    "is it",
    "are there",
    "tell me",
    "explain",
    "help me",
    "create",
    "make",
    "build",
    "plan",
    "remind me",
    # FA
    "چی",
    "چه",
    "چطور",
    "چگونه",
    "چقدر",
    "چند",
    "چرا",
    "کی",
    "کجا",
    "آیا",
    "میشه",
    "می\u200cشه",
    "میتونی",
    "می\u200cتونی",
    "بگو",
    "توضیح بده",
    "کمکم کن",
    "برنامه بساز",
    "یادآوری کن",
    # AR
    "ما",
    "ماذا",
    "كيف",
    "كم",
    "لماذا",
    "متى",
    "أين",
    "هل",
    "يمكن",
    "هل يمكنك",
    "أخبرني",
    "اشرح",
    "ساعدني",
    "أنشئ",
    "اعمل",
    "خطط",
    "ذكرني",
)

_EXPLICIT_NEW_REQUEST_RE = re.compile(
    r"(?:"
    r"^\s*(?:what|how|why|when|where|who)\b"
    r"|\b(?:can|could|would)\s+you\b"
    r"|\b(?:should|do)\s+i\b"
    r"|\bis\s+it\b"
    r"|\bare\s+there\b"
    r"|\btell\s+me\b"
    r"|\bhelp\s+me\b"
    r"|\bremind\s+me\b"
    r")",
    re.IGNORECASE | re.UNICODE,
)

_SLEEP_QUALITY_CUES: tuple[str, ...] = (
    "sleep",
    "slept",
    "restless",
    "insomnia",
    "poor sleep",
    "good sleep",
    "sleep quality",
    "light sleeper",
    "deep sleep",
    "خواب",
    "بی‌خوابی",
    "بیخوابی",
    "کیفیت خواب",
    "خوابم",
    "نوم",
    "أرق",
    "جودة النوم",
    "نومي",
)

_FOOD_HABIT_CUES: tuple[str, ...] = (
    "vegetarian",
    "vegan",
    "pescatarian",
    "home-cooked",
    "home cooked",
    "eat",
    "eating",
    "diet",
    "food habit",
    "food habits",
    "meals",
    "mostly eat",
    "گیاه‌خوار",
    "گیاهخوار",
    "وگان",
    "عادت غذایی",
    "غذا",
    "می\u200cخورم",
    "میخورم",
    "نباتي",
    "نباتية",
    "آكل",
)

_ACTIVITY_LEVEL_CUES: tuple[str, ...] = (
    "walk",
    "walking",
    "run",
    "running",
    "jog",
    "active",
    "activity",
    "sedentary",
    "steps",
    "exercise",
    "workout",
    "gym",
    "پیاده",
    "پیاده‌روی",
    "پیاده روی",
    "می‌دوم",
    "میدوم",
    "فعال",
    "کم‌تحرک",
    "کم تحرک",
    "أمشي",
    "امشي",
    "أركض",
    "اركض",
    "نشيط",
    "خامل",
    "تمارين",
)

_EXERCISE_SCHEDULE_CUES: tuple[str, ...] = (
    "times a week",
    "times per week",
    "every day",
    "daily",
    "mornings",
    "evenings",
    "monday",
    "wednesday",
    "friday",
    "mon-wed",
    "schedule",
    "هفته‌ای",
    "هفته ای",
    "در هفته",
    "هر روز",
    "صبح\u200cها",
    "صبحها",
    "عصرها",
    "ثلاث مرات",
    "مرات في الأسبوع",
    "مرات في الاسبوع",
    "كل يوم",
    "صباحا",
    "مساء",
)

_EXERCISE_FREQ_RE = re.compile(
    r"(?:"
    r"\b(?:\d+|one|two|three|four|five|six|seven)\s*times?\s*(?:a|per)?\s*week\b"
    r"|\b(?:daily|every\s+day|mornings?|evenings?)\b"
    r"|هفته\s*ای\s*(?:یک|دو|سه|چهار|پنج|\d+)"
    r"|هفته\s*ای\s*\d+"
    r"|(?:یک|دو|سه|چهار|پنج|\d+)\s*بار\s*(?:در\s*)?هفته"
    r"|ثلاث\s*مرات"
    r"|مرات\s*في\s*ال(?:ا)?سبوع"
    r")",
    re.IGNORECASE,
)

_TOPIC_SHIFT_BY_TARGET: dict[str, tuple[str, ...]] = {
    "lifestyle.activity_level": (
        "headache",
        "migraine",
        "fever",
        "سردرد",
        "تب",
        "صداع",
        "حمى",
        "حمی",
    ),
    "lifestyle.food_habits": (
        "headache",
        "سردرد",
        "صداع",
    ),
    "lifestyle.sleep_quality": (
        "meal plan",
        "برنامه غذایی",
    ),
    "routines.exercise_schedule": (
        "headache",
        "سردرد",
        "صداع",
        "meal plan",
        "برنامه غذایی",
    ),
}


class DiscoveryDisposition(str, Enum):
    NO_MARKER = "NO_MARKER"
    ANSWER = "ANSWER"
    SKIP = "SKIP"
    AMBIGUOUS = "AMBIGUOUS"
    UNRELATED = "UNRELATED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class DiscoveryClassification:
    disposition: DiscoveryDisposition
    target_key: Optional[str] = None
    normalized_value: Optional[Any] = None
    skip_outcome: Optional[str] = None


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_target_key(last_question_type: str) -> Optional[str]:
    raw = str(last_question_type or "").strip()
    if not raw.startswith(MARKER_PREFIX):
        return None
    key = raw[len(MARKER_PREFIX) :].strip()
    return key or None


def _split_target(target_key: str) -> Optional[tuple[str, str]]:
    if "." not in target_key:
        return None
    domain, key = target_key.split(".", 1)
    domain, key = domain.strip(), key.strip()
    if not domain or not key:
        return None
    return domain, key


def _fact_type_for_key(key: str) -> str:
    return key


def _norm_msg(message: str) -> str:
    """Consistent normalization for boundary-safe cue matching."""
    text = (message or "").strip().lower()
    text = text.replace("\u200c", "").replace("\u200d", "")
    return text


def _normalize_cue(phrase: str) -> str:
    return _norm_msg(phrase)


def _contains_phrase_boundary(text: str, phrase: str) -> bool:
    """
    Deterministic boundary-safe phrase match.
    text must already be _norm_msg-normalized; phrase is normalized here.
    Latin and FA/AR use Unicode-aware token boundaries via \\w.
    """
    needle = _normalize_cue(phrase)
    if not needle:
        return False
    hay = text if text == _norm_msg(text) else _norm_msg(text)
    if " " in needle:
        # Multiword: require phrase with non-word boundaries around the whole span.
        return bool(
            re.search(
                rf"(?<!\w){re.escape(needle)}(?!\w)",
                hay,
                flags=re.UNICODE,
            )
        )
    return bool(
        re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", hay, flags=re.UNICODE)
    )


def _contains_any_boundary(text: str, cues: tuple[str, ...]) -> bool:
    hay = _norm_msg(text) if text != _norm_msg(text) else text
    # Prefer longer cues first so multiword phrases win over fragments.
    ordered = sorted((c for c in cues if c), key=len, reverse=True)
    return any(_contains_phrase_boundary(hay, c) for c in ordered)


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    """Boundary-safe cue membership (CR-03.3)."""
    return _contains_any_boundary(text, cues)


def peek_relationship_discovery_marker(
    db: Optional[Session], user_id: int
) -> Optional[str]:
    """Non-mutating read of pending relationship_discovery:<target_key>."""
    if db is None:
        return None
    from backend.app.services.knowledge.kc_fatigue_policy import get_existing_state

    state = get_existing_state(db, user_id)
    if state is None:
        return None
    return _parse_target_key(getattr(state, "last_question_type", None) or "")


def consume_relationship_discovery_marker(db: Session, user_id: int) -> None:
    """Clear one-shot marker. Never leave marker active after the binding turn."""
    from backend.app.services.knowledge.kc_fatigue_policy import get_existing_state

    state = get_existing_state(db, user_id)
    if state is None:
        return
    if str(getattr(state, "last_question_type", None) or "").startswith(MARKER_PREFIX):
        state.last_question_type = None
        db.commit()


def expire_relationship_discovery_marker_on_early_return(
    db: Optional[Session], user_id: int
) -> None:
    """
    Lifecycle expiry for successful chat turns that return before orchestrator.
    Consume marker only — no fact write, no fatigue outcome from content.
    """
    if db is None:
        return
    try:
        consume_relationship_discovery_marker(db, user_id)
    except Exception:
        return


def _normalize_response_length(message: str) -> Optional[str]:
    text = (message or "").strip().lower()
    if not text:
        return None
    for tok in sorted(_DETAILED_TOKENS, key=len, reverse=True):
        if tok in text:
            return "detailed"
    for tok in sorted(_BRIEF_TOKENS, key=len, reverse=True):
        if tok in text:
            return "brief"
    return None


def _normalize_time_text(message: str) -> Optional[str]:
    text = (message or "").strip()
    if not text:
        return None
    m = _TIME_RE.search(text)
    if not m:
        lowered = text.lower()
        if any(x in lowered for x in (":", "am", "pm", "صبح", "شب", "عصر", "ظهر")):
            return text[:_MAX_TIME_TEXT].strip() or None
        return None
    return (m.group("t") or "").strip()[:_MAX_TIME_TEXT] or None


def _normalize_bounded_text(message: str) -> Optional[str]:
    text = (message or "").strip()
    if not text:
        return None
    bounded = text[:_MAX_BOUNDED_TEXT].strip()
    return bounded or None


def is_ambiguous_open_text_answer(message: str) -> bool:
    """Bare acknowledgements / unsure replies — no fabricated semantic value."""
    text = (message or "").strip().lower()
    if not text:
        return True
    return text in _AMBIGUOUS_ACKNOWLEDGEMENTS


def normalize_discovery_value(target_key: str, message: str) -> Optional[Any]:
    """Deterministic normalization. Never persist unbounded full message."""
    if target_key == "preferences.response_length":
        return _normalize_response_length(message)
    if target_key in ("routines.bedtime", "routines.wake_time"):
        return _normalize_time_text(message)
    if target_key in _OPEN_TEXT_TARGETS and is_ambiguous_open_text_answer(message):
        return None
    return _normalize_bounded_text(message)


def _looks_unrelated_request(text: str) -> bool:
    return _contains_any(text, _UNRELATED_REQUEST_CUES)


def is_explicit_new_request(message: str, language: LanguageCode) -> bool:
    """
    CR-03.5 — pure deterministic current-need / new-request guard.
    No DB / network / LLM / writes. Boundary-safe cues.
    Bare 'please' alone is NOT evidence.
    """
    raw = (message or "").strip()
    if not raw:
        return False
    # Explicit question mark (EN/FA/AR) — treat as plausible new question (safe bias).
    if "?" in raw or "؟" in raw:
        return True
    text = _norm_msg(raw)
    if not text:
        return False
    if _EXPLICIT_NEW_REQUEST_RE.search(text):
        return True
    if _contains_any_boundary(text, _EXPLICIT_NEW_REQUEST_CUES):
        return True
    # Preserve prior meal-plan / reminder cue coverage.
    if _looks_unrelated_request(text):
        return True
    return False


# Software/device phrases that must not count as personal activity (CR-03.3).
_NONPERSONAL_ACTIVITY_CUES: tuple[str, ...] = (
    "app is running",
    "software is running",
    "server is running",
    "process is running",
    "service is running",
)


def _target_fit(target_key: str, message: str) -> bool:
    text = _norm_msg(message)
    if target_key == "lifestyle.sleep_quality":
        return _contains_any(text, _SLEEP_QUALITY_CUES)
    if target_key == "lifestyle.food_habits":
        if _looks_unrelated_request(text):
            return False
        return _contains_any(text, _FOOD_HABIT_CUES)
    if target_key == "lifestyle.activity_level":
        if _contains_any_boundary(text, _NONPERSONAL_ACTIVITY_CUES):
            return False
        return _contains_any(text, _ACTIVITY_LEVEL_CUES)
    if target_key == "routines.exercise_schedule":
        if _EXERCISE_FREQ_RE.search(text):
            return True
        return _contains_any(text, _EXERCISE_SCHEDULE_CUES)
    return False


def _looks_topic_shift(target_key: str, message: str) -> bool:
    text = _norm_msg(message)
    if _looks_unrelated_request(text):
        return True
    cues = _TOPIC_SHIFT_BY_TARGET.get(target_key, ())
    return _contains_any(text, cues)


def classify_discovery_reply(
    target_key: Optional[str],
    message: str,
    language: LanguageCode,
) -> DiscoveryClassification:
    """
    Pure target/message classification. No DB / network / writes.
    """
    if not target_key:
        return DiscoveryClassification(DiscoveryDisposition.NO_MARKER)

    skip = detect_discovery_skip_reject(message, language)
    if skip is not None:
        return DiscoveryClassification(
            DiscoveryDisposition.SKIP,
            target_key=target_key,
            skip_outcome=skip,
        )

    # CR-03.5: current user request > relationship discovery.
    if is_explicit_new_request(message, language):
        return DiscoveryClassification(
            DiscoveryDisposition.UNRELATED, target_key=target_key
        )

    if not looks_substantive_discovery_answer(message) or is_ambiguous_open_text_answer(
        message
    ):
        return DiscoveryClassification(
            DiscoveryDisposition.AMBIGUOUS, target_key=target_key
        )

    if target_key not in SUPPORTED_TARGETS:
        return DiscoveryClassification(
            DiscoveryDisposition.UNSUPPORTED, target_key=target_key
        )

    if target_key == "preferences.response_length":
        value = _normalize_response_length(message)
        if value is None:
            return DiscoveryClassification(
                DiscoveryDisposition.AMBIGUOUS, target_key=target_key
            )
        return DiscoveryClassification(
            DiscoveryDisposition.ANSWER,
            target_key=target_key,
            normalized_value=value,
        )

    if target_key in ("routines.bedtime", "routines.wake_time"):
        value = _normalize_time_text(message)
        if value is None:
            # Time-like targets: unnormalizable substantive text is ambiguous, not a write.
            return DiscoveryClassification(
                DiscoveryDisposition.AMBIGUOUS, target_key=target_key
            )
        return DiscoveryClassification(
            DiscoveryDisposition.ANSWER,
            target_key=target_key,
            normalized_value=value,
        )

    # Open-text lifestyle / schedule targets — require target-fit evidence.
    if _looks_topic_shift(target_key, message) and not _target_fit(target_key, message):
        return DiscoveryClassification(
            DiscoveryDisposition.UNRELATED, target_key=target_key
        )
    if _looks_unrelated_request(_norm_msg(message)):
        return DiscoveryClassification(
            DiscoveryDisposition.UNRELATED, target_key=target_key
        )
    if not _target_fit(target_key, message):
        # Explicit topic-shift cues without fit → unrelated; else ambiguous.
        if _looks_topic_shift(target_key, message):
            return DiscoveryClassification(
                DiscoveryDisposition.UNRELATED, target_key=target_key
            )
        return DiscoveryClassification(
            DiscoveryDisposition.AMBIGUOUS, target_key=target_key
        )

    value = _normalize_bounded_text(message)
    if value is None:
        return DiscoveryClassification(
            DiscoveryDisposition.AMBIGUOUS, target_key=target_key
        )
    return DiscoveryClassification(
        DiscoveryDisposition.ANSWER,
        target_key=target_key,
        normalized_value=value,
    )


def _stage_conflict_candidate(
    db: Session,
    *,
    user_id: int,
    target_key: str,
    domain: str,
    key: str,
    value: Any,
    evidence: str,
) -> None:
    from backend.app.services.knowledge.service import create_candidate

    create_candidate(
        db,
        user_id=user_id,
        source="chat",
        fact_type=_fact_type_for_key(key),
        value_json=json.dumps({"value": value}, ensure_ascii=False, default=str),
        confidence=0.85,
        evidence=(evidence or "")[:200] or None,
        metadata_json=json.dumps(
            {
                "needs_confirmation": True,
                "source": "relationship_discovery",
                "target_key": target_key,
                "domain": domain,
                "key": key,
            },
            sort_keys=True,
        ),
    )


def _try_write_or_stage(
    db: Session,
    *,
    user_id: int,
    target_key: str,
    value: Any,
    evidence: str,
) -> None:
    pair = _split_target(target_key)
    if pair is None:
        return
    domain, key = MemoryContract.canonicalize_key(pair[0], pair[1])
    ok, _err = MemoryContract.validate_fact(domain, key)
    if not ok:
        return
    permitted, _owner_err = MemoryContract.i6_write_permitted(domain, key)
    if not permitted:
        return
    if not has_permission(db, user_id, PERM_WRITE):
        return

    existing = _active_fact(db, user_id, domain, key)
    if existing is not None:
        blob = json.dumps(value, ensure_ascii=False, default=str)
        if existing.value_json == blob:
            try:
                write_fact(
                    db,
                    user_id,
                    domain,
                    key,
                    value,
                    provenance_class="USER_STATED",
                    source="relationship_discovery",
                    commit=True,
                )
            except ConsentDenied:
                return
            return
        _stage_conflict_candidate(
            db,
            user_id=user_id,
            target_key=target_key,
            domain=domain,
            key=key,
            value=value,
            evidence=evidence,
        )
        return

    try:
        write_fact(
            db,
            user_id,
            domain,
            key,
            value,
            provenance_class="USER_STATED",
            source="relationship_discovery",
            commit=True,
        )
    except ConsentDenied:
        return


def process_relationship_discovery_answer(
    db: Optional[Session],
    *,
    user_id: int,
    message: str,
    language: LanguageCode,
    allow_binding: bool,
    classification: Optional[DiscoveryClassification] = None,
) -> DiscoveryClassification:
    """
    Process one-shot relationship_discovery marker for this user turn.

    Always consumes the marker when present so it cannot survive the next turn.
    Fact / fatigue binding writes run only when allow_binding is True and
    disposition is ANSWER (or SKIP updates fatigue only).
    """
    empty = DiscoveryClassification(DiscoveryDisposition.NO_MARKER)
    if db is None:
        return empty
    try:
        from backend.app.services.knowledge.kc_fatigue_policy import mark_answer

        target_key = None
        if classification is not None and classification.target_key:
            target_key = classification.target_key
            clf = classification
        else:
            target_key = peek_relationship_discovery_marker(db, user_id)
            if target_key is None:
                return empty
            clf = classify_discovery_reply(target_key, message, language)

        if clf.disposition is DiscoveryDisposition.NO_MARKER:
            return clf

        now = _utcnow_naive()

        if not allow_binding:
            # Compatibility / caution / terminal: consume only, no fact/outcome.
            consume_relationship_discovery_marker(db, user_id)
            return clf

        if clf.disposition is DiscoveryDisposition.UNRELATED:
            consume_relationship_discovery_marker(db, user_id)
            return clf

        if clf.disposition is DiscoveryDisposition.SKIP:
            mark_answer(db, user_id, now, clf.skip_outcome or "skipped")
            consume_relationship_discovery_marker(db, user_id)
            return clf

        if clf.disposition in (
            DiscoveryDisposition.AMBIGUOUS,
            DiscoveryDisposition.UNSUPPORTED,
        ):
            consume_relationship_discovery_marker(db, user_id)
            return clf

        if clf.disposition is DiscoveryDisposition.ANSWER:
            value = clf.normalized_value
            if value is None:
                consume_relationship_discovery_marker(db, user_id)
                return DiscoveryClassification(
                    DiscoveryDisposition.AMBIGUOUS, target_key=target_key
                )
            evidence = (message or "").strip()[:200]
            try:
                _try_write_or_stage(
                    db,
                    user_id=user_id,
                    target_key=target_key or "",
                    value=value,
                    evidence=evidence,
                )
            except Exception:
                pass
            mark_answer(db, user_id, now, "accepted")
            consume_relationship_discovery_marker(db, user_id)
            return clf

        consume_relationship_discovery_marker(db, user_id)
        return clf
    except Exception:
        try:
            consume_relationship_discovery_marker(db, user_id)
        except Exception:
            pass
        return empty
