"""CR-03.6 — Language-scoped, request-framed explicit-current-request detection (F12)."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.relationship_discovery import (
    DiscoveryDisposition,
    classify_discovery_reply,
    is_explicit_new_request,
    peek_relationship_discovery_marker,
    process_relationship_discovery_answer,
)
from backend.app.services.intelligence.contracts import STAGE_ORDER, IntentId, RequestKind
from backend.app.services.intelligence.intent_registry import (
    DISCOVERY_REPLY_RULE_ID,
    resolve_intent,
    resolve_intent_safe,
)
from backend.app.services.knowledge.kc_fatigue_policy import mark_asked


def _user(db, name: str, *, language: str = "en") -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language=language)
    db.add(row)
    db.flush()
    return row


def _set_marker(db, user_id: int, target_key: str) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(db, user_id, now, f"relationship_discovery:{target_key}")


def _active(db, user_id: int, domain: str, key: str):
    return (
        db.query(models.UserMemoryFact)
        .filter(
            models.UserMemoryFact.user_id == user_id,
            models.UserMemoryFact.domain == domain,
            models.UserMemoryFact.key == key,
            models.UserMemoryFact.fact_status == "active",
            models.UserMemoryFact.soft_invalidated_at.is_(None),
        )
        .first()
    )


# ---- Direct answers must NOT trip request guard ----


@pytest.mark.parametrize(
    "target,message,language,domain,key",
    [
        (
            "routines.exercise_schedule",
            "I exercise when I have time",
            "en",
            "routines",
            "exercise_schedule",
        ),
        (
            "lifestyle.food_habits",
            "I make most of my meals at home",
            "en",
            "lifestyle",
            "food_habits",
        ),
        (
            "lifestyle.food_habits",
            "I eat what my family cooks",
            "en",
            "lifestyle",
            "food_habits",
        ),
        (
            "lifestyle.food_habits",
            "ما گیاهخوار هستیم",
            "fa",
            "lifestyle",
            "food_habits",
        ),
        (
            "lifestyle.food_habits",
            "هر چه در خانه باشد غذا می‌خورم",
            "fa",
            "lifestyle",
            "food_habits",
        ),
        (
            "lifestyle.food_habits",
            "ما آكل اللحوم",
            "ar",
            "lifestyle",
            "food_habits",
        ),
        (
            "lifestyle.food_habits",
            "أنا آكل ما تطبخه عائلتي",
            "ar",
            "lifestyle",
            "food_habits",
        ),
    ],
)
def test_cr036_direct_answers_not_unrelated_by_request_guard(
    db, target, message, language, domain, key
):
    assert is_explicit_new_request(message, language) is False
    clf = classify_discovery_reply(target, message, language)
    assert clf.disposition is DiscoveryDisposition.ANSWER

    user = _user(db, f"da-{hash(message) % 100000}", language=language)
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, target)
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
        classification=clf,
    )
    fact = _active(db, user.id, domain, key)
    assert fact is not None
    assert fact.source == "relationship_discovery"
    assert peek_relationship_discovery_marker(db, user.id) is None

    final = resolve_intent(
        message=message,
        language=language,
        relationship_discovery_disposition=clf.disposition.value,
    )
    assert final.rule_id == DISCOVERY_REPLY_RULE_ID


def test_cr036_bare_action_verbs_not_request():
    assert is_explicit_new_request("I make most of my meals at home", "en") is False
    assert is_explicit_new_request("I plan my meals on Sunday", "en") is False
    assert is_explicit_new_request("Create a meal plan for me", "en") is True
    assert is_explicit_new_request("Please create a nutrition plan for me", "en") is True


def test_cr036_bare_interrogatives_not_request_in_declarative():
    assert is_explicit_new_request("I exercise when I have time", "en") is False
    assert is_explicit_new_request("I eat what my family cooks", "en") is False
    assert is_explicit_new_request("How much sleep should I get?", "en") is True
    assert is_explicit_new_request("What should I eat?", "en") is True
    assert is_explicit_new_request("When should I exercise?", "en") is True


def test_cr036_ar_ma_does_not_leak_into_fa():
    assert is_explicit_new_request("ما گیاهخوار هستیم", "fa") is False
    assert is_explicit_new_request("ما آكل اللحوم", "ar") is False
    assert is_explicit_new_request("ما هو النوم الجيد؟", "ar") is True  # ؟ bias
    assert is_explicit_new_request("ما هو النظام الغذائي", "ar") is True  # ما هو


# ---- New requests remain UNRELATED ----


@pytest.mark.parametrize(
    "target,message,language,expected_intent",
    [
        (
            "lifestyle.sleep_quality",
            "How much sleep should I get?",
            "en",
            IntentId.SLEEP,
        ),
        (
            "lifestyle.food_habits",
            "Please create a nutrition plan for me",
            "en",
            IntentId.NUTRITION,
        ),
        (
            "lifestyle.activity_level",
            "Help me exercise more",
            "en",
            IntentId.ACTIVITY,
        ),
        (
            "lifestyle.sleep_quality",
            "چقدر باید بخوابم؟",
            "fa",
            IntentId.GENERAL,  # FA sleep phrasing may fall to GENERAL; must not be discovery
        ),
        (
            "lifestyle.food_habits",
            "میشه برام برنامه غذایی بسازی؟",
            "fa",
            None,  # check not discovery below
        ),
        (
            "lifestyle.sleep_quality",
            "كم يجب أن أنام؟",
            "ar",
            None,
        ),
        (
            "lifestyle.food_habits",
            "هل يمكنك عمل خطة غذائية لي؟",
            "ar",
            None,
        ),
    ],
)
def test_cr036_new_requests_unrelated_preserve_i3(
    db, target, message, language, expected_intent
):
    assert is_explicit_new_request(message, language) is True
    clf = classify_discovery_reply(target, message, language)
    assert clf.disposition is DiscoveryDisposition.UNRELATED

    final = resolve_intent(
        message=message,
        language=language,
        relationship_discovery_disposition=clf.disposition.value,
    )
    assert final.rule_id != DISCOVERY_REPLY_RULE_ID
    if expected_intent is not None:
        assert final.intent_id is expected_intent
    if message == "Please create a nutrition plan for me":
        assert final.request_kind is RequestKind.PERSONALIZED_PLAN
    if message == "Help me exercise more":
        assert final.request_kind is RequestKind.PERSONALIZED_PLAN

    user = _user(db, f"nr-{hash(message) % 100000}", language=language)
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, target)
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
        classification=clf,
    )
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() == 0
    assert peek_relationship_discovery_marker(db, user.id) is None


def test_cr036_discovery_reply_still_sets_skip_kc(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.intelligence.missing_information import evaluate_readiness
    from backend.app.services.intelligence.contracts import (
        PostGenerationSafetyResult,
        PostGenerationSafetyStatus,
        ReasonCode,
        RiskAssessment,
        RiskDomain,
        RiskLevel,
        SafetyAction,
    )
    from backend.app.services.intelligence.context_types import (
        ContextSection,
        ContextSnapshot,
    )
    from backend.app.services.i6.relationship_discovery import DiscoveryClassification

    seen = []

    def gen(uid, msg, name=None, **kw):
        seen.append(dict(kw))
        return {"message": "ok", "language": "en"}

    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: "lifestyle.food_habits",
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._apply_discovery_fatigue_response",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )

    class StubAsm:
        def assemble(self, *a, **k):
            return ContextSnapshot(
                request_id="x",
                owner_user_id=1,
                sections={"lifestyle": ContextSection(name="lifestyle", items=[])},
                items=[],
                preferred_name=None,
                conflict_count=0,
                truncated_count=0,
                reason_codes=(ReasonCode.CONTEXT_ASSEMBLED.value,),
                adapter_order=("lifestyle",),
            )

        def build_compatibility_projection(self, snapshot):
            return MagicMock(text="[CTX]", preferred_name=None, truncated=False)

    orch = IntelligenceOrchestrator(
        db=MagicMock(),
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=resolve_intent_safe,
        missing_information_engine=evaluate_readiness,
        safety_assessor=lambda **k: RiskAssessment(
            registry_version="t",
            level=RiskLevel.NONE,
            action=SafetyAction.CONTINUE,
            domain=RiskDomain.NONE,
            rule_id="none",
            language="en",
        ),
        safety_validator=lambda **k: PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.SAFE,
            violation_code=None,
            message=k["text"],
        ),
        safety_response_builder=lambda a: MagicMock(localized_message="S"),
    )
    result = orch.process(
        authenticated_user_id=1,
        message="I make most of my meals at home",
        language="en",
    )
    assert result.intent_id == IntentId.GENERAL.value
    assert "I3_RELATIONSHIP_DISCOVERY_REPLY" in result.reason_codes
    assert seen and seen[0].get("skip_generic_kc_extraction") is True


def test_cr036_protected_symptom_still_wins():
    msg = "خوابم بد است و سردرد دارم"
    clf = classify_discovery_reply("lifestyle.sleep_quality", msg, "fa")
    final = resolve_intent(
        message=msg,
        language="fa",
        relationship_discovery_disposition=clf.disposition.value,
    )
    assert final.intent_id is IntentId.SYMPTOM
    assert final.rule_id != DISCOVERY_REPLY_RULE_ID


def test_cr036_notification_origin_still_wins():
    result = resolve_intent(
        message="I make most of my meals at home",
        language="en",
        has_verified_notification_origin=True,
        relationship_discovery_disposition="ANSWER",
    )
    assert result.intent_id is IntentId.NOTIFICATION_FOLLOW_UP


def test_cr036_stage_order_unchanged():
    assert [s.value for s in STAGE_ORDER] == [
        "initialize_request",
        "resolve_safe_identity",
        "resolve_locale_context",
        "resolve_conversation_origin",
        "assess_safety_risk",
        "assemble_authorized_context",
        "resolve_intent",
        "evaluate_information_readiness",
        "build_clarification_response",
        "build_safety_response",
        "prepare_compatibility_generation",
        "generate_with_legacy_brain",
        "validate_generation_result",
        "complete",
    ]
