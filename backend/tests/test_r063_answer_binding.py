"""R-063/R-065: answer-binding is a GENERAL mechanism - every kind of question Sedi asks, in fa/ar/en.

Matrix: question type x language, plus the short/long reply rules and the wiring contract. The sleep dialogue of the
phone test (2026-11-05) is just one row of the matrix.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.intelligence.answer_binding import binding_hint, expected_answer_type, last_question

_QUESTIONS = [
    # (language, question, expected type)
    ("fa", "این سه شب، تقریباً هر شب چند ساعت خوابیده‌ای؟", "duration"),
    ("fa", "معمولاً چه ساعتی می‌خوابی؟", "time_of_day"),
    ("fa", "ساعت چند بیدار می‌شوی؟", "time_of_day"),
    ("fa", "هفته‌ای چند بار ورزش می‌کنی؟", "frequency"),
    ("fa", "روزی چند لیوان آب می‌خوری؟", "quantity"),
    ("fa", "درد را از ۰ تا ۱۰ چند می‌دهی؟", "scale"),
    ("fa", "چند سال داری؟", "age_body"),
    ("fa", "قدت چقدر است؟", "age_body"),
    ("fa", "چه داروهایی مصرف می‌کنی؟", "medication"),
    ("fa", "اسمت چیه؟", "name"),
    ("fa", "آیا به چیزی آلرژی داری؟", "yes_no"),
    ("fa", "بیشتر صبح ورزش می‌کنی یا عصر؟", "choice"),
    ("ar", "كم ساعة نمت؟", "duration"),
    ("ar", "في أي ساعة تنام عادة؟", "time_of_day"),
    ("ar", "كم مرة تمارس الرياضة؟", "frequency"),
    ("ar", "كم كوباً من الماء تشرب؟", "quantity"),
    ("ar", "كم عمرك؟", "age_body"),
    ("ar", "ما اسمك؟", "name"),
    ("ar", "هل لديك حساسية من شيء؟", "yes_no"),
    ("en", "How many hours did you sleep?", "duration"),
    ("en", "What time do you usually go to bed?", "time_of_day"),
    ("en", "How often do you exercise?", "frequency"),
    ("en", "How many glasses of water do you drink?", "quantity"),
    ("en", "On a scale from 0 to 10, how bad is the pain?", "scale"),
    ("en", "How old are you?", "age_body"),
    ("en", "Which medication do you take?", "medication"),
    ("en", "What should I call you?", "name"),
    ("en", "Do you have any allergies?", "yes_no"),
]


@pytest.mark.parametrize("lang,question,kind", _QUESTIONS)
def test_every_kind_of_question_is_recognised(lang, question, kind):
    assert expected_answer_type(question) == kind


@pytest.mark.parametrize("lang,question,kind", _QUESTIONS)
def test_a_short_reply_after_the_question_gets_the_binding_hint(lang, question, kind):
    previous = f"یک جمله‌ی کوتاه. {question}" if lang == "fa" else f"A short sentence. {question}"
    hint = binding_hint(previous, "۱۱ یا ۱۲ شب" if lang == "fa" else "11 or 12", lang)
    assert hint and question[:30] in hint
    assert hint.startswith({"fa": "[پاسخ_به_سؤال_تو]", "ar": "[جواب_سؤالك]", "en": "[ANSWER_TO_YOUR_QUESTION]"}[lang])


def test_the_phone_test_dialogue_reads_the_reply_as_a_clock_time_not_a_duration_of_eleven_hours():
    sedi = "سه شب بی‌خوابی واقعاً فرساینده است. این سه شب، تقریباً هر شب چند ساعت خوابیده‌ای؟"
    hint = binding_hint(sedi, "۱۱ یا ۱۲ شب", "fa")
    assert "مدت زمان" in hint  # what she asked for
    assert "اگر پاسخ از نوعی غیر از آنچه پرسیدی است" in hint and "ساعت به‌جای مدت" in hint  # a clock time is accepted as such
    assert "دوباره توضیح بدهد" in hint


def test_time_of_day_questions_say_the_reply_is_a_clock_time():
    hint = binding_hint("معمولاً چه ساعتی می‌خوابی؟", "۱۱ شب", "fa")
    assert "یک ساعت از شبانه‌روز" in hint


@pytest.mark.parametrize("message", [
    "من چند شب است که خوابم نمی‌برد و سر کار هم خیلی خسته‌ام و نمی‌دانم چه کنم",  # long message: a new statement
    "چرا این‌طور است؟",  # the user asks back
    "",
])
def test_the_hint_does_not_apply_to_long_messages_or_counter_questions(message):
    assert binding_hint("چند ساعت خوابیده‌ای؟", message, "fa") == ""


def test_no_question_asked_means_no_hint():
    assert binding_hint("امشب زودتر بخواب.", "باشه", "fa") == ""
    assert binding_hint(None, "باشه", "fa") == ""
    assert last_question("یک. دو؟ سه.") == "دو؟"


def test_a_question_of_an_unknown_kind_still_binds_the_reply_without_a_type():
    hint = binding_hint("حالت امروز چطور است؟", "بد نیستم", "fa")
    assert hint and "او احتمالاً گفته" not in hint


def test_the_chat_brain_wires_answer_binding_and_the_typography_contract():
    source = (Path(__file__).resolve().parents[1] / "app" / "core" / "conversation" / "brain.py").read_text(encoding="utf-8")
    assert "from backend.app.services.intelligence.answer_binding import binding_hint" in source
    assert "from backend.app.typography import normalize as _normalize_typography" in source
    assert source.index("binding_hint(_last_assistant") < source.index('messages.append({"role": "user", "content": user_message})')
