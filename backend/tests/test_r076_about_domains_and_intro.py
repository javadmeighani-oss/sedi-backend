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
    ("gadgets", "tell me about your gadgets"),
    ("gadgets", "what are your smart devices"),
    ("gadgets", "ما هي أجهزتك الذكية"),
    ("gadgets", "گجت‌هات چیه"),
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
    assert "گجت" in parts[2] and "علائم حیاتی" in parts[2]  # the specialised smart gadgets and the continuous watch of vital signs
    assert "هدف" in parts[3] and parts[3].strip().endswith("؟")  # her aim, then the one starting question
    for lang in ("fa", "ar", "en"):
        text = sedi_copy.t("about.sedi", lang)
        assert not re.search(r"دوست قابل|دوست\u200cت|رفيقتك الموثوق|trusted friend|reliable friend", text, re.I)
    assert "صدي" in sedi_copy.t("about.sedi", "ar") and "صدی" not in sedi_copy.t("about.sedi", "ar")


def test_gadgets_are_described_as_part_of_her_continuous_care_without_inventing_readings():
    """Javad 2026-11-07: no «being prepared» wording - the gadgets are part of her care. The honesty line stays: the texts state
    what she does (a continuous watch over vital signs for a healthy, long life) and never quote a reading or a device status."""
    for lang, marker in (("fa", "گجت"), ("ar", "أجهزة صدي"), ("en", "smart gadgets")):
        for key in ("about.sedi", "about.domain.gadgets"):
            text = sedi_copy.t(key, lang)
            assert marker in text, (key, lang)
            assert not re.search(r"در دست آماده|قيد الإعداد|being prepared|coming soon|به‌زودی", text, re.I), (key, lang)
            assert not re.search(r"\d+\s*(?:bpm|ضربان|mmHg|%|°)", text, re.I), (key, lang)
    assert "علائم حیاتی" in sedi_copy.t("about.domain.gadgets", "fa") and "زندگی سالم و طولانی" in sedi_copy.t("about.domain.gadgets", "fa")


def test_the_orchestrator_uses_the_field_aware_reply():
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1] / "app/services/intelligence/orchestrator.py").read_text(encoding="utf-8")
    assert "about_sedi_reply(message, lang)" in src


JAVAD_APPROVED_FA = (
    "سلام، من صدی هستم، همراه و مشاور سلامت تو. وضعیت جسم و روانت را همراه با گفت\u200cوگوهایمان با دقت به خاطر می\u200cسپارم و هر چه این تصویر کامل\u200cتر شود، توصیه\u200cهای من به شرایط تو نزدیک\u200cتر و دقیق\u200cتر خواهد بود. هر موضوعی که برایت مهم است، از خواب و تغذیه تا درد و حال\u200cو\u200cروزت، با خیال آسوده و بی\u200cهیچ قضاوتی با من در میان بگذار.\n\n"
    "آنچه برایت انجام می\u200cدهم: آزمایش\u200cها، نسخه\u200cها و ویزیت\u200cهایت را می\u200cخوانم و در تصویر کلی سلامتت ثبت می\u200cکنم؛ برنامه\u200cی غذایی و ورزشی متناسب با شرایطت می\u200cنویسم و تا اجرای آن کنارت می\u200cمانم؛ دارو و کارهای مهمت را یادآوری می\u200cکنم و نوتیف می\u200cفرستم (کافی است بگویی «فردا ساعت ۱۰ یادم بینداز»)؛ و برای نگرانی\u200cها و فشارهای روانی، با روش\u200cهای علمی و تمرین\u200cهای عملی کنارت هستم. هر زمان لازم باشد، متخصص مناسب را هم برایت پیدا می\u200cکنم.\n\n"
    "با گجت\u200cهای هوشمند تخصصی صدی، علائم حیاتی تو را به\u200cطور پیوسته زیر نظر دارم، آن\u200cها را با تصویر کلی سلامتت می\u200cسنجم و تغییرهای مهم را زودتر درمی\u200cیابم؛ همه\u200cی این\u200cها برای رسیدن تو به یک زندگی سالم و طولانی است.\n\n"
    "هدف من برای تو، یک زندگی سالم، آرام و طولانی است. برای شروع بگو دقیقاً چه چیزی را می\u200cخواهی در سلامتت یا زندگی\u200cات تغییر بدهی؟"
)


def test_the_general_introduction_is_exactly_the_text_javad_approved():
    """Javad 2026-11-07 pasted this text: «دقیقا این جمله را در معرفی کلی صدی بکار ببریم»."""
    assert sedi_copy.t("about.sedi", "fa") == JAVAD_APPROVED_FA
