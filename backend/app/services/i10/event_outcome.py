"""R-071 / R-072 (step 2E): the OUTCOME of an event is asked, understood and remembered.

Every event has a follow-up path: reminders of everyday events get the 2D assurance after the reminder; appointments and
meetings (medical / care visits, lab, imaging, surgery, physiotherapy, work meetings, exams, deadlines - anything whose
domain is not «other») get THIS loop after they end:

* ``create_due_event_outcome_tasks`` - on the existing follow-up worker tick, ONE post-event task (CareFollowUpTask kind
  ``post_event``) about 30 minutes after the event ends; the lock-screen text stays generic, the in-app opener asks the question
  that fits THAT kind of event (what the doctor said, when the lab result is ready, how the meeting went ...);
* ``apply_chat_answer`` - the user's first reply is read cautiously (attended / missed + bounded reason) and recorded through
  the owner (UserEvent completed) and I7 (``user_done`` / ``user_not_done``); the reply itself is an ordinary I7 chat turn
  and the model is told how to continue (restate advice as ONE concrete step, ask once for a result / next-visit date).

If the user does not answer for about a day, the 2C-1 follow-up asks again in the FIRST chat message (R-072). Recurring events
are excluded (they are recorded per occurrence). Fail-open throughout; nothing here may break the worker tick or the chat.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models, sedi_copy

logger = logging.getLogger(__name__)

POST_EVENT_KIND = "post_event"
POST_EVENT_TEMPLATE_KEY = "post_event_follow_up"
_DUE_AFTER_END = timedelta(minutes=30)
_EXPIRES_AFTER_END = timedelta(hours=24)
_SCAN_CAP = 300
_SKIP_TYPES = frozenset({"memory_note", "important_day", "birthday"})
_DURATION_MIN = {"visit": 60, "lab": 30, "meeting": 60, "exam": 120, "deadline": 0, "event": 60}
_MAX_TITLE = 80

_LAB_TYPES = frozenset({"lab_test"})
_EXAM_TYPES = frozenset({"exam"})
_DEADLINE_TYPES = frozenset({"deadline"})


def outcome_kind(event: models.UserEvent) -> Optional[str]:
    """The kind of question that fits the event, or None when it is not an appointment / meeting (the 2D assurance owns it)."""
    from backend.app.services.i7 import user_done

    etype = (event.event_type or "").strip()
    if etype in _SKIP_TYPES or event.recurrence_rule:
        return None
    domain = user_done.domain_for("event", etype, event.event_domain)
    if domain == "other":
        return None
    if etype in _LAB_TYPES:
        return "lab"
    if etype in _EXAM_TYPES:
        return "exam"
    if etype in _DEADLINE_TYPES:
        return "deadline"
    return "visit" if domain == "appointment" else "meeting"


def _starts_utc(event: models.UserEvent) -> Optional[datetime]:
    from backend.app.services.i10.event_reminder_i10_adapter import event_starts_utc

    return event_starts_utc(event)


def end_utc(event: models.UserEvent, kind: str) -> Optional[datetime]:
    """Naive UTC end of the event: its own end time, else start + a default length for its kind."""
    start = _starts_utc(event)
    if start is None:
        return None
    if event.ends_at is not None and event.starts_at is not None:
        length = event.ends_at - event.starts_at
        if length >= timedelta(0):
            return start + length
    return start + timedelta(minutes=_DURATION_MIN.get(kind, 60))


def _naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _existing_event_ids(db: Session, user_id: int) -> set:
    from backend.app.services.i10.contextual_followup_task_meta import parse_bounded_meta

    rows = (
        db.query(models.CareFollowUpTask)
        .filter(models.CareFollowUpTask.user_id == user_id, models.CareFollowUpTask.created_at >= datetime.utcnow() - timedelta(days=4))
        .all()
    )
    return {int(m.user_event_id) for m in (parse_bounded_meta(r.description)[1] for r in rows) if m.follow_up_kind == POST_EVENT_KIND and m.user_event_id}


def create_due_event_outcome_tasks(db: Session, *, now: Optional[datetime] = None) -> int:
    """Sweep on the existing worker tick: an appointment / meeting that ended 30 min .. 24 h ago and has no post-event task yet
    gets ONE. Returns how many were created. Fail-open."""
    created = 0
    try:
        from backend.app.services.i10.contextual_followup_task_meta import BoundedFollowUpMeta, pack_description
        from backend.app.services.i10.contextual_followup_types import FollowUpTaskSource, FollowUpTaskStatus

        now_naive = _naive_utc(now or datetime.now(timezone.utc))
        # starts_at is local wall-clock time of the event's own zone: widen the SQL window by a day, decide exactly in Python
        lower = now_naive - _EXPIRES_AFTER_END - timedelta(days=1)
        upper = now_naive + timedelta(days=1)
        base = db.query(models.UserEvent).filter(
            models.UserEvent.starts_at >= lower,
            models.UserEvent.starts_at <= upper,
            models.UserEvent.status.in_(("scheduled", "confirmed", "completed")),
            models.UserEvent.recurrence_rule.is_(None),
        )
        rows: list = []
        last_id = 0
        for _batch in range(10):
            chunk = base.filter(models.UserEvent.id > last_id).order_by(models.UserEvent.id.asc()).limit(_SCAN_CAP).all()
            rows.extend(chunk)
            if len(chunk) < _SCAN_CAP:
                break
            last_id = int(chunk[-1].id)
        known: dict = {}
        for ev in rows:
            kind = outcome_kind(ev)
            if kind is None:
                continue
            end = end_utc(ev, kind)
            if end is None or not (end + _DUE_AFTER_END <= now_naive <= end + _EXPIRES_AFTER_END):
                continue
            uid = int(ev.user_id)
            if uid not in known:
                known[uid] = _existing_event_ids(db, uid)
            if int(ev.id) in known[uid]:
                continue
            meta = BoundedFollowUpMeta(follow_up_kind=POST_EVENT_KIND, user_event_id=int(ev.id), domain=kind)
            ts = datetime.utcnow()
            with db.begin_nested():
                db.add(
                    models.CareFollowUpTask(
                        user_id=uid, title=(ev.title or kind)[:256], description=pack_description(None, meta),
                        status=FollowUpTaskStatus.OPEN.value, due_at=now_naive, source=FollowUpTaskSource.POST_EVENT.value,
                        created_at=ts, updated_at=ts,
                    )
                )
            known[uid].add(int(ev.id))
            created += 1
        if created:
            db.flush()
    except Exception:
        logger.exception("[R-071] event outcome sweep skipped")
    return created


def post_event_may_send(db: Session, task: models.CareFollowUpTask, now: datetime) -> bool:
    """The post-event question obeys the send guard like every Sedi notification; it waits, and is dropped 24 h after the event
    (a late «how did it go» is no longer natural - the chat follow-up of 2C-1 still asks in the first message)."""
    from backend.app.services.i10.contextual_followup_task_meta import parse_bounded_meta
    from backend.app.services.notifications.send_guard_v1 import can_send_v1

    now_naive = _naive_utc(now)
    meta = parse_bounded_meta(task.description)[1]
    event = (
        db.query(models.UserEvent).filter(models.UserEvent.id == int(meta.user_event_id or 0), models.UserEvent.user_id == task.user_id).first()
        if meta.user_event_id
        else None
    )
    if event is None or event.status == "cancelled":
        task.status = "cancelled"
        task.updated_at = datetime.utcnow()
        return False
    kind = meta.domain or outcome_kind(event) or "event"
    end = end_utc(event, kind)
    if end is not None and now_naive - end > _EXPIRES_AFTER_END:
        task.status = "cancelled"
        task.updated_at = datetime.utcnow()
        return False
    if end is not None and now_naive < end + _DUE_AFTER_END:
        return False  # the event was moved into the future: wait until it has ended (the task stays pending)
    return bool(can_send_v1(db, task.user_id, "companion", POST_EVENT_TEMPLATE_KEY, "normal", now_naive).get("allowed"))


# ---- the notification -> the event ------------------------------------------------------------------------------------
def task_of_notification(db: Session, notification: models.Notification, user_id: int) -> Optional[models.CareFollowUpTask]:
    ref = str(notification.source_id or "").strip()
    if not ref.isdigit():
        return None
    return db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.id == int(ref), models.CareFollowUpTask.user_id == user_id).first()


def event_of_notification(db: Session, notification: models.Notification, user_id: int) -> Optional[tuple]:
    """(event, kind) behind a post-event notification, ownership checked; None otherwise."""
    from backend.app.services.i10.contextual_followup_task_meta import parse_bounded_meta

    task = task_of_notification(db, notification, user_id)
    if task is None:
        return None
    meta = parse_bounded_meta(task.description)[1]
    if meta.follow_up_kind != POST_EVENT_KIND or not meta.user_event_id:
        return None
    event = db.query(models.UserEvent).filter(models.UserEvent.id == int(meta.user_event_id), models.UserEvent.user_id == user_id).first()
    if event is None:
        return None
    return event, (meta.domain or outcome_kind(event) or "event")


def opener(db: Session, user_id: int, notification: models.Notification, lang: str) -> Optional[str]:
    """The in-app question for THIS kind of event, naming the user's own event (the push itself stays generic)."""
    found = event_of_notification(db, notification, user_id)
    if found is None:
        return None
    event, kind = found
    title = " ".join((event.title or "").split())[:_MAX_TITLE]
    if not title:
        return None
    return sedi_copy.t(f"session.origin.post_event.{kind if kind in _DURATION_MIN else 'event'}", lang, title=title)


