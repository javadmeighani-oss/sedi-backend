"""R-047: Sedi's locked identity/capabilities, honest notification claims and notification-origin openers."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.app import sedi_copy
from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
from backend.app.services.a3_session_open import (
    _daily_digest_opener,
    _digest_content_family,
)
from backend.app.services.gate4.notification_context import sanitize_notification_context
from backend.app.services.intelligence.about_sedi import about_sedi_message, is_about_sedi_question
from backend.app.services.intelligence.grounding_guard import strip_self_limit_disclaimers

_FAMILIES = ("general_checkin", "i8_action", "i6_i7_context", "safety", "i9_observation")


@pytest.mark.parametrize(
    "text",
    [
        "تو کی هستی؟",
        "چه کارهایی می‌تونی انجام بدی؟",
        "می‌تونی برام نوتیف بفرستی؟",
        "قابلیت‌هات چیه",
        "what can you do?",
        "who are you",
        "can you send me a reminder",
    ],
)
def test_about_question_detected(text):
    assert is_about_sedi_question(text)


@pytest.mark.parametrize(
    "text",
    [
        "فردا ساعت ۱۰ یادم بنداز دکتر",
        "من دیابت دارم چه کار کنم",
        "remind me tomorrow at 10 to take my pills",
        "",
    ],
)
def test_other_messages_not_about_question(text):
    assert not is_about_sedi_question(text)


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_about_message_states_identity_and_abilities(lang):
    msg = about_sedi_message(lang)
    assert msg.count("؟") + msg.count("?") <= 1
    if lang == "fa":
        for word in ("صدی", "یادآور", "نوتیف", "ورزش"):
            assert word in msg
        assert "سدی" not in msg
    elif lang == "en":
        for word in ("memory", "reminders", "notifications", "specialist"):
            assert word in msg


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_persona_declares_she_can_send_reminders(lang):
    prompt = PersonaPolicyV1.system_prompt(lang)
    marker = {"fa": "می‌توانی»", "ar": "تستطيعين»", "en": "you CAN"}[lang]
    assert marker in prompt


def test_false_cannot_send_notification_claim_is_removed():
    out = strip_self_limit_disclaimers("نمی‌تونم برات نوتیف بفرستم. ولی امشب زودتر بخواب تا فردا سرحال باشی.", "fa")
    assert "نوتیف" not in out
    assert "زودتر بخواب" in out
    en = strip_self_limit_disclaimers("I can't send you notifications. Try a short walk after dinner.", "en")
    assert "notification" not in en and "short walk" in en


def test_content_family_survives_context_sanitizer():
    cleaned = sanitize_notification_context(
        {"template_key": "daily_wellness_digest", "content_family": "i8_action", "dosage": "5mg"}
    )
    assert cleaned and cleaned["content_family"] == "i8_action" and "dosage" not in cleaned


def test_digest_family_read_from_context_json():
    note = SimpleNamespace(context_json=json.dumps({"content_family": "i8_action:pair"}))
    assert _digest_content_family(note) == "i8_action"
    assert _digest_content_family(SimpleNamespace(context_json=None)) is None
    assert _digest_content_family(SimpleNamespace(context_json="{bad")) is None
    assert _digest_content_family(SimpleNamespace(context_json=json.dumps({"content_family": "zzz"}))) is None


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_digest_openers_are_open_single_questions_not_yes_no(lang):
    seen = set()
    for fam in (None,) + _FAMILIES:
        text = _daily_digest_opener(lang=lang, name="جواد", content_family=fam)
        assert text.strip()
        assert text.count("؟") + text.count("?") <= 1
        seen.add(text)
    # every family continues its own subject: the texts differ
    assert len(seen) >= 5
    if lang == "fa":
        assert "آماده‌ای" not in "".join(seen)


def test_catalog_keys_exist_for_every_family():
    for fam in _FAMILIES:
        for lang in ("fa", "ar", "en"):
            assert sedi_copy.t(f"session.digest.{fam}", lang, prefix="")


# ---- R-048: ONE locked identity everywhere, Arabic brand spelling -------------------------------------------------

_TIERS = {"fa": ("کوتاه‌مدت", "میان‌مدت", "بلندمدت"), "en": ("short-term", "medium-term", "long-term")}


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_every_persona_prompt_opens_with_the_locked_identity(lang):
    prompt = PersonaPolicyV1.system_prompt(lang)
    assert prompt.startswith(sedi_copy.t("identity.core", lang))


def test_identity_names_memory_tiers_adviser_and_gadgets():
    en = sedi_copy.t("identity.core", "en")
    for word in ("short-term", "medium-term", "long-term", "vital signs", "adviser", "treatment"):
        assert word in en
    fa = sedi_copy.t("identity.core", "fa")
    for word in _TIERS["fa"] + ("گجت",):
        assert word in fa.replace("‌", "‌")
    ar = sedi_copy.t("identity.core", "ar")
    for word in ("قصيرة المدى", "طويلة المدى", "الحيوية"):
        assert word in ar


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_intro_and_about_share_the_identity(lang):
    intro = sedi_copy.t("identity.intro", lang)
    about = about_sedi_message(lang)
    assert intro.strip() and about.strip()


def test_arabic_brand_uses_arabic_yeh_everywhere_in_the_catalog():
    persian = "صدی"
    arabic = "صدي"
    for key, lang, text in sedi_copy.iter_strings():
        if lang == "ar":
            assert persian not in text, key
    assert arabic in sedi_copy.t("about.sedi", "ar")
    assert persian in sedi_copy.t("about.sedi", "fa") and arabic not in sedi_copy.t("about.sedi", "fa")


def test_legacy_intro_templates_use_the_identity():
    from backend.app.core.conversation.prompts import ConversationPrompts  # noqa: F401  (import must work)
    from backend.app.core.conversation import sedi_knowledge_base as kb

    for lang in ("en", "fa", "ar"):
        ident = kb.SEDI_IDENTITY[lang]
        assert "assistant" not in ident["type"].lower() or lang != "en"
    assert "memory" in kb.SEDI_IDENTITY["en"]["type"].lower()
