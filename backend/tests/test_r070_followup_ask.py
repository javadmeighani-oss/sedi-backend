"""R-070 / R-072 (step 2C-1): Sedi asks the REASON herself in chat and follows up a notification nobody answered.

Matrix: reason answers x languages (parser), notification states x kinds (selection), opener, answer flow, wiring.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app import models, sedi_copy
from backend.app.services import a3_session_open as so
from backend.app.services import notification_followup_ask as fa
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

_LANGS = ["fa", "ar", "en"]
_NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)


def _user_in(db, phone, lang="fa"):
    u = _user(db, phone, tz="Asia/Tehran")
    u.name = "جواد"
    u.preferred_language = lang
    u.sedi_intro_completed_at = _NOW - timedelta(days=5)
    db.commit()
    _seed_consent(db, u.id)
    ensure_self_subject_for_account(db, u.id, commit=True)
    return u


def _notif(db, uid, template_key, family, *, hours_ago, status="sent", source_type=None, source_id=None):
    when = (_NOW - timedelta(hours=hours_ago)).replace(tzinfo=None)
    n = models.Notification(
        user_id=uid, type="connection_ping", title="صدی", body="x", channel="push", status=status, is_sent=True,
        template_key=template_key, semantic_family=family, source_type=source_type, source_id=source_id,
        created_at=when, sent_at=when,
    )
    db.add(n)
    db.commit()
    return n


def _event(db, uid, nid, event_type, *, reason=None, source="notification"):
    db.add(models.InteractionEvent(
        user_id=uid, event_type=event_type, source=source, source_notification_id=nid,
        metadata_json=json.dumps({"reason": reason}) if reason else None,
        created_at=(_NOW - timedelta(hours=1)).replace(tzinfo=None),
    ))
    db.commit()


# ---- reading the reason (parser) -----------------------------------------------------------------------------------------
_REASONS = [
    ("الان درگیرم", "busy_now"), ("سرم شلوغ بود", "busy_now"), ("وقت نداشتم", "busy_now"), ("مشغول بودم", "busy_now"),
    ("وقت استراحتم بود", "rest_time"), ("خواب بودم", "rest_time"), ("حوصله نداشتم", "not_in_mood"), ("دلم نخواست", "not_in_mood"),
    ("درگیر بودم و حوصله هم نداشتم", "busy_now"),
    ("خیلی پیام می‌فرستی", "too_frequent"), ("به من ربطی ندارد", "irrelevant"), ("نفهمیدم", "unclear"), ("وقتش مناسب نبود", "wrong_timing"),
    ("به درد نخورد", "not_helpful"),
    ("I was busy", "busy_now"), ("no time", "busy_now"), ("it was my rest time", "rest_time"), ("I was asleep", "rest_time"),
    ("not in the mood", "not_in_mood"), ("I didn't feel like it", "not_in_mood"), ("too many messages", "too_frequent"),
    ("not relevant to me", "irrelevant"), ("I didn't understand", "unclear"), ("bad timing", "wrong_timing"), ("not helpful", "not_helpful"),
    ("كنت مشغولا", "busy_now"), ("وقت الراحة", "rest_time"), ("ما عندي مزاج", "not_in_mood"), ("رسائل كثيرة", "too_frequent"),
    ("غير واضح", "unclear"), ("توقيت سيئ", "wrong_timing"), ("غير مفيد", "not_helpful"),
    # never guessed
    ("درگیر نبودم", None), ("I was not busy", None), ("چرا می‌پرسی؟", None), ("why do you ask?", None), ("", None), ("سلام", None),
    ("درگیر بودم ولی پیام‌ها هم زیاد پیام بود و به من ربطی ندارد", None),
    ("امروز صبح رفتم بیرون قدم زدم و بعد برگشتم خانه و ناهار خوردم و کمی درگیر بودم و بعد هم رفتم سر کار و دیر آمدم خانه و خسته بودم خیلی", None),
]


@pytest.mark.parametrize("message,expected", _REASONS)
def test_a_short_answer_is_read_into_one_bounded_reason_and_everything_else_is_never_guessed(message, expected):
    assert fa.parse_reason(message) == expected


def test_every_reason_the_parser_returns_is_a_bounded_reason_of_the_ledger():
    from backend.app.services.i10.interaction_vocabulary import BOUNDED_DISLIKE_REASONS

    assert {r for _m, r in _REASONS if r} <= BOUNDED_DISLIKE_REASONS


# ---- selection -----------------------------------------------------------------------------------------------------------
def test_a_negative_reaction_without_a_reason_is_asked_once_after_three_hours(db):
    u = _user_in(db, "+17770090001")
    n = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=5)
    _event(db, u.id, n.id, "notification_dislike")
    pending = fa.pick_pending(db, u, now=_NOW)
    assert pending == fa.Pending(n.id, "reason", "plan_nutrition")
    fa.mark_asked(db, u.id, pending, "q")
    db.commit()
    assert fa.pick_pending(db, u, now=_NOW + timedelta(days=1)) is None  # once per notification


@pytest.mark.parametrize("hours,expected", [(1, False), (2.9, False), (3.1, True), (47, True), (49, False)])
def test_a_reason_is_only_asked_between_three_and_forty_eight_hours(db, hours, expected):
    u = _user_in(db, f"+177700910{int(hours * 10):02d}")
    n = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=hours)
    _event(db, u.id, n.id, "notification_not_now")
    assert (fa.pick_pending(db, u, now=_NOW) is not None) is expected


def test_a_reaction_that_already_has_a_reason_is_never_asked_again(db):
    u = _user_in(db, "+17770090002")
    a = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=5)
    _event(db, u.id, a.id, "notification_dislike")
    _event(db, u.id, a.id, "notification_dislike_reason", reason="busy_now")
    b = _notif(db, u.id, "exercise_plan_follow_up", "EXERCISE_PLAN_FOLLOW_UP", hours_ago=6)
    _event(db, u.id, b.id, "notification_not_now", reason="not_in_mood")
    assert fa.pick_pending(db, u, now=_NOW) is None
    c = _notif(db, u.id, "exercise_plan_follow_up", "EXERCISE_PLAN_FOLLOW_UP", hours_ago=7)
    _event(db, u.id, c.id, "notification_not_now", reason="other")  # a tray «not done» with no real reason is still unanswered
    assert fa.pick_pending(db, u, now=_NOW).notification_id == c.id


@pytest.mark.parametrize("template,family", [("commitment_follow_up", "CARE_ACTION"), ("daily_digest", "DAILY_WELLNESS_DIGEST")])
def test_the_morning_digest_and_the_commitment_loop_are_never_asked(db, template, family):
    u = _user_in(db, f"+1777009{abs(hash(template)) % 90000 + 10000}")
    n = _notif(db, u.id, template, family, hours_ago=5)
    _event(db, u.id, n.id, "notification_dislike")
    assert fa.pick_pending(db, u, now=_NOW) is None


def test_the_reaction_of_another_user_is_never_used(db):
    mine = _user_in(db, "+17770090003")
    other = _user_in(db, "+17770090004")
    n = _notif(db, other.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=5)
    _event(db, other.id, n.id, "notification_dislike")
    assert fa.pick_pending(db, mine, now=_NOW) is None


def test_at_most_one_question_per_local_day_and_the_reaction_comes_before_silence(db):
    u = _user_in(db, "+17770090005")
    silent = _notif(db, u.id, "generic_event_reminder", "REMINDER", hours_ago=30, source_type="user_event")
    ev = models.UserEvent(user_id=u.id, title="جلسه", event_domain="work", event_type="meeting", starts_at=(_NOW - timedelta(hours=29)).replace(tzinfo=None), status="scheduled")
    db.add(ev)
    db.commit()
    silent.source_id = str(ev.id)
    db.commit()
    reacted = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=10)
    _event(db, u.id, reacted.id, "notification_dislike")
    first = fa.pick_pending(db, u, now=_NOW)
    assert first.kind == "reason" and first.notification_id == reacted.id
    fa.mark_asked(db, u.id, first, "q")
    db.commit()
    assert fa.pick_pending(db, u, now=_NOW + timedelta(hours=1)) is None  # same local day
    nxt = fa.pick_pending(db, u, now=_NOW + timedelta(hours=20))  # the next local day: the silent reminder, now still < 72 h
    assert nxt is not None and nxt.kind == "unanswered" and nxt.notification_id == silent.id


def _reminder(db, u, *, hours_ago=30, event_status="scheduled", event_ago_hours=29):
    n = _notif(db, u.id, "generic_event_reminder", "REMINDER", hours_ago=hours_ago, source_type="user_event")
    ev = models.UserEvent(
        user_id=u.id, title="جلسه", event_domain="work", event_type="meeting",
        starts_at=(_NOW - timedelta(hours=event_ago_hours)).replace(tzinfo=None), status=event_status,
    )
    db.add(ev)
    db.commit()
    n.source_id = str(ev.id)
    db.commit()
    return n


@pytest.mark.parametrize("hours,expected", [(10, False), (23, False), (25, True), (71, True), (80, False)])
def test_an_unanswered_action_notification_is_followed_up_after_about_a_day(db, hours, expected):
    u = _user_in(db, f"+177700920{int(hours):02d}")
    _reminder(db, u, hours_ago=hours, event_ago_hours=hours - 1)
    assert (fa.pick_pending(db, u, now=_NOW) is not None) is expected


@pytest.mark.parametrize("answer", ["notification_done", "notification_open_chat", "chat_message", "notification_like", "notification_talk_later"])
def test_an_answered_notification_is_not_followed_up(db, answer):
    u = _user_in(db, f"+1777009300{abs(hash(answer)) % 90}")
    n = _reminder(db, u)
    _event(db, u.id, n.id, answer)
    kind = fa.pick_pending(db, u, now=_NOW)
    assert kind is None or kind.kind != "unanswered"


@pytest.mark.parametrize("status", ["completed", "cancelled", "missed"])
def test_a_thing_already_completed_elsewhere_is_never_asked_about(db, status):
    u = _user_in(db, f"+1777009400{abs(hash(status)) % 90}")
    _reminder(db, u, event_status=status)
    assert fa.pick_pending(db, u, now=_NOW) is None


def test_an_event_that_has_not_happened_yet_is_never_asked_about(db):
    u = _user_in(db, "+17770094001")
    _reminder(db, u, event_ago_hours=-5)
    assert fa.pick_pending(db, u, now=_NOW) is None


def test_medication_and_plan_items_are_only_asked_when_their_owner_confirms_it_is_still_open(db):
    u = _user_in(db, "+17770095001")
    _notif(db, u.id, "medication_reminder", "MEDICATION_DUE", hours_ago=30)  # no dose occurrence: unsure -> never ask
    _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=30)  # no I8 provenance: unsure -> never ask
    assert fa.pick_pending(db, u, now=_NOW) is None


def test_informational_pushes_are_not_followed_up_when_unanswered(db):
    u = _user_in(db, "+17770095002")
    _notif(db, u.id, "plan_motivation_milestone", "ENGAGEMENT", hours_ago=30)
    _notif(db, u.id, "weekly_plan_review", "CARE_ACTION", hours_ago=30)
    assert fa.pick_pending(db, u, now=_NOW) is None


# ---- the opener ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", _LANGS)
def test_the_opener_is_the_greeting_plus_one_question_and_marks_the_notification(db, lang):
    u = _user_in(db, f"+1777009600{_LANGS.index(lang)}", lang)
    n = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=5)
    _event(db, u.id, n.id, "notification_dislike")
    text = fa.compose_opener(db, u, "Hi.", lang)
    assert text.startswith("Hi.\n\n") and "{" not in text
    assert text.count("؟") + text.count("?") == 1  # ONE question in the whole opener
    assert db.query(models.InteractionEvent).filter_by(user_id=u.id, event_type=fa.ASKED_EVENT, source_notification_id=n.id).count() == 1
    assert fa.compose_opener(db, u, "Hi.", lang) is None  # nothing pending any more


def test_the_session_opener_is_replaced_by_the_question_only_when_something_is_pending(db):
    u = _user_in(db, "+17770096100")
    plain = so._with_pending_followup(db, u, "fa", "سلام قدیمی؟")
    assert plain == "سلام قدیمی؟"
    n = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=5)
    _event(db, u.id, n.id, "notification_dislike")
    # the real clock is used inside: age the notification relative to now
    n.created_at = n.sent_at = datetime.utcnow() - timedelta(hours=5)
    db.commit()
    text = so._with_pending_followup(db, u, "fa", "سلام قدیمی؟")
    assert text != "سلام قدیمی؟" and sedi_copy.t("ask.subject.plan_nutrition", "fa") in text and text.count("؟") == 1


# ---- the answer ---------------------------------------------------------------------------------------------------------
def _ask(db, u, n, kind, subject="plan_nutrition"):
    fa.mark_asked(db, u.id, fa.Pending(n.id, kind, subject), "پرسش؟")
    db.commit()


def test_a_reason_answer_is_recorded_through_the_same_ledger_path_as_the_tray(db):
    u = _user_in(db, "+17770097001")
    n = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=5)
    _event(db, u.id, n.id, "notification_dislike")
    _ask(db, u, n, "reason")
    ctx = fa.answer_pending(db, u.id, "الان درگیرم", now=_NOW)
    db.commit()
    assert ctx["followup_result"] == "reason:busy_now" and ctx["opening_message"] == "پرسش؟" and ctx["template_key"] == "followup_reason_ask"
    reason_rows = db.query(models.InteractionEvent).filter_by(user_id=u.id, event_type="notification_dislike_reason", source_notification_id=n.id).all()
    assert len(reason_rows) == 1 and json.loads(reason_rows[0].metadata_json)["reason"] == "busy_now"
    # the same notification now HAS a reason, so it is never a candidate again
    db.query(models.InteractionEvent).filter_by(user_id=u.id, event_type=fa.ASKED_EVENT).delete()
    db.commit()
    assert fa.pick_pending(db, u, now=_NOW) is None


def test_only_the_first_reply_is_read_and_an_unclear_reply_records_nothing(db):
    u = _user_in(db, "+17770097002")
    n = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=5)
    _ask(db, u, n, "reason")
    ctx = fa.answer_pending(db, u.id, "نمی‌دانم راستش", now=_NOW)
    db.commit()
    assert ctx["followup_result"] == "unparsed"
    assert db.query(models.InteractionEvent).filter_by(user_id=u.id, event_type="notification_dislike_reason").count() == 0
    assert fa.answer_pending(db, u.id, "الان درگیرم", now=_NOW) is None  # the next message is just a conversation


def test_a_reply_after_the_session_window_is_not_read_as_the_answer(db):
    u = _user_in(db, "+17770097003")
    n = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=5)
    _ask(db, u, n, "reason")
    row = db.query(models.InteractionEvent).filter_by(user_id=u.id, event_type=fa.ASKED_EVENT).one()
    row.created_at = (_NOW - timedelta(hours=7)).replace(tzinfo=None)
    db.commit()
    assert fa.answer_pending(db, u.id, "الان درگیرم", now=_NOW) is None


@pytest.mark.parametrize("message,expected", [("آره", "done"), ("نه، وقت نداشتم", "not_done:no_time"), ("نشد", "not_done:other"), ("یک چیز دیگر", "unparsed")])
def test_an_unanswered_follow_up_reads_done_or_not_done_and_keeps_it_in_the_ledger(db, message, expected):
    u = _user_in(db, f"+1777009710{abs(hash(message)) % 90:02d}")
    n = _reminder(db, u)
    _ask(db, u, n, "unanswered", "reminder")
    ctx = fa.answer_pending(db, u.id, message, now=_NOW)
    db.commit()
    assert ctx["followup_result"] == expected and ctx["template_key"] == "followup_unanswered_ask"
    result = db.query(models.InteractionEvent).filter_by(user_id=u.id, event_type=fa.RESULT_EVENT).one()
    assert json.loads(result.metadata_json)["result"] == expected


def test_nobody_elses_question_is_ever_answered(db):
    u = _user_in(db, "+17770097201")
    other = _user_in(db, "+17770097202")
    n = _notif(db, other.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=5)
    _ask(db, other, n, "reason")
    assert fa.answer_pending(db, u.id, "الان درگیرم", now=_NOW) is None


# ---- wiring -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("key", ["reminder", "medication", "plan_nutrition", "plan_exercise", "weekly_review", "motivation_workout_day",
                                 "motivation_comeback", "motivation_milestone", "post_event", "commitment", "other"])
def test_every_subject_has_a_noun_in_every_language_and_the_questions_have_one_question_mark(key, lang):
    subject = sedi_copy.t(f"ask.subject.{key}", lang, default="en")
    for kind in ("reason", "unanswered"):
        text = fa.question_text(fa.Pending(1, kind, key), lang)
        assert subject in text and "{" not in text and text.count("؟") + text.count("?") == 1


def test_the_opener_the_chat_and_the_model_context_are_wired():
    app = Path(__file__).resolve().parents[1] / "app"
    assert "_with_pending_followup(db, user, lang, proactive)" in (app / "services" / "a3_session_open.py").read_text(encoding="utf-8")
    assert "answer_pending(db, user_id, message)" in (app / "routers" / "interact.py").read_text(encoding="utf-8")
    from backend.app.core.conversation.brain import _format_notification_context_block

    block = _format_notification_context_block(
        {"template_key": "followup_reason_ask", "opening_message": "q", "followup_result": "reason:busy_now"}
    )
    assert "set the notification aside (busy_now)" in block and "do not ask a new question" in block
    unparsed = _format_notification_context_block({"template_key": "followup_reason_ask", "opening_message": "q", "followup_result": "unparsed"})
    assert "in their own words" in unparsed
