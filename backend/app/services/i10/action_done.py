"""R-070 (step 2D): what the user DID is recorded once through its owner and remembered by I7 - from the tray, from the chat
and from Sedi's one 30-minute assurance.

* ``kind_of``              - medication dose / one-off event reminder / plan item behind a notification;
* ``complete``             - the OWNER completion (dose CONFIRMED_TAKEN, UserEvent completed, I8 action completed) plus the
                             I7 ``user_done`` ledger row; idempotent, so a replay or a second path never double-counts;
* ``mark_not_done``        - «not done» + its bounded reason into the I7 ledger (the owner state is not changed);
* ``handle_action_answer`` - the tray answer (done / not done / later) on a medication or reminder notification or on the
                             assurance; the answer on the assurance is mirrored onto the ORIGINAL notification;
* ``create_due_assurance_tasks`` - ONE new-text «I only want to be sure» follow-up about 30 minutes after an ignored action
                             notification (CareFollowUpTask kind ``assurance`` on the existing worker tick and I10 queue).

Excluded by design: the morning digest and every informational push; appointments / meetings / medical events (they get the
event-outcome question after the event, step 2E); anything already answered or completed elsewhere. Fail-open throughout.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models

logger = logging.getLogger(__name__)

ASSURANCE_KIND = "assurance"
ASSURANCE_TEMPLATE_KEY = "assurance_follow_up"
ASSURED_EVENT = "notification_assured"  # ledger mark on the ORIGINAL notification: its assurance was answered
ACTION_TEMPLATE_KEYS = frozenset({"medication_reminder", "generic_event_reminder", ASSURANCE_TEMPLATE_KEY})
_PLAN_TEMPLATES = frozenset({"nutrition_plan_follow_up", "exercise_plan_follow_up"})
_PLAN_FAMILIES = frozenset({"NUTRITION_PLAN_FOLLOW_UP", "EXERCISE_PLAN_FOLLOW_UP"})
_MEDICATION_FAMILIES = frozenset({"MEDICATION_DUE", "MEDICATION_FOLLOW_UP"})

_ASSURANCE_MIN_AGE = timedelta(minutes=30)
_ASSURANCE_MAX_AGE = timedelta(minutes=90)  # a late «just making sure» is no longer caring
_SCAN_CAP = 300
_ANSWER_EVENTS = (
    "notification_done", "notification_like", "notification_dislike", "notification_dislike_reason", "notification_not_now",
    "notification_talk_later", "notification_open_chat", "chat_message", "notification_ack", ASSURED_EVENT,
)


@dataclass(frozen=True)
class Target:
    kind: str  # "medication" | "event" | "plan"
    original: models.Notification


def _naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _zone(db: Session, user_id: int):
    from backend.app.services.i7.memory_explorer import _zone as zone_of

    return zone_of(db, user_id)[0]


def _context(notification: models.Notification) -> dict:
    try:
        loaded = json.loads(notification.context_json) if isinstance(notification.context_json, str) else (notification.context_json or {})
        return loaded if isinstance(loaded, dict) else {}
    except (TypeError, ValueError):
        return {}


def kind_of(notification: models.Notification) -> Optional[str]:
    template = (notification.template_key or "").strip()
    family = (notification.semantic_family or "").strip()
    if template == "medication_reminder" or family in _MEDICATION_FAMILIES:
        return "medication"
    if template == "generic_event_reminder":
        return "event"
    if template in _PLAN_TEMPLATES or family in _PLAN_FAMILIES:
        return "plan"
    return None


def is_action_notification(notification: models.Notification) -> bool:
    """Notifications whose tray answer (done / not done / later) is handled here instead of the generic recorder."""
    return (notification.template_key or "").strip() in ACTION_TEMPLATE_KEYS


def resolve_target(db: Session, notification: models.Notification, user_id: int) -> Optional[Target]:
    """The notification the answer is ABOUT: the assurance points at its original (ownership checked)."""
    try:
        original = notification
        if (notification.template_key or "").strip() == ASSURANCE_TEMPLATE_KEY:
            ref = str(_context(notification).get("assured_notification_id") or "").strip()
            if not ref.isdigit():
                return None
            original = (
                db.query(models.Notification)
                .filter(models.Notification.id == int(ref), models.Notification.user_id == user_id)
                .first()
            )
            if original is None:
                return None
        kind = kind_of(original)
        return Target(kind, original) if kind else None
    except Exception:
        return None


# ---- owner completion + I7 --------------------------------------------------------------------------------------------
def _complete_medication(db: Session, user_id: int, original: models.Notification, source: str) -> bool:
    from backend.app.services.i10.medication_adherence import MedicationAdherenceError, confirm_dose_taken_by_notification
    from backend.app.services.i7 import user_done

    try:
        occ = confirm_dose_taken_by_notification(
            db, user_id=user_id, notification_id=int(original.id), confirmation_source=source, commit=False
        )
    except MedicationAdherenceError:
        return False
    when = occ.scheduled_for if occ.scheduled_for.tzinfo else occ.scheduled_for.replace(tzinfo=timezone.utc)
    local = when.astimezone(_zone(db, user_id))
    user_done.record(
        db, user_id, kind="medication", ref_id=int(occ.user_medication_id), day=local.date(), hhmm=local.strftime("%H:%M"),
        domain="medication", done=True,
    )
    return True


def _event_of(db: Session, user_id: int, original: models.Notification) -> Optional[models.UserEvent]:
    ref = str(original.source_id or "").strip()
    if not ref.isdigit():
        return None
    return db.query(models.UserEvent).filter(models.UserEvent.id == int(ref), models.UserEvent.user_id == user_id).first()


def _event_day(db: Session, user_id: int, ev: models.UserEvent):
    zone = _zone(db, user_id)
    if ev.starts_at is not None and not ev.recurrence_rule:
        return ev.starts_at.date()
    return datetime.now(timezone.utc).astimezone(zone).date()


def _complete_event(db: Session, user_id: int, original: models.Notification) -> bool:
    from backend.app.services.i7 import user_done

    ev = _event_of(db, user_id, original)
    if ev is None:
        return False
    if not ev.recurrence_rule:
        ev.status = "completed"
        ev.updated_at = datetime.utcnow()
    user_done.record(
        db, user_id, kind="event", ref_id=int(ev.id), day=_event_day(db, user_id, ev), hhmm=None,
        domain=user_done.domain_for("event", ev.event_type, ev.event_domain), done=True,
    )
    return True


def _complete_plan(db: Session, user_id: int, original: models.Notification) -> bool:
    from backend.app.services.i10.coaching_done import handle_coaching_done_for_notification

    # the I8 owner completes the exact action; coaching_done records the I7 ledger row (record_plan_outcome)
    handle_coaching_done_for_notification(db, notification=original, actor_user_id=user_id, payload={"action_id": "done"})
    return True


def complete(db: Session, user_id: int, target: Target, *, source: str = "USER_TRAY") -> bool:
    """Owner completion + I7 for ONE target. Idempotent. Returns False when nothing could be completed (never raises)."""
    try:
        if target.kind == "plan":
            # the I8 owner commits its own work (record_review / completion): it must not run inside a savepoint (Codex P2 PR #147)
            return _complete_plan(db, user_id, target.original)
        with db.begin_nested():
            if target.kind == "medication":
                return _complete_medication(db, user_id, target.original, source)
            if target.kind == "event":
                return _complete_event(db, user_id, target.original)
    except Exception:
        logger.exception("[R-070] done not recorded")
    return False


def mark_not_done(db: Session, user_id: int, target: Target, reason: Optional[str]) -> bool:
    """«Not done» + the bounded reason as memory (I7 ledger). The owner state is not changed."""
    try:
        from backend.app.services.i7 import user_done

        original = target.original
        if target.kind == "plan":
            # plan: the I8 review (skipped + reason) is written - and committed - by the I8 owner, outside any savepoint
            from backend.app.services.i10.coaching_done import handle_coaching_not_done_for_notification

            handle_coaching_not_done_for_notification(
                db, notification=original, actor_user_id=user_id, payload={"action_id": "plan_not_done", "reason": reason or ""}
            )
            return True
        with db.begin_nested():
            if target.kind == "medication":
                occ = (
                    db.query(models.MedicationDoseOccurrence)
                    .filter(models.MedicationDoseOccurrence.source_notification_id == original.id, models.MedicationDoseOccurrence.user_id == user_id)
                    .first()
                )
                if occ is None:
                    return False
                when = occ.scheduled_for if occ.scheduled_for.tzinfo else occ.scheduled_for.replace(tzinfo=timezone.utc)
                local = when.astimezone(_zone(db, user_id))
                user_done.record_not_done(
                    db, user_id, kind="medication", ref_id=int(occ.user_medication_id), day=local.date(), hhmm=local.strftime("%H:%M"),
                    domain="medication", reason=reason,
                )
            elif target.kind == "event":
                ev = _event_of(db, user_id, original)
                if ev is None:
                    return False
                user_done.record_not_done(
                    db, user_id, kind="event", ref_id=int(ev.id), day=_event_day(db, user_id, ev), hhmm=None,
                    domain=user_done.domain_for("event", ev.event_type, ev.event_domain), reason=reason,
                )
        return True
    except Exception:
        logger.exception("[R-070] not-done not recorded")
        return False


def record_plan_outcome(db: Session, user_id: int, action_id: int, *, done: bool, reason: Optional[str] = None) -> None:
    """Called by coaching_done after the I8 owner accepted the outcome: the plan item becomes I7 memory (fail-open)."""
    try:
        from backend.app.services.i7 import user_done

        day = datetime.now(timezone.utc).astimezone(_zone(db, user_id)).date()
        if done:
            user_done.record(db, user_id, kind="plan", ref_id=int(action_id), day=day, hhmm=None, domain="plan", done=True)
        else:
            user_done.record_not_done(db, user_id, kind="plan", ref_id=int(action_id), day=day, hhmm=None, domain="plan", reason=reason)
    except Exception:
        logger.exception("[R-070] plan outcome not recorded in I7")


def _mirror_on_original(db: Session, user_id: int, notification: models.Notification, target: Target) -> None:
    """The answer on the assurance also answers the original: it is never asked about again (2C-1) and not assured twice."""
    if target.original.id == notification.id:
        return
    db.add(
        models.InteractionEvent(
            user_id=user_id, event_type=ASSURED_EVENT, source="system", source_notification_id=target.original.id,
            source_type="notification_assurance", metadata_json=json.dumps({"assurance_notification_id": int(notification.id)}),
        )
    )
    db.flush()


def handle_action_answer(db: Session, *, notification: models.Notification, actor_user_id: int, payload: dict):
    """Tray answer on a medication / reminder / assurance notification: done -> owner + I7; not done -> I7 + reason; later -> ledger."""
    from backend.app.services.i10.interaction_recorder import record_notification_interaction
    from backend.app.services.i10.interaction_vocabulary import CanonicalInteractionVerb, resolve_interaction_verb

    verb = resolve_interaction_verb(payload).verb
    action_id = str(payload.get("action_id") or "").strip().lower()
    target = resolve_target(db, notification, actor_user_id)
    authorized = False
    if target is not None:
        if verb is CanonicalInteractionVerb.DONE:
            authorized = complete(db, actor_user_id, target, source="USER_TRAY")
            if authorized:
                _mirror_on_original(db, actor_user_id, notification, target)
        elif action_id == "plan_not_done":
            if mark_not_done(db, actor_user_id, target, str(payload.get("reason") or "").strip() or None):
                _mirror_on_original(db, actor_user_id, notification, target)
        elif action_id == "later" or verb is CanonicalInteractionVerb.TALK_LATER:
            _mirror_on_original(db, actor_user_id, notification, target)
    kwargs = {"domain_completion_authorized": True} if authorized else {}
    if verb is CanonicalInteractionVerb.DONE and not authorized:
        # the owner could not confirm (already completed elsewhere / unknown): the tap is still recorded as an acknowledgement
        payload = {k: v for k, v in payload.items() if k not in ("action_id", "reaction")}
        payload["reaction"] = "seen"
    return record_notification_interaction(db, notification=notification, recipient_user_id=actor_user_id, payload=payload, **kwargs)


def apply_chat_answer(db: Session, notification: models.Notification, user_id: int, verdict: tuple) -> Optional[str]:
    """The user's SHORT chat answer (done / not done + reason) about the thing behind ``notification`` - same owners, same I7."""
    try:
        target = resolve_target(db, notification, user_id)
        if target is None:
            return None
        if _already_answered(db, user_id, target.original):
            return None
        if verdict[0] == "done":
            if not complete(db, user_id, target, source="USER_CHAT"):
                return None
            _mirror_on_original(db, user_id, notification, target)
            return "done"
        reason = verdict[1] if len(verdict) > 1 else None
        if not mark_not_done(db, user_id, target, reason):
            return None
        _mirror_on_original(db, user_id, notification, target)
        return f"not_done:{reason}"
    except Exception:
        logger.exception("[R-070] chat answer not applied")
        return None