# ---- reading the reply ------------------------------------------------------------------------------------------------
def _fold(text: str) -> str:
    from backend.app.services.notification_openers import _fold as fold

    return fold(text).replace("ة", "ه")


def _p(*parts: str) -> re.Pattern:
    from backend.app.services.notification_openers import _fold_letters

    return re.compile("(?:" + "|".join(_fold_letters(p).replace("ة", "ه") for p in parts) + ")")


_MISSED = _p(
    r"نرفتم", r"نتونستم", r"نتوانستم", r"نشد", r"نرسیدم", r"کنسل", r"لغو", r"عقب افتاد", r"به تعویق", r"نیامد", r"برگزار نشد", r"نرفت",
    r"انجام ندادم", r"شرکت نکردم", r"حاضر نشدم",
    r"\bcancel", r"postponed", r"didn t go", r"did not go", r"couldn t", r"could not", r"missed", r"didn t happen", r"did not happen", r"never went",
    r"did not attend", r"didn t attend", r"have not", r"haven t", r"did not do", r"didn t do",
    r"لم اذهب", r"لم استطع", r"تاجل", r"الغي", r"لم يتم", r"فاتني", r"لم احضر", r"لم انجز",
)
# affirmative EVIDENCE that the event took place (a reply without it is never read as attendance - Codex P1 on PR #148)
_ATTENDED = _p(
    r"\bرفتم\b", r"\bانجام شد\b", r"\bانجام دادم\b", r"\bگذشت\b", r"\bخوب بود\b", r"\bدکتر گفت\b", r"\bپزشک گفت\b", r"\bبرگزار شد\b",
    r"\bتحویل دادم\b", r"\bتجویز کرد\b", r"\bنتیجه اش\b", r"\bجوابش\b",
    r"\bwent\b", r"it went", r"\bdone\b", r"(?:doctor|dr|he|she|they) said", r"told me", r"prescribed", r"\battended\b", r"was fine", r"finished",
    r"handed (?:it )?in", r"submitted",
    r"\bذهبت\b", r"\bتمت\b", r"كان جيدا", r"\bقال\b", r"\bسلمت\b", r"وصف لي",
)
# any negation in the reply: without an explicit «missed» pattern it is ambiguous, so nothing is recorded
_NEGATION = _p(
    r"\bنه\b", r"نشد", r"نکرد", r"نرفت", r"نتون", r"نتوان", r"نداد", r"نداشت", r"\bنیست\b", r"\bنبود", r"نیامد", r"نگرفت", r"\bهنوز\b",
    r"\bnot\b", r"\bno\b", r"\bnever\b", r"\bn t\b", r"\byet\b", r"\bلم\b", r"\bلا\b", r"\bليس\b", r"\bلن\b",
)
_MAX_WORDS = 60


