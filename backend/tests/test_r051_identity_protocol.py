"""R-051/R-057/R-059/R-060/R-061 (step 1A): identity, professional protocol, voice and output guards.

Offline checks only: they prove the prompt text, the catalog and the deterministic guards. How the live model behaves is
proven later by the golden scenarios (step 3) and a phone test.
"""

from __future__ import annotations

import re

import pytest

from backend.app import sedi_copy
from backend.app.core.conversation import persona_policy_v1 as pp
from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
from backend.app.services.intelligence.about_sedi import about_sedi_message, is_about_sedi_question
from backend.app.services.intelligence.grounding_guard import (
    collapse_repetitions,
    strip_hedging_offers,
    strip_self_limit_disclaimers,
)

_PHONE_TEST_MESSAGE = (
    "صدی میخواهم در مورد توانایی های تو صحبت کنیم و اینکه بدانم تو دقیقا قرارهدچه کمکی به من بکنی"
)

# The «second self / twin» idea is Sedi's INTERNAL design (R-059): it is never said to the user.
_INNER_DESIGN = {
    "fa": ("نسخه‌ی دوم", "نسخه ی دوم", "همزاد", "دوقلو"),
    "ar": ("نسخة ثانية", "نسخته الثانية", "توأم"),
    "en": ("second self", "twin", "your double"),
}


def test_the_long_capability_question_from_the_phone_test_gets_the_locked_answer():
    assert is_about_sedi_question(_PHONE_TEST_MESSAGE)
    assert not is_about_sedi_question("فردا ساعت ۱۰ صبح بهم نوتیف بده برای صحبت در مورد توانایی‌های تو")


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_user_facing_identity_texts_never_say_second_self(lang):
    for key, language, text in sedi_copy.iter_strings():
        if language != lang or key in ("identity.core", "identity.voice"):
            continue  # those two are prompt-only and carry the PROHIBITION itself
        for banned in _INNER_DESIGN[lang]:
            assert banned not in text.lower(), (key, banned)


def test_the_approved_reference_introduction_is_the_core_of_every_greeting():
    fa_intro = sedi_copy.t("identity.intro", "fa")
    assert fa_intro.startswith("من صدی هستم، همراه و مشاور سلامت تو.")
    for key in ("about.sedi", "session.intro"):
        text = sedi_copy.t(key, "fa", name_part="") if key == "session.intro" else sedi_copy.t(key, "fa")
        assert "همراه و مشاور سلامت تو" in text, key
        assert "تا اجرای آن کنارت می‌مانم" in text, key
        assert "دقیقاً چه چیزی را می‌خواهی در سلامتت یا زندگی‌ات تغییر بدهی" in text, key
    assert "صدي" in sedi_copy.t("identity.intro", "ar") and "صدی" not in sedi_copy.t("identity.intro", "ar")
    assert "health companion and adviser" in sedi_copy.t("identity.intro", "en")


def test_a_new_user_is_asked_for_the_goal_first():
    # first contact: the goal question closes the greeting, one question only.
    for lang in ("fa", "ar", "en"):
        text = sedi_copy.t("session.intro", lang, name_part="")
        assert text.count("؟") + text.count("?") <= 1, lang


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_prompt_carries_mission_and_the_professional_protocol(lang):
    prompt = PersonaPolicyV1.system_prompt(lang)
    needles = {
        "en": ("Mission", "motivational interviewing", "stage of change", "at most three priority areas", "Record:"),
        "fa": ("مأموریت", "مصاحبه‌ی انگیزشی", "مرحله‌ی تغییر", "حداکثر سه اولویت", "ثبت:"),
        "ar": ("المهمة", "المقابلة التحفيزية", "مرحلة التغيير", "ثلاث أولويات", "التسجيل:"),
    }[lang]
    for needle in needles:
        assert needle in prompt, (lang, needle)


def test_prompt_forbids_telling_the_user_about_the_inner_design():
    assert "NEVER describe yourself to the user as their" in pp._SYSTEM_PROMPT_EN
    assert "هرگز خودت را برای کاربر «نسخه‌ی دوم»" in pp._SYSTEM_PROMPT_FA
    assert "لا تصفي نفسك أبداً أمام المستخدم" in pp._SYSTEM_PROMPT_AR


