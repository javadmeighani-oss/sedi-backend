"""R-108 / R-092 partial lift (Javad 2026-11-20): the chat<->notification CONTINUITY of a care appointment.

A user who tells Sedi in chat «Tuesday 14:00 physiotherapy» gets, on the SAME I10 follow-up rails every Sedi notification already uses
(``CareFollowUpTask`` + the 10-minute worker + the gate4 send guard + quiet hours; no second scheduler, R-005):
  * ``event_day_of``  - ONE message at 09:00 local on the day: «today at 14:00 you have <the appointment>»;
  * ``event_pre_check`` - ONE check-in two hours before: «the appointment is at 14:00 ... ready? how are you?».
The appointment is NAMED exactly as the user named it, with its time and place (R-084 / Javad: notifications must name precisely).

Rules (Javad's answers, D-466): the event kinds are doctor visit, lab test, imaging, surgery and PHYSIOTHERAPY; an event that starts before
12:00 gets only the pre-check (a 09:00 message and a check-in an hour apart would be noise); the day-of message is sent only when the
event existed before 09:00 of its day (a same-morning booking was just confirmed in chat); the pre-check is skipped when the user's own
reminder already fires about two hours before (no duplicate, DEBT-042) or when its time would fall in quiet hours (before 07:00 / after 22:00).
Tasks are created just in time by the worker tick (so a moved or cancelled event never leaves a stale task) and every send re-checks the
event. Consent: the tasks are created only for users who allowed memory writes. Default OFF: flag SEDI_EVENT_CARE_NOTIFS_ENABLED.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, time, timedelta, timezone
from typing import Optional

import pytz
from sqlalchemy.orm import Session

from backend.app import models

logger = logging.getLogger(__name__)

FLAG = "SEDI_EVENT_CARE_NOTIFS_ENABLED"
KIND_DAY_OF = "event_day_of"
KIND_PRE = "event_pre_check"
KINDS = (KIND_DAY_OF, KIND_PRE)
CARE_EVENT_TYPES = frozenset({"doctor_visit", "lab_test", "imaging", "surgery", "physiotherapy"})
_ACTIVE_STATUSES = ("scheduled", "confirmed")
DAY_OF_HOUR = 9
PRE_LEAD = timedelta(hours=2)
EARLY_START_HOUR = 12  # an event before this hour gets only the pre-check
QUIET_FROM, QUIET_TO = 22, 7
_CREATE_AHEAD = timedelta(minutes=15)   # a task is created when its due time is this close ...
_DAY_OF_GRACE = timedelta(hours=2)      # a day-of message that could not go out within 2 h of 09:00 is dropped
_PRE_GRACE = timedelta(minutes=45)
# ... and not later than this after it: always SHORTER than the grace, so a task is never created already too late to be sent
_CREATE_WINDOW = {KIND_DAY_OF: timedelta(hours=1), KIND_PRE: timedelta(minutes=30)}
_MOVED_TOLERANCE = timedelta(minutes=20)
_SCAN_CAP = 300
_MAX_PAGES = 10
_MAX_TITLE = 80
_MAX_PLACE = 60


def enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def _naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _starts_utc(event: models.UserEvent) -> Optional[datetime]:
    from backend.app.services.i10.event_reminder_i10_adapter import event_starts_utc

    return event_starts_utc(event)


def _zone(db: Session, user_id: int):
    from backend.app.services.i10.commitment_followup import _zone as user_zone

    return user_zone(db, user_id)


def _local(dt_utc: datetime, zone) -> datetime:
    return pytz.UTC.localize(dt_utc).astimezone(zone)


def _local_to_utc(local_naive: datetime, zone) -> datetime:
    return zone.localize(local_naive).astimezone(pytz.UTC).replace(tzinfo=None)


def is_care_event(event: models.UserEvent) -> bool:
    return (event.event_type or "").strip() in CARE_EVENT_TYPES and not event.recurrence_rule


def _own_reminder_near_pre_check(event: models.UserEvent) -> bool:
    """The user's own reminder already fires about two hours before (offset 90..150 min): a second message would duplicate it."""
    if not event.reminder_enabled or not event.reminder_offsets_json:
        return False
    try:
        offsets = [int(x) for x in json.loads(event.reminder_offsets_json)]
    except Exception:  # noqa: BLE001
        return False
    return any(90 <= o <= 150 for o in offsets)


