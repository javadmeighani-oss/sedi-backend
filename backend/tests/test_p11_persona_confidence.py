"""R-033 (Javad 2026-10-28): Sedi never puts herself on trial in front of the user ("I am not a human psychologist and I do
not diagnose"). She helps first; alongside her guidance she may OFFER to find a suitable specialist, and an «آره» to that
offer is the find-a-specialist request."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.app import models
from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
from backend.app.services.i5.care_navigation_directory import is_care_navigation_query
from backend.app.services.intelligence.grounding_guard import limit_questions, strip_self_limit_disclaimers
from backend.app.services.intelligence.specialist_offer import (
    is_affirmative,
    is_specialist_offer,
    specialist_request_for_reply,
)
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

# the real reply from the phone test
SCREENSHOT_REPLY = (
    "جواد، می‌تونم در موضوعاتی مثل مدیریت استرس، تنظیم احساسات، عادت‌ها و بهتر حرف‌زدن با دیگران راهنمایی عملی بدم و کمک کنم "
    "موقعیت رو از چند زاویه ببینی. اما روان‌شناس انسانی نیستم و تشخیص نمی‌دم؛ اگر مسئله‌ای سنگین یا ماندگار باشه، می‌تونم "
    "کنارت باشم تا قدم بعدی رو روشن‌تر کنی. چه موضوعی توی ذهنت هست که دوست داری با هم بررسی کنیم؟"
)


def test_the_phone_test_reply_loses_only_the_self_limit_clause():
    out = strip_self_limit_disclaimers(SCREENSHOT_REPLY, "fa")
    assert "نیستم" not in out and "تشخیص نمی" not in out
    assert "اگر مسئله‌ای سنگین یا ماندگار باشه، می‌تونم کنارت باشم" in out  # the useful half stays
    assert out.startswith("جواد، می‌تونم در موضوعاتی مثل مدیریت استرس")
    assert out.endswith("با هم بررسی کنیم؟")
    assert limit_questions(out, 1) == out  # still one question


@pytest.mark.parametrize(
    "reply,gone",
    [
        ("I am not a psychologist, but I can walk you through a breathing exercise. Want to try it?", "not a psychologist"),
        ("I can't diagnose anything. Here is one thing that helps with sleep: a fixed bedtime.", "diagnose"),
        ("As an AI I cannot help. Try the 4-6 breathing now.", "As an AI"),
        ("أنا لست أخصائية نفسية؛ لكن يمكنني أن أرافقك في تمرين التنفس.", "لست أخصائية"),
        ("من فقط یه هوش مصنوعی‌ام. بیا یه نفس عمیق بکشیم.", "هوش مصنوعی"),
    ],
)
def test_other_languages_and_phrasings(reply, gone):
    out = strip_self_limit_disclaimers(reply, "en" if reply.isascii() else "fa")
    assert gone not in out and out.strip()


def test_replies_without_a_self_limit_are_untouched_and_never_emptied():
    ok = "می‌فهمم، سخته. بیا با هم یه نفس عمیق بکشیم؛ دم چهار ثانیه، بازدم شش ثانیه."
    assert strip_self_limit_disclaimers(ok, "fa") == ok
    only = "من روانشناس انسانی نیستم."
    assert strip_self_limit_disclaimers(only, "fa") == only  # nothing else to say: keep rather than return an empty reply
    assert strip_self_limit_disclaimers("", "fa") == ""
    honest = "I'm an AI companion, and I'm here with you."  # an honest answer to a sincere question is NOT removed
    assert strip_self_limit_disclaimers(honest, "en") == honest


def test_the_prompt_helps_first_offers_a_specialist_and_never_talks_about_her_limits():
    for lang, needles in {
        "en": ("always give your own concrete help first", "I can find a suitable specialist for you", "Never talk about your own limits"),
        "fa": ("همیشه اول خودت کمک مشخص می‌کنی", "یه متخصص مناسب برات پیدا کنم", "هرگز از محدودیت یا ناتوانی خودت"),
        "ar": ("تقدّمين دائماً مساعدتك الملموسة أولاً", "أجد لك مختصاً مناسباً", "لا تتحدثي أبداً عن حدودك"),
    }.items():
        prompt = PersonaPolicyV1.system_prompt(lang)
        for n in needles:
            assert n in prompt, (lang, n)
        assert "سدی" not in prompt


def test_the_offer_and_the_yes_become_a_directory_request():
    offer = "می‌دونم سخته. اگه دوست داری، یه روانشناس مناسب برات پیدا کنم؟"
    assert is_specialist_offer(offer)
    assert not is_specialist_offer("بهتره به یه روانشناس مراجعه کنی.")  # no offer, no follow-up
    assert not is_specialist_offer("می‌تونم پیدا کنم؟ یه نفس عمیق بکش")  # the question is not at the end
    for yes in ("آره", "آره لطفا", "بله", "باشه", "yes please", "نعم"):
        assert is_affirmative(yes), yes
    for no in ("نه", "الان نه", "آره ولی اول بگو چطور نفس بکشم و بعد چه کار کنم", ""):
        assert not is_affirmative(no), no
    request = specialist_request_for_reply(offer, "آره", "fa")
    assert request == "یک متخصص روانشناسی برام پیدا کن"
    assert is_care_navigation_query(request)  # the existing directory flow understands it
    assert specialist_request_for_reply(offer, "نه", "fa") is None
    assert specialist_request_for_reply("سلام", "آره", "fa") is None
    assert specialist_request_for_reply("Want me to find a doctor for you?", "yes", "en") == "Please find me a suitable specialist doctor"
    for lang in ("fa", "en", "ar"):  # every wording is something the directory flow really understands
        from backend.app.services.intelligence.specialist_offer import _REQUEST
        for text in _REQUEST[lang].values():
            assert is_care_navigation_query(text), (lang, text)


def test_orchestrator_turns_the_yes_into_the_request_only_after_the_offer(db):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator

    u = _user(db, "+17770071001", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    orch = IntelligenceOrchestrator.__new__(IntelligenceOrchestrator)
    orch._db = db
    # no previous turn -> unchanged
    assert orch._continue_specialist_offer(None, u.id, "آره", "fa") == "آره"
    db.add(models.Memory(user_id=u.id, user_message="خیلی استرس دارم", language="fa", created_at=datetime.utcnow() - timedelta(minutes=2),
                         sedi_response="کنارتم. اگه دوست داری، یه روانشناس مناسب برات پیدا کنم؟"))
    db.commit()
    assert orch._continue_specialist_offer(None, u.id, "آره", "fa") == "یک متخصص روانشناسی برام پیدا کن"
    assert orch._continue_specialist_offer(None, u.id, "نه ممنون", "fa") == "نه ممنون"
    # an old offer is not continued
    db.query(models.Memory).filter(models.Memory.user_id == u.id).update({"created_at": datetime.utcnow() - timedelta(hours=2)})
    db.commit()
    assert orch._continue_specialist_offer(None, u.id, "آره", "fa") == "آره"
