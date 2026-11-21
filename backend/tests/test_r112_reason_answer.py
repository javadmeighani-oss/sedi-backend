"""R-112 (Javad 2026-11-21): the answer to «what do you take it for?» is answered like a caretaker, not with a canned form.

Pilot #2: «تقویت مو چون ریزش مو دارم» got «ثبت شد… فردا حالت را می‌پرسم»: no reflection, no questions, no steps. Now the deterministic part stays
(registration, tracked companionship) and the REPLY is the chat model's, steered by a REASON ANSWER hint built from memory (pill, times, age).
Real session (in-memory SQLite); the interview, the registry, the commitment loop and the guide are not stubbed.
"""
from types import SimpleNamespace

import pytest

from backend.app import models, sedi_copy
from backend.app.services.interview import guide
from backend.app.services.medication_care import chat_reminder as cr
from backend.tests.test_r103_pill_time_change import (  # noqa: F401  (real-session fixtures and helpers)
    REQUEST, TZ, _draft, _old_reminder, _pinned, _say, db, user,
)

REASON = "تقویت مو چون ریزش مو دارم"


def _ask_same(db, user):
    res = cr.start_interview(db, user_id=user.id, message=REQUEST, draft=_draft(), language="fa", timezone_name=TZ)
    _say(db, user, REQUEST, cr.confirmation(res, "fa", ""))


def _to_the_reason_question(db, user):
    """Pilot turns 1-2: the request, «same pill, change its time» -> Sedi asks WHY (the promotion answer)."""
    _old_reminder(db, user, "14:00")
    _ask_same(db, user)
    reply = cr.continue_interview(db, user_id=user.id, message="همون قرص مکمل است ساعتشو تغییر بده", language="fa", timezone_name=TZ)
    assert reply and cr._stage_of(reply, "fa") == "ask_reason_promoted"
    _say(db, user, "همون قرص مکمل است ساعتشو تغییر بده", reply)
    return reply


def _commitments(db, user):
    return db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == user.id).count()


# --- the reply is the model's, the side effects are deterministic --------------------------------------------------------------------------------------
def test_the_reason_after_a_promotion_is_left_to_the_chat_model_and_the_companionship_is_tracked(db, user):
    _to_the_reason_question(db, user)
    assert _commitments(db, user) == 0
    assert cr.continue_interview(db, user_id=user.id, message=REASON, language="fa", timezone_name=TZ) is None  # no canned reply
    assert _commitments(db, user) == 1  # ONE tracked commitment (the existing I10 loop) - the follow-up is real


def test_the_hint_carries_the_schedule_the_reason_frame_and_the_caretaker_steps(db, user):
    _to_the_reason_question(db, user)
    hint = guide.hint_for_turn(db, user.id, REASON, "fa")
    assert hint.startswith("REASON ANSWER (R-112)")
    assert "«قرص مکمل»" in hint and "09:00، 16:00" in hint                      # the facts from memory: the pill and ITS NEW times
    assert "14:00" not in hint                                                  # the replaced time is gone
    for needle in ("reflecting their reason", "did you see a doctor", "what did they say", "stress", "HOW to do it", "food and exercise",
                   "Never diagnose", "follow-up promise", "THREE short questions"):
        assert needle in hint, needle
    assert "age is unknown" in hint                                             # no age in memory: it becomes one of the questions


def test_a_known_age_and_sex_are_given_to_the_model(db, user, monkeypatch):
    from backend.app.services.user_context import user_state as us

    _to_the_reason_question(db, user)
    monkeypatch.setattr(us, "get_user_state", lambda d, u: us.UserState(user_id=u, age=34, sex="male"))
    hint = guide.hint_for_turn(db, user.id, REASON, "fa")
    assert "34, male" in hint and "normal at that age" in hint and "age is unknown" not in hint


def test_a_new_pill_follows_the_same_path_after_its_reason(db, user):
    res = cr.start_interview(db, user_id=user.id, message=REQUEST, draft=_draft(), language="fa", timezone_name=TZ)
    reply = cr.confirmation(res, "fa", "")
    _say(db, user, REQUEST, reply)
    reply = cr.continue_interview(db, user_id=user.id, message="ویتامین دی", language="fa", timezone_name=TZ)
    assert cr._stage_of(reply, "fa") == "ask_reason"
    _say(db, user, "ویتامین دی", reply)
    assert cr.continue_interview(db, user_id=user.id, message="چون کمبود دارم و خسته‌ام", language="fa", timezone_name=TZ) is None
    assert _commitments(db, user) == 1
    hint = guide.hint_for_turn(db, user.id, "چون کمبود دارم و خسته‌ام", "fa")
    assert "«ویتامین دی»" in hint and "09:00، 16:00" in hint