def due_times(event: models.UserEvent, zone, *, created_before_day_of: bool) -> dict:
    """{kind: naive-UTC due time} the care messages of this event should go out (an empty dict = none). Pure: no database access."""
    start = _starts_utc(event)
    if start is None:
        return {}
    local_start = _local(start, zone)
    day = local_start.date()
    out: dict = {}
    pre_local = local_start - PRE_LEAD
    if local_start.hour >= EARLY_START_HOUR:
        if created_before_day_of:
            out[KIND_DAY_OF] = _local_to_utc(datetime.combine(day, time(DAY_OF_HOUR, 0)), zone)
    else:
        # a morning event: the check-in is the only message; it never goes out before 07:00 and never closer than 30 min to the start
        floor = zone.localize(datetime.combine(day, time(QUIET_TO, 0)))
        pre_local = max(pre_local, floor)
        if pre_local > local_start - timedelta(minutes=30):
            return {}
    if QUIET_TO <= pre_local.hour < QUIET_FROM and not _own_reminder_near_pre_check(event):
        out[KIND_PRE] = pre_local.astimezone(pytz.UTC).replace(tzinfo=None)
    return out


def _created_before_day_of(db: Session, event: models.UserEvent, zone) -> bool:
    start = _starts_utc(event)
    created = _naive_utc(event.created_at)
    if start is None or created is None:
        return False
    day = _local(start, zone).date()
    return created < _local_to_utc(datetime.combine(day, time(DAY_OF_HOUR, 0)), zone)


def _existing(db: Session, user_ids: set) -> set:
    """{(event_id, kind)} that already have a LIVE task (open / notified / done) in the last days - one message of each kind per event.
    A cancelled task (a moved event, a dropped stale task) is not counted, so the rescheduled appointment gets its replacement (Codex P2)."""
    from backend.app.services.i10.contextual_followup_task_meta import parse_bounded_meta

    if not user_ids:
        return set()
    rows = (
        db.query(models.CareFollowUpTask)
        .filter(
            models.CareFollowUpTask.user_id.in_(list(user_ids)),
            models.CareFollowUpTask.created_at >= datetime.utcnow() - timedelta(days=4),
            models.CareFollowUpTask.status != "cancelled",
        )
        .all()
    )
    found = set()
    for row in rows:
        meta = parse_bounded_meta(row.description)[1]
        if meta.follow_up_kind in KINDS and meta.user_event_id:
            found.add((int(meta.user_event_id), meta.follow_up_kind))
    return found


def _reconcile_open_tasks(db: Session, events: list) -> int:
    """Cancel OPEN event-care tasks whose due time no longer matches their appointment (a moved event): the worker only looks at tasks
    that are already due, so a future-due stale task would otherwise suppress its own replacement (Codex P2, PR 204)."""
    from backend.app.services.i10.contextual_followup_task_meta import parse_bounded_meta

    by_id = {int(e.id): e for e in events}
    if not by_id:
        return 0
    cancelled = 0
    rows = (
        db.query(models.CareFollowUpTask)
        .filter(
            models.CareFollowUpTask.user_id.in_(list({int(e.user_id) for e in events})),
            models.CareFollowUpTask.status == "open",
            models.CareFollowUpTask.created_at >= datetime.utcnow() - timedelta(days=4),
        )
        .all()
    )
    zones: dict = {}
    for task in rows:
        meta = parse_bounded_meta(task.description)[1]
        event = by_id.get(int(meta.user_event_id or 0))
        if meta.follow_up_kind not in KINDS or event is None:
            continue
        zone = zones.setdefault(int(task.user_id), _zone(db, int(task.user_id)))
        expected = due_times(event, zone, created_before_day_of=True).get(meta.follow_up_kind)
        due = _naive_utc(task.due_at)
        if expected is None or due is None or abs(expected - due) > _MOVED_TOLERANCE:
            task.status = "cancelled"
            task.updated_at = datetime.utcnow()
            cancelled += 1
    return cancelled


