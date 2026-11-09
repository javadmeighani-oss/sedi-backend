"""BE-A (Javad 2026-11-09, screenshots 1-3): colloquial pain talk gets the complete-answer guide, a follow-up stays on its topic, and
Sedi is told what she already said so she does not repeat it (fa / ar / en)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.core.conversation import brain
from backend.app.core.conversation.domain_guides import answer_guide_block, matched_guides

POSITIVE = [
    # the real chat (screenshots) and the same concept in other words / other body parts / other languages
    "کمرم کمی درد میکنه",
    "کمرم درد می‌کنه",
    "کمرم درد می کنه",
    "کمر درد دارم",
    "درد کمر دارم",
    "گردنم خیلی درد میکنه",
    "زانوم درد می‌کنه",
    "شونه‌ام گرفته",
    "شانه‌م درد می‌کنه",
    "پام درد می‌کنه بعد از دویدن",
    "مچ دستم ورم کرده و درد داره",
    "مهره‌های پایین کمرم تیر می‌کشه",
    "پاشنه‌ی پام خیلی درد داره",
    "my lower back hurts a little",
    "my knee aches when I climb stairs",
    "I have neck pain",
    "pain in my shoulder",
    "my back is stiff and sore",
    "ظهري يؤلمني",
    "عندي ألم في الركبة",
    "رقبتي تؤلمني كثيرا",
]


@pytest.mark.parametrize("message", POSITIVE)
def test_colloquial_pain_talk_matches_the_musculoskeletal_guide(message):
    assert matched_guides(message) == ["msk_pain"], message
    block = answer_guide_block(message)
    assert block and "MUSCLE AND JOINT PAIN" in block


NEGATIVE = [
    "امروز هوا خوبه",
    "پایین رفتم و نون خریدم",  # «پا» inside «پایین» must not count as a body part
    "دستم رو شستم",
    "برام یه چایی بریز",
    "my back garden is nice",
    "I will back up the files",
    "what time is it",
    "ما هو الطقس اليوم",
    "",
]


@pytest.mark.parametrize("message", NEGATIVE)
def test_unrelated_sentences_do_not_attach_a_guide(message):
    assert matched_guides(message) == [], message


def test_a_follow_up_without_a_topic_word_keeps_the_topic_of_the_last_turns():
    follow_up = "نه روی مهره های پایین کمرم است بیشتر شاید بخاطر رانندگی طولانی باشد"
    assert matched_guides("نه فکر نمی‌کنم") == []
    assert matched_guides(follow_up) == []  # a body part but no pain word: alone it is not a guide topic
    assert matched_guides(follow_up, previous=["کمرم کمی درد میکنه"]) == ["msk_pain"]  # the real two-turn chat
    assert matched_guides("نه فکر نمی‌کنم", previous=["کمرم کمی درد میکنه"]) == ["msk_pain"]
    assert matched_guides("it started yesterday", previous=["my lower back hurts"]) == ["msk_pain"]
    assert matched_guides("it started yesterday", previous=["hello", "how are you"]) == []


def test_only_the_last_two_turns_are_consulted():
    assert matched_guides("ok", previous=["x", "y", "کمرم درد می‌کنه"]) == []


def test_the_guide_counts_an_answer_to_sedis_question_as_a_fact():
    assert "answering a question you asked earlier" in answer_guide_block("کمرم درد می‌کنه")


# ---- continuity block ------------------------------------------------------------------------------------------------------------------
def _turn(reply):
    return SimpleNamespace(user_message="x", sedi_response=reply)


def test_the_continuity_block_quotes_the_last_reply_and_forbids_repeating_it():
    reply = "متأسفم جواد؛ درد خفیف کمر اغلب با حرکت ملایم بهتر از درازکشیدن طولانی می‌شود. " * 10
    block = brain._continuity_block([_turn(reply)])
    assert block and "Do NOT repeat" in block and "ONE new question" in block
    assert "متأسفم جواد" in block
    assert len(block) < 900  # bounded: a short reminder, not the whole reply


@pytest.mark.parametrize("turns", [[], [_turn("")], [_turn("مشکل فنی از سمت خودم")], [_turn("technical problem on my side")]])
def test_no_continuity_block_without_a_usable_last_reply(turns):
    assert brain._continuity_block(turns) is None


def test_recent_turns_is_fail_open():
    class _Boom:
        def get_recent_messages(self, *a, **k):
            raise RuntimeError("db down")

    assert brain._recent_turns(_Boom(), 1) == []
    assert brain._recent_turns(None, 1) == []


def test_recent_turns_goes_only_through_the_consent_gated_memory_reader():
    """Codex P1 (PR 181): no memory.read consent -> the reader returns [] -> nothing reaches the prompt; the code never queries the table itself."""
    import inspect
    from datetime import datetime

    class _NoConsent:
        calls = 0

        def get_recent_messages(self, user_id, limit=10):
            _NoConsent.calls += 1
            return []

    assert brain._recent_turns(_NoConsent(), 1) == [] and _NoConsent.calls == 1
    src = inspect.getsource(brain._recent_turns)
    assert "models.Memory" not in src and ".query(" not in src

    class _Consent:
        def get_recent_messages(self, user_id, limit=10):
            return [SimpleNamespace(user_message="x", sedi_response="y", created_at=datetime.utcnow())]

    assert len(brain._recent_turns(_Consent(), 1)) == 1


def test_the_brain_wires_previous_turns_and_continuity_into_the_knowledge_step():
    import inspect

    src = inspect.getsource(brain._maybe_append_structured_governed_knowledge)
    assert "_recent_turns(memory, user_id)" in src and "answer_guide_block(user_message, _previous_users)" in src
    assert src.index("answer_guide_block") < src.index("_continuity_block")
    assert "memory=self.memory" in inspect.getsource(brain)
