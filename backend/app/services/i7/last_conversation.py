# backend.app.services.i7.last_conversation
"""R-121 (Javad 2026-11-28): Sedi's welcome is drawn from the LATEST chats - what she DID there and what is still open - so the connection
stays continuous. Phone test D-544: after she had introduced five cardiologists the opener said «امروز قبلاً درباره‌ی پیدا کردن پزشک مناسب
برایت صحبت کردیم. از کجا ادامه بدهیم؟», as if nothing had been done.

ONE owner for every opener path (same-day return, first opening of a new day, continuity). It reads the last conversation (the newest turns
that belong together, at most ``MAX_AGE_DAYS`` old) and returns the continuation sentence + ONE question, first match wins:
  1. doctors / centres introduced (the turn's ``provider_intro``) while that is still the latest subject -> «… معرفی کردم. با کدام‌شان تماس
     گرفتی یا وقت گرفتی؟» (the booking step of the care journey, R-105/R-109),
  2. a reminder set from that chat (``UserEvent`` source «conversation») -> its name + time + «ready?» / «done?» (R-084 names the item),
  3. an open care journey started in that chat -> the subject + «how are you now?» (R-109 am.2),
  4. Sedi's own unanswered question -> that question,
  otherwise None and the caller keeps the coarse topic opener.
Deterministic (no model), consent-gated (memory.read), retention-gated (eligible raw only), read-only, no schema; never quotes the user's words
(R-013) - only structured facts (specialty, place, item name). Fails open: any problem returns None.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from backend.app import sedi_copy

logger = logging.getLogger(__name__)

MAX_AGE_DAYS = 7
CHAIN_GAP = timedelta(hours=3)  # turns closer than this belong to the same conversation
_SCAN = 12
_MAX_QUESTION_CHARS = 320
_DIGITS = {"fa": "۰۱۲۳۴۵۶۷۸۹", "ar": "٠١٢٣٤٥٦٧٨٩"}


def _lang(language: Optional[str]) -> str:
    return language if language in ("fa", "ar", "en") else "en"


def _digits(text: str, lang: str) -> str:
    table = _DIGITS.get(lang)
    return "".join(table[int(c)] if table and c.isdigit() and c.isascii() else c for c in str(text))


def _aware(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _chain(rows: list, now: datetime) -> list:
    """The newest turns that belong together (newest first); [] when the newest is older than ``MAX_AGE_DAYS``."""
    rows = [r for r in rows if getattr(r, "created_at", None) is not None]
    if not rows or now - _aware(rows[0].created_at) > timedelta(days=MAX_AGE_DAYS):
        return []
    chain = [rows[0]]
    for row in rows[1:]:
        if _aware(chain[-1].created_at) - _aware(row.created_at) > CHAIN_GAP:
            break
        chain.append(row)
    return chain


def _when(db: Any, user_id: int, moment: datetime, now: datetime, lang: str) -> str:
    """«امروز» / «دیروز» / «آخرین بار» by the user's local calendar."""
    try:
        from backend.app.services.i7.memory_explorer import _zone

        zone, _ = _zone(db, user_id)
        days = (now.astimezone(zone).date() - _aware(moment).astimezone(zone).date()).days
    except Exception:  # noqa: BLE001
        days = (now.date() - _aware(moment).date()).days
    key = "today" if days <= 0 else "yesterday" if days == 1 else "earlier"
    return sedi_copy.t(f"opener.last.when.{key}", lang)


def _doctors(db: Any, user_id: int, rows: list, chain: list, now: datetime, lang: str) -> Optional[str]:
    from backend.app.services.i5 import care_nav_memory
    from backend.app.services.i7 import governed_raw

    from backend.app.services.i5 import care_navigation_directory as cn
    from backend.app.services.i5 import provider_next

    for pos, row in enumerate(chain):
        state = governed_raw.provider_intro_of_turn(row)
        if state is None:
            continue
        if not care_nav_memory.doctor_topic_open(rows, now.replace(tzinfo=None)):
            return None  # a newer subject came after the introduction
        for later in chain[:pos]:  # «I don't need a doctor any more» after the introduction closes it (Codex P2, PR 231)
            said = str(getattr(later, "user_message", "") or "")
            if cn._declined_provider(said) or provider_next._REFUSAL.search(said):
                return None
        spec = str(state.get("specialty") or "").strip()
        if not spec:
            return None
        count = int(state.get("shown") or 0) or min(5, len(state.get("names") or ())) or 5
        if state.get("entity") == "SPECIALTY_CENTER":
            kind = sedi_copy.t("opener.last.kind.center", lang, specialty=spec)
        elif spec.startswith(("پزشک", "طبيب", "general")):
            kind = spec
        else:
            kind = sedi_copy.t("opener.last.kind.doctor", lang, specialty=spec)
        place = " ".join(str(x) for x in (state.get("area"), state.get("city")) if x).strip()
        when = _when(db, user_id, row.created_at, now, lang)
        key = "opener.last.doctors" if place else "opener.last.doctors_noplace"
        return sedi_copy.t(key, lang, when=when, count=_digits(count, lang), kind=kind, place=place)
    return None


