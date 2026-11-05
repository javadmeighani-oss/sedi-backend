"""R-068 (step 2A): the COMMITMENT LOOP - Sedi keeps what she promises and the user is never left.

When Sedi gives a personal plan and promises to follow up («فردا درباره‌اش می‌پرسم», "I will ask you about it tomorrow"),
that promise becomes a real ``CareFollowUpTask`` (``follow_up_kind="commitment"``, no migration) and is delivered by the
existing I10-B12 worker through the smart-notification framework. Owners are reused (R-005): CareFollowUpTask + bounded
meta (I10-B12), the I10 queue + send guard, I7 ``user_done``; the tray buttons are the plan ones (done / not done /
later).

Rules (R-068, Javad 2026-11-05):
* extraction is deterministic: the follow-up PROMISE sentence + the 1-2 sentences before it (the step); memory-consent
  gated; fail-open;
* the user is NEVER left: every follow-up that was sent immediately schedules the next one; the interval never exceeds
  2 days (next local day 09:00, then +1 day, then +2 days, then every 2 days) and every attempt CHANGES approach
  (wording, a lighter step, a better time, asking what got in the way);
* the lock-screen text never names an illness; the detail lives inside the chat.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models, sedi_copy
from backend.app.services.i10.contextual_followup_task_meta import (
    BoundedFollowUpMeta,
    pack_description,
    parse_bounded_meta,
)
from backend.app.services.i10.contextual_followup_types import FollowUpTaskSource, FollowUpTaskStatus

logger = logging.getLogger(__name__)

COMMITMENT_KIND = "commitment"
COMMITMENT_TEMPLATE_KEY = "commitment_follow_up"
FOLLOW_UP_HOUR = 9
MAX_OPEN_CHAINS = 3
MAX_STEP_CHARS = 160
_OPEN_STATUSES = (FollowUpTaskStatus.OPEN.value, FollowUpTaskStatus.NOTIFIED.value)

_SENTENCE = re.compile(r"(?<=[.!?؟…])\s+|\n+")
_FOLD = (("ي", "ی"), ("ى", "ی"), ("ك", "ک"), ("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("‌", " "))


def _fold(text: str) -> str:
    out = (text or "").lower()
    for a, b in _FOLD:
        out = out.replace(a, b)
    return re.sub(r"[ً-ْ]", "", out)


def _p(*alternatives: str) -> re.Pattern:
    return re.compile("(?:" + "|".join(_fold(a) for a in alternatives) + ")", re.I)


# ---- the follow-up PROMISE sentence (fa / ar / en) --------------------------------------------------------------------
_PROMISE = _p(
    # fa: «فردا درباره‌اش می‌پرسم» / «دفعه‌ی بعد ازت می‌پرسم» / «فردا بگو چند بار بیدار شدی»
    r"(?:فردا|فردا صبح|دفعه ی بعد|دفعه بعد|روز بعد|بعدا)\b.*\b(?:می پرسم|میپرسم|خبر می گیرم|سر می زنم|پیگیر(?:ت|ی)? می (?:مانم|کنم)|بگو|بنویس|خبرم کن|گزارش بده)",
    r"\b(?:می پرسم|میپرسم|پیگیر(?:ت|ی)? می (?:مانم|کنم))\b.*\b(?:فردا|دفعه ی بعد|دفعه بعد|روز بعد)\b",
    # ar
    r"(?:ساسال|سوف اسال|ساتابع|ساطمئن|ساتحقق).*(?:غدا|المر[هة] القادم[هة]|لاحقا)",
    r"(?:غدا|المر[هة] القادم[هة]).*(?:اخبرني|قل لي|اعلمني|طمئني)",
    # en
    r"\bi(?:'ll| will)\s+(?:ask|check|follow\s+up)\b.*\b(?:tomorrow|next\s+time|later)\b",
    r"\b(?:tomorrow|next\s+time)\b.*\b(?:tell\s+me|let\s+me\s+know|report\s+back)\b",
    r"\b(?:tell\s+me|let\s+me\s+know)\b.*\btomorrow\b",
)

# severe-symptom messages never become a (lock-screen) commitment: the safety floor owns them
_SEVERE = re.compile(
    r"(?:chest\s+pain|shortness\s+of\s+breath|bleeding|stroke|suicid|self[-\s]?harm|overdose|"
    r"درد\s+قفسه|تنگی\s+نفس|خونریزی|سکته|خودکشی|آسیب\s+به\s+خود|مسمومیت|"
    r"ألم\s+في\s+الصدر|ضيق\s+(?:في\s+)?التنفس|نزيف|سكتة|انتحار|إيذاء\s+النفس)",
    re.I,
)

# coarse domain of a step (used only to supersede an older commitment on the same subject; never shown)
_DOMAINS: tuple = (
    ("sleep", _p(r"خواب", r"بیدار", r"تخت", r"نوم", r"النوم", r"\bsleep", r"\bbed\b", r"\bwake")),
    ("exercise", _p(r"ورزش", r"پیاده", r"تمرین", r"حرکت", r"رياضه", r"الرياضه", r"المشي", r"\bامش\b", r"\bwalk", r"exercise", r"workout", r"stretch")),
    ("nutrition", _p(r"غذا", r"تغذیه", r"آب\b", r"قند", r"رژیم", r"وجبه", r"طعام", r"\bdiet", r"\bmeal", r"water", r"\beat")),
    ("pain", _p(r"درد", r"کمر", r"گردن", r"\bألم\b", r"\bالظهر\b", r"\bpain", r"\bback\b", r"posture")),
    ("mood", _p(r"غم", r"استرس", r"اضطراب", r"خلق", r"ذهن", r"توتر", r"\bstress", r"\bmood", r"anxi", r"breath")),
)


@dataclass(frozen=True)
class Commitment:
    step: str
    promise: str


def commitment_domain(text: str) -> str:
    folded = _fold(text or "")
    for name, pattern in _DOMAINS:
        if pattern.search(folded):
            return name
    return "other"


def _shorten(step: str) -> str:
    step = " ".join(step.split())
    if len(step) <= MAX_STEP_CHARS:
        return step
    cut = step[: MAX_STEP_CHARS - 1].rsplit(" ", 1)[0].rstrip(" ,،;؛:")
    return cut + "…"


def extract_commitment(reply: str, language: str = "fa") -> Optional[Commitment]:
    """The promise sentence (one of the last two sentences) + the 1-2 non-question sentences before it, or None."""
    text = (reply or "").strip()
    if not text or _SEVERE.search(text):
        return None
    sentences = [s.strip() for s in _SENTENCE.split(text) if s and s.strip()]
    if not sentences:
        return None
    start = max(0, len(sentences) - 2)
    index = next((i for i in range(len(sentences) - 1, start - 1, -1) if _PROMISE.search(_fold(sentences[i]))), None)
    if index is None:
        return None
    promise = sentences[index]
    before = [s for s in sentences[:index] if not s.rstrip("\"'») ").endswith(("?", "؟")) and len(s.split()) >= 3]
    steps = before[-2:]
    if not steps:
        if len(promise.split()) < 4:
            return None
        steps = [promise]
    step = " ".join(steps)
    if len(step) > MAX_STEP_CHARS and len(steps) > 1:
        step = steps[-1]
    return Commitment(step=_shorten(step), promise=promise)


# ---- time: always 09:00 in the user's local timezone ------------------------------------------------------------------
def _zone(db: Session, user_id: int):
    from backend.app.services.i7.memory_explorer import _zone as zone_of

    return zone_of(db, user_id)[0]


def follow_up_time(db: Session, user_id: int, *, base_utc: datetime, days_ahead: int) -> datetime:
    """09:00 local, ``days_ahead`` local days after ``base_utc``, as a NAIVE UTC datetime (the column convention)."""
    zone = _zone(db, user_id)
    base = base_utc if base_utc.tzinfo else base_utc.replace(tzinfo=timezone.utc)
    target = base.astimezone(zone).date() + timedelta(days=days_ahead)
    local = zone.localize(datetime.combine(target, time(FOLLOW_UP_HOUR, 0)))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def interval_days_after(attempt: int) -> int:
    """R-068: the gap after an UNANSWERED attempt never exceeds 2 days: 1 -> +1 day, 2 -> +2 days, then every 2 days."""
    return 1 if int(attempt or 1) <= 1 else 2


_APPROACHES: tuple = ("nudge", "why", "lighter", "time")


def approach_for(attempt: int) -> str:
    """Every attempt changes approach: 2 = nudge, then why / lighter step / a better time, cycling."""
    attempt = int(attempt or 1)
    if attempt <= 1:
        return "first"
    if attempt == 2:
        return "nudge"
    return _APPROACHES[1 + (attempt - 3) % 3]


# ---- copy (lock-screen safe: never names an illness or the step) --------------------------------------------------------
def commitment_copy(lang: str, attempt: int) -> tuple:
    lang = lang if lang in ("fa", "ar", "en") else "en"
    title = sedi_copy.t("commitment.title", lang)
    attempt = int(attempt or 1)
    if attempt <= 1:
        body = sedi_copy.t("commitment.body.1", lang)
    elif attempt == 2:
        body = sedi_copy.t("commitment.body.2", lang)
    else:
        body = sedi_copy.t("commitment.body.3", lang, pick=attempt - 3)
    return title, body


# ---- the task chain ------------------------------------------------------------------------------------------------------
def meta_of(task: models.CareFollowUpTask) -> BoundedFollowUpMeta:
    return parse_bounded_meta(task.description)[1]


def is_commitment(task: models.CareFollowUpTask) -> bool:
    return meta_of(task).follow_up_kind == COMMITMENT_KIND


def _repack(task: models.CareFollowUpTask, **changes: Any) -> None:
    user_text, meta = parse_bounded_meta(task.description)
    fields = {
        "follow_up_kind": meta.follow_up_kind,
        "user_event_id": meta.user_event_id,
        "source_notification_id": meta.source_notification_id,
        "notification_id": meta.notification_id,
        "attempt": meta.attempt,
        "domain": meta.domain,
        "chain_id": meta.chain_id,
        "approach": meta.approach,
        "reason": meta.reason,
    }
    fields.update(changes)
    task.description = pack_description(user_text, BoundedFollowUpMeta(**fields))
    task.updated_at = datetime.utcnow()


def _commitment_tasks(db: Session, user_id: int, statuses: tuple = _OPEN_STATUSES) -> list:
    rows = (
        db.query(models.CareFollowUpTask)
        .filter(
            models.CareFollowUpTask.user_id == user_id,
            models.CareFollowUpTask.status.in_(statuses),
            models.CareFollowUpTask.description.contains(f'"follow_up_kind":"{COMMITMENT_KIND}"'),
        )
        .order_by(models.CareFollowUpTask.id.asc())
        .all()
    )
    return [t for t in rows if is_commitment(t)]


def chain_of(db: Session, task: models.CareFollowUpTask, statuses: tuple = _OPEN_STATUSES) -> list:
    chain_id = meta_of(task).chain_id or task.id
    return [t for t in _commitment_tasks(db, task.user_id, statuses) if (meta_of(t).chain_id or t.id) == chain_id]


def _create_task(
    db: Session,
    user_id: int,
    title: str,
    due_at: datetime,
    *,
    attempt: int,
    domain: str,
    chain_id: Optional[int],
    approach: str,
) -> models.CareFollowUpTask:
    now = datetime.utcnow()
    meta = BoundedFollowUpMeta(
        follow_up_kind=COMMITMENT_KIND, attempt=attempt, domain=domain, chain_id=chain_id, approach=approach
    )
    row = models.CareFollowUpTask(
        user_id=user_id,
        title=title.strip()[:256],
        description=pack_description(None, meta),
        status=FollowUpTaskStatus.OPEN.value,
        due_at=due_at,
        source=FollowUpTaskSource.GENERAL_CONTEXTUAL.value,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    if chain_id is None:
        _repack(row, chain_id=row.id)
    return row


def _supersede(db: Session, user_id: int, domain: str) -> None:
    """A new commitment replaces an older open one on the same subject; at most MAX_OPEN_CHAINS chains stay open."""
    chains: dict = {}
    for task in _commitment_tasks(db, user_id):
        chains.setdefault(meta_of(task).chain_id or task.id, []).append(task)
    for chain_id, tasks in list(chains.items()):
        if meta_of(tasks[0]).domain == domain and domain != "other":
            for t in tasks:
                t.status = FollowUpTaskStatus.CANCELLED.value
                t.updated_at = datetime.utcnow()
            chains.pop(chain_id)
    overflow = len(chains) - (MAX_OPEN_CHAINS - 1)
    for chain_id in sorted(chains)[: max(0, overflow)]:
        for t in chains[chain_id]:
            t.status = FollowUpTaskStatus.CANCELLED.value
            t.updated_at = datetime.utcnow()


def create_commitment(db: Session, user_id: int, step: str, *, now: Optional[datetime] = None) -> models.CareFollowUpTask:
    """A new chain, attempt 1: the first follow-up is the next local day at 09:00."""
    when = now or datetime.now(timezone.utc)
    domain = commitment_domain(step)
    _supersede(db, user_id, domain)
    due = follow_up_time(db, user_id, base_utc=when, days_ahead=1)
    return _create_task(db, user_id, step, due, attempt=1, domain=domain, chain_id=None, approach="first")


def capture_from_reply(
    db: Session, user_id: int, reply: str, language: str = "fa", *, user_message: str = ""
) -> Optional[models.CareFollowUpTask]:
    """Chat hook: memory-consent gated, fail-open (chat must never break because of the loop). A severe-symptom message
    never becomes a commitment (the safety floor owns it)."""
    try:
        from backend.app.services.i6.consent_service import PERM_WRITE, has_permission

        if _SEVERE.search(user_message or "") or not has_permission(db, user_id, PERM_WRITE):
            return None
        found = extract_commitment(reply, language)
        if not found:
            return None
        with db.begin_nested():
            return create_commitment(db, user_id, found.step)
    except Exception:
        logger.exception("[R-068] commitment capture skipped")
        return None


def schedule_next_attempt(db: Session, task: models.CareFollowUpTask) -> Optional[models.CareFollowUpTask]:
    """Called right after a follow-up was SENT: the next one is already scheduled (the user is never left)."""
    meta = meta_of(task)
    if meta.follow_up_kind != COMMITMENT_KIND:
        return None
    chain_id = meta.chain_id or task.id
    attempt = int(meta.attempt or 1)
    for existing in chain_of(db, task, (FollowUpTaskStatus.OPEN.value,)):
        if int(meta_of(existing).attempt or 1) > attempt:
            return existing  # idempotent
    base = task.due_at or datetime.utcnow()
    due = follow_up_time(db, task.user_id, base_utc=base, days_ahead=interval_days_after(attempt))
    return _create_task(
        db,
        task.user_id,
        task.title,
        due,
        attempt=attempt + 1,
        domain=meta.domain or commitment_domain(task.title),
        chain_id=chain_id,
        approach=approach_for(attempt + 1),
    )


# ---- the user's answers (tray buttons) ------------------------------------------------------------------------------------
def _next_pending(db: Session, task: models.CareFollowUpTask) -> Optional[models.CareFollowUpTask]:
    pending = [t for t in chain_of(db, task, (FollowUpTaskStatus.OPEN.value,)) if t.id != task.id]
    return max(pending, key=lambda t: int(meta_of(t).attempt or 1)) if pending else None


def apply_done(db: Session, task: models.CareFollowUpTask) -> None:
    """Done: the chain ends (the answered task DONE, pending ones cancelled) and I7 learns what the user did."""
    chain = chain_of(db, task)
    for t in chain:
        t.status = FollowUpTaskStatus.DONE.value if t.id == task.id else FollowUpTaskStatus.CANCELLED.value
        t.updated_at = datetime.utcnow()
    try:
        from backend.app.services.i7 import user_done

        zone = _zone(db, task.user_id)
        today = datetime.now(timezone.utc).astimezone(zone).date()
        user_done.record(
            db, task.user_id, kind="commitment", ref_id=int(meta_of(task).chain_id or task.id), day=today, hhmm=None,
            domain="commitment", done=True,
        )
    except Exception:
        logger.exception("[R-068] I7 user_done not recorded")


_REASONS = frozenset({"no_time", "dont_like", "not_feeling_well", "other"})


def apply_not_done(db: Session, task: models.CareFollowUpTask, reason: Optional[str]) -> None:
    """Not done + the bounded reason: the answered attempt closes, the next follow-up becomes a LIGHTER step tomorrow."""
    clean = reason if reason in _REASONS else "other"
    _repack(task, reason=clean)
    task.status = FollowUpTaskStatus.CANCELLED.value
    nxt = _next_pending(db, task)
    due = follow_up_time(db, task.user_id, base_utc=datetime.now(timezone.utc), days_ahead=1)
    if nxt is None:
        meta = meta_of(task)
        nxt = _create_task(
            db, task.user_id, task.title, due, attempt=int(meta.attempt or 1) + 1,
            domain=meta.domain or commitment_domain(task.title), chain_id=meta.chain_id or task.id, approach="lighter",
        )
    else:
        nxt.due_at = due
    _repack(nxt, approach="lighter", reason=clean)


def apply_later(db: Session, task: models.CareFollowUpTask) -> None:
    """Later: asked again the next local day at 09:00 (never further than 1 day for a postponement)."""
    due = follow_up_time(db, task.user_id, base_utc=datetime.now(timezone.utc), days_ahead=1)
    nxt = _next_pending(db, task)
    if nxt is None:
        nxt = schedule_next_attempt(db, task)
    if nxt is not None:
        # a postponement never moves the next follow-up EARLIER; it is never further than 2 days by construction
        nxt.due_at = max(nxt.due_at, due) if nxt.due_at else due
        nxt.updated_at = datetime.utcnow()


def task_from_notification(db: Session, notification: models.Notification, actor_user_id: int) -> Optional[models.CareFollowUpTask]:
    """Server-side provenance: notification -> the exact task (context_json.commitment_task_id); never a client id."""
    import json

    try:
        ctx = json.loads(notification.context_json) if isinstance(notification.context_json, str) else (notification.context_json or {})
        task_id = int(str((ctx or {}).get("commitment_task_id") or "0"))
    except (TypeError, ValueError):
        return None
    if task_id <= 0 or int(notification.user_id) != int(actor_user_id):
        return None
    task = db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.id == task_id).first()
    if task is None or int(task.user_id) != int(actor_user_id) or not is_commitment(task):
        return None
    return task


def handle_commitment_answer(db: Session, *, notification: models.Notification, actor_user_id: int, payload: dict):
    """Tray answer on a commitment follow-up: done / not done (+reason) / later; any other reaction is only recorded."""
    from backend.app.services.i10.interaction_recorder import record_notification_interaction
    from backend.app.services.i10.interaction_vocabulary import CanonicalInteractionVerb, resolve_interaction_verb

    task = task_from_notification(db, notification, actor_user_id)
    action_id = str(payload.get("action_id") or "").strip().lower()
    verb = resolve_interaction_verb(payload).verb
    authorized = False
    if task is not None:
        if verb is CanonicalInteractionVerb.DONE:
            apply_done(db, task)
            authorized = True
        elif action_id == "plan_not_done":
            apply_not_done(db, task, str(payload.get("reason") or "").strip())
        elif action_id == "later" or verb is CanonicalInteractionVerb.TALK_LATER:
            apply_later(db, task)
    kwargs = {"domain_completion_authorized": True} if authorized else {}
    return record_notification_interaction(
        db, notification=notification, recipient_user_id=actor_user_id, payload=payload, **kwargs
    )
