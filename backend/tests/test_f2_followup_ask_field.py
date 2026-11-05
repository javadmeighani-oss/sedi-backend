"""R-073 (2F, backend part): the opener tells the app which question it asked and which one-tap answers to draw inside Sedi's
message box (``followup_ask``). A tapped answer is sent as an ordinary chat message, so the SAME parsers that read typed answers
must read every label in every language."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app import models, sedi_copy
from backend.app.schemas.interaction import InteractionResponse
from backend.app.services import a3_session_open as so
from backend.app.services import notification_followup_ask as ask
from backend.app.services.notification_openers import parse_followup_reply
from backend.tests.test_r070_followup_ask import _notif, _user_in

_LANGS = ["fa", "ar", "en"]
_REASON_IDS = ["busy_now", "rest_time", "not_in_mood"]


@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("reason_id", _REASON_IDS)
def test_every_reason_label_is_read_back_as_its_own_reason(lang, reason_id):
    label = sedi_copy.t(f"ask.quick.reason.{reason_id}", lang)
    assert ask.parse_reason(label) == reason_id, (lang, label)


@pytest.mark.parametrize("lang", _LANGS)
def test_the_other_reason_label_is_never_read_as_a_reason(lang):
    label = sedi_copy.t("ask.quick.reason.other", lang)
    assert ask.parse_reason(label) is None  # the conversation continues; nothing is recorded by guess


@pytest.mark.parametrize("lang", _LANGS)
def test_the_done_and_not_done_labels_are_read_back(lang):
    assert parse_followup_reply(sedi_copy.t("ask.quick.unanswered.done", lang)) == ("done", None), lang
    verdict = parse_followup_reply(sedi_copy.t("ask.quick.unanswered.not_done", lang))
    assert verdict is not None and verdict[0] == "not_done", lang


@pytest.mark.parametrize("lang", _LANGS)
def test_the_options_of_each_kind(lang):
    reason = ask.quick_options(ask.Pending(1, "reason", "plan_nutrition"), lang)
    assert [o["id"] for o in reason] == ["busy_now", "rest_time", "not_in_mood", "other"]
    assert all(o["label"] and "{" not in o["label"] for o in reason)
    unanswered = ask.quick_options(ask.Pending(1, "unanswered", "reminder"), lang)
    assert [o["id"] for o in unanswered] == ["done", "not_done"]
    assert ask.quick_options(ask.Pending(1, "unanswered", "post_event"), lang) == []  # the outcome is free text


def test_the_opener_carries_the_ask_and_nothing_else_does(db):
    u = _user_in(db, "+17770400001")
    plain_text, plain_ask = so._followup_opener(db, u, "fa", "سلام قدیمی؟")
    assert plain_text == "سلام قدیمی؟" and plain_ask is None
    n = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=5)
    db.add(models.InteractionEvent(user_id=u.id, event_type="notification_dislike", source="notification", source_notification_id=n.id))
    n.created_at = n.sent_at = datetime.utcnow() - timedelta(hours=5)
    db.commit()
    text, found = so._followup_opener(db, u, "fa", "سلام قدیمی؟")
    assert text != "سلام قدیمی؟" and found["kind"] == "reason" and found["notification_id"] == n.id
    assert [o["id"] for o in found["options"]] == ["busy_now", "rest_time", "not_in_mood", "other"]
    again_text, again = so._followup_opener(db, u, "fa", "سلام قدیمی؟")  # once per notification and once per day
    assert again_text == "سلام قدیمی؟" and again is None


def test_the_response_model_accepts_the_field_and_defaults_to_none():
    base = dict(message="x", language="fa", timestamp=datetime.now(timezone.utc))
    assert InteractionResponse(**base).followup_ask is None
    with_ask = InteractionResponse(**base, followup_ask={"kind": "reason", "notification_id": 3, "options": [{"id": "busy_now", "label": "درگیر بودم"}]})
    assert with_ask.followup_ask["options"][0]["label"] == "درگیر بودم"


@pytest.mark.parametrize("lang,reason_id", [(lang, rid) for lang in _LANGS for rid in _REASON_IDS])
def test_a_tapped_label_is_recorded_exactly_like_a_typed_answer(db, lang, reason_id):
    u = _user_in(db, f"+177704{abs(hash((lang, reason_id))) % 90000 + 10000}", lang)
    n = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", hours_ago=5)
    db.add(models.InteractionEvent(user_id=u.id, event_type="notification_dislike", source="notification", source_notification_id=n.id))
    db.commit()
    ask.mark_asked(db, u.id, ask.Pending(n.id, "reason", "plan_nutrition"), "q?")
    db.commit()
    label = sedi_copy.t(f"ask.quick.reason.{reason_id}", lang)
    ctx = ask.answer_pending(db, u.id, label)
    db.commit()
    assert ctx["followup_result"] == f"reason:{reason_id}"
    assert db.query(models.InteractionEvent).filter_by(user_id=u.id, event_type="notification_dislike_reason", source_notification_id=n.id).count() == 1


def test_the_route_and_the_session_open_are_wired():
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "app"
    assert 'followup_ask=data.get("followup_ask")' in (app / "routers" / "interact.py").read_text(encoding="utf-8")
    assert '"followup_ask": followup_ask' in (app / "services" / "a3_session_open.py").read_text(encoding="utf-8")
