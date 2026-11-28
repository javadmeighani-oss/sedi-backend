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

MAX_AGE = timedelta(days=7)  # an introduction older than this is no longer «the previous five» (R-120 am.4: was 12 h; the doctor topic of the opener lives a week)
MAX_TURNS_BACK = 8  # ... and must be among the user's latest turns
MAX_MESSAGE_CHARS = 90  # a next-five request is short; a long message is a new topic

_NEXT = re.compile(
    r"(?:پنج|۵|5)\s*تا(?:ی)?\s*(?:دکتر|پزشک|متخصص)?\s*(?:بعدی|دیگه|دیگر|جدید|تازه)|(?:پنج|۵|5)\s*(?:نفر|پزشک|دکتر|متخصص)\s*(?:بعدی|دیگه|دیگر|جدید|تازه)|"
    # D-550 (pilot 2026-11-27, «۵ تا جدید معرفی کن»): new / fresh / other than these / change them = the next five
    r"(?:دکتر|پزشک|متخصص)(?:ها|های|ای|‌ها|‌های|ان)?(?:ی)?\s*(?:جدید|تازه)|(?:چند|یه|یک)\s*(?:تا(?:ی)?\s*)?(?:دکتر|پزشک|متخصص)?\s*(?:جدید|تازه)|"
    r"(?:لیست|فهرست|اسم|اسامی)(?:‌ی|ی)?\s*(?:جدید|تازه|دیگه|دیگر)\s*(?:رو|را)?\s*(?:بده|بفرست|بیار|معرفی\s*کن|میخوام|می‌خوام|لطفا)?\W*$|^\W*(?:جدید|جدیدا|جدیدها|جدید‌ها|تازه‌ها)\W*(?:رو|را|بده|بفرست|معرفی\s*کن|لطفا|\s)*\W*$|"
    r"غیر\s*از\s*(?:اینا|اینها|این‌ها|اونا|اونها|آن‌ها|این\s*(?:پنج|۵|5)\s*(?:تا|نفر))|(?:عوض|تعویض)(?:شون)?\s*(?:کن|بکن)|"
    r"(?:أطباء|اطباء|خمسة)\s*(?:جدد|جديدين|جديدة)|قائمة\s*(?:جديدة|أخرى|اخرى)\W*$|"
    r"\bnew\s+(?:ones|doctors?|five|options|names)\b|\bnew\s+list\W*$|\b(?:five|5)\s+new\b|\bdifferent\s+(?:doctors?|ones|options)\b|"
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


_REFUSAL = re.compile(
    r"نمی\W*(?:خوام|خواهم|خواهیم)|نیاز\s*ندارم|لازم\s*ندارم|دیگه\s*کافیه|"
    r"لا\s*(?:أريد|اريد|أحتاج|احتاج)|"
    r"\b(?:don.?t|do not|no)\s+(?:need|want)\b|\bno\s+more\b|\benough\b",
    re.I,
)


# D-550 / DEBT-108: «introduce them AGAIN» = the SAME doctors once more (exact rows of the stored introduction, same bubbles + links)
_AGAIN = re.compile(
    r"(?:دوباره|مجددا|مجدداً|مجدد|یه\s*بار\s*دیگه|یک\s*بار\s*دیگر|باز\s*هم)\s*(?:\S+\s+){0,3}?(?:معرفی|بفرست|بفرستی|نشون|نشان|بگو|بگی|بنویس|لیست|فهرست|اسم)|"
    r"(?:معرفی|بفرست|نشون|نشان|بنویس)\s*(?:\S+\s+){0,2}?(?:دوباره|مجددا|مجدداً|مجدد)|"
    r"(?:همونا|همون‌ها|همونها|همان‌ها|همانها|همانا|همون\s*(?:پنج|۵|5)\s*(?:تا|نفر)|همان\s*(?:پنج|۵|5)\s*(?:تا|نفر)|(?:لیست|فهرست)(?:‌ی|ی)?\s*قبلی)"
    r"\s*(?:\S+\s+){0,2}?(?:رو|را)?\s*(?:دوباره\s*)?(?:بفرست|بگو|نشون|نشان|بده|معرفی|بنویس)|"
    r"(?:أعد|اعد|كرر)\s*(?:لي\s*)?(?:القائمة|الأسماء|الاسماء|إرسال|ارسال|عرض)|نفس\s*(?:القائمة|الأطباء|الاطباء)|(?:أرسل|ارسل|اعرض)\S*\s*(?:\S+\s+){0,2}?مرة\s*أخرى|"
    r"\b(?:show|send|give|list|tell|introduce)\b(?:\s+\S+){0,3}?\s+again\b|\bresend\b|\brepeat\s+(?:the\s+)?(?:list|names|doctors)\b|\bsame\s+(?:list|doctors|ones|names)\b",
    re.I,
)
# D-550 / DEBT-110: a short «go ahead / do it / search» right after a doctor search was offered or asked for
_CONFIRM = re.compile(
    r"^\W*(?:(?:خب|خوب|باشه|آره|اره|بله|اوکی|حتما|حتماً|لطفا|لطفاً|پس)\s*)*"
    r"(?:انجام(?:ش)?\s*(?:بده|بدید|بدهید)|بگرد|بگردید|جست[\s‌]*و?[\s‌]*جو\s*کن|جستجو\s*کن|سرچ\s*کن|پیدا(?:شون)?\s*کن|بفرما|برو\s*جلو|شروع\s*کن)"
    r"(?:\s*(?:لطفا|لطفاً|دیگه|پس|برام))*\W*$|"
    r"^\W*(?:(?:نعم|حسنا|حسناً|طيب|اوكي)\s*)*(?:ابحث|افعل(?:ها)?|ابدأ|تفضل)\W*$|"
    r"^\W*(?:(?:ok(?:ay)?|yes|sure|fine|alright|please)[\s,]*)*(?:do\s+it|go\s+ahead|search(?:\s+for\s+them)?|find\s+them|go\s+on|please\s+do)\W*$",
    re.I,
)
# D-550 / DEBT-110: the generator must never answer a doctor search with «I have no live access / send me the results» (R-089, R-114)
_NO_ACCESS = re.compile(
    r"دسترسی\s*(?:\S+\s+){0,5}?(?:ندارم|نیست)|(?:نتایج|نتیجه)(?:‌ی|ی)?\s*(?:جست[\s‌]*و?[\s‌]*جو|جستجو)\S*\s*(?:\S+\s+){0,4}?(?:بفرست|بده)|"
    r"(?:نام|اسم|شماره|نشانی)\S*\s*(?:\S+\s+){0,4}?(?:تأییدنشده|تایید\s*نشده|تأیید\s*نشده)\s*(?:\S+\s+){0,2}?(?:بدهم|بسازم|نمی‌دهم|نمیدم)|"
    r"نمی\W*(?:توانم|تونم)\s*(?:\S+\s+){0,3}?(?:جست[\s‌]*و?[\s‌]*جو|جستجو|پیدا|معرفی)|"
    r"لا\s*(?:أملك|املك|يمكنني)\s*(?:\S+\s+){0,2}?(?:وصول|الوصول|البحث)|"
    r"\b(?:i\s+(?:don.?t|do\s+not)\s+have\s+(?:live\s+)?access|i\s+(?:can.?t|cannot)\s+(?:search|browse|look\s+up|find))\b|\bsend\s+me\s+the\s+(?:search\s+)?results\b",
    re.I,
)


_ONCE_MORE = re.compile(r"(?:یه|یک)\s*بار\s*(?:دیگه|دیگر)")


def _once_more_is_again(text: str) -> str:
    """«یه بار دیگه» = «دوباره» (once more), never «another doctor» (D-550)."""
    return _ONCE_MORE.sub("دوباره", text)


# a five-count or a doctor word makes a next-five ask explicit (it continues the doctors even after a newer subject); anything else needs the open talk
_EXPLICIT_DOCTOR = re.compile(r"پنج|۵|5|دکتر|پزشک|متخصص|الخمسة|طبيب|أطباء|اطباء|دكتور|\b(?:five|doctors?|specialists?)\b", re.I)


def _other_subject(message: str) -> bool:
    """The message names its own subject (food, sleep, feelings…): «یک لیست جدید غذا» is about food, never the next doctors (Codex P2, PR 232)."""
    if _EXPLICIT_DOCTOR.search(message or ""):
        return False  # «یه دکتر پوست دیگه»: a doctor word makes it a doctor message, whatever body part it names
    try:
        from backend.app.services.i7 import conversation_recap as _recap

        topic = _recap.classify_turn(message or "")
        return topic is not None and topic != "doctor"
    except Exception:  # noqa: BLE001
        return False


def is_doctor_message(message: Optional[str]) -> bool:
    """The CURRENT message itself belongs to a doctor talk (a request, a follow-up of one, or a doctor word)."""
    text = (message or "").strip()
    if not text:
        return False
    if wants_next(text) or wants_again(text) or confirms_search(text) or _EXPLICIT_DOCTOR.search(text):
        return True
    try:
        from backend.app.services.i5 import care_nav_memory as _mem
        from backend.app.services.i5 import care_navigation_directory as cn
        from backend.app.services.i7 import conversation_recap as _recap

        return cn.is_care_navigation_query(text) or _mem.asks_doctor_ellipsis(text) or _recap.classify_turn(text) == "doctor"
    except Exception:  # noqa: BLE001
        return False


def wants_again(message: Optional[str]) -> bool:
    """«introduce them again / send the same list»: short, no refusal, and not a request for NEW ones (that is the next five)."""
    text = _once_more_is_again((message or "").strip())
    if not text or len(text) > MAX_MESSAGE_CHARS or _REFUSAL.search(text) or _NEXT.search(text):
        return False
    return bool(_AGAIN.search(text))


def confirms_search(message: Optional[str]) -> bool:
    """«خوب انجام بده», «باشه بگرد», "go ahead": a short go-ahead with no subject of its own."""
    text = (message or "").strip()
    return bool(text) and len(text) <= 40 and not _REFUSAL.search(text) and bool(_CONFIRM.search(text))


def claims_no_access(reply: Optional[str]) -> bool:
    """A reply that says Sedi cannot search / has no access / wants the user to bring the results (never allowed in a doctor talk)."""
    return bool(reply) and bool(_NO_ACCESS.search(reply or ""))


def wants_next(message: Optional[str]) -> bool:
    """The message asks for the next doctors / says the last ones did not suit - and is short enough to be only that."""
    text = _once_more_is_again((message or "").strip())
    if not text or len(text) > MAX_MESSAGE_CHARS or _REFUSAL.search(text):
        return False
    if _NEXT.search(text):
        return True
    from backend.app.services.i5 import care_nav_memory as _mem  # «introduce me some more» / «find me some more» (Codex P2, PR 230)

    return _mem.asks_for_more(text)


def latest_state(db: Any, user_id: Optional[int], now: Optional[datetime] = None) -> Optional[dict]:
    """The introduction state of the user's latest provider introduction (among the last turns, not older than ``MAX_AGE``), else None."""
    found = _latest_intro(db, user_id, now)
    return found[1] if found else None


def _recent_rows(db: Any, user_id: Optional[int]) -> list:
    """The user's latest turns, newest first, through the GOVERNED reader (memory.read consent + retention)."""
    from backend.app.core.conversation.memory import ConversationMemory

    return sorted(ConversationMemory(db).get_recent_messages(int(user_id), limit=MAX_TURNS_BACK), key=lambda r: getattr(r, "id", 0), reverse=True)


def _latest_intro(db: Any, user_id: Optional[int], now: Optional[datetime] = None) -> Optional[tuple]:
    """(row, state) of the latest provider introduction among the last turns (not older than ``MAX_AGE``), else None."""
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
            return row, state
    except Exception:  # noqa: BLE001
        logger.info("provider_next_state_failed")
    return None


def _doctor_topic_still_open(db: Any, user_id: Optional[int]) -> bool:
    """The newest meaningful turns are still the doctor talk (care_nav_memory.doctor_topic_open over the same governed reader)."""
    try:
        from backend.app.core.conversation.memory import ConversationMemory
        from backend.app.services.i5 import care_nav_memory as _mem

        rows = sorted(ConversationMemory(db).get_recent_messages(int(user_id), limit=MAX_TURNS_BACK), key=lambda r: getattr(r, "id", 0), reverse=True)
        return _mem.doctor_topic_open(rows, datetime.utcnow())
    except Exception:  # noqa: BLE001
        return False


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
        # a go-ahead continues the next five ONLY when the user's previous turn asked for them: after a newer request (another specialty, a
        # place…) it belongs to THAT request, never to an older introduction (Codex P2, PR 232 round 3)
        confirmed = confirms_search(message) and _previous_ask(db, user_id) == "next"
        if not (wants_next(message) or confirmed):
            return None
        from backend.app.services.i5 import care_navigation_directory as cn

        if cn._has_real_location(message or ""):
            return None  # «another doctor in Shiraz» is a NEW request with its own place
        if cn._declined_provider(message or "") or cn._NOT_A_FIND_REQUEST.search(message or ""):
            return None  # «I don't need another doctor» is a refusal, never a continuation (Codex P2, PR 225)
        state = latest_state(db, user_id)
        if not state or _names_another_search(message or "", state):
            return None
        if _other_subject(message or ""):
            return None  # «a new list of meals» names its own subject (Codex P2, PR 232)
        explicit = bool(_NEXT.search(_once_more_is_again((message or "").strip()))) and bool(_EXPLICIT_DOCTOR.search(message or ""))
        if (confirmed or not explicit) and not _doctor_topic_still_open(db, user_id):
            return None  # a subject-less «recommend some more» after a newer food/sleep talk is about THAT talk (Codex P2, PR 230)
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


def _previous_ask(db: Any, user_id: Optional[int]) -> Optional[str]:
    """What the user's previous turn asked: "next", "again" or None (a go-ahead continues THAT ask)."""
    try:
        rows = _recent_rows(db, user_id)
        said = str(getattr(rows[0], "user_message", "") or "") if rows else ""
        if wants_next(said):
            return "next"
        if wants_again(said):
            return "again"
    except Exception:  # noqa: BLE001
        pass
    return None


def _bullet_block(reply: str) -> str:
    """The doctor lines of a stored introduction («• name — specialty…» and their indented continuation lines), in order - plus the
    «some of these are not verified» warning when the list carried it (a replay never drops a qualification, Codex P2 PR 232)."""
    from backend.app.services.i5 import care_navigation_directory as cn

    warnings = {w.strip() for w in cn.UNVERIFIED_WEB_NOTE.values()}
    out: list = []
    for line in (reply or "").splitlines():
        if line.lstrip().startswith("•"):
            out.append(line)
        elif out and line.startswith("   ") and line.strip():
            out.append(line)
        elif out and line.strip():
            if line.strip() in warnings:
                out.append(line.strip())
            break  # the first ordinary line after the list ends it (closing / care text are not replayed)
    return chr(10).join(out)


class AgainReply:
    """The re-show of the latest introduction: the same doctor lines, the same links, the same introduction state."""

    def __init__(self, message: str, links: tuple, intro_state: dict):
        self.message, self.links, self.intro_state = message, links, intro_state


def again_reply(db: Any, user_id: Optional[int], message: Optional[str], language: str) -> Optional[AgainReply]:
    """D-550 / DEBT-108: «introduce them again» (or a go-ahead right after it) replays the latest introduction exactly; None = not that /
    nothing to replay (the ordinary flow answers)."""
    try:
        if not (wants_again(message) or (confirms_search(message) and _previous_ask(db, user_id) == "again")):
            return None
        from backend.app.services.i5 import care_navigation_directory as cn
        from backend.app.services.i7 import governed_raw

        if cn._has_real_location(message or "") or cn._declined_provider(message or "") or _other_subject(message or ""):
            return None
        found = _latest_intro(db, user_id)
        if not found:
            return None
        row, state = found
        if _names_another_search(message or "", state) or not _doctor_topic_still_open(db, user_id):
            return None
        block = _bullet_block(str(getattr(row, "sedi_response", "") or ""))
        if not block:
            return None
        lang = (language or "en").lower()[:2]
        lang = lang if lang in ("fa", "ar", "en") else "en"
        text = sedi_copy.t("care_nav.again.intro", lang) + chr(10) * 2 + block + chr(10) * 2 + sedi_copy.t("care_nav.again.close", lang)
        return AgainReply(text, tuple(governed_raw.links_of_turn(row)), dict(state))
    except Exception:  # noqa: BLE001
        logger.info("provider_again_failed")
        return None


def guard_no_access(db: Any, user_id: Optional[int], reply: str, language: str, user_message: Optional[str] = None) -> str:
    """D-550 / DEBT-110 (defense in depth): a generated «I have no access / send me the results» inside an open doctor talk is replaced by the
    concrete way forward; any other reply (or any doubt) is returned unchanged. The CURRENT message must itself be part of the doctor talk: the
    first unrelated question after it («هوا چطوره؟») is never answered with the doctor redirect (Codex P2, PR 232)."""
    try:
        if not claims_no_access(reply) or db is None or user_id is None:
            return reply
        if user_message is not None and not is_doctor_message(user_message):
            return reply
        if not _doctor_topic_still_open(db, user_id):
            return reply
        lang = (language or "en").lower()[:2]
        lang = lang if lang in ("fa", "ar", "en") else "en"
        logger.info("provider_no_access_claim_replaced")
        return sedi_copy.t("care_nav.no_access.redirect", lang)
    except Exception:  # noqa: BLE001
        return reply