def _already_answered(db: Session, user_id: int, original: models.Notification) -> bool:
    return (
        db.query(models.InteractionEvent.id)
        .filter(
            models.InteractionEvent.user_id == user_id,
            models.InteractionEvent.source_notification_id == original.id,
            models.InteractionEvent.event_type.in_(("notification_done", ASSURED_EVENT)),
        )
        .first()
        is not None
    )


# ---- the ONE 30-minute assurance ----------------------------------------------------------------------------------------
def _existing_assurance_ids(db: Session, user_id: int) -> set:
    from backend.app.services.i10.contextual_followup_task_meta import parse_bounded_meta

    rows = (
        db.query(models.CareFollowUpTask)
        .filter(models.CareFollowUpTask.user_id == user_id, models.CareFollowUpTask.created_at >= datetime.utcnow() - timedelta(days=3))
        .all()
    )
    out = set()
    for row in rows:
        meta = parse_bounded_meta(row.description)[1]
        if meta.follow_up_kind == ASSURANCE_KIND and meta.source_notification_id:
            out.add(int(meta.source_notification_id))
    return out


def _assurable(db: Session, user_id: int, n: models.Notification, now_naive: datetime) -> bool:
    from backend.app.services.i7 import user_done
    from backend.app.services.notification_followup_ask import _completed_elsewhere

    kind = kind_of(n)
    if kind is None or (n.semantic_family or "") == "DAILY_WELLNESS_DIGEST":
        return False
    if kind == "event":
        ev = _event_of(db, user_id, n)
        # appointments / meetings get the event-outcome question after the event (2E), not an assurance
        if ev is None or user_done.domain_for("event", ev.event_type, ev.event_domain) != "other":
            return False
    key = {"medication": "medication", "event": "reminder", "plan": "plan_nutrition"}[kind]
    return not _completed_elsewhere(db, user_id, n, key, now_naive)


