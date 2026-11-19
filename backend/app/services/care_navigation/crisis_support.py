"""S1 (R-099, D-398): when a user talks about not wanting to live, Sedi TALKS with them - she does not hand them a phone number and leave.

Javad: «صدی باید با استفاده از علوم روانشناسی با کاربر صحبت کند و از کاربر بخواهد با او صحبت کند و بگوید چه چیزی او را آزار می‌دهد.
اگر صدی یک همراه و دوست است باید با تعامل کاربر را آرام کند.»

The first reply to the disclosure is the I4 safety template (safety_risk.py: presence + «tell me what is hurting you» + real help
when in danger). The user's NEXT messages are ordinary chat turns - without this module the model would not remember that the
person is in a vulnerable moment. ``crisis_hint`` is the protocol handed to the chat model for those turns; it follows the
standard evidence-based practice (R-017 / R-060: reflect and validate before anything else, open invitation to talk, direct and
gentle safety questions, means safety, a small next step, follow-up), never methods, never secrecy promises, never a lecture,
never «I cannot help» (R-033), never a diagnosis or a drug start/stop/change (R-014/R-074).

Deterministic, no model call. Reading earlier turns is consent-gated (R-021) and fail-open.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

LOOKBACK = timedelta(hours=24)
MAX_TURNS = 6

_BASE = (
    "SUPPORT MODE - the user has spoken about not wanting to live or hurting themselves (now or earlier today). This person is in a "
    "vulnerable moment. You are their calm, caring companion: stay with them and TALK. Reply in the user's language, warm, unhurried, "
    "plain, with full polite forms (no slang). Follow this protocol: "
    "(1) First reflect and validate what you hear in one or two sentences (their pain makes sense; you are glad they said it; they are "
    "not alone) - before any question or advice. "
    "(2) Invite them to talk: ask what is hurting them most right now, and listen; ask ONE question per reply; reflect back what they "
    "tell you; do not rush to fix, do not argue, do not lecture, do not say «think about your family» or «it is not that bad». "
    "(3) Gently and directly ask about safety when the connection is there (not necessarily in the first reply): whether they are "
    "thinking of ending their life, and whether they have a plan or something nearby they could use; asking directly does not harm. "
    "(4) If there is an immediate plan, means, or intent: stay with them, ask them to move the means away from themselves and not to "
    "be alone, ask someone close to come now, and urge calling the emergency number 115 or the social emergency line 123 (free, 24 "
    "hours); the counselling line 1480 is also free but not 24 hours; keep talking with them while they do it. "
    "(5) If they are panicking, offer one simple calming step at a time (slow breathing: in for four, out for six; name five things "
    "they can see). "
    "(6) Offer hope without false promises (feelings change, this moment can pass), a small safe step for tonight, one person they "
    "trust, and - when it fits - help to reach a psychologist or psychiatrist (offer to find one near them). "
    "(7) Say you will check on them again the next time you talk, and ask them to come back to you; never promise a call, message or "
    "visit you cannot make. "
    "(8) When the first words were an explicit wish or intent to die, ask the direct safety question (are you thinking of ending your "
    "life; do you have a plan or something nearby) by your second reply at the latest, as ONE question, after one line of validation. "
    "(9) Use plain words for the topic (say «ending your life», never «commit suicide»); keep a steady, unshocked tone. "
    "NEVER: give methods or details, promise to keep a secret that could cost their life, say you cannot help, say you are only an AI, "
    "diagnose, or advise starting/stopping/changing any drug; never use guilt, sin or religious condemnation, never ask accusing "
    "«why did you…» questions, never argue whether life is worth living, never say «everything will be fine» or «I understand exactly»."
)

_ONGOING = (
    " This is a CONTINUATION: the person raised this earlier. Do not repeat the emergency numbers unless danger is immediate; continue "
    "the conversation, deepen what is hurting them, and keep the safety check gentle and current."
)


def crisis_hint(*, ongoing: bool = False) -> str:
    return _BASE + (_ONGOING if ongoing else "")


def _consented(db: Any, user_id: int) -> bool:
    try:
        from backend.app.services.i6.consent_service import PERM_READ, has_permission

        return bool(has_permission(db, user_id, PERM_READ))
    except Exception:  # noqa: BLE001
        return False


def _recent_user_messages(db: Any, user_id: int) -> list[str]:
    try:
        from backend.app.services.i7.retention import query_eligible_raw

        since = datetime.now(timezone.utc).replace(tzinfo=None) - LOOKBACK
        rows = query_eligible_raw(db, user_id, limit=MAX_TURNS)
        return [str(r.user_message or "") for r in rows if r.created_at is not None and r.created_at >= since]
    except Exception:  # noqa: BLE001
        return []


def is_self_harm_text(text: str, language: str = "fa") -> bool:
    """The same I4 assessor the safety layer uses (one definition of «self-harm talk», R-005)."""
    try:
        from backend.app.services.intelligence.contracts import RiskDomain
        from backend.app.services.intelligence.safety_risk import assess_safety_risk

        a = assess_safety_risk(message=text or "", language=language if language in ("fa", "ar", "en") else "en")
        return a.domain is RiskDomain.SELF_HARM_CRISIS
    except Exception:  # noqa: BLE001
        return False


def hint_for_turn(db: Any, user_id: Optional[int], user_message: str, language: str = "fa") -> Optional[str]:
    """The support-mode hint for this chat turn, or None. Fires when this message or an earlier turn (last 24 h, consent-gated) was
    self-harm talk. Never raises."""
    try:
        if is_self_harm_text(user_message, language):
            return crisis_hint(ongoing=False)
        if db is None or not user_id or not _consented(db, user_id):
            return None
        if any(is_self_harm_text(m, language) for m in _recent_user_messages(db, user_id)):
            return crisis_hint(ongoing=True)
    except Exception:  # noqa: BLE001
        return None
    return None