def expires_at(db: Session, task: models.CareFollowUpTask) -> Optional[datetime]:
    """Provider expiry (aware UTC) of an event-care push: its grace window, and never later than the appointment itself, so a delayed
    delivery cannot reach the user after the appointment started or the next morning (Codex P2, PR 204)."""
    event, kind = _event_and_kind(db, task)
    start = _starts_utc(event) if event is not None else None
    due = _naive_utc(task.due_at)
    if kind is None or start is None or due is None:
        return None
    limit = min(start, due + (_DAY_OF_GRACE if kind == KIND_DAY_OF else _PRE_GRACE))
    zone = _zone(db, task.user_id)
    local_due = _local(due, zone)
    if local_due.hour < QUIET_FROM:  # a queued push cannot be delivered after 22:00 local either
        limit = min(limit, _local_to_utc(datetime.combine(local_due.date(), time(QUIET_FROM, 0)), zone))
    return limit.replace(tzinfo=timezone.utc)


def create_due_event_care_tasks(db: Session, *, now: Optional[datetime] = None) -> int:
    """Sweep on the existing worker tick: for every care appointment starting soon, create the day-of / pre-check task whose due time
    is now (just in time). Returns how many were created. Default OFF, fail-open, consent-gated; never raises."""
    if not enabled():
        return 0
    created = 0
    try:
        from backend.app.services.i10.contextual_followup_task_meta import BoundedFollowUpMeta, pack_description
        from backend.app.services.i10.contextual_followup_types import FollowUpTaskSource, FollowUpTaskStatus
        from backend.app.services.i6.consent_service import PERM_WRITE, has_permission

        now_naive = _naive_utc(now or datetime.now(timezone.utc))
        base = db.query(models.UserEvent).filter(
            models.UserEvent.starts_at >= now_naive - timedelta(days=1),
            models.UserEvent.starts_at <= now_naive + timedelta(days=2),
            models.UserEvent.status.in_(_ACTIVE_STATUSES),
            models.UserEvent.recurrence_rule.is_(None),
            models.UserEvent.event_type.in_(sorted(CARE_EVENT_TYPES)),
        )
        rows: list = []
        last_id = 0
        for _page in range(_MAX_PAGES):  # bounded keyset pages: a busy day never hides the higher-id events from every tick (Codex P2)
            chunk = base.filter(models.UserEvent.id > last_id).order_by(models.UserEvent.id.asc()).limit(_SCAN_CAP).all()
            rows.extend(chunk)
            if len(chunk) < _SCAN_CAP:
                break
            last_id = int(chunk[-1].id)
        if not rows:
            return 0
        _reconcile_open_tasks(db, rows)  # a moved appointment's stale open task must not suppress its replacement
        known = _existing(db, {int(r.user_id) for r in rows})
        consent: dict = {}
        for ev in rows:
            uid = int(ev.user_id)
            if uid not in consent:
                consent[uid] = bool(has_permission(db, uid, PERM_WRITE))
            if not consent[uid]:
                continue
            zone = _zone(db, uid)
            for kind, due in due_times(ev, zone, created_before_day_of=_created_before_day_of(db, ev, zone)).items():
                if (int(ev.id), kind) in known or not (due - _CREATE_AHEAD <= now_naive <= due + _CREATE_WINDOW[kind]):
                    continue
                meta = BoundedFollowUpMeta(follow_up_kind=kind, user_event_id=int(ev.id), domain=(ev.event_type or "")[:32])
                ts = datetime.utcnow()
                with db.begin_nested():
                    db.add(
                        models.CareFollowUpTask(
                            user_id=uid, title=(ev.title or kind)[:256], description=pack_description(None, meta),
                            status=FollowUpTaskStatus.OPEN.value, due_at=due, source=FollowUpTaskSource.GENERAL_CONTEXTUAL.value,
                            created_at=ts, updated_at=ts,
                        )
                    )
                known.add((int(ev.id), kind))
                created += 1
        if created:
            db.flush()
    except Exception:
        logger.exception("[R-108] event care sweep skipped")
    return created


def _event_and_kind(db: Session, task: models.CareFollowUpTask):
    from backend.app.services.i10.contextual_followup_task_meta import parse_bounded_meta

    meta = parse_bounded_meta(task.description)[1]
    if meta.follow_up_kind not in KINDS or not meta.user_event_id:
        return None, None
    event = db.query(models.UserEvent).filter(models.UserEvent.id == int(meta.user_event_id), models.UserEvent.user_id == task.user_id).first()
    return event, meta.follow_up_kind


