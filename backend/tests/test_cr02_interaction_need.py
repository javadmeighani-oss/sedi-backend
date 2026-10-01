"""CR-02 — Pure interaction-need classification (EN/FA/AR)."""

from __future__ import annotations

import inspect

from backend.app.services.intelligence.contracts import (
    IntentConfidenceBand,
    IntentId,
    IntentResult,
    RequestKind,
)
from backend.app.services.intelligence import psychological_interaction as psy
from backend.app.services.intelligence.psychological_interaction import (
    InteractionNeed,
    classify_interaction_need,
    detect_discovery_skip_reject,
)


def _intent(
    intent_id: IntentId = IntentId.GENERAL,
    kind: RequestKind = RequestKind.INFORMATIONAL,
) -> IntentResult:
    return IntentResult(
        registry_version="t",
        intent_id=intent_id,
        request_kind=kind,
        confidence_band=IntentConfidenceBand.HIGH,
        rule_id="t",
    )


def test_be_heard_en_fa_ar():
    assert (
        classify_interaction_need(
            message="I feel overwhelmed and just need someone to listen",
            intent=_intent(),
            language="en",
        )
        is InteractionNeed.BE_HEARD
    )
    assert (
        classify_interaction_need(
            message="امروز خیلی ناراحت و استرسم، فقط گوش بده",
            intent=_intent(),
            language="fa",
        )
        is InteractionNeed.BE_HEARD
    )
    assert (
        classify_interaction_need(
            message="أشعر بالقلق وأريد أن أتحدث",
            intent=_intent(),
            language="ar",
        )
        is InteractionNeed.BE_HEARD
    )


def test_decide_act_motivate_cues():
    assert (
        classify_interaction_need(
            message="Which option is better, walking or swimming?",
            intent=_intent(),
            language="en",
        )
        is InteractionNeed.DECIDE
    )
    assert (
        classify_interaction_need(
            message="What should I do as a next step today?",
            intent=_intent(),
            language="en",
        )
        is InteractionNeed.ACT
    )
    assert (
        classify_interaction_need(
            message="I keep falling off and need motivation to keep going",
            intent=_intent(),
            language="en",
        )
        is InteractionNeed.MOTIVATE
    )


def test_intent_fallback_without_diagnosis():
    sleep = classify_interaction_need(
        message="tell me about sleep basics",
        intent=_intent(IntentId.SLEEP),
        language="en",
    )
    assert sleep is InteractionNeed.UNDERSTAND
    plan = classify_interaction_need(
        message="build my meal plan",
        intent=_intent(IntentId.NUTRITION, RequestKind.PERSONALIZED_PLAN),
        language="en",
    )
    assert plan is InteractionNeed.ACT
    src = inspect.getsource(psy)
    assert "Session" not in src
    assert "openai" not in src.lower()
    assert "write_fact" not in src
    assert "UserFact" not in src
    assert "KcUserFact" not in src
    assert "personality disorder" not in src.lower()
    assert "you are depressed" not in src.lower()
    assert "bipolar" not in src.lower()


def test_skip_reject_detection_multilang():
    assert detect_discovery_skip_reject("later", "en") == "skipped"
    assert detect_discovery_skip_reject("not now", "en") == "skipped"
    assert detect_discovery_skip_reject("prefer not", "en") == "rejected"
    assert detect_discovery_skip_reject("بعدا", "fa") == "skipped"
    assert detect_discovery_skip_reject("فعلا نه", "fa") == "skipped"
    assert detect_discovery_skip_reject("نمیخوام", "fa") == "rejected"
    assert detect_discovery_skip_reject("ليس الآن", "ar") == "skipped"
    assert detect_discovery_skip_reject("لا أريد", "ar") == "rejected"
    assert detect_discovery_skip_reject("I usually sleep at 11", "en") is None
