"""R-074 step 2: knowledge turns carry more governed evidence and a topic ANSWER GUIDE (shape only).

Measured on production (step 1): 5 units / 4400 chars gave ~0.58 concept coverage and the block always hit its cap.
Matrix: topics x languages for the guide detection; wiring (limit, caps) pinned; guides never carry numbers/doses."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.app.core.conversation import domain_guides as dg
from backend.app.services.i5 import reference_renderer as rr
from backend.app.services.i5.runtime_knowledge_retrieval import MAX_LIMIT

ROOT = Path(__file__).resolve().parents[2]

MATRIX = [
    ("sleep", "fa", "دیشب خوابم نمی‌برد و چند بار بیدار شدم"),
    ("sleep", "en", "how can I treat my insomnia"),
    ("sleep", "ar", "أعاني من أرق شديد"),
    ("meal_plan", "fa", "یه برنامه غذایی برای کاهش وزن می‌خواهم"),
    ("meal_plan", "en", "give me a meal plan for weight loss"),
    ("meal_plan", "ar", "أريد نظام غذائي للتخسيس"),
    ("exercise_plan", "fa", "یک برنامه ورزشی مبتدی می‌خواهم"),
    ("exercise_plan", "en", "what exercise plan should I start with"),
    ("exercise_plan", "ar", "أريد برنامج تمارين للمبتدئين"),
    ("msk_pain", "fa", "کمردرد دارم چه کنم"),
    ("msk_pain", "fa", "درد زانو دارم"),
    ("msk_pain", "en", "my neck pain gets worse at the desk"),
    ("msk_pain", "en", "I have sciatica"),
    ("msk_pain", "ar", "عندي ألم الظهر"),
    ("labs", "fa", "نتیجه آزمایش خونم رو برات بفرستم"),
    ("labs", "en", "can you explain my blood test results"),
    ("labs", "ar", "اشرح لي نتيجة التحليل"),
    ("elder_care", "fa", "از مادر سالمندم چطور مراقبت کنم"),
    ("elder_care", "en", "how do I care for a parent with dementia"),
    ("elder_care", "ar", "كيف أعتني بأحد كبار السن"),
    ("chronic", "fa", "دیابت دارم و می‌خواهم مراقبت کنم"),
    ("chronic", "en", "tips for managing high blood pressure"),
    ("chronic", "ar", "عندي السكري"),
]


@pytest.mark.parametrize("gid,lang,message", MATRIX)
def test_topic_message_selects_its_guide(gid, lang, message):
    assert gid in dg.matched_guides(message)
    block = dg.answer_guide_block(message)
    assert block and block.startswith("[ANSWER GUIDE - shape only]")


@pytest.mark.parametrize("message", ["سلام", "hello there", "مرسی از کمکت", "امروز هوا خوبه", ""])
def test_small_talk_gets_no_guide_and_costs_no_tokens(message):
    assert dg.answer_guide_block(message) is None


def test_at_most_two_guides_and_personal_problem_shape_is_kept():
    ids = dg.matched_guides("کمردرد و بی‌خوابی و رژیم و ورزش و دیابت دارم")
    assert len(ids) == 2
    block = dg.answer_guide_block("خوابم نمی‌برد")
    assert "at most two actions" in block and "one question" in block  # R-063 shape while facts are missing


def test_guides_carry_shape_only_never_numbers_or_doses():
    for _gid, _rx, text in dg._GUIDES:
        assert not re.search(r"\d", text), text
        assert not re.search(r"\b(mg|ml|mmol|kcal)\b", text, re.IGNORECASE)
    assert "ONLY from the knowledge block" in dg._HEADER


def test_the_chat_asks_for_up_to_ten_units_and_a_wider_block():
    brain = (ROOT / "backend/app/core/conversation/brain.py").read_text(encoding="utf-8")
    assert "_KNOWLEDGE_LIMIT = 10" in brain and "_KNOWLEDGE_BLOCK_CHARS = 8200" in brain
    assert "limit=_KNOWLEDGE_LIMIT" in brain and "max_chars=_KNOWLEDGE_BLOCK_CHARS" in brain
    assert "answer_guide_block(user_message)" in brain
    assert MAX_LIMIT == 10
    retrieval = (ROOT / "backend/app/services/i5/runtime_knowledge_retrieval.py").read_text(encoding="utf-8")
    assert "serving_lim = min(lim, MAX_LIMIT)" in retrieval


def test_default_block_budget_is_unchanged_and_a_wider_budget_carries_more_text():
    long_text = "x" * 7000
    small = _answer(long_text)
    assert len(rr.format_care_context_block(small)) <= 4400 + 700
    big = rr.format_care_context_block(small, max_chars=8200)
    assert len(big) > len(rr.format_care_context_block(small))


def _answer(text: str):
    base = rr.render_grounded_answer({"status": "NO_ELIGIBLE", "items": []}, language="en")
    return base.model_copy(update={"synthesized_text": text, "status": "OK"})