def create_due_assurance_tasks(db: Session, *, now: Optional[datetime] = None) -> int:
    """Sweep on the existing worker tick: an action notification sent 30-90 minutes ago that nobody answered gets ONE
    assurance task (due now). Returns how many were created. Fail-open."""
    created = 0
    try:
        from backend.app.services.i10.contextual_followup_types import FollowUpTaskSource, FollowUpTaskStatus
        from backend.app.services.i10.contextual_followup_task_meta import BoundedFollowUpMeta, pack_description

        when = now or datetime.now(timezone.utc)
        now_naive = _naive_utc(when)
        from sqlalchemy import and_, exists, or_

        answered_sql = exists().where(
            and_(
                models.InteractionEvent.source_notification_id == models.Notification.id,
                models.InteractionEvent.event_type.in_(_ANSWER_EVENTS),
            )
        )
        base = db.query(models.Notification).filter(
            models.Notification.created_at >= now_naive - _ASSURANCE_MAX_AGE - timedelta(hours=1),
            models.Notification.created_at <= now_naive,
            models.Notification.status.in_(("sent", "delivered")),
            or_(
                models.Notification.template_key.in_(("medication_reminder", "generic_event_reminder") + tuple(_PLAN_TEMPLATES)),
                models.Notification.semantic_family.in_(tuple(_MEDICATION_FAMILIES | _PLAN_FAMILIES)),
            ),
            ~answered_sql,
        )
        # bounded batches by id (never one global prefix that newer eligible rows can starve behind)
        rows: list = []
        last_id = 0
        for _batch in range(10):
            chunk = base.filter(models.Notification.id > last_id).order_by(models.Notification.id.asc()).limit(_SCAN_CAP).all()
            rows.extend(chunk)
            if len(chunk) < _SCAN_CAP:
                break
            last_id = int(chunk[-1].id)
        known: dict = {}
        for n in rows:
            sent = _naive_utc(n.sent_at or n.created_at)
            if sent is None or not (_ASSURANCE_MIN_AGE <= now_naive - sent <= _ASSURANCE_MAX_AGE):
                continue
            if kind_of(n) is None:
                continue
            uid = int(n.user_id)
            if uid not in known:
                known[uid] = _existing_assurance_ids(db, uid)
            if int(n.id) in known[uid]:
                continue
            answered = (
                db.query(models.InteractionEvent.id)
                .filter(
                    models.InteractionEvent.user_id == uid,
                    models.InteractionEvent.source_notification_id == n.id,
                    models.InteractionEvent.event_type.in_(_ANSWER_EVENTS),
                )
                .first()
            )
            if answered is not None or not _assurable(db, uid, n, now_naive):
                continue
            meta = BoundedFollowUpMeta(follow_up_kind=ASSURANCE_KIND, source_notification_id=int(n.id), domain=kind_of(n))
            ts = datetime.utcnow()
            with db.begin_nested():
                db.add(
                    models.CareFollowUpTask(
                        user_id=uid, title=str(kind_of(n)), description=pack_description(None, meta),
                        status=FollowUpTaskStatus.OPEN.value, due_at=now_naive, source=FollowUpTaskSource.GENERAL_CONTEXTUAL.value,
                        created_at=ts, updated_at=ts,
                    )
                )
            known[uid].add(int(n.id))
            created += 1
        if created:
            db.flush()
    except Exception:
        logger.exception("[R-070] assurance sweep skipped")
    return created


