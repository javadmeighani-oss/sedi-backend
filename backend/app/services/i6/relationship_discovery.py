"""CR-03 — One-shot relationship-discovery answer binding into I6.

Deterministic. No LLM/network. Structured relationship path only.
Marker: kc_fatigue_policy last_question_type = relationship_discovery:<target_key>
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
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

# Open-text targets: bare acknowledgements must not become fabricated facts.
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
        # EN
        "yes",
        "no",
        "yep",
        "nope",
        "unsure",
        "don't know",
        "dont know",
        "do not know",
        # FA
        "بله",
        "آره",
        "نه",
        "نمی‌دانم",
        "نمیدانم",
        "نمیدونم",
        "نمی دانم",
        # AR
        "نعم",
        "لا",
        "لا أعرف",
        "لا اعرف",
        "مش عارف",
        # existing trivial acknowledgements (also covered in looks_substantive)
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


def consume_relationship_discovery_marker(db: Session, user_id: int) -> None:
    """Clear one-shot marker. Never leave marker active after the binding turn."""
    from backend.app.services.knowledge.kc_fatigue_policy import get_existing_state

    state = get_existing_state(db, user_id)
    if state is None:
        return
    if str(getattr(state, "last_question_type", None) or "").startswith(MARKER_PREFIX):
        state.last_question_type = None
        db.commit()


def _normalize_response_length(message: str) -> Optional[str]:
    text = (message or "").strip().lower()
    if not text:
        return None
    # Prefer multi-word detailed phrases first.
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
        # Bounded fallback: keep short user-stated fragment only when clearly time-like.
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
            # Same value → refresh only (write_fact identical path; no I7 invalidate).
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
        # Different value → NON-AUTHORITATIVE staging; keep old fact canonical.
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
) -> None:
    """
    Process one-shot relationship_discovery marker for this user turn.

    Always consumes the marker when present so it cannot survive the next turn.
    Fact / fatigue binding writes run only when allow_binding is True
    (I4 non-terminal and non-caution).
    """
    if db is None:
        return
    try:
        from backend.app.services.knowledge.kc_fatigue_policy import (
            get_existing_state,
            mark_answer,
        )

        state = get_existing_state(db, user_id)
        if state is None:
            return
        target_key = _parse_target_key(getattr(state, "last_question_type", None) or "")
        if target_key is None:
            return

        now = _utcnow_naive()

        if not allow_binding:
            consume_relationship_discovery_marker(db, user_id)
            return

        skip = detect_discovery_skip_reject(message, language)
        if skip is not None:
            mark_answer(db, user_id, now, skip)
            consume_relationship_discovery_marker(db, user_id)
            return

        if not looks_substantive_discovery_answer(message):
            consume_relationship_discovery_marker(db, user_id)
            return

        if target_key in _OPEN_TEXT_TARGETS and is_ambiguous_open_text_answer(message):
            # Ambiguous bare ack → consume, no fact, no conflict candidate.
            consume_relationship_discovery_marker(db, user_id)
            return

        if target_key not in SUPPORTED_TARGETS:
            # Unsupported / high-sensitivity: consume, no fact.
            mark_answer(db, user_id, now, "accepted")
            consume_relationship_discovery_marker(db, user_id)
            return

        value = normalize_discovery_value(target_key, message)
        if value is None:
            # Unnormalizable (non-ack) → consume, no fact; clear reject streak.
            mark_answer(db, user_id, now, "accepted")
            consume_relationship_discovery_marker(db, user_id)
            return

        evidence = (message or "").strip()[:200]
        try:
            _try_write_or_stage(
                db,
                user_id=user_id,
                target_key=target_key,
                value=value,
                evidence=evidence,
            )
        except Exception:
            # Consent / ownership / storage failures must not leave marker active.
            pass
        mark_answer(db, user_id, now, "accepted")
        consume_relationship_discovery_marker(db, user_id)
    except Exception:
        # Best-effort; never fail the chat path. Still try to consume marker.
        try:
            consume_relationship_discovery_marker(db, user_id)
        except Exception:
            return
