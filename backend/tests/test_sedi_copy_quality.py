"""Quality gate for the Sedi copy catalog (R-043).

Every user-facing text lives in ``backend/app/sedi_copy.py``. This test is the single place that checks spelling,
orthography and voice for all of it, in fa / ar / en. A new text that breaks a rule turns CI red.
"""

import re
from collections import defaultdict

import pytest

from backend.app import sedi_copy as copy

ZWNJ = "‌"
FA = r"؀-ۿ"

# Keys that are knowingly incomplete (fa/ar only) - the English text is produced elsewhere. Empty = every key is complete.
_INCOMPLETE_ALLOWED: set = set()

_FA_JOINED_VERB = re.compile(
    r"(?<![" + FA + r"])ن?می(?:شه|شی|شم|شید|شن|خوام|خوای|خواد|خوایم|خوان|تونم|تونی|تونه|تونید|تونیم|کنم|کنی|کنه|کنیم|کنید|دم|دی|ده|دیم|دید|دن|"
    r"گم|گی|گه|گیم|ره|رم|ری|ریم|رن|بینم|بینی|بینه|دونم|دونی|دونه|ذارم|ذاری|ذاره|گیرم|گیری|گیره|خورم|خوری|خوره|رسم|رسی|رسه|فرسته|فرستم)(?![" + FA + r"])"
)
_FA_MI_SPACE = re.compile(r"(?<![" + FA + r"])ن?می (?=[" + FA + r"])")
_FA_HA_SPACE = re.compile(r"[" + FA + r"] ها(?:ی|یی)?(?![" + FA + r"])")
_SPACE_BEFORE_PUNCT = re.compile(r"[" + FA + r"A-Za-z] [،؟!؛:](?!\S)")
_DOUBLE_SPACE = re.compile(r"\S  +\S")
_EN_LOWER_AFTER_STOP = re.compile(r"(?<![A-Za-z]\.[A-Za-z])(?<!e\.g)(?<!i\.e)[.!?] [a-z]")
_ASCII_Q_IN_FA = re.compile(r"[" + FA + r"]\s?\?")

# Phrases that were wrong once and must never come back.
_BANNED = (
    ("قدم قدم‌زدن", "repeated word (use «یه کم قدم‌زدن»)"),
    ("رول‌آپ", "internal jargon («rollup») reached the user"),
    ("rollup", "internal jargon reached the user"),
    ("یادآور رو", "«یادآور» is a person; the word is «یادآوری»"),
    ("میشی", "missing half-space (می‌شی)"),
    ("سدی", "brand is «صدی»"),
    ("سِدی", "brand is «صدی»"),
)


def _entries():
    return list(copy.iter_strings())


def test_catalog_has_unique_hierarchical_keys():
    keys = copy.keys()
    assert len(keys) == len(set(keys))
    for key in keys:
        assert re.fullmatch(r"[a-z0-9_]+(\.[A-Za-z0-9_\-]+)+", key), f"bad key shape: {key}"


def test_every_key_has_fa_ar_en():
    for key in copy.keys():
        have = set(copy.by_lang(key))
        if key in _INCOMPLETE_ALLOWED:
            continue
        assert have == set(copy.LANGS), f"{key}: languages {sorted(have)}"


def test_no_empty_text():
    for key, lang, text in _entries():
        assert text.strip(), f"{key}[{lang}] is empty"


def test_same_placeholders_in_every_language():
    per_key = defaultdict(dict)
    for key, lang, text in _entries():
        per_key[key].setdefault(lang, set()).update(copy.placeholders(text))
    for key, langs in per_key.items():
        sets = {tuple(sorted(v)) for v in langs.values()}
        assert len(sets) <= 1, f"{key}: placeholders differ between languages {langs}"


def test_persian_orthography():
    problems = []
    for key, lang, text in _entries():
        if lang != "fa":
            continue
        if re.search("[يكةى]", text):
            problems.append((key, "Arabic letter in Persian text", text))
        if _FA_JOINED_VERB.search(text):
            problems.append((key, "missing half-space after می/نمی", text))
        if _FA_MI_SPACE.search(text):
            problems.append((key, "می/نمی separated by a space (use half-space)", text))
        if _FA_HA_SPACE.search(text):
            problems.append((key, "plural «ها» separated by a space", text))
        if _SPACE_BEFORE_PUNCT.search(text):
            problems.append((key, "space before punctuation", text))
        if _ASCII_Q_IN_FA.search(text):
            problems.append((key, "Latin question mark in Persian text (use ؟)", text))
    assert not problems, "\n".join(f"{k}: {why}: {t}" for k, why, t in problems)


