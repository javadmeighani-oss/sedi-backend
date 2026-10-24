"""R-018: golden conversation scenarios for Sedi's human/psychologist/caretaker behaviour (DEBT-034).

Offline part: deterministic guards that must hold for every scenario (no LLM).
Live part (skipped unless SEDI_LIVE_LLM_EVAL=1 and a valid OPENAI_API_KEY): sends each scenario through the real persona
prompt and checks the reply against hard rules. Run it manually before/after a persona change:
    SEDI_LIVE_LLM_EVAL=1 python -m pytest backend/tests/test_r018_golden_scenarios.py -q
"""
from __future__ import annotations

import os
import re

import pytest

from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
from backend.app.services.i5.care_navigation_directory import is_care_navigation_query
from backend.app.services.intelligence.grounding_guard import strip_unsupported_personal_claims

# (user message, known-context text the reply may rely on)
SCENARIOS = [
    ("راهکارهای تو چیه؟ متخصص صدی باشه", ""),
    ("اطلاعات بیشتر بده", ""),
    ("چند شبه خوابم نمیاد و کلافه‌ام", ""),
    ("مادرم دیروز فوت کرد، نمی‌دونم چکار کنم", ""),
    ("من دیابت دارم، چی بخورم که قندم نره بالا؟", "health.condition=دیابت"),
    ("میخوام ورزش کنم ولی انگیزه ندارم", ""),
    ("استرس امتحان دارم و دلم شور می‌زنه", ""),
]

_REFERRAL = re.compile(r"(به\s*پزشک\s*مراجعه|با\s*پزشک\s*مشورت|به\s*دکتر\s*مراجعه|حتماً?\s*به\s*دکتر|see\s+a\s+doctor|consult\s+(?:a|your)\s+(?:doctor|physician))", re.I)
_FAMILY_CLAIM = re.compile(r"(مادرت|پدرت|مادر\s*شما|پدر\s*شما)\s+.{0,20}(دیابت|سرطان|فشار)", re.I)


def test_scenarios_never_trigger_the_doctor_directory():
    for msg, _ctx in SCENARIOS:
        assert not is_care_navigation_query(msg), msg


def test_prompts_carry_the_non_negotiables_in_every_language():
    must = {
        "fa": ("تمام نکن", "حافظه‌ی دوم", "هرگز اختراع نکن"),
        "en": ("never end a reply with", "second memory", "never invent"),
        "ar": ("ولا تنهي الرد", "الذاكرة الثانية", "لا اختلاق"),
    }
    for lang, needles in must.items():
        prompt = PersonaPolicyV1.system_prompt(lang)
        for n in needles:
            assert n in prompt, (lang, n)
        assert len(PersonaPolicyV1.safety_rules(lang)) >= 5


def test_guard_removes_invented_family_claims_from_any_scenario_reply():
    reply = "با توجه به اینکه مادرت دیابت داشته، مراقب باش. یه پیاده‌روی کوتاه بعد از شام خوبه."
    for msg, ctx in SCENARIOS:
        out = strip_unsupported_personal_claims(reply, f"{msg}\n{ctx}", "fa")
        assert not _FAMILY_CLAIM.search(out), msg


def _live_enabled() -> bool:
    return os.environ.get("SEDI_LIVE_LLM_EVAL") == "1" and bool(os.environ.get("OPENAI_API_KEY"))


@pytest.mark.skipif(not _live_enabled(), reason="live LLM evaluation is opt-in (SEDI_LIVE_LLM_EVAL=1 + OPENAI_API_KEY)")
@pytest.mark.parametrize("msg,ctx", SCENARIOS)
def test_live_reply_meets_the_hard_rules(msg, ctx):
    from backend.app.core.conversation.prompts import create_primary_chat_response

    messages = [{"role": "system", "content": PersonaPolicyV1.system_prompt("fa", {"preferred_name": "جواد"})}]
    if ctx:
        messages.append({"role": "system", "content": f"[STRUCTURED_CONTEXT]\n- {ctx}"})
    messages.append({"role": "user", "content": msg})
    reply = create_primary_chat_response(messages).output_text.strip()
    assert reply
    assert not _REFERRAL.search(reply), reply
    assert not _FAMILY_CLAIM.search(reply), reply
    assert len(re.findall(r"[.!؟?]", reply)) <= 9, reply  # proportionate, not a lecture
    assert reply.count("؟") + reply.count("?") <= 2, reply  # at most one real question (+ rhetorical slack)