def test_persian_prompt_is_educated_standard_persian_not_street_slang():
    fa = pp._SYSTEM_PROMPT_FA
    for slang in ("می‌تونی", "می‌خوای", "نمی‌شه", "بهتره", "چطوره", "برات", "بهت "):
        assert slang not in fa, slang
    for formal in ("می‌توانی", "می‌خواهی", "تو «می‌توانی»"):
        assert formal in fa, formal
    assert "«تو» خطاب" in fa


def test_prompt_keeps_the_hard_limits_silent_and_the_direct_specialist_question():
    assert "Shall I find a suitable specialist for you?" in pp._SYSTEM_PROMPT_EN
    assert "یک متخصص مناسب برایت پیدا کنم؟" in pp._SYSTEM_PROMPT_FA
    assert "هل أجد لك مختصاً مناسباً؟" in pp._SYSTEM_PROMPT_AR
    assert "Never talk about your own limits" in pp._SYSTEM_PROMPT_EN


def test_collapse_repetitions_writes_a_repeated_phrase_and_sentence_once():
    stutter = "قرار است همراهی‌ات کنم تا موضوع‌ها روشن‌تر بشن و قدم بعدی موضوع‌ها روشن‌تر بشن و قدم بعدی مشخص بشه."
    assert collapse_repetitions(stutter) == "قرار است همراهی‌ات کنم تا موضوع‌ها روشن‌تر بشن و قدم بعدی مشخص بشه."
    doubled = "این کار مهم است. این کار مهم است. بعدش گام بعدی را بردار."
    assert collapse_repetitions(doubled) == "این کار مهم است. بعدش گام بعدی را بردار."
    fine = "امشب زودتر بخواب؛ فردا صبح احوالت را می‌پرسم."
    assert collapse_repetitions(fine) == fine
    assert collapse_repetitions("") == ""
    short_repeat = "نه نه نه"  # fewer than three distinct words repeated: kept
    assert collapse_repetitions(short_repeat) == short_repeat


def test_self_doubt_about_memory_or_diagnosis_is_removed_but_help_stays():
    reply = "نکته‌ها را نگه می‌دارم؛ اما حافظه‌ام کامل و تضمینی نیست. تشخیص پزشکی یا تغییر داروی تجویزشده انجام نمی‌دم."
    out = strip_self_limit_disclaimers(reply, "fa")
    assert "تضمینی" not in out and "انجام نمی" not in out
    assert out.startswith("نکته‌ها را نگه می‌دارم")
    en = "I can note it. My memory is not complete, though."
    assert "memory is not complete" not in strip_self_limit_disclaimers(en, "en")


def test_closing_menu_question_is_removed_in_both_registers_and_the_specialist_offer_stays():
    colloquial = "برنامه‌ات را امشب شروع کن. می‌خوای بدونی چطور حافظه را مدیریت کنم، یا چه نوع کمکی می‌تونی ازم بگیری؟"
    formal = "برنامه‌ات را امشب شروع کن. می‌خواهی بدانی چگونه حافظه را مدیریت کنم، یا چه نوع کمکی می‌توانی از من بگیری؟"
    for reply in (colloquial, formal):
        assert strip_hedging_offers(reply, "fa") == "برنامه‌ات را امشب شروع کن."
    offer = "این موضوع طولانی شده است. یک متخصص مناسب برایت پیدا کنم؟"
    assert strip_hedging_offers(offer, "fa") == offer


def test_whole_phone_test_reply_is_cleaned_end_to_end():
    reply = (
        "من می‌توانم نکته‌ها را بسپارم؛ اما حافظه‌ام کامل و تضمینی نیست. "
        "درباره‌ی قیمت واکسن هم باید از منبع به‌روز بررسی واکسن هم باید از منبع به‌روز بررسی کرد. "
        "الان بیشتر می‌خوای بدونی چطور حافظه را مدیریت کنم، یا چه نوع کمک روزمره‌ای می‌تونی ازم بگیری؟"
    )
    out = strip_hedging_offers(strip_self_limit_disclaimers(collapse_repetitions(reply), "fa"), "fa")
    assert out == "من می‌توانم نکته‌ها را بسپارم. درباره‌ی قیمت واکسن هم باید از منبع به‌روز بررسی کرد."


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_about_answer_has_no_stock_hedge_and_one_question(lang):
    msg = about_sedi_message(lang)
    assert msg.count("؟") + msg.count("?") == 1
    assert not re.search(r"اگه دوست داری|if you like|إن أحببت", msg, re.I)
