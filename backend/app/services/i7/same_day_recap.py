# backend.app.services.i7.same_day_recap
"""P9: the same-day return. Whenever the app is opened again and the user already talked to Sedi TODAY, she opens
like she does on a new day: one warm message that compresses today's earlier chats ("earlier today we talked about A and
B …") and invites the user to continue, hear a new idea, or name their own topic.

Same rules as the cross-day recap (``conversation_recap``): deterministic (no LLM), consent-gated (memory.read),
retention-gated (eligible raw only), read-only, no schema, and it never quotes the user's own words — it maps today's
turns to coarse topic phrases. Fails open: any problem returns ``None`` and the caller keeps the old behaviour.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i7.conversation_recap import _lang, is_trivial_turn, topic_phrase_from_text

MAX_TOPICS = 3
_SCAN = 200


def _todays_turns(db: Session, user_id: int, now: Optional[datetime] = None) -> list[models.Memory]:
    """Eligible raw turns of the user's local today, oldest first."""
    from backend.app.services.i6.consent_service import PERM_READ, has_permission
    from backend.app.services.i7.memory_explorer import _zone, day_bounds_utc
    from backend.app.services.i7.retention import as_utc, query_eligible_raw

    if not has_permission(db, user_id, PERM_READ):
        return []
    zone, _ = _zone(db, user_id)
    moment = (now or datetime.now(timezone.utc)).astimezone(zone)
    start, end = day_bounds_utc(moment.date(), zone)
    rows = [
        m
        for m in query_eligible_raw(db, user_id, limit=_SCAN)
        if m.created_at is not None and start <= as_utc(m.created_at) < end and int(m.user_id) == int(user_id)
    ]
    return sorted(rows, key=lambda m: as_utc(m.created_at))


def build_same_day_recap(
    db: Session, user_id: int, language: Optional[str] = "fa", *, now: Optional[datetime] = None
) -> Optional[dict[str, Any]]:
    """{'topics': [phrase, …], 'count': n, 'open_question': bool} for today's earlier chats, or None when there are none."""
    lang = _lang(language)
    try:
        turns = _todays_turns(db, user_id, now)
    except Exception:
        return None
    meaningful = [m for m in turns if not is_trivial_turn(str(m.user_message or ""))]
    if not meaningful:
        return None
    topics: list[str] = []
    for m in reversed(meaningful):  # newest first, so the freshest threads win the three slots
        try:
            phrase = topic_phrase_from_text(str(m.user_message or ""), lang, privacy="in_app")
        except Exception:
            phrase = None
        if phrase and phrase not in topics:
            topics.append(phrase)
        if len(topics) >= MAX_TOPICS:
            break
    topics.reverse()  # told in the order they happened
    last_reply = str(turns[-1].sedi_response or "").strip()
    return {
        "topics": topics,
        "count": len(meaningful),
        "open_question": last_reply.endswith(("؟", "?", "؟»", "?\"")),
    }


def _join(items: list[str], lang: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    and_word = {"fa": " و ", "ar": " و", "en": " and "}[lang]
    comma = "، " if lang in ("fa", "ar") else ", "
    return comma.join(items[:-1]) + and_word + items[-1]


def same_day_opener(lang: str, hello: str, recap: dict[str, Any]) -> str:
    """One warm message: what we talked about today + continue / something new / your own topic."""
    lang = _lang(lang)
    topics = _join(list(recap.get("topics") or []), lang)
    thread = bool(recap.get("open_question"))
    if lang == "fa":
        what = f"امروز قبلاً درباره‌ی {topics} حرف زدیم" if topics else "امروز قبلاً با هم حرف زده بودیم"
        tail = " و آخرش یه سؤال بی‌جواب مونده بود" if thread else ""
        return f"{hello} {what}{tail}. می‌خوای همون رو ادامه بدیم، یه پیشنهاد تازه بدم، یا خودت بگی چی تو ذهنته؟"
    if lang == "ar":
        what = f"تحدثنا اليوم قبل قليل عن {topics}" if topics else "تحدثنا اليوم قبل قليل"
        tail = " وبقي في النهاية سؤال بلا جواب" if thread else ""
        return f"{hello} {what}{tail}. هل تحب أن نكمل، أم أقترح عليك فكرة جديدة، أم تخبرني بما يشغل بالك؟"
    what = f"Earlier today we talked about {topics}" if topics else "We already talked earlier today"
    tail = ", and one question was left unanswered" if thread else ""
    return f"{hello} {what}{tail}. Want to pick that up, hear a fresh idea from me, or tell me what is on your mind?"


def today_so_far_hint(db: Session, user_id: int, language: Optional[str], *, now: Optional[datetime] = None) -> str:
    """One bounded prompt line for the chat model: today's earlier topics (so a later «continue» has a referent even
    when the turns fall outside the 8-turn window). '' when nothing nameable / on any problem."""
    try:
        recap = build_same_day_recap(db, user_id, language, now=now)
    except Exception:
        return ""
    if not recap or not recap.get("topics"):
        return ""
    lang = _lang(language)
    topics = _join(list(recap["topics"]), lang)
    if lang == "fa":
        return (
            f"[امروز_تا_اینجا] کاربر امروز قبلاً با تو درباره‌ی {topics} حرف زده ({recap['count']} گفتگو). "
            "اگر گفت «ادامه بده» یا «همون»، از همین موضوع‌ها ادامه بده؛ آن‌ها را دوباره خلاصه نکن."
        )
    if lang == "ar":
        return (
            f"[اليوم_حتى_الآن] تحدث المستخدم معك اليوم عن {topics} ({recap['count']} محادثات). "
            "إن قال «تابعي» أو «نفس الموضوع» فتابعي من هذه المواضيع ولا تعيدي تلخيصها."
        )
    return (
        f"[TODAY_SO_FAR] Earlier today the user already talked with you about {topics} ({recap['count']} chats). "
        "If they say \"continue\" or \"that one\", continue from these topics; do not re-summarise them."
    )
