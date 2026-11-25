"""R-116 am.1 (Javad 2026-11-23/25): «the NEXT FIVE». When the user says the introduced doctors do not suit («مناسب نیست», «نتونستم نوبت بگیرم»)
or asks for more («پنج تای بعدی»), Sedi introduces the next five - the same search, the doctors already introduced left out.

State lives with the stored turn of the introduction (``Memory.provenance_json["provider_intro"]``, additive, no migration): the request (what /
where) plus the keys and names of everyone introduced so far. This module only decides «is this a next-five request?» and rebuilds the request;
the search itself stays in ``care_navigation_directory`` (ONE owner, no parallel path). Deterministic, no model, consent follows the stored turn
(a turn that was not stored leaves no state, so the request is then answered by the ordinary flow); fail-open: any problem = None.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from backend.app import sedi_copy

logger = logging.getLogger(__name__)

MAX_AGE = timedelta(hours=12)  # an introduction older than this is no longer «the previous five»
MAX_TURNS_BACK = 8  # ... and must be among the user's latest turns
MAX_MESSAGE_CHARS = 90  # a next-five request is short; a long message is a new topic

_NEXT = re.compile(
    r"(?:پنج|۵|5)\s*تا(?:ی)?\s*(?:بعدی|دیگه|دیگر)|(?:پنج|۵|5)\s*(?:نفر|پزشک|دکتر)\s*(?:بعدی|دیگه|دیگر)|"
    r"^\W*(?:لطفا\s*)?(?:بعدی|بعدیا|بعدی\s*ها|بعدی‌ها)(?:\s*(?:رو|را|بده|نشون\s*بده|لطفا))*\W*$|"
    r"(?:یه|یک|چند)\s*(?:تا\s*)?(?:دکتر|پزشک)?\s*(?:\S+\s+)?(?:دیگه|دیگر)\b|(?:دکتر|پزشک)(?:ان|ها)?(?:ی)?\s*(?:دیگه|دیگر|بیشتر)\b|"
    r"بقیه(?:‌ی)?\s*(?:ش(?:ون)?\s*)?(?:رو|را)?\s*(?:نشون|نشان|بگو|بده|معرفی|ببینم)|بیشتر\s*(?:نشون|نشان|معرفی)\s*(?:بده|بدهید|کن)|"
    r"(?:اینها|اینا|این‌ها|اینارو|این)\s*(?:مناسب|خوب|جور)\s*(?:نیست|نبود|نیستن|نیستند)|مناسب\s*(?:نیست|نبود)|"
    r"(?:نتونستم|نتوانستم|نشد)\s*(?:که\s*)?(?:ازشون\s*|از\s*اینها\s*|از\s*اینا\s*)?(?:نوبت|وقت)|"
    r"(?:نوبت|وقت)\s*(?:نداره|ندارن|ندارند|نداشت|نمیده|نمی\s*ده|نمی‌دهد|نمی‌دن|نمیدن)|"
    r"الخمسة\s*(?:التالية|الآخرين|الاخرين)|(?:طبيب|أطباء|دكتور)\s*(?:آخر|آخرين|اخر|غيرهم)|غير\s*مناسب(?:ين|ة)?|لم\s*(?:أستطع|استطع)\s*الحجز|"
    r"لا\s*(?:يوجد|توجد)\s*(?:موعد|مواعيد)|المزيد\s*من\s*الأطباء|"
    r"\b(?:next|another|other|more)\s+(?:five|5|doctors?|ones|options|specialists?)\b|\bnext\s+(?:five|5)\b|\bshow\s+(?:me\s+)?(?:more|others|the\s+rest)\b|"
    r"\b(?:not|isn.?t|aren.?t)\s+(?:suitable|a\s+good\s+fit|right\s+for\s+me)\b|\b(?:could(?:n.?t|\s+not)|can.?t|cannot)\s+(?:get|book|make)\s+(?:an?\s+)?(?:appointment|booking|slot)\b|"
    r"\bno\s+(?:appointments?|slots?|availability)\b",
    re.I,
)


def wants_next(message: Optional[str]) -> bool:
    """The message asks for the next doctors / says the last ones did not suit - and is short enough to be only that."""
    text = (message or "").strip()
    return bool(text) and len(text) <= MAX_MESSAGE_CHARS and bool(_NEXT.search(text))


def latest_state(db: Any, user_id: Optional[int], now: Optional[datetime] = None) -> Optional[dict]:
    """The introduction state of the user's latest provider introduction (among the last turns, not older than ``MAX_AGE``), else None."""
    if db is None or user_id is None:
        return None
    try:
        from backend.app.core.conversation.memory import ConversationMemory
        from backend.app.services.i7 import governed_raw

        # the GOVERNED reader: current memory.read consent + retention eligibility (a revoked consent leaves no «previous five» to continue from)
        rows = sorted(ConversationMemory(db).get_recent_messages(int(user_id), limit=MAX_TURNS_BACK), key=lambda r: getattr(r, "id", 0), reverse=True)
        moment = (now or datetime.utcnow())
        for row in rows:
            state = governed_raw.provider_intro_of_turn(row)
            if state is None:
                continue
            created = getattr(row, "created_at", None)
            if created is not None and moment - created.replace(tzinfo=None) > MAX_AGE:
                return None
            return state
    except Exception:  # noqa: BLE001
        logger.info("provider_next_state_failed")
    return None