def _negated_near(folded: str, start: int, end: int) -> bool:
    window = " ".join(folded[:start].split()[-4:] + ["|"] + folded[end:].split()[:3])
    return bool(_NEGATION.search(window))


def parse_attendance(message: str) -> Optional[tuple]:
    """('attended', None) / ('missed', reason) for a reply to «how did it go?», or None. Cautious by design: attendance needs
    AFFIRMATIVE evidence («رفتم», «it went», «the doctor said»); a question, a negation without an explicit «missed» pattern, a reply
    that names both, or any unrelated text records nothing. A permanent I7 «done» must never be written from a guess."""
    from backend.app.services.notification_openers import _REASONS

    raw = message or ""
    folded = _fold(raw)
    if not folded or "?" in raw or "؟" in raw:
        return None
    if len(folded.split()) > _MAX_WORDS:
        return None
    missed = bool(_MISSED.search(folded))
    # an evidence word that sits next to a negation («I have NOT done it», «رفتم ولی نشد») is not evidence
    attended = any(not _negated_near(folded, m.start(), m.end()) for m in _ATTENDED.finditer(folded))
    if missed and attended:
        return None
    if missed:
        reason = next((name for name, pattern in _REASONS if pattern.search(folded)), "other")
        return ("missed", reason)
    if attended and not _NEGATION.search(folded):
        return ("attended", None)
    return None


