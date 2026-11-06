"""R-075 (Javad 2026-11-06): «talk with Sedi» is ALWAYS on a notification. The reminder said «الان وقت … است» with only
«آره انجام شد / نشد / بعداً»; it must also carry «صحبت با صدی» (3 tray buttons max)."""
from __future__ import annotations

import pytest

from backend.app.services.gate4.push_payload import (
    MAX_TRAY_ACTIONS,
    MOBILE_INTERACTION_ACTIONS,
    PLAN_FOLLOWUP_ACTIONS,
    PLAN_FOLLOWUP_TEMPLATE_KEYS,
    ensure_talk_action,
)

CASES = [
    (("done", "plan_not_done", "later"), ["done", "plan_not_done", "open_chat"]),
    (("done", "plan_not_done"), ["done", "plan_not_done", "open_chat"]),
    (("dislike",), ["dislike", "open_chat"]),
    (("like", "dislike"), ["like", "dislike", "open_chat"]),
    (("like", "dislike", "later"), ["like", "dislike", "open_chat"]),
    (("open_chat", "dislike"), ["open_chat", "dislike"]),
    (("done", "plan_not_done", "open_chat"), ["done", "plan_not_done", "open_chat"]),
]


@pytest.mark.parametrize("given,expected", CASES)
def test_talk_is_always_present_within_three_buttons(given, expected):
    out = ensure_talk_action(given)
    assert out == expected
    assert "open_chat" in out and len(out) <= MAX_TRAY_ACTIONS


def test_the_follow_up_family_set_and_every_template_family_carry_talk():
    assert "open_chat" in PLAN_FOLLOWUP_ACTIONS and "open_chat" in MOBILE_INTERACTION_ACTIONS
    assert len(PLAN_FOLLOWUP_ACTIONS) <= MAX_TRAY_ACTIONS
    for key in ("medication_reminder", "generic_event_reminder", "assurance_follow_up", "commitment_follow_up"):
        assert key in PLAN_FOLLOWUP_TEMPLATE_KEYS


def test_legacy_and_empty_action_lists_are_left_alone():
    assert ensure_talk_action(None) is None
    assert ensure_talk_action([]) == []
    legacy = ["OPEN_CHAT", "SOMETHING_ELSE"]
    assert ensure_talk_action(legacy) == legacy


def test_the_generic_reminder_text_reads_naturally_for_a_conversation_topic():
    from backend.app import sedi_copy

    fa = sedi_copy.t("reminder.event.generic", "fa", lead="الان", label="چه خبر جواد")
    assert "وقتِ" not in fa and "«چه خبر جواد»" in fa and fa.startswith("الان")
    ar = sedi_copy.t("reminder.event.generic", "ar", lead="الآن", label="ما الأخبار")
    assert "«ما الأخبار»" in ar


def test_a_default_title_is_not_shown_as_the_users_own_label():
    from types import SimpleNamespace

    from backend.app.services.i10.event_reminder_i10_adapter import _reminder_copy

    for lang, default in (("fa", "یادآوری"), ("en", "Reminder")):
        ev = SimpleNamespace(title=default, event_type="other")
        _t, body, _key = _reminder_copy(ev, medical=False, lang=lang, offset_min=0)
        assert f"«{default}»" not in body and f": {default}" not in body, (lang, body)
    ev = SimpleNamespace(title="چه خبر جواد", event_type="other")
    assert "«چه خبر جواد»" in _reminder_copy(ev, medical=False, lang="fa", offset_min=0)[1]
