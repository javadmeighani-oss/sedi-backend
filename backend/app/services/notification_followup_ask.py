"""R-070 / R-072 (step 2C-1): Sedi asks the REASON herself in chat, and follows up a notification nobody answered.

Two kinds of pending question are found on the server and asked ONCE per notification in the FIRST message of the chat:

* ``reason``     - the user pressed a negative reaction (Dislike / «later» / swipe-away / «not done») and gave no reason.
                   Sedi asks why, the answer is read into a BOUNDED reason (busy_now / rest_time / not_in_mood / too_frequent /
                   irrelevant / unclear / wrong_timing / not_helpful) and recorded through the SAME ledger path as the tray
                   answer (``record_notification_interaction``), so timing / text / frequency adapt (R-023, never a stop).
* ``unanswered`` - an ACTION notification (reminder, medication, plan follow-up, post-event) got no answer for about a day:
                   Sedi asks whether it was done. The answer is kept in the ledger and tells the model how to continue; the
                   owner-level completion (medication / plan / event) belongs to the owner packages (2D / 2E).

Guardrails: the morning digest and the commitment loop (own ladder) are never asked; at most ONE question per local day;
reasons only for notifications 3-48 h old, unanswered ones 24-72 h old; a thing already completed elsewhere (event done on
the schedule page, dose confirmed, plan item completed) is never asked about; every function is fail-open (chat never breaks).
The user's own reply is stored as a normal I7 chat turn by the chat flow; this module adds the ledger rows
``notification_followup_asked`` / ``notification_followup_result``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models, sedi_copy

logger = logging.getLogger(__name__)

ASKED_EVENT = "notification_followup_asked"
RESULT_EVENT = "notification_followup_result"
_SOURCE = "system"
_SOURCE_TYPE = "notification_followup"

_REASON_MIN_AGE = timedelta(hours=3)
_REASON_MAX_AGE = timedelta(hours=48)
_UNANSWERED_MIN_AGE = timedelta(hours=24)
_UNANSWERED_MAX_AGE = timedelta(hours=72)
_ANSWER_WINDOW = timedelta(hours=6)  # the reply must come in the same chat session as the question
_MAX_REPLY_WORDS = 25
_SCAN_CAP = 400

_NEGATIVE_EVENTS = frozenset({"notification_dislike", "notification_not_now", "notification_talk_later", "notification_dislike_reason"})
# any of these means the user already ANSWERED / engaged with the notification
_ANSWERED_EVENTS = frozenset(
    {
        "notification_done", "notification_like", "notification_dislike", "notification_dislike_reason", "notification_not_now",
        "notification_talk_later", "notification_open_chat", "chat_message", "notification_ack", "notification_assured",
    }
)
_ACTION_KEYS = frozenset({"reminder", "medication", "plan_nutrition", "plan_exercise", "post_event"})
_EXCLUDED_TEMPLATES = frozenset({"commitment_follow_up", "assurance_follow_up"})  # each has its own ladder / is the one assurance
_EXCLUDED_FAMILIES = frozenset({"DAILY_WELLNESS_DIGEST"})
_BOUNDED_TIMING = ("busy_now", "rest_time", "not_in_mood")


@dataclass(frozen=True)
class Pending:
    notification_id: int
    kind: str  # "reason" | "unanswered"
    subject_key: str


def _lang(user: models.User) -> str:
    from backend.app.services import a3_session_open as so

    return so._lang(user)


def _naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _meta(raw: Any) -> dict:
    try:
        loaded = json.loads(raw) if isinstance(raw, str) else (raw or {})
        return loaded if isinstance(loaded, dict) else {}
    except (TypeError, ValueError):
        return {}


def _subject_key(notification: models.Notification) -> str:
    from backend.app.services.notification_openers import _key_for

    return _key_for(notification) or "other"


def _excluded(notification: models.Notification) -> bool:
    return (notification.template_key or "") in _EXCLUDED_TEMPLATES or (notification.semantic_family or "") in _EXCLUDED_FAMILIES


def _asked_today(db: Session, user_id: int, now: datetime) -> bool:
    """At most ONE follow-up question per local day (R-070). Any read problem counts as «asked» (fail-closed: never nag)."""
    try:
        from backend.app.services.i7.memory_explorer import _zone

        zone, _tz = _zone(db, user_id)
        local_midnight = now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
        start = local_midnight.astimezone(timezone.utc).replace(tzinfo=None)
        return (
            db.query(models.InteractionEvent.id)
            .filter(
                models.InteractionEvent.user_id == user_id,
                models.InteractionEvent.event_type == ASKED_EVENT,
                models.InteractionEvent.created_at >= start,
            )
            .first()
            is not None
        )
    except Exception:
        return True


def _completed_elsewhere(db: Session, user_id: int, notification: models.Notification, key: str, now_naive: datetime) -> bool:
    """True when the thing the notification asked about is already done / cannot be asked about. Unsure -> True (never ask)."""
    try:
        if key == "reminder":
            source_id = str(notification.source_id or "").strip()
            if not source_id.isdigit():
                return True
            event = db.query(models.UserEvent).filter(models.UserEvent.id == int(source_id), models.UserEvent.user_id == user_id).first()
            if event is None or (event.status or "") in ("completed", "cancelled", "missed"):
                return True
            from backend.app.services.i10.event_reminder_i10_adapter import event_starts_utc

            starts = event_starts_utc(event)  # starts_at is local wall-clock time of the event's own zone
            return starts is not None and starts > now_naive
        if key == "medication":
            occ = (
                db.query(models.MedicationDoseOccurrence)
                .filter(models.MedicationDoseOccurrence.source_notification_id == notification.id, models.MedicationDoseOccurrence.user_id == user_id)
                .first()
            )
            return occ is None or occ.state == "CONFIRMED_TAKEN"
        if key in ("plan_nutrition", "plan_exercise"):
            decision = (
                db.query(models.I10NotificationDecision)
                .filter(
                    models.I10NotificationDecision.notification_id == notification.id,
                    models.I10NotificationDecision.recipient_user_id == user_id,
                    models.I10NotificationDecision.decision == "SEND",
                )
                .order_by(models.I10NotificationDecision.id.desc())
                .first()
            )
            sid = str(getattr(decision, "source_id", "") or "").strip() if decision is not None else ""
            if not sid.isdigit():
                return True
            action = (
                db.query(models.I8OperationalPlanAction)
                .filter(models.I8OperationalPlanAction.id == int(sid), models.I8OperationalPlanAction.user_id == user_id)
                .first()
            )
            return action is None or action.status != "ACTIVE"
        from backend.app.services.i10.event_outcome import _already_recorded, event_of_notification

        found = event_of_notification(db, notification, user_id)  # post_event: the outcome may already be recorded
        return found is None or _already_recorded(db, user_id, found[0])
    except Exception:
        return True


def pick_pending(db: Session, user: models.User, *, now: Optional[datetime] = None) -> Optional[Pending]:
    """The ONE notification Sedi should ask about now, or None. Read-only; fail-open."""
    try:
        now = now or datetime.now(timezone.utc)
        user_id = int(user.id)
        if _asked_today(db, user_id, now):
            return None
        now_naive = _naive_utc(now)
        events = (
            db.query(models.InteractionEvent)
            .filter(
                models.InteractionEvent.user_id == user_id,
                models.InteractionEvent.source_notification_id.isnot(None),
                models.InteractionEvent.created_at >= now_naive - _UNANSWERED_MAX_AGE - timedelta(hours=1),
            )
            .order_by(models.InteractionEvent.id.desc())
            .limit(_SCAN_CAP)
            .all()
        )
        by_notification: dict[int, list] = {}
        for ev in events:
            by_notification.setdefault(int(ev.source_notification_id), []).append(ev)
        notifications = (
            db.query(models.Notification)
            .filter(
                models.Notification.user_id == user_id,
                models.Notification.created_at >= now_naive - _UNANSWERED_MAX_AGE - timedelta(hours=12),
                models.Notification.status.in_(("sent", "delivered")),
            )
            .order_by(models.Notification.id.asc())
            .limit(_SCAN_CAP)
            .all()
        )
        reason_candidates: list[Pending] = []
        unanswered_candidates: list[Pending] = []
        for n in notifications:
            if _excluded(n):
                continue
            evs = by_notification.get(int(n.id), [])
            types = {e.event_type for e in evs}
            if ASKED_EVENT in types:
                continue  # once per notification
            sent = _naive_utc(n.sent_at or n.created_at)
            if sent is None:
                continue
            age = now_naive - sent
            key = _subject_key(n)
            if types & _NEGATIVE_EVENTS:
                known_reason = "notification_dislike_reason" in types or any(
                    (_meta(e.metadata_json).get("reason") or "other") != "other" for e in evs if e.event_type in _NEGATIVE_EVENTS
                )
                if not known_reason and _REASON_MIN_AGE <= age <= _REASON_MAX_AGE:
                    reason_candidates.append(Pending(int(n.id), "reason", key))
                continue
            if key in _ACTION_KEYS and not (types & _ANSWERED_EVENTS) and _UNANSWERED_MIN_AGE <= age <= _UNANSWERED_MAX_AGE:
                if not _completed_elsewhere(db, user_id, n, key, now_naive):
                    unanswered_candidates.append(Pending(int(n.id), "unanswered", key))
        # the user's explicit reaction comes first; within a kind the oldest is the most urgent (notifications are id-ordered)
        if reason_candidates:
            return reason_candidates[0]
        if unanswered_candidates:
            return unanswered_candidates[0]
        return None
    except Exception:
        logger.exception("[R-070] pick_pending skipped")
        return None


def question_text(pending: Pending, lang: str) -> str:
    if pending.kind == "unanswered" and pending.subject_key == "post_event":
        return sedi_copy.t("ask.outcome", lang)
    subject = sedi_copy.t(f"ask.subject.{pending.subject_key}", lang, default="en")
    key = "ask.reason" if pending.kind == "reason" else "ask.unanswered"
    return sedi_copy.t(key, lang, subject=subject)


def mark_asked(db: Session, user_id: int, pending: Pending, question: str) -> None:
    """Ledger row: this notification was asked about (once). Flushed, not committed (the caller commits)."""
    db.add(
        models.InteractionEvent(
            user_id=user_id,
            event_type=ASKED_EVENT,
            source=_SOURCE,
            source_notification_id=pending.notification_id,
            source_type=_SOURCE_TYPE,
            metadata_json=json.dumps({"kind": pending.kind, "subject": pending.subject_key, "question": question[:400]}, ensure_ascii=False),
        )
    )
    db.flush()


def compose_opener(db: Session, user: models.User, greeting: str, lang: str) -> Optional[str]:
    """greeting + the pending question (ONE question in the whole opener), or None when nothing is pending."""
    pending = pick_pending(db, user)
    if pending is None:
        return None
    question = question_text(pending, lang)
    mark_asked(db, int(user.id), pending, question)
    db.commit()
    return f"{greeting.strip()}\n\n{question}".strip()


# ---- reading the answer -------------------------------------------------------------------------------------------------
def _fold(text: str) -> str:
    from backend.app.services.notification_openers import _fold as fold

    return fold(text)


def _re(*parts: str) -> re.Pattern:
    from backend.app.services.notification_openers import _fold_letters

    return re.compile("(?:" + "|".join(_fold_letters(p) for p in parts) + ")")


# (reason, intrinsic phrases whose own words already carry a negation or the whole meaning, words/phrases that a nearby
# negation turns around: «سرم شلوغ نبود», «It was not bad timing», «There are not too many messages» are DENIALS - Codex P2 PR #146)
_REASON_RULES = (
    ("busy_now",
     _re(r"وقت ندا", r"no time", r"ما عندي وقت", r"لم يكن عندي وقت"),
     _re(r"سرم شلوغ", r"کار داشتم", r"کار دارم", r"عندي عمل", r"درگیر", r"مشغول", r"شلوغ", r"\bbusy\b", r"\bworking\b", r"\bmeeting\b", r"منشغل")),
    ("rest_time",
     None,
     _re(r"وقت استراحت", r"وقت خواب", r"خواب بودم", r"خوابیده بودم", r"rest time", r"bedtime", r"was sleeping", r"was asleep", r"وقت الراحه",
         r"وقت النوم", r"كنت نائم", r"استراحت", r"\brest\b", r"\bnap\b", r"راحه")),
    ("not_in_mood",
     _re(r"حوصله ندا", r"حوصله نبود", r"میل ندا", r"دلم نمی ?خواست", r"دلم نخواست", r"not in the mood", r"didn t feel like", r"did not feel like",
         r"wasn t in the mood", r"can t be bothered", r"ما عندي مزاج", r"ما عندي رغبه", r"قله رغبه", r"ما حبيت", r"بلا رغبه"),
     None),
    ("too_frequent",
     None,
     _re(r"زیاد پیام", r"خیلی پیام", r"مدام پیام", r"زیادی", r"too many", r"too often", r"too frequent", r"كثير", r"كثره")),
    ("irrelevant",
     _re(r"ربطی ندار", r"مربوط نیست", r"به من نمی ?خور", r"نیازی ندار", r"لازم ندار", r"not relevant", r"don t need", r"not for me", r"لا يخصني",
         r"ما يخصني", r"لا احتاج"),
     _re(r"irrelevant")),
    ("unclear",
     _re(r"نفهمیدم", r"نامفهوم", r"didn t understand", r"did not understand", r"ما فهمت", r"غير واضح"),
     _re(r"گنگ", r"مبهم", r"unclear", r"confusing")),
    ("wrong_timing",
     _re(r"وقتش مناسب نبود", r"وقت مناسب نبود", r"not a good time", r"وقت غير مناسب"),
     _re(r"بد موقع", r"بد وقت", r"bad timing", r"wrong time", r"توقيت")),
    ("not_helpful",
     _re(r"به درد نخور", r"مفید نبود", r"کمکی نکرد", r"بی ?فایده", r"not helpful", r"didn t help", r"ما فادني", r"غير مفيد", r"بلا فايده"),
     _re(r"useless")),
)
_NEGATION_NEAR = _re(r"نبود", r"نیستم", r"نبودم", r"نیست", r"\bnot\b", r"\bwasn t\b", r"\bn t\b", r"\bnever\b", r"\bno\b", r"لم ", r"لست", r"ليس", r"ما كنت")


def _negated_near(folded: str, start: int, end: int) -> bool:
    """A negation right after («درگیر نبودم») or right before («I was not busy») the matched state word."""
    window = " ".join(folded[:start].split()[-4:] + ["|"] + folded[end:].split()[:3])
    return bool(_NEGATION_NEAR.search(window))


def parse_reason(message: str) -> Optional[str]:
    """A short free-text answer to «why?» as one bounded reason, or None. Cautious: a question, a long text, an answer that
    names a timing reason together with a non-timing one, or a negated state («درگیر نبودم») is never guessed."""
    raw = message or ""
    folded = _fold(raw).replace("ة", "ه")  # Arabic teh marbuta meets heh (the patterns are written with heh)
    if not folded or len(folded.split()) > _MAX_REPLY_WORDS or "?" in raw or "؟" in raw:
        return None
    matched: list[str] = []
    for name, intrinsic, checked in _REASON_RULES:
        hit = intrinsic is not None and bool(intrinsic.search(folded))
        if not hit and checked is not None:
            for m in checked.finditer(folded):
                if not _negated_near(folded, m.start(), m.end()):
                    hit = True
                    break
        if hit:
            matched.append(name)
    if not matched:
        return None
    timing = [name for name in matched if name in _BOUNDED_TIMING]
    if len(timing) == len(matched):
        return timing[0]  # several «not now» reasons: still «not now»; the first by priority
    return matched[0] if len(matched) == 1 else None


# ---- the reply in the chat ----------------------------------------------------------------------------------------------
def _latest_open_ask(db: Session, user_id: int, now_naive: datetime) -> Optional[models.InteractionEvent]:
    ask = (
        db.query(models.InteractionEvent)
        .filter(models.InteractionEvent.user_id == user_id, models.InteractionEvent.event_type == ASKED_EVENT)
        .order_by(models.InteractionEvent.id.desc())
        .first()
    )
    if ask is None or ask.created_at is None or now_naive - _naive_utc(ask.created_at) > _ANSWER_WINDOW:
        return None
    answered = (
        db.query(models.InteractionEvent.id)
        .filter(
            models.InteractionEvent.user_id == user_id,
            models.InteractionEvent.event_type == RESULT_EVENT,
            models.InteractionEvent.source_notification_id == ask.source_notification_id,
        )
        .first()
    )
    return None if answered is not None else ask


def _record_reason(db: Session, user_id: int, notification: models.Notification, reason: str) -> bool:
    """Same ledger path as the tray answer: bounded reason -> DISLIKE_REASON event -> adaptation (never a stop)."""
    try:
        from backend.app.services.i10.interaction_recorder import record_notification_interaction

        with db.begin_nested():
            record_notification_interaction(
                db, notification=notification, recipient_user_id=user_id, payload={"reaction": "dislike", "reason": reason}
            )
        return True
    except Exception:
        logger.exception("[R-070] reason not recorded")
        return False


def answer_pending(db: Session, user_id: int, message: str, *, now: Optional[datetime] = None) -> Optional[dict]:
    """The user's FIRST message after Sedi's follow-up question. Returns the chat context for the model (or None when there is
    no open question). The reply is read once: a result row is always written so it is never read twice."""
    try:
        now_naive = _naive_utc(now or datetime.now(timezone.utc))
        ask = _latest_open_ask(db, user_id, now_naive)
        if ask is None:
            return None
        meta = _meta(ask.metadata_json)
        kind = str(meta.get("kind") or "")
        notification = (
            db.query(models.Notification)
            .filter(models.Notification.id == ask.source_notification_id, models.Notification.user_id == user_id)
            .first()
        )
        result = "unparsed"
        recorded = False
        if kind == "reason":
            reason = parse_reason(message)
            if reason is not None and notification is not None:
                recorded = _record_reason(db, user_id, notification, reason)
                result = f"reason:{reason}" if recorded else "unparsed"
        elif kind == "unanswered":
            from backend.app.services.notification_openers import parse_followup_reply

            if meta.get("subject") == "post_event":
                from backend.app.services.i10.event_outcome import apply_chat_answer as record_outcome

                result = (record_outcome(db, notification, user_id, message) if notification is not None else None) or "unparsed"
                verdict = None
            else:
                verdict = parse_followup_reply(message)
            if verdict is not None:
                result = "done" if verdict[0] == "done" else f"not_done:{verdict[1]}"
                if notification is not None:
                    # R-070 (2D): the answer is recorded through the OWNER (dose / event / plan item) and I7, not only the ledger
                    from backend.app.services.i10.action_done import apply_chat_answer as record_owner

                    record_owner(db, notification, user_id, verdict)
        db.add(
            models.InteractionEvent(
                user_id=user_id,
                event_type=RESULT_EVENT,
                source=_SOURCE,
                source_notification_id=ask.source_notification_id,
                source_type=_SOURCE_TYPE,
                metadata_json=json.dumps({"kind": kind, "result": result, "recorded": recorded}, ensure_ascii=False),
            )
        )
        db.flush()
        return {
            "template_key": "followup_reason_ask" if kind == "reason" else "followup_unanswered_ask",
            "opening_message": str(meta.get("question") or "")[:256],
            "followup_result": result,
        }
    except Exception:
        logger.exception("[R-070] answer_pending skipped")
        return None