def _already_recorded(db: Session, user_id: int, event: models.UserEvent) -> bool:
    day = _event_day(db, user_id, event)
    occ = f"event:{int(event.id)}:{day.strftime('%Y%m%d')}"
    return (
        db.query(models.InteractionEvent.id)
        .filter(
            models.InteractionEvent.user_id == user_id,
            models.InteractionEvent.source == "schedule",
            models.InteractionEvent.source_id == occ,
            models.InteractionEvent.event_type.in_(("user_schedule_done", "user_schedule_notdone")),
        )
        .first()
        is not None
    )


def _event_day(db: Session, user_id: int, event: models.UserEvent):
    return event.starts_at.date() if event.starts_at is not None else datetime.now(timezone.utc).date()


def record_outcome(db: Session, user_id: int, event: models.UserEvent, verdict: tuple) -> Optional[str]:
    """Owner + I7 for one outcome. Returns 'attended' / 'missed:<reason>' or None. Idempotent per event."""
    from backend.app.services.i7 import user_done

    if _already_recorded(db, user_id, event):
        return None
    domain = user_done.domain_for("event", event.event_type, event.event_domain)
    day = _event_day(db, user_id, event)
    with db.begin_nested():
        if verdict[0] == "attended":
            if not event.recurrence_rule:
                event.status = "completed"
                event.updated_at = datetime.utcnow()
            user_done.record(db, user_id, kind="event", ref_id=int(event.id), day=day, hhmm=None, domain=domain, done=True)
            return "attended"
        user_done.record_not_done(db, user_id, kind="event", ref_id=int(event.id), day=day, hhmm=None, domain=domain, reason=verdict[1])
        return f"missed:{verdict[1]}"


def apply_chat_answer(db: Session, notification: models.Notification, user_id: int, message: str) -> Optional[str]:
    """The first reply to the post-event question. Fail-open: any problem returns None and the chat carries on."""
    try:
        found = event_of_notification(db, notification, user_id)
        if found is None:
            return None
        verdict = parse_attendance(message)
        if verdict is None:
            return None
        return record_outcome(db, user_id, found[0], verdict)
    except Exception:
        logger.exception("[R-071] outcome not recorded")
        return None