def assurance_still_needed(db: Session, task: models.CareFollowUpTask, now: Optional[datetime] = None) -> bool:
    """A deferred assurance is re-checked right before it is sent: if the original was answered or completed meanwhile (dose
    confirmed, event done, plan item done, any tray / chat answer) the task is dropped (Codex P2 PR #147)."""
    try:
        from backend.app.services.i10.contextual_followup_task_meta import parse_bounded_meta

        meta = parse_bounded_meta(task.description)[1]
        ref = int(meta.source_notification_id or 0)
        original = (
            db.query(models.Notification).filter(models.Notification.id == ref, models.Notification.user_id == task.user_id).first()
            if ref
            else None
        )
        if original is None:
            return False
        answered = (
            db.query(models.InteractionEvent.id)
            .filter(
                models.InteractionEvent.user_id == task.user_id,
                models.InteractionEvent.source_notification_id == original.id,
                models.InteractionEvent.event_type.in_(_ANSWER_EVENTS),
            )
            .first()
        )
        return answered is None and _assurable(db, int(task.user_id), original, _naive_utc(now or datetime.now(timezone.utc)))
    except Exception:
        return False


def subject_name(db: Session, original: Optional[models.Notification], user_id: int) -> str:
    """The name of the thing a notification is about: the drug of a dose reminder or the plan name the user gave an event.
    '' when unknown or when it is only a generic default title. Never raises (Javad 2026-11-09, R-084)."""
    try:
        if original is None:
            return ""
        kind = kind_of(original)
        if kind == "medication":
            # Codex P2 (PR 182): the dose occurrence is linked to its reminder through source_notification_id (the same link
            # confirm_dose_taken_by_notification uses), NOT through the notification's source_id.
            occ = (
                db.query(models.MedicationDoseOccurrence)
                .filter(
                    models.MedicationDoseOccurrence.source_notification_id == int(original.id),
                    models.MedicationDoseOccurrence.user_id == user_id,
                )
                .first()
            )
            um = (
                db.query(models.UserMedication)
                .filter(models.UserMedication.id == occ.user_medication_id, models.UserMedication.user_id == user_id)
                .first()
                if occ is not None
                else None
            )
            med = db.query(models.Medication).filter(models.Medication.id == um.medication_id).first() if um is not None else None
            return (med.name or "").strip() if med is not None else ""
        if kind == "event":
            from backend.app.services.i10.event_reminder_i10_adapter import _DEFAULT_LABELS

            ev = _event_of(db, user_id, original)
            title = (ev.title or "").strip() if ev is not None else ""
            return "" if title in _DEFAULT_LABELS else title
    except Exception:
        logger.exception("[R-084] subject name skipped")
    return ""


def assurance_copy(lang: str, domain: Optional[str], subject: str = "") -> tuple:
    """(title, body). R-084 (Javad 2026-11-09): when the subject is known the text names it (the drug / the plan name the user gave)."""
    from backend.app import sedi_copy

    lang = lang if lang in ("fa", "ar", "en") else "en"
    key = domain if domain in ("medication", "plan") else "other"
    name = (subject or "").strip()
    if name and key in ("medication", "other"):  # R-084: the follow-up names what it follows up
        return sedi_copy.t("assurance.title", lang), sedi_copy.t(f"assurance.body.{key}_named", lang, name=name)
    return sedi_copy.t("assurance.title", lang), sedi_copy.t(f"assurance.body.{key}", lang)
