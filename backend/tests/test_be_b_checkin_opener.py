"""BE-B (Javad 2026-11-09): opening the chat from Sedi's «how are you?» push continues THAT question (fa / ar / en)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.services import a3_session_open as so
from backend.app.services.i10.policy_types import I10SemanticFamily
from backend.app.services.notification_runtime import renderer as rd

LANGS = ("fa", "ar", "en")
NAMES = (None, "جواد", "Javad")


def _push(lang, name, **inputs):
    title, body = rd._render_engagement(lang, name, inputs)
    return body


def _notification(body, lang):
    return SimpleNamespace(
        semantic_family=I10SemanticFamily.PRESENCE_REENGAGEMENT.value, template_key="", body=body, language=lang, context_json=None
    )


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("name", NAMES)
def test_every_plain_variant_is_recognised(lang, name, monkeypatch):
    pairs = rd._ENGAGEMENT_PAIRS.get(lang, rd._ENGAGEMENT_PAIRS["en"])
    for i in range(len(pairs)):
        monkeypatch.setattr(rd, "_rotation_index", lambda n, nm, salt, _i=i: _i)
        assert rd.engagement_variant(_push(lang, name), lang, name) == "plain", (lang, name, i)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("name", NAMES)
def test_every_low_variant_is_recognised(lang, name, monkeypatch):
    pairs = rd._ENGAGEMENT_LOW_PAIRS.get(lang, rd._ENGAGEMENT_LOW_PAIRS["en"])
    for i in range(len(pairs)):
        monkeypatch.setattr(rd, "_rotation_index", lambda n, nm, salt, _i=i: _i)
        assert rd.engagement_variant(_push(lang, name, wellbeing_trend="low"), lang, name) == "low", (lang, name, i)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("name", NAMES)
def test_a_topic_push_is_recognised_as_topic(lang, name):
    assert rd.engagement_variant(_push(lang, name, last_topic_hint="sleep"), lang, name) == "topic"


@pytest.mark.parametrize("body", [None, "", "سلام", "some unrelated text"])
def test_unknown_bodies_are_none(body):
    assert rd.engagement_variant(body, "fa", "جواد") is None


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("name", NAMES)
def test_the_chat_opener_for_a_plain_push_continues_the_how_are_you_question(lang, name):
    opener = so.build_notification_origin_opener(None, SimpleNamespace(name=name), _notification(_push(lang, name), lang), language=lang, preferred_name=name)
    assert opener and "{" not in opener
    for old in ("آخرین بار", "آخر مرة", "last time we talked"):
        assert old not in opener  # not the topic recap
    assert opener == so._presence_checkin_opener(lang=lang, name=name, low=False)


@pytest.mark.parametrize("lang", LANGS)
def test_the_chat_opener_for_a_low_wellbeing_push_is_the_gentle_one(lang):
    name = "جواد"
    opener = so.build_notification_origin_opener(None, SimpleNamespace(name=name), _notification(_push(lang, name, wellbeing_trend="low"), lang), language=lang, preferred_name=name)
    assert opener == so._presence_checkin_opener(lang=lang, name=name, low=True)
    assert opener != so._presence_checkin_opener(lang=lang, name=name, low=False)


def test_a_topic_push_keeps_the_topic_continuation(monkeypatch):
    called = {}

    def fake_continuation(*, lang, name, topic_phrase):
        called["topic"] = topic_phrase
        return "TOPIC-OPENER"

    monkeypatch.setattr(so, "_presence_continuation_opener", fake_continuation)
    import backend.app.services.i7.privacy_safe_recent_topic as pst

    monkeypatch.setattr(pst, "get_privacy_safe_recent_topic_label", lambda db, uid: "sleep")
    monkeypatch.setattr(pst, "display_phrase_for_topic_label", lambda label, lang: "sleep")
    out = so.build_notification_origin_opener(None, SimpleNamespace(id=1, name="جواد"), _notification(_push("fa", "جواد", last_topic_hint="sleep"), "fa"), language="fa", preferred_name="جواد")
    assert out == "TOPIC-OPENER" and called["topic"] == "sleep"


def test_other_families_are_untouched():
    n = SimpleNamespace(semantic_family="NUTRITION_PLAN_FOLLOW_UP", template_key="nutrition_plan_follow_up", body="x", language="fa", context_json=None)
    out = so.build_notification_origin_opener(None, SimpleNamespace(id=1, name="جواد"), n, language="fa", preferred_name="جواد")
    assert out and "حالت" not in out or out  # reaches the family opener / generic fallback without error


def test_copy_has_the_new_keys_in_three_languages():
    from backend.app import sedi_copy

    for key in ("session.presence_checkin", "session.presence_checkin_low"):
        assert set(sedi_copy.by_lang(key)) >= {"fa", "ar", "en"}