def request_from_state(state: dict, language: str, user_id: Optional[int] = None) -> Any:
    """The explicit request of the previous introduction, with everyone already introduced left out."""
    from backend.app.services.i5 import care_navigation_directory as cn

    return cn.CareNavRequest(
        entity=cn.CareNavEntity(state.get("entity") or "SPECIALIST"),
        specialty_or_service=state.get("specialty"),
        city=state.get("city"),
        province=state.get("province"),
        area=state.get("area"),
        language=language,
        authenticated_user_id=user_id,
        qualifiers=tuple(str(q) for q in (state.get("qualifiers") or ())),  # 24h / high_rating / urgent stay part of the search
        exclude_keys=tuple(str(k) for k in (state.get("keys") or ())),
        exclude_names=tuple(str(n) for n in (state.get("names") or ())),
    )


def _names_another_search(message: str, state: dict) -> bool:
    """«another doctor, a cardiologist please» names a DIFFERENT specialty (or another kind of place) than the stored search: that is a new request
    for the ordinary flow, not the next five of the old one (Codex P2, PR 225)."""
    from backend.app.services.i5 import care_navigation_directory as cn
    from backend.app.services.i5 import specialty_lexicon as sl

    named = sl.find_specialty(message)
    stored = state.get("specialty")
    if named and named != (sl.find_specialty(str(stored or "")) or stored):
        return True
    detected = cn.detect_care_nav_entity(message)
    return detected is not cn.CareNavEntity.SPECIALIST and detected.value != state.get("entity")


def next_request(db: Any, user_id: Optional[int], message: Optional[str], language: str) -> Optional[Any]:
    """The request for «the next five», or None when the message is not such a request (or there is nothing to continue from)."""
    try:
        if not wants_next(message):
            return None
        from backend.app.services.i5 import care_navigation_directory as cn

        if cn._has_real_location(message or ""):
            return None  # «another doctor in Shiraz» is a NEW request with its own place
        state = latest_state(db, user_id)
        if not state or _names_another_search(message or "", state):
            return None
        return request_from_state(state, language, user_id)
    except Exception:  # noqa: BLE001
        logger.info("provider_next_request_failed")
        return None


def compose(result: Any, language: str) -> str:
    """The reply for a next-five result: a short lead + the list; when nothing is left, one plain sentence with the concrete next step."""
    lang = (language or "en").lower()[:2]
    lang = lang if lang in ("fa", "ar", "en") else "en"
    from backend.app.services.i5 import care_navigation_directory as cn

    if getattr(result, "status", None) == cn.STATUS_VERIFIED and getattr(result, "identities", ()):
        return sedi_copy.t("care_nav.next.intro", lang) + "\n\n" + str(result.user_message or "")
    return sedi_copy.t("care_nav.next.none", lang)
