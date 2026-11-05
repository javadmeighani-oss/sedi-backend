"""R-052 (step 2B): notification -> chat CONTINUITY - one unbroken line push -> opener -> conversation.

When the user opens the app from a Sedi notification, Sedi starts the chat HERSELF on the SAME subject and the same tracked
commitment the push carried - a direct, specific follow-up (the push itself stays lock-screen safe; inside the app she can
name the step / the event). Before this module only the daily digest, the care check-in and the presence ping had a
specific opener; every other family fell back to the generic «continue that or something else?».

* ``family_opener``        - the opener of a commitment follow-up, event reminders, medication, plan follow-ups, the weekly
                             review, the motivation notifications and the post-event follow-up (text lives in the copy
                             catalog, R-043, keys ``session.origin.*``);
* ``parse_followup_reply`` - a SHORT answer to the commitment opener («آره» / «نه، وقت نداشتم») read deterministically;
* ``apply_chat_answer``    - that answer updates the commitment exactly like the tray buttons (done / not done + reason).

Deterministic, no model call, fail-open (every function returns None / the input on any problem).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models, sedi_copy

logger = logging.getLogger(__name__)

_MAX_TITLE = 80
_MAX_REPLY_WORDS = 6
_EVENT_REMINDER_KEYS = frozenset({"generic_event_reminder", "doctor_appointment_reminder", "lab_appointment_reminder", "medical_event_reminder"})
_MEDICATION_FAMILIES = frozenset({"MEDICATION_DUE", "MEDICATION_FOLLOW_UP"})


def _lang(language: Optional[str]) -> str:
    code = (language or "fa").split("-")[0].lower()
    return code if code in ("fa", "ar", "en") else "en"


def _prefix(name: Optional[str], lang: str) -> str:
    cleaned = (name or "").strip()
    return sedi_copy.t("address.plain", lang, name=cleaned) if cleaned else ""


def _event_title(db: Session, user_id: int, notification: models.Notification) -> str:
    """The title of the user's OWN event behind an event reminder (ownership checked); '' when unknown."""
    try:
        source_id = str(notification.source_id or "").strip()
        if not source_id.isdigit():
            return ""
        row = db.query(models.UserEvent).filter(models.UserEvent.id == int(source_id), models.UserEvent.user_id == user_id).first()
        return " ".join((row.title or "").split())[:_MAX_TITLE] if row else ""
    except Exception:
        return ""


def _context(notification: models.Notification) -> dict:
    try:
        loaded = json.loads(notification.context_json) if isinstance(notification.context_json, str) else (notification.context_json or {})
        return loaded if isinstance(loaded, dict) else {}
    except (TypeError, ValueError):
        return {}


def _commitment_opener(db: Session, user_id: int, notification: models.Notification, lang: str) -> Optional[str]:
    from backend.app.services.i10.commitment_followup import task_from_notification

    task = task_from_notification(db, notification, user_id)
    if task is None:
        return None
    from backend.app.services.i10.commitment_followup import meta_of

    step = " ".join((task.title or "").split())[:160]
    if not step:
        return None
    meta = meta_of(task)
    key = "session.origin.commitment_lighter" if meta.approach == "lighter" and int(meta.attempt or 1) > 1 else "session.origin.commitment"
    return sedi_copy.t(key, lang, step=step)


def _key_for(notification: models.Notification) -> Optional[str]:
    template = (notification.template_key or "").strip()
    family = (notification.semantic_family or "").strip()
    if template == "commitment_follow_up":
        return "commitment"
    if template == "assurance_follow_up":
        return "assurance"
    if template in _EVENT_REMINDER_KEYS:
        return "reminder"
    if family in _MEDICATION_FAMILIES:
        return "medication"
    if template == "nutrition_plan_follow_up" or family == "NUTRITION_PLAN_FOLLOW_UP":
        return "plan_nutrition"
    if template == "exercise_plan_follow_up" or family == "EXERCISE_PLAN_FOLLOW_UP":
        return "plan_exercise"
    if template == "weekly_plan_review":
        return "weekly_review"
    if template.startswith("plan_motivation_"):
        kind = template[len("plan_motivation_"):]
        return f"motivation_{kind}" if kind in ("workout_day", "comeback", "milestone") else None
    if template == "post_event_follow_up" or family == "POST_EVENT_FOLLOW_UP":
        return "post_event"
    return None


def family_opener(
    db: Session, user: models.User, notification: models.Notification, *, language: str, name: Optional[str] = None
) -> Optional[str]:
    """The specific opener of a notification family, or None (the caller keeps its generic fallback)."""
    try:
        lang = _lang(language)
        key = _key_for(notification)
        if key is None:
            return None
        user_id = int(user.id)
        if key == "commitment":
            body = _commitment_opener(db, user_id, notification, lang)
            if body is None:
                return None
        elif key == "reminder":
            title = _event_title(db, user_id, notification)
            body = sedi_copy.t("session.origin.reminder", lang, title=title) if title else sedi_copy.t("session.origin.reminder_notitle", lang)
        else:
            body = sedi_copy.t(f"session.origin.{key}", lang)
        return (_prefix(name, lang) + body).strip()
    except Exception:
        logger.exception("[R-052] family opener skipped")
        return None


