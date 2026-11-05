"""R-064/R-065: ONE typography contract for everything Sedi writes - a matrix over rules x languages."""
from __future__ import annotations

import pytest

from backend.app import sedi_copy
from backend.app.typography import ZWNJ, normalize, normalize_title

# ---- Persian / Arabic punctuation, spacing, quotes ------------------------------------------------------------------
_RTL_CASES = [
    ("fa", "سلام , جواد ; حالت چطور است ?", "سلام، جواد؛ حالت چطور است؟"),
    ("fa", "سلام،جواد.امروز چطوری؟", "سلام، جواد. امروز چطوری؟"),
    ("fa", "بگو \"فردا ساعت ۱۰\" بعد", "بگو «فردا ساعت ۱۰» بعد."),
    ("fa", "قدم بعدی ...", "قدم بعدی…"),
    ("fa", "ساعت 10:30 و 3.5 کیلو و 2 ساعت", "ساعت ۱۰:۳۰ و ۳.۵ کیلو و ۲ ساعت."),
    ("ar", "أرسل لك تذكيرات , وإشعارات ؟", "أرسل لك تذكيرات، وإشعارات؟"),
    ("ar", "قل لي \"ذكّرني غداً\" الساعة 10", "قل لي «ذكّرني غداً» الساعة ١٠."),
]


@pytest.mark.parametrize("lang,raw,expected", _RTL_CASES)
def test_persian_and_arabic_punctuation_spacing_quotes_and_digits(lang, raw, expected):
    assert normalize(raw, lang) == expected


def test_persian_half_space_in_mi_nemi_and_the_plural_ha():
    assert normalize("من می توانم و نمی خواهم این ها را", "fa") == f"من می{ZWNJ}توانم و نمی{ZWNJ}خواهم این{ZWNJ}ها را."
    assert normalize("كتاب ها", "ar") == "كتاب ها"  # the Persian plural rule is Persian-only (and a 2-word line is no sentence)


def test_arabic_yeh_and_kaf_become_persian_in_persian_text_only():
    assert normalize("كتاب كردي", "fa").startswith("کتاب") and "ي" not in normalize("نويسي", "fa")
    assert "ي" in normalize("نويسي", "ar")


# ---- paragraphs, starts and ends -----------------------------------------------------------------------------------
def test_paragraphs_are_separated_by_one_blank_line_and_start_clean():
    raw = "- سلام جواد\n\n\n* این یک جمله‌ی کامل برای آزمایش است\n**خوب** است"
    out = normalize(raw, "fa")
    assert out.split("\n\n") == ["سلام جواد", "این یک جمله‌ی کامل برای آزمایش است.", "خوب است"] or out.count("\n\n") == 2
    assert "*" not in out and not any(p.startswith(("-", "*", "•")) for p in out.split("\n\n"))


def test_a_real_sentence_gets_its_full_stop_but_a_heading_does_not():
    assert normalize("امشب زودتر بخواب و فردا صبح بگو", "fa").endswith("بگو.")
    assert normalize("نکته‌های مهم خواب\nامشب زودتر بخواب و فردا بگو", "fa").split("\n\n")[0] == "نکته‌های مهم خواب"
    assert normalize("Go to bed earlier tonight and tell me tomorrow", "en") == "Go to bed earlier tonight and tell me tomorrow."


def test_english_capital_at_paragraph_start_and_punctuation_spacing():
    assert normalize("hello ,world .this is fine\n\nsecond paragraph here today", "en") == "Hello, world.this is fine.\n\nSecond paragraph here today."
    assert normalize("What is this ?  Fine !", "en") == "What is this? Fine!"


def test_titles_have_no_trailing_full_stop():
    assert normalize_title("سلام روز بخیر.", "fa") == "سلام روز بخیر"
    assert normalize_title("  Daily check-in . ", "en") == "Daily check-in"
    assert normalize_title("پیگیری صدی؟", "fa") == "پیگیری صدی؟"


# ---- safety: never touch placeholders, URLs, e-mail --------------------------------------------------------------
def test_placeholders_urls_and_emails_are_untouched():
    raw = "سلام{name_part} ، به https://sedi.app/a,b?x=1 برو و به me@sedi.app بنویس {topic}"
    out = normalize(raw, "fa", paragraphs=False)
    assert "{name_part}" in out and "https://sedi.app/a,b?x=1" in out and "me@sedi.app" in out and "{topic}" in out


@pytest.mark.parametrize("lang,text", [
    ("fa", "ساعت 10:30 و 3.5 کیلو. بعد ؟ ۲ بار،سلام\nقدم بعدی را بگو"),
    ("fa", "من می توانم  ...  کمک کنم , خوب ?"),
    ("ar", "مرحباً.كيف حالك ? الساعة 10.30"),
    ("en", "hello ,world .This is a test  ...\n\n- second paragraph without end here ok"),
])
def test_normalize_is_idempotent(lang, text):
    once = normalize(text, lang)
    assert normalize(once, lang) == once


def test_paragraphs_false_keeps_the_line_structure_for_notification_bodies():
    assert normalize("سلام ،جواد\nامروز چطوری ?", "fa", paragraphs=False) == "سلام، جواد\nامروز چطوری؟"


# ---- the catalog is already clean (the gate): every eligible text is stable under the normalizer ------------------
def test_the_catalog_is_typographically_clean():
    problems = []
    for key, lang, text in sedi_copy.iter_strings():
        if key.startswith("identity.") or len(text) < 12 or text != text.strip():
            continue
        if normalize(text, lang, paragraphs=key.startswith("about."), digits=False) != text:
            problems.append((key, lang, text[:60]))
    assert not problems, f"typography contract (R-064) violated in the catalog: {problems}"
