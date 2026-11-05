"""R-065 (step 1D): a message that points at an unanswered question must SAY the question - a general rule.

Phone test 2026-11-05: the same-day opener said "one question remained unanswered, write the answer" and the user had to
ask "what was the question?". Matrix: topics x languages x question shapes (ends with the question, question followed by
its reason, Latin / Persian / Arabic question mark) + the DB path + the fallback when no question text is known.
"""
from __future__ import annotations

import pytest

from backend.app.services.i7 import same_day_recap as sdr
from backend.app.services import a3_session_open as so
from backend.tests.test_p9_same_day_recap import _earlier_today, _fa_user

_TOPIC = {"fa": "خوابت", "ar": "نومك", "en": "your sleep"}
_HELLO = {"fa": "سلام جواد.", "ar": "أهلاً جواد.", "en": "Hello, Sara."}
_QUESTIONS = {
    "fa": ["وقتی شب بیدار می‌شوی، معمولاً زود دوباره خوابت می‌برد یا مدت زیادی بیدار می‌مانی؟", "هفته‌ای چند بار ورزش می‌کنی؟", "درد کمرت بیشتر صبح است یا عصر؟"],
    "ar": ["كم ساعة تنام عادة؟", "هل يزداد ألم الظهر صباحاً أم مساءً؟", "كم مرة تمارس الرياضة في الأسبوع؟"],
    "en": ["How long does it take you to fall back asleep?", "How many times a week do you exercise?", "Is your back pain worse in the morning or the evening?"],
}


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
@pytest.mark.parametrize("index", [0, 1, 2])
def test_the_opener_says_the_open_question_in_every_language(lang, index):
    question = _QUESTIONS[lang][index]
    recap = {"topics": [_TOPIC[lang]], "count": 3, "open_question": True, "open_question_text": question}
    text = sdr.same_day_opener(lang, _HELLO[lang], recap)
    assert question in text and text.startswith(_HELLO[lang])
    # the question IS the invitation: no separate «write the answer» line, exactly one question mark
    assert text.count("؟") + text.count("?") == 1
    assert "{" not in text


def test_without_a_known_question_text_the_old_wording_is_the_fallback():
    recap = {"topics": ["خوابت"], "count": 2, "open_question": True}
    text = sdr.same_day_opener("fa", "سلام جواد.", recap)
    assert "یک سؤال بی‌پاسخ مانده بود" in text and "جوابش را بنویس" in text
    closed = {"topics": ["خوابت"], "count": 2, "open_question": False}
    assert "از کجا ادامه بدهیم؟" in sdr.same_day_opener("fa", "سلام جواد.", closed)


@pytest.mark.parametrize("reply,expected", [
    ("گاهی بیدارشدن کوتاه پیش می‌آید. وقتی بیدار می‌شوی، زود دوباره خوابت می‌برد؟", "وقتی بیدار می‌شوی، زود دوباره خوابت می‌برد؟"),
    ("وقتی بیدار می‌شوی، زود دوباره خوابت می‌برد؟ این کمک می‌کند بفهمیم بیدارشدن‌ها چقدر خوابت را مختل می‌کنند.", "وقتی بیدار می‌شوی، زود دوباره خوابت می‌برد؟"),
    ("Does it take long to fall back asleep? This helps me see how much waking hurts your sleep.", "Does it take long to fall back asleep?"),
    ("باشه، امشب زودتر بخواب و ساعت بیدارشدنت را ثابت نگه دار.", ""),
])
def test_the_recap_extracts_the_open_question_even_when_a_reason_follows_it(db, reply, expected):
    u = _fa_user(db, "+17770065001")
    _earlier_today(db, u.id, ["این چند شب خوابم خوب نیست"], reply=reply)
    recap = sdr.build_same_day_recap(db, u.id, "fa")
    assert recap and recap["open_question_text"] == expected and recap["open_question"] is bool(expected)


def test_the_whole_opener_through_the_session_path_names_the_question(db):
    u = _fa_user(db, "+17770065002")
    _earlier_today(db, u.id, ["میخوام برنامه ورزشی داشته باشم"], reply="چند روز در هفته می‌توانی ورزش کنی؟ این برای تنظیم برنامه لازم است.")
    text = so.maybe_proactive_opener(db, u)
    assert "«چند روز در هفته می‌توانی ورزش کنی؟»" in text
    assert "این برای تنظیم برنامه لازم است" not in text  # only the question itself, not the reason
