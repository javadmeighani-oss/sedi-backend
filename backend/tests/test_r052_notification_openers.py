"""R-052 (step 2B): notification -> chat continuity - family openers, the opener in the chat context, short chat answers.

Matrix: families x languages (openers), answers x languages (parser), states (apply), wiring.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app import models, sedi_copy
from backend.app.services import a3_session_open as so
from backend.app.services import notification_openers as no
from backend.app.services.i10 import commitment_followup as cf
from backend.app.services.i10.contextual_followup_worker import process_due_follow_up_tasks
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

_LANGS = ["fa", "ar", "en"]
# (template_key, semantic_family, copy key suffix)
_FAMILIES = [
    ("nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", "plan_nutrition"),
    ("exercise_plan_follow_up", "EXERCISE_PLAN_FOLLOW_UP", "plan_exercise"),
    ("weekly_plan_review", "CARE_ACTION", "weekly_review"),
    ("plan_motivation_workout_day", "ENGAGEMENT", "motivation_workout_day"),
    ("plan_motivation_comeback", "ENGAGEMENT", "motivation_comeback"),
    ("plan_motivation_milestone", "ENGAGEMENT", "motivation_milestone"),
    ("post_event_follow_up", "POST_EVENT_FOLLOW_UP", "post_event"),
    ("medication_reminder", "MEDICATION_DUE", "medication"),
]


@pytest.fixture(autouse=True)
def _flag_and_policy():
    with patch(
        "backend.app.services.i10.contextual_followup_worker.contextual_followup_enabled", return_value=True
    ), patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy", return_value=(True, {})
    ), patch(
        "backend.app.services.notification_runtime.quiet_hours.is_within_quiet_hours", return_value=False
    ):
        yield


def _user_in(db, phone, lang="fa"):
    u = _user(db, phone, tz="Asia/Tehran")
    u.name = "جواد"
    u.preferred_language = lang
    db.commit()
    _seed_consent(db, u.id)
    ensure_self_subject_for_account(db, u.id, commit=True)
    return u


def _notif(db, uid, template_key, family, *, source_type=None, source_id=None, context=None):
    n = models.Notification(
        user_id=uid, type="connection_ping", title="صدی", body="x", channel="push", status="sent",
        template_key=template_key, semantic_family=family, source_type=source_type, source_id=source_id,
    )
    if context:
        import json

        n.context_json = json.dumps(context)
    db.add(n)
    db.commit()
    return n


@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("template_key,family,suffix", _FAMILIES)
def test_every_family_continues_its_own_subject_in_every_language(db, template_key, family, suffix, lang):
    u = _user_in(db, f"+1777008{abs(hash((template_key, lang))) % 90000 + 10000}", lang)
    n = _notif(db, u.id, template_key, family)
    text = so.build_notification_origin_opener(db, u, n, language=lang)
    expected = sedi_copy.t(f"session.origin.{suffix}", lang)
    assert expected in text
    assert text != sedi_copy.t("session.origin_generic", lang, prefix="").strip()  # never the generic line
    assert "{" not in text and text.count("؟") + text.count("?") in (1, 2)


@pytest.mark.parametrize("lang", _LANGS)
def test_an_event_reminder_names_the_users_own_event_and_never_another_users(db, lang):
    u = _user_in(db, "+17770081001", lang)
    other = _user_in(db, "+17770081002", lang)
    mine = models.UserEvent(user_id=u.id, title="آزمایش خون", event_domain="medical", event_type="lab_test", starts_at=datetime.utcnow() + timedelta(days=1))
    theirs = models.UserEvent(user_id=other.id, title="راز دیگری", event_domain="medical", event_type="lab_test", starts_at=datetime.utcnow() + timedelta(days=1))
    db.add_all([mine, theirs])
    db.commit()
    own = _notif(db, u.id, "lab_appointment_reminder", "LAB_APPOINTMENT_REMINDER", source_type="user_event", source_id=str(mine.id))
    text = so.build_notification_origin_opener(db, u, own, language=lang)
    assert "آزمایش خون" in text
    foreign = _notif(db, u.id, "generic_event_reminder", "REMINDER", source_type="user_event", source_id=str(theirs.id))
    text = so.build_notification_origin_opener(db, u, foreign, language=lang)
    assert "راز دیگری" not in text and sedi_copy.t("session.origin.reminder_notitle", lang) in text


def test_an_unknown_family_keeps_the_generic_fallback(db):
    u = _user_in(db, "+17770081003")
    n = _notif(db, u.id, "care_data_gap", "CARE_DATA_GAP")
    assert no.family_opener(db, u, n, language="fa") is None
    assert so.build_notification_origin_opener(db, u, n, language="fa") == so._generic_notification_origin_opener(lang="fa", name="جواد")


# ---- the commitment opener ---------------------------------------------------------------------------------------------
_SLEEP = "وقتی بیدار شدی ساعت را چک نکن و در نور کم کار آرامی انجام بده. فردا درباره‌اش می‌پرسم."


def _send(db, task):
    assert process_due_follow_up_tasks(db, now=task.due_at + timedelta(minutes=1)) == 1
    db.refresh(task)
    return db.query(models.Notification).filter(models.Notification.user_id == task.user_id).order_by(models.Notification.id.desc()).first()


@pytest.mark.parametrize("lang", _LANGS)
def test_the_commitment_opener_says_the_step_and_asks_once(db, lang):
    u = _user_in(db, f"+1777008200{_LANGS.index(lang)}", lang)
    task = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    notif = _send(db, task)
    text = so.build_notification_origin_opener(db, u, notif, language=lang)
    assert "نور کم" in text and "{" not in text
    assert text.count("؟") + text.count("?") == 2  # «done?» + «if not, what got in the way?»


def test_after_a_not_done_answer_the_opener_offers_a_lighter_step(db):
    u = _user_in(db, "+17770083001")
    task = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    notif = _send(db, task)
    cf.apply_not_done(db, task, "no_time")
    db.commit()
    pending = [t for t in db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == u.id).all() if t.status == "open"][0]
    nxt = _send(db, pending)
    text = so.build_notification_origin_opener(db, u, nxt, language="fa")
    assert "سبک‌تر" in text and "نور کم" in text and notif.id != nxt.id


# ---- the short answer (parser) -------------------------------------------------------------------------------------------
_ANSWERS = [
    ("آره", ("done", None)), ("بله", ("done", None)), ("انجام دادم", ("done", None)), ("آره آماده‌ام", ("done", None)),
    ("نه", ("not_done", "other")), ("نشد", ("not_done", "other")), ("نه، وقت نداشتم", ("not_done", "no_time")),
    ("نشد چون حالم خوب نبود", ("not_done", "not_feeling_well")), ("نکردم دوست نداشتم", ("not_done", "dont_like")),
    ("yes", ("done", None)), ("done", ("done", None)), ("I did it", ("done", None)),
    ("no", ("not_done", "other")), ("no time, busy", ("not_done", "no_time")), ("I didn't, I was sick", ("not_done", "not_feeling_well")),
    ("نعم", ("done", None)), ("لا", ("not_done", "other")), ("لم أستطع", ("not_done", "other")),
    # Codex P2 on PR #145: a negation or a question is never a completion
    ("I did not", ("not_done", "other")), ("I have not", ("not_done", "other")), ("I haven't yet", ("not_done", "other")),
    ("I have a question", None), ("yes?", None), ("آره نکردم", None), ("yes I did not", None), ("آره؟", None),
    # never guess
    ("سلام", None), ("نه ولی آره", None), ("آره ولی خیلی سخت بود", None), ("no but later", None), ("", None),
    ("آره خیلی خوب بود و بعدش رفتم بیرون قدم زدم و دوباره برگشتم", None),  # long message: a new statement
]


@pytest.mark.parametrize("message,expected", _ANSWERS)
def test_a_short_answer_is_read_and_everything_else_is_never_guessed(message, expected):
    assert no.parse_followup_reply(message) == expected


def test_apply_chat_answer_updates_the_commitment_like_the_tray(db):
    u = _user_in(db, "+17770084001")
    task = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    notif = _send(db, task)
    assert no.apply_chat_answer(db, notif, u.id, "سلام") is None  # not an answer
    assert no.apply_chat_answer(db, notif, u.id, "آره") == "done"
    db.expire_all()
    assert [t.status for t in db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == u.id).order_by(models.CareFollowUpTask.id)] == ["done", "cancelled"]
    assert no.apply_chat_answer(db, notif, u.id, "نه") is None  # replay / later unrelated «نه» never changes a closed chain


def test_a_not_done_chat_answer_stores_the_reason_and_lightens_the_next_step(db):
    u = _user_in(db, "+17770084002")
    task = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    notif = _send(db, task)
    assert no.apply_chat_answer(db, notif, u.id, "نه، وقت نداشتم") == "not_done:no_time"
    db.expire_all()
    rows = db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == u.id).order_by(models.CareFollowUpTask.id).all()
    assert rows[0].status == "cancelled" and cf.meta_of(rows[0]).reason == "no_time"
    assert rows[1].status == "open" and cf.meta_of(rows[1]).approach == "lighter"


def test_only_the_owner_and_only_a_commitment_notification_can_be_answered(db):
    u = _user_in(db, "+17770084003")
    other = _user_in(db, "+17770084004")
    task = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    notif = _send(db, task)
    assert no.apply_chat_answer(db, notif, other.id, "آره") is None
    plain = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP")
    assert no.apply_chat_answer(db, plain, u.id, "آره") is None


# ---- wiring: the chat context -----------------------------------------------------------------------------------------------
def test_the_chat_context_carries_the_opening_message_and_the_followup_result():
    from backend.app.core.conversation.brain import _format_notification_context_block

    block = _format_notification_context_block(
        {"template_key": "commitment_follow_up", "opening_message": "قرارمان این بود: «x». انجام شد؟", "followup_result": "not_done:no_time"}
    )
    assert "opening_message: قرارمان این بود" in block and "answer it, do not ask it again" in block
    assert "followup_result_note: the step was NOT done (no_time)" in block
    done = _format_notification_context_block({"template_key": "commitment_follow_up", "followup_result": "done"})
    assert "celebrate briefly" in done
    assert "opening_message" not in (_format_notification_context_block({"template_key": "x", "category": "c"}) or "")


def test_the_router_and_the_session_open_are_wired():
    app = Path(__file__).resolve().parents[1] / "app"
    router = (app / "routers" / "interact.py").read_text(encoding="utf-8")
    assert "apply_chat_answer(db, notification, user_id, message)" in router and 'notification_context["opening_message"]' in router
    opener = (app / "services" / "a3_session_open.py").read_text(encoding="utf-8")
    assert opener.index("family_opener(db, user, notification") < opener.index("_generic_notification_origin_opener(lang=lang, name=name)")
