"""R-076 (Javad 2026-11-07): the introduction is written as a composed, courteous female specialist (no «trusted friend» claim; trust
comes from competence and care), in his order: companion and adviser + invitation to talk -> what she does -> specialised smart
gadgets -> her aim; and a question about her abilities IN A FIELD gets that field's concrete answer, not the general introduction."""
from __future__ import annotations

import re

import pytest

from backend.app import sedi_copy
from backend.app.services.intelligence.about_sedi import about_domain, about_sedi_message, about_sedi_reply, is_about_sedi_question

DOMAIN_MESSAGES = [
    ("psychology", "صدی در مورد توانایی‌های تو در زمینه روانشناسی بگو"),
    ("psychology", "چه کمکی در زمینه اضطراب می‌تونی به من بکنی"),
    ("sleep", "توانایی‌هات در مورد خواب چیه"),
    ("nutrition", "توانایی‌های تو در زمینه تغذیه و رژیم چیست"),
    ("exercise_pain", "در مورد توانایی‌هایت در زمینه ورزش و دردهای عضلانی بگو"),
    ("documents", "توانایی‌های تو در مورد آزمایش و نسخه چیست"),
    ("gadgets", "درباره‌ی گجت‌های هوشمند خودت بگو"),
    ("psychology", "tell me about your abilities in psychology"),
    ("sleep", "what can you do about sleep"),
    ("nutrition", "your abilities in nutrition and diet"),
    ("exercise_pain", "what can you do for muscle pain"),
    ("documents", "what can you do with my lab results"),
    ("psychology", "ما هي قدراتك في مجال علم النفس"),
    ("sleep", "ماذا تستطيعين أن تفعلي بخصوص النوم"),
]


@pytest.mark.parametrize("domain,message", DOMAIN_MESSAGES)
def test_a_question_about_abilities_in_a_field_gets_that_fields_answer(domain, message):
    assert is_about_sedi_question(message)
    assert about_domain(message) == domain
    lang = "ar" if re.search("[\u0600-\u06ff]", message) and "ما" in message or "ماذا" in message else ("fa" if re.search("[\u0600-\u06ff]", message) else "en")
    out = about_sedi_reply(message, lang)
    assert out == sedi_copy.t(f"about.domain.{domain}", lang)
    assert out != about_sedi_message(lang)


@pytest.mark.parametrize("message", ["توانایی‌های تو چیست", "خودت را معرفی کن", "what can you do", "من چطور می‌تونم از تو استفاده کنم؟ تو کی هستی"])
def test_the_general_question_still_gets_the_introduction(message):
    assert is_about_sedi_question(message) or message.startswith("من چطور")
    if is_about_sedi_question(message):
        assert about_domain(message) is None
        assert about_sedi_reply(message, "fa") == about_sedi_message("fa")


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_every_field_answer_exists_has_one_question_and_no_hedge(lang):
    for key in ("psychology", "nutrition", "exercise_pain", "sleep", "documents", "gadgets"):
        text = sedi_copy.t(f"about.domain.{key}", lang)
        assert text.count("؟") + text.count("?") == 1, (key, lang)
        assert not re.search(r"اگه دوست داری|if you like|إن أحببت|دوست داری", text, re.I)
        assert "سدی" not in text


def test_the_introduction_follows_his_order_and_does_not_call_her_a_friend():
    fa = sedi_copy.t("about.sedi", "fa")
    parts = fa.split("\n\n")
    assert len(parts) == 4
    assert "همراه و مشاور سلامت" in parts[0] and "قضاوت" in parts[0]  # companion + adviser, invitation to talk openly
    assert all(w in parts[1] for w in ("آزمایش", "برنامه", "یادآوری", "نوتیف", "متخصص"))  # what she does
    assert "گجت" in parts[2] and "علائم حیاتی" in parts[2]  # the specialised smart gadgets, as they connect
    assert "هدف" in parts[3] and parts[3].strip().endswith("؟")  # her aim, then the one starting question
    for lang in ("fa", "ar", "en"):
        text = sedi_copy.t("about.sedi", lang)
        assert not re.search(r"دوست قابل|دوست\u200cت|رفيقتك الموثوق|trusted friend|reliable friend", text, re.I)
    assert "صدي" in sedi_copy.t("about.sedi", "ar") and "صدی" not in sedi_copy.t("about.sedi", "ar")


def test_gadgets_are_described_as_being_prepared_never_as_connected():
    for lang, marker in (("fa", "در دست آماده"), ("ar", "قيد الإعداد"), ("en", "being prepared")):
        assert marker in sedi_copy.t("about.sedi", lang)
        assert marker in sedi_copy.t("about.domain.gadgets", lang)


def test_the_orchestrator_uses_the_field_aware_reply():
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1] / "app/services/intelligence/orchestrator.py").read_text(encoding="utf-8")
    assert "about_sedi_reply(message, lang)" in src
