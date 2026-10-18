"""Conversation topic carry-over for follow-up messages (I1 owned, read-only).

A follow-up such as "برنامه غذایی مناسب این بیماری چیه؟" names no disease, so knowledge retrieval ran
without it and the answer turned generic. This module finds the verified I5 concept (approved catalog
label) the user named in their most recent messages and returns its English label so the retrieval
key can carry it. It only reads: no write, no new storage, no new taxonomy.

Boundaries: I6 consent (memory.read) and I7 retention decide which prior messages may be read
(`query_eligible_raw`); I5 owns the verified concept labels (`resolve_verified_concept_authority`).
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from sqlalchemy.orm import Session

# Recent user messages scanned for the topic (newest first).
_LOOKBACK_MESSAGES = 6
# A message with no own health keyword is a topic-less follow-up only when it is short.
_SHORT_FOLLOWUP_MAX_CHARS = 90

_ANAPHOR_CUES = {
    "fa": (
        "این بیماری", "همین بیماری", "آن بیماری", "اون بیماری", "این مرض", "همین مرض",
        "این مشکل", "همین مشکل", "این وضعیت", "همین وضعیت", "این عارضه", "این سندرم",
    ),
    "ar": ("هذا المرض", "هذه الحالة", "هذا الاضطراب", "نفس المرض", "هذه المشكلة"),
    "en": (
        "this disease", "that disease", "this condition", "that condition", "this illness",
        "the same condition", "this disorder",
    ),
}

# "give me a plan / suggest / explain" without naming any subject.
_REQUEST_CUES = {
    "fa": ("برنامه", "پیشنهاد", "توضیح بده", "توضیح بدی", "بگو", "راهنمایی", "چکار کنم", "چه کنم"),
    "ar": ("خطة", "اقترح", "اشرح", "أخبرني", "ماذا أفعل"),
    "en": ("plan", "suggest", "explain", "recommend", "what should i do", "tell me"),
}


def _root(language: Optional[str]) -> str:
    lang = (language or "en").strip().lower().split("-")[0]
    return lang if lang in _ANAPHOR_CUES else "en"


def needs_topic(message: str, language: Optional[str], *, has_own_health_term: bool) -> bool:
    """True when the message depends on an earlier subject.

    Anaphor ("این بیماری") always depends on it; a short request cue ("برنامه بده") depends on it only
    when the message carries no health term of its own.
    """
    text = " ".join((message or "").lower().split())
    if not text:
        return False
    root = _root(language)
    if any(cue in text for cue in _ANAPHOR_CUES[root]):
        return True
    if has_own_health_term or len(text) > _SHORT_FOLLOWUP_MAX_CHARS:
        return False
    return any(cue in text for cue in _REQUEST_CUES[root])


def augment_query(message: str, topic: Optional[str]) -> str:
    """Retrieval key carrying the earlier subject; the user's own words stay first."""
    if not topic:
        return message
    return f"{message} ({topic})"


def find_topic_in_messages(
    previous_messages: Sequence[str],
    resolver: Callable[[str], Optional[str]],
    *,
    current_message: str = "",
) -> Optional[str]:
    """First (newest) previous message whose text resolves to a verified concept label."""
    current = (current_message or "").strip()
    for text in previous_messages[:_LOOKBACK_MESSAGES]:
        cleaned = (text or "").strip()
        if not cleaned or cleaned == current:
            continue
        label = resolver(cleaned)
        if label:
            return label
    return None


def find_carried_topic(
    db: Session, user_id: int, message: str, language: Optional[str]
) -> Optional[str]:
    """English verified-concept label carried from the user's recent messages, or None.

    Never raises: any failure means "no carried topic" and the caller keeps the original message.
    """
    try:
        from backend.app.services.gate3.medical_intent import is_medical_care_intent
        from backend.app.services.i5.know02.taxonomy import (
            resolve_verified_concept_authority,
            verified_label_texts,
        )
        from backend.app.services.i6.consent_service import PERM_READ, has_permission
        from backend.app.services.i7.retention import query_eligible_raw

        lang = language or "fa"
        own_term = resolve_verified_concept_authority(
            db, message or "", lang
        ) is not None or is_medical_care_intent(message or "", lang)
        if not needs_topic(message, lang, has_own_health_term=own_term):
            return None
        if not has_permission(db, user_id, PERM_READ):
            return None
        rows = query_eligible_raw(db, user_id, limit=_LOOKBACK_MESSAGES + 1)
        previous = [str(getattr(r, "user_message", "") or "") for r in rows]

        def _resolve(text: str) -> Optional[str]:
            authority = resolve_verified_concept_authority(db, text, lang)
            if authority is None:
                return None
            labels = verified_label_texts(db, concept_id=authority.concept_id, language="en")
            return labels[0] if labels else authority.concept_key

        return find_topic_in_messages(previous, _resolve, current_message=message)
    except Exception:
        return None