def may_send(db: Session, task: models.CareFollowUpTask, now: datetime) -> bool:
    """Re-check at send time: the event still exists, is still active and has not moved; a late message is dropped; then the send guard."""
    from backend.app.services.notifications.send_guard_v1 import can_send_v1

    now_naive = _naive_utc(now)
    event, kind = _event_and_kind(db, task)

    def drop() -> bool:
        task.status = "cancelled"
        task.updated_at = datetime.utcnow()
        return False

    if event is None or kind is None or not enabled() or (event.status or "") not in _ACTIVE_STATUSES:
        return drop()
    from backend.app.services.i6.consent_service import PERM_WRITE, has_permission

    if not has_permission(db, task.user_id, PERM_WRITE):
        return drop()  # consent revoked after the task was created: the appointment's title and place are never sent (Codex P2, round 3)
    start = _starts_utc(event)
    if start is None or now_naive >= start:
        return drop()
    zone = _zone(db, task.user_id)
    if not (QUIET_TO <= _local(now_naive, zone).hour < QUIET_FROM):
        return drop()  # the 22:00-07:00 cutoff holds at SEND time too, not only when the task was scheduled (Codex P2, round 3)
    expected = due_times(event, zone, created_before_day_of=True).get(kind)
    due = _naive_utc(task.due_at)
    if expected is None or due is None or abs(expected - due) > _MOVED_TOLERANCE:
        return drop()  # the event was moved (or no longer qualifies): the sweep creates a fresh task if one is due
    if now_naive - due > (_DAY_OF_GRACE if kind == KIND_DAY_OF else _PRE_GRACE):
        return drop()
    return bool(can_send_v1(db, task.user_id, "companion", kind, "normal", now_naive).get("allowed"))


def _still_upcoming(db: Session, task: models.CareFollowUpTask, kind: str, now: Optional[datetime] = None) -> bool:
    """The appointment is still active, has not started, and - for the day-of message - is still TODAY in the user's zone."""
    event, _kind = _event_and_kind(db, task)
    if event is None or (event.status or "") not in _ACTIVE_STATUSES:
        return False
    start = _starts_utc(event)
    now_naive = _naive_utc(now or datetime.now(timezone.utc))
    if start is None or now_naive >= start:
        return False
    if kind == KIND_DAY_OF:
        zone = _zone(db, task.user_id)
        return _local(start, zone).date() == _local(now_naive, zone).date()
    return True


def opener(db: Session, user_id: int, notification: models.Notification, lang: str) -> Optional[str]:
    """R-108 / R-052 (2c-2): the chat that opens from a day-of / pre-check push continues the SAME subject: the appointment (title, time,
    place as the push named them) and, when the shared care state holds an open issue, that issue - ONE specific question, never the
    generic greeting. None when the appointment is gone (the caller keeps its generic opener). Read-only; fail-open."""
    try:
        from backend.app import sedi_copy
        from backend.app.services.i10.event_outcome import task_of_notification

        task = task_of_notification(db, notification, user_id)
        facts = event_facts(db, task) if task is not None else None
        if facts is None or not _still_upcoming(db, task, facts["kind"]):
            return None  # cancelled, past or moved to another day: an old push must not announce it as upcoming (Codex P2, PR 209)
        issue = ""
        try:
            from backend.app.services.care_state import get_care_state

            state = get_care_state(db, user_id)
            if state is not None and state.issues:
                issue = state.issues[0].text
        except Exception:  # noqa: BLE001
            issue = ""
        place = sedi_copy.t("event_care.place", lang, location=facts["place"]) if facts["place"] else ""
        which = "event_pre" if facts["kind"] == KIND_PRE else "event_day_of"
        key = f"session.origin.{which}_issue" if issue else f"session.origin.{which}"
        return sedi_copy.t(key, lang, time=facts["time"], title=facts["title"], place=place, issue=issue)
    except Exception:  # noqa: BLE001
        logger.exception("[R-108] event care opener skipped")
        return None


def event_facts(db: Session, task: models.CareFollowUpTask) -> Optional[dict]:
    """What the message names, exactly as the user gave it: title, local start time (HH:MM) and place; None when the event is gone."""
    event, kind = _event_and_kind(db, task)
    if event is None or kind is None:
        return None
    start = _starts_utc(event)
    if start is None:
        return None
    title = " ".join((event.title or "").split())[:_MAX_TITLE]
    if not title:
        return None
    place = " ".join((event.location or "").split())[:_MAX_PLACE]
    return {"kind": kind, "title": title, "time": _local(start, _zone(db, task.user_id)).strftime("%H:%M"), "place": place}