def test_arabic_uses_arabic_letters():
    problems = []
    for key, lang, text in _entries():
        if lang != "ar":
            continue
        stripped = text.replace("صدی", "")  # the brand keeps its Persian Yeh in every language (R-007)
        if re.search("[یک]", stripped):
            problems.append((key, text))
    assert not problems, f"Persian Yeh/Kaf inside Arabic text: {problems}"


def test_no_double_spaces_or_stray_whitespace():
    for key, lang, text in _entries():
        assert not _DOUBLE_SPACE.search(text), f"{key}[{lang}] double space: {text!r}"


def test_english_sentences_start_with_a_capital():
    for key, lang, text in _entries():
        if lang != "en":
            continue
        assert not _EN_LOWER_AFTER_STOP.search(text), f"{key}: lowercase after a full stop: {text!r}"


def test_no_repeated_adjacent_word():
    allowed = {("had", "had"), ("that", "that"), ("وقت", "وقت")}  # «هر وقت وقت داشتی» is correct Persian
    for key, lang, text in _entries():
        words = [w for w in re.split(r"[\s‌.,;:!?،؛؟«»\"'()—-]+", text) if w]
        for a, b in zip(words, words[1:]):
            if a.lower() == b.lower() and (a.lower(), b.lower()) not in allowed and not a.isdigit():
                pytest.fail(f"{key}[{lang}] repeats «{a}»: {text!r}")


def test_banned_phrases_never_return():
    for key, lang, text in _entries():
        for phrase, why in _BANNED:
            assert phrase not in text, f"{key}[{lang}] contains {phrase!r}: {why}"


def test_t_formats_and_never_breaks_the_caller():
    key = next(k for k in copy.keys() if any(copy.placeholders(x) for x in copy.variants(k, "fa") if isinstance(x, str)))
    names = copy.placeholders(copy.variants(key, "fa")[0])
    assert copy.t(key, "fa", **{n: "X" for n in names}).count("{") == 0
    assert copy.t(key, "fa")  # missing placeholders: unformatted text, no exception
    assert copy.t(key, "xx-YY") == copy.t(key, "en")  # unknown language falls back
    with pytest.raises(KeyError):
        copy.t("no.such.key", "fa")


def test_norm_lang():
    assert copy.norm_lang("fa-IR") == "fa"
    assert copy.norm_lang(" AR ") == "ar"
    assert copy.norm_lang("fr", default="fa") == "fa"
    assert copy.norm_lang(None) == "en"


# Stiff, written-style wording that does not belong in Sedi's friend-like voice (R-008/R-011). Known leftovers are listed
# explicitly so the list can only shrink; new texts must be warm and colloquial.
_FA_FORMAL = re.compile(r"لطفاً|لطفا|کنید|بدهید|بفرمایید|می‌باشد|نمایید|خود را|را باز کن|را بررسی|را در برنامه")
_FORMAL_KNOWN = {
    "digest.i9_sufficient.bodies",  # device-data digests: gadget work is paused (R-032)
    "digest.i9_partial.bodies",
    "digest.i9_stale.bodies",
    "digest.general.bodies",  # legacy general digest variants - rewrite tracked as copy debt
    "notification.health_alert.emergency",  # emergency wording is kept formal on purpose (R-014)
    "reminder.clarify.title",  # opening is matched against chat history; change together with a legacy opening
    "reminder.clarify_opening.title",
}


def test_persian_voice_is_not_formal():
    problems = [
        (k, t) for k, lang, t in _entries() if lang == "fa" and k not in _FORMAL_KNOWN and _FA_FORMAL.search(t)
    ]
    assert not problems, f"formal wording in Sedi's voice: {problems}"
    stale = [k for k in _FORMAL_KNOWN if k not in copy.keys()]
    assert not stale, f"_FORMAL_KNOWN lists keys that no longer exist: {stale}"


def test_clarification_openings_are_the_start_of_the_clarification():
    """reminder_event_readiness recognises Sedi's own question by its opening; the two must never drift apart."""
    for which in ("datetime", "past", "title"):
        for lang in copy.LANGS:
            message = copy.by_lang(f"reminder.clarify.{which}")[lang]
            opening = copy.by_lang(f"reminder.clarify_opening.{which}")[lang]
            assert message.startswith(opening), f"{which}[{lang}]: {opening!r} is not the start of {message!r}"


def test_address_templates_take_the_name():
    for key in copy.keys():
        if key.startswith("address."):
            for lang in copy.LANGS:
                assert "{name}" in copy.by_lang(key)[lang], f"{key}[{lang}] must contain {{name}}"