def _at(db: Any, user_id: int, starts_at: datetime, now: datetime, lang: str) -> str:
    """«فردا ساعت ۰۹:۰۰» in the user's local time."""
    try:
        from backend.app.services.i7.memory_explorer import _zone

        zone, _ = _zone(db, user_id)
    except Exception:  # noqa: BLE001
        zone = timezone.utc
    local = _aware(starts_at).astimezone(zone)
    days = (local.date() - now.astimezone(zone).date()).days
    clock = _digits(local.strftime("%H:%M"), lang)
    day = {0: "today", 1: "tomorrow", -1: "yesterday"}.get(days)
    if day is None:
        return sedi_copy.t("opener.last.at.clock", lang, clock=clock)
    return sedi_copy.t(f"opener.last.at.{day}", lang, clock=clock)


def _reminder(db: Any, user_id: int, chain: list, now: datetime, lang: str) -> Optional[str]:
    from backend.app import models

    start = _aware(chain[-1].created_at) - timedelta(minutes=2)
    end = _aware(chain[0].created_at) + timedelta(minutes=2)
    events = (
        db.query(models.UserEvent)
        .filter(models.UserEvent.user_id == int(user_id), models.UserEvent.source == "conversation", models.UserEvent.status == "scheduled")
        .order_by(models.UserEvent.created_at.desc())
        .limit(10)
        .all()
    )
    for ev in events:
        created = _aware(ev.created_at)
        if created is None or not (start <= created <= end) or not (ev.title or "").strip() or ev.starts_at is None:
            continue
        from backend.app.services.i10.event_reminder_i10_adapter import event_starts_utc

        starts = _aware(event_starts_utc(ev))  # starts_at is the event's LOCAL wall clock (its own timezone), not UTC (Codex P2, PR 231)
        if starts is None:
            continue
        when = _when(db, user_id, ev.created_at, now, lang)
        at = _at(db, user_id, starts, now, lang)
        key = "opener.last.reminder_future" if starts > now else "opener.last.reminder_past"
        return sedi_copy.t(key, lang, when=when, title=" ".join(str(ev.title).split())[:80], at=at)
    return None


def _care(db: Any, user_id: int, chain: list, now: datetime, lang: str) -> Optional[str]:
    from backend.app.services.i10 import commitment_followup as cf
    from backend.app.services.i7.conversation_recap import is_trivial_turn, topic_phrase_from_text

    start = _aware(chain[-1].created_at) - timedelta(minutes=2)
    end = _aware(chain[0].created_at) + timedelta(minutes=2)
    started_here = any(
        getattr(t, "created_at", None) is not None and start <= _aware(t.created_at) <= end for t in cf._open_journey_tasks(db, user_id)
    )
    if not started_here:
        return None
    when = _when(db, user_id, chain[0].created_at, now, lang)
    for row in chain:
        said = str(getattr(row, "user_message", "") or "")
        if is_trivial_turn(said):
            continue
        topic = topic_phrase_from_text(said, lang, privacy="in_app")
        if topic:
            return sedi_copy.t("opener.last.care", lang, when=when, topic=topic)
    return sedi_copy.t("opener.last.care_generic", lang, when=when)


def _question(db: Any, user_id: int, chain: list, now: datetime, lang: str) -> Optional[str]:
    from backend.app.services.intelligence.answer_binding import last_question

    question = (last_question(str(chain[0].sedi_response or "")) or "").strip(" \"'«»")
    if not question or len(question) > _MAX_QUESTION_CHARS:
        return None
    return sedi_copy.t("opener.last.question", lang, when=_when(db, user_id, chain[0].created_at, now, lang), question=question)


def continuation(db: Any, user_id: int, language: Optional[str], *, now: Optional[datetime] = None) -> Optional[str]:
    """The sentence that continues the last conversation (+ ONE question), or None (the caller keeps its topic opener)."""
    lang = _lang(language)
    try:
        from backend.app.services.i6.consent_service import PERM_READ, has_permission
        from backend.app.services.i7.retention import query_eligible_raw

        if db is None or not has_permission(db, user_id, PERM_READ):
            return None
        moment = _aware(now) or datetime.now(timezone.utc)
        rows = sorted(
            [r for r in (query_eligible_raw(db, user_id, limit=_SCAN) or []) if int(getattr(r, "user_id", user_id) or user_id) == int(user_id)],
            key=lambda r: (_aware(getattr(r, "created_at", None)) or moment, getattr(r, "id", 0) or 0),
            reverse=True,
        )
        chain = _chain(rows, moment)
        if not chain:
            return None
        for step in (
            lambda: _doctors(db, user_id, rows, chain, moment, lang),
            lambda: _reminder(db, user_id, chain, moment, lang),
            lambda: _care(db, user_id, chain, moment, lang),
            lambda: _question(db, user_id, chain, moment, lang),
        ):
            try:
                text = step()
            except Exception:  # noqa: BLE001 - one source failing never hides the next
                logger.info("last_conversation_step_failed")
                text = None
            if text:
                return text
        return None
    except Exception:  # noqa: BLE001
        logger.info("last_conversation_failed")
        return None