# --- what stays deterministic ----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["نمی‌دانم", "فقط یادم بنداز", "just remind me"])
def test_a_non_answer_still_closes_the_step_with_the_plain_confirmation(db, user, text):
    _to_the_reason_question(db, user)
    reply = cr.continue_interview(db, user_id=user.id, message=text, language="fa", timezone_name=TZ)
    assert reply and "قرص مکمل" in reply and "09:00" in reply  # honest: the schedule is stated; no model is needed
    assert _commitments(db, user) == 0                          # no reason, no companionship promise


def test_there_is_no_reason_hint_when_the_last_reply_was_something_else(db, user):
    _old_reminder(db, user, "14:00")
    _say(db, user, "سلام", "سلام! چطوری؟")
    hint = guide.hint_for_turn(db, user.id, "سرم درد می‌کند", "fa")
    assert hint is None or "REASON ANSWER" not in hint


def test_without_memory_consent_there_is_no_reason_context(db):
    other = models.User(name="بی‌رضایت", secret_key="x", preferred_language="fa")
    db.add(other)
    db.commit()
    assert cr.reason_context(db, other.id, "fa") is None and guide.reason_hint(db, other.id, "fa") is None


def test_the_reason_hint_never_breaks_the_guide(db, user, monkeypatch):
    monkeypatch.setattr(cr, "reason_context", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert guide.reason_hint(db, user.id, "fa") is None  # fail-open: the chat just answers normally


def test_the_reason_hint_comes_first_and_the_usual_guide_follows(db, user):
    _to_the_reason_question(db, user)
    hint = guide.hint_for_turn(db, user.id, "ریزش مو دارم و سرم هم درد می‌کند", "fa")
    assert hint.startswith("REASON ANSWER (R-112)") and "SYMPTOM INTERVIEW" in hint
    assert hint.index("REASON ANSWER") < hint.index("SYMPTOM INTERVIEW")


def test_an_emergency_in_the_reason_is_left_to_the_safety_path(db, user):
    _to_the_reason_question(db, user)
    assert guide.hint_for_turn(db, user.id, "برای قلبم مصرفش می‌کنم و الان قفسه سینه‌ام درد می‌کند و نفسم بند آمده", "fa") is None


# --- Codex round 1 on PR 207 ------------------------------------------------------------------------------------------------------------------
def test_p2_a_non_answer_or_a_long_message_gets_no_reason_hint(db, user):
    _to_the_reason_question(db, user)
    assert guide.reason_hint(db, user.id, "fa", "نمی‌دانم") is None                     # a non-answer closes the step
    assert guide.reason_hint(db, user.id, "fa", "فقط یادم بنداز") is None
    assert guide.reason_hint(db, user.id, "fa", " ".join(["کلمه"] * 41)) is None        # >40 words: another topic, nothing was registered for it
    assert guide.reason_hint(db, user.id, "fa", REASON).startswith(guide.REASON_HINT_PREFIX)


def test_p2_no_registration_no_confirmation_instruction(db, user):
    """The reason question exists but nothing is registered under that name: the model is never told to confirm a registration."""
    _say(db, user, "ویتامین", sedi_copy.t("medication.chat.q.ask_reason", "fa", name="ویتامین ناموجود"))
    assert cr.reason_context(db, user.id, "fa", message=REASON) is None and guide.reason_hint(db, user.id, "fa", REASON) is None


def test_p2_the_models_own_promise_does_not_create_a_second_follow_up_chain(db, user, monkeypatch):
    """The brain skips capture_from_reply on a turn steered by the reason hint (the medication flow already made the commitment)."""
    import inspect

    from backend.app.core.conversation import brain

    source = inspect.getsource(brain)
    assert "REASON ANSWER (R-112)" in source and "_reason_turn" in source
    index = source.index("_reason_turn = any(")
    assert "capture_from_reply(self.db, user_id, sedi_response, lang, user_message=user_message)" in source[index:index + 700]
    assert source[index:index + 700].index("if not _reason_turn") < source[index:index + 700].index("capture_from_reply(self.db")