# ---- the user's SHORT answer to the commitment opener -------------------------------------------------------------------
_FOLD = (("ي", "ی"), ("ك", "ک"), ("ى", "ی"), ("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("‌", " "))


def _fold_letters(text: str) -> str:
    """Arabic / Persian letter variants meet in one form (regex-safe: punctuation is kept)."""
    out = (text or "").lower()
    for a, b in _FOLD:
        out = out.replace(a, b)
    return re.sub(r"[ً-ْ]", "", out)


def _fold(text: str) -> str:
    """A user message in the form the patterns expect: letters folded, punctuation and extra spaces removed."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", _fold_letters(text))).strip()


def _p(*parts: str) -> re.Pattern:
    return re.compile("(?:" + "|".join(_fold_letters(p) for p in parts) + ")")


_DONE = _p(
    r"^(?:اره|ارع|بله|اری|انجام دادم|انجام شد|کردم|خوردم|رفتم|ورزش کردم|زدم|خواندم)\b",
    r"^(?:yes|yeah|yep|yup|done|i did|did it|i have done|i have finished|i finished|completed|sure|all done)\b",
    r"^(?:نعم|اجل|انجزت|فعلتها|تم)\b",
)
# negations are checked FIRST and ANYWHERE: «I did not», «I have not», «آره نکردم» are never a completion (Codex P2 on PR #145)
_NOT_DONE = _p(
    r"^(?:نه|خیر|نشد|نکردم|نتونستم|نتوانستم|انجام نشد|هنوز نه|نخوردم|نرفتم)\b",
    r"^(?:no|nope|not yet|didn t|did not|couldn t|could not|can t|cannot|never|haven t|have not|hasn t|i didn t|i did not|i couldn t|i could not|i haven t|i have not|i never)\b",
    r"^(?:لا|لم افعل|لم استطع|ما قدرت|لم انجز)\b",
)
_NEGATION = _p(
    r"\bnot\b", r"\bnever\b", r"\bno\b", r"\bnope\b", r"\bcan t\b", r"\bcannot\b", r"\bwon t\b", r"\bn t\b",
    r"\bنه\b", r"نکرد", r"نشد", r"نتون", r"نتوان", r"نخورد", r"نرفت", r"\bخیر\b", r"\bلا\b", r"\bلم\b", r"ما قدرت", r"ما استطع",
)
_BUT = _p(r"\bولی\b", r"\bاما\b", r"\bbut\b", r"\bلكن\b", r"\bلکن\b")
_REASONS = (
    ("no_time", _p(r"وقت ندا", r"شلوغ", r"فرصت", r"no time", r"busy", r"لم يكن عندي وقت", r"مشغول")),
    ("not_feeling_well", _p(r"حال ندا", r"حالم خوب", r"حالم بد", r"مریض", r"بیمار", r"خسته", r"درد", r"unwell", r"sick", r"tired", r"not feeling", r"مريض", r"تعب")),
    ("dont_like", _p(r"دوست ندا", r"حوصله", r"نخواستم", r"خوشم نیا", r"don t like", r"didn t like", r"bored", r"مللت", r"لم احب")),
)


def parse_followup_reply(message: str) -> Optional[tuple]:
    """('done', None) / ('not_done', reason) for a SHORT, unambiguous answer; None for anything else.

    Cautious by design (a wrong «done» would close a commitment the user never completed): a question, a mixed answer
    («آره ولی …»), a negation anywhere in an affirmative, or more than four words after «done» is never read as done."""
    raw = message or ""
    folded = _fold(raw)
    if not folded or len(folded.split()) > _MAX_REPLY_WORDS or "?" in raw or "؟" in raw:
        return None
    if _BUT.search(folded):
        return None
    if _NOT_DONE.search(folded):
        reason = next((name for name, pattern in _REASONS if pattern.search(folded)), "other")
        return ("not_done", reason)
    if _NEGATION.search(folded):
        return None
    if _DONE.search(folded) and len(folded.split()) <= 4:
        return ("done", None)
    return None


def apply_chat_answer(
    db: Session, notification: models.Notification, user_id: int, message: str
) -> Optional[str]:
    """A short chat answer to a commitment opener updates the commitment like the tray buttons. Only a follow-up that is
    still awaiting its answer (NOTIFIED) is touched, so a replay or a later unrelated «نه» never changes it. Returns
    'done' / 'not_done:<reason>' or None. Fail-open."""
    try:
        if (notification.template_key or "") in (
            "assurance_follow_up", "medication_reminder", "generic_event_reminder", "nutrition_plan_follow_up", "exercise_plan_follow_up"
        ):
            # R-070 (2D): a short chat answer about a dose / reminder / assurance goes through the owner and I7
            from backend.app.services.i10.action_done import apply_chat_answer as record_owner

            verdict_owner = parse_followup_reply(message)
            return record_owner(db, notification, user_id, verdict_owner) if verdict_owner is not None else None
        if (notification.template_key or "") != "commitment_follow_up":
            return None
        from backend.app.services.i10.commitment_followup import apply_done, apply_not_done, task_from_notification

        task = task_from_notification(db, notification, user_id)
        if task is None or task.status != "notified":
            return None
        verdict = parse_followup_reply(message)
        if verdict is None:
            return None
        with db.begin_nested():
            if verdict[0] == "done":
                apply_done(db, task)
                return "done"
            apply_not_done(db, task, verdict[1])
            return f"not_done:{verdict[1]}"
    except Exception:
        logger.exception("[R-052] chat answer not applied")
        return None
