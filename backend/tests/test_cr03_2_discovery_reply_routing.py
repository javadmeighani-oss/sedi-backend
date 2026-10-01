"""CR-03.2 — Discovery reply target-fit, I3/I8 precedence, early-return marker lifecycle."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.relationship_discovery import (
    DiscoveryDisposition,
    classify_discovery_reply,
    expire_relationship_discovery_marker_on_early_return,
    peek_relationship_discovery_marker,
    process_relationship_discovery_answer,
)
from backend.app.services.intelligence.contracts import STAGE_ORDER
from backend.app.services.knowledge.kc_fatigue_policy import mark_asked


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
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


# ---- A) target fit ----


def test_cr032_activity_headache_unrelated(db):
    user = _user(db, "act-head")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.activity_level")
    clf = classify_discovery_reply(
        "lifestyle.activity_level", "I have a headache today", "en"
    )
    assert clf.disposition is DiscoveryDisposition.UNRELATED
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="I have a headache today",
        language="en",
        allow_binding=True,
        classification=clf,
    )
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() == 0
    assert peek_relationship_discovery_marker(db, user.id) is None


def test_cr032_food_meal_plan_unrelated(db):
    user = _user(db, "food-plan")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.food_habits")
    clf = classify_discovery_reply(
        "lifestyle.food_habits", "create a meal plan for me", "en"
    )
    assert clf.disposition is DiscoveryDisposition.UNRELATED
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="create a meal plan for me",
        language="en",
        allow_binding=True,
        classification=clf,
    )
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() == 0
    assert peek_relationship_discovery_marker(db, user.id) is None


@pytest.mark.parametrize(
    "message,language",
    [
        ("I mostly eat vegetarian meals", "en"),
        ("گیاه‌خوار هستم و خانگی می‌خورم", "fa"),
        ("أنا نباتي وآكل في المنزل", "ar"),
    ],
)
def test_cr032_valid_food_habit_answer(db, message, language):
    user = _user(db, f"food-{hash(message) % 10000}")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.food_habits")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
    )
    assert _active(db, user.id, "lifestyle", "food_habits") is not None


@pytest.mark.parametrize(
    "message,language",
    [
        ("I walk about thirty minutes most days", "en"),
        ("روزها پیاده‌روی می‌کنم", "fa"),
        ("أمشي حوالي ثلاثين دقيقة", "ar"),
    ],
)
def test_cr032_valid_activity_answer(db, message, language):
    user = _user(db, f"act-{hash(message) % 10000}")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.activity_level")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
    )
    assert _active(db, user.id, "lifestyle", "activity_level") is not None


@pytest.mark.parametrize(
    "message,language",
    [
        ("My sleep has been restless lately", "en"),
        ("کیفیت خوابم خوب نیست", "fa"),
        ("جودة نومي سيئة مؤخرا", "ar"),
    ],
)
def test_cr032_valid_sleep_quality_answer(db, message, language):
    user = _user(db, f"sleep-{hash(message) % 10000}")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.sleep_quality")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
    )
    assert _active(db, user.id, "lifestyle", "sleep_quality") is not None


@pytest.mark.parametrize(
    "message,language",
    [
        ("I exercise three times a week", "en"),
        ("هفته‌ای سه بار ورزش می‌کنم", "fa"),
        ("أتمرن ثلاث مرات في الأسبوع", "ar"),
    ],
)
def test_cr032_valid_exercise_schedule_answer(db, message, language):
    user = _user(db, f"ex-{hash(message) % 10000}")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "routines.exercise_schedule")
    clf = classify_discovery_reply("routines.exercise_schedule", message, language)
    assert clf.disposition is DiscoveryDisposition.ANSWER
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
        classification=clf,
    )
    assert _active(db, user.id, "routines", "exercise_schedule") is not None


def test_cr032_response_length_and_time_strict():
    assert (
        classify_discovery_reply(
            "preferences.response_length", "brief please", "en"
        ).disposition
        is DiscoveryDisposition.ANSWER
    )
    assert (
        classify_discovery_reply(
            "preferences.response_length", "whatever you think", "en"
        ).disposition
        is DiscoveryDisposition.AMBIGUOUS
    )
    assert (
        classify_discovery_reply(
            "routines.bedtime", "I go to bed at 11:00 pm", "en"
        ).normalized_value
        is not None
    )
    assert (
        classify_discovery_reply(
            "routines.bedtime", "I go to bed sometime", "en"
        ).disposition
        is DiscoveryDisposition.AMBIGUOUS
    )


# ---- B) dispatch precedence ----


def test_cr032_exercise_answer_suppresses_i8(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.intelligence.contracts import (
        IntentId,
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

    i8_calls = {"n": 0}

    def boom_i8(*a, **k):
        i8_calls["n"] += 1
        raise AssertionError("I8 exercise must not run on discovery ANSWER")

    monkeypatch.setattr(
        "backend.app.services.i8.exercise_primary_path.execute_primary_exercise_action",
        boom_i8,
    )
    monkeypatch.setattr(
        "backend.app.services.i8.exercise_primary_path.is_activity_operational_intent",
        lambda iid: True,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )

    bind_calls = []

    def capture_bind(db, *, user_id, message, language, allow_binding, classification=None):
        bind_calls.append(
            {
                "allow_binding": allow_binding,
                "disposition": classification.disposition if classification else None,
            }
        )
        return classification

    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._apply_discovery_fatigue_response",
        capture_bind,
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: "routines.exercise_schedule",
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.classify_discovery_reply",
        lambda target, message, language: __import__(
            "backend.app.services.i6.relationship_discovery", fromlist=["DiscoveryClassification", "DiscoveryDisposition"]
        ).DiscoveryClassification(
            __import__(
                "backend.app.services.i6.relationship_discovery", fromlist=["DiscoveryDisposition"]
            ).DiscoveryDisposition.ANSWER,
            target_key=target,
            normalized_value="three times a week",
        ),
    )

    from backend.app.services.intelligence.intent_registry import resolve_intent_safe
    from backend.app.services.intelligence.missing_information import evaluate_readiness

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
        legacy_generator=lambda *a, **k: {"message": "ok", "language": "en"},
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
        message="I exercise three times a week",
        language="en",
    )
    assert i8_calls["n"] == 0
    assert any(c.get("disposition") is DiscoveryDisposition.ANSWER for c in bind_calls)
    assert result.intent_id == IntentId.GENERAL.value
    assert "I3_RELATIONSHIP_DISCOVERY_REPLY" in result.reason_codes


def test_cr032_unrelated_nutrition_request_preserves_i8_path(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.intelligence.contracts import (
        IntentConfidenceBand,
        IntentId,
        IntentResult,
        PostGenerationSafetyResult,
        PostGenerationSafetyStatus,
        ReadinessResult,
        ReadinessStatus,
        ReasonCode,
        RequestKind,
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

    i8_calls = {"n": 0}

    class FakeNutrition:
        user_message = "NUTRITION_OK"
        status = "READY"
        grounded = True
        fail_safe = False
        action_id = 7

    def fake_i8(*a, **k):
        i8_calls["n"] += 1
        return FakeNutrition()

    monkeypatch.setattr(
        "backend.app.services.i8.nutrition_primary_path.execute_primary_nutrition_action",
        fake_i8,
    )
    monkeypatch.setattr(
        "backend.app.services.i8.nutrition_primary_path.is_nutrition_operational_intent",
        lambda iid: True,
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: "lifestyle.food_habits",
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.classify_discovery_reply",
        lambda target, message, language: DiscoveryClassification(
            DiscoveryDisposition.UNRELATED, target_key=target
        ),
    )
    consumed = {"n": 0}

    def capture_bind(db, *, user_id, message, language, allow_binding, classification=None):
        consumed["n"] += 1
        return classification

    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._apply_discovery_fatigue_response",
        capture_bind,
    )

    intent = IntentResult(
        registry_version="t",
        intent_id=IntentId.NUTRITION,
        request_kind=RequestKind.PERSONALIZED_PLAN,
        confidence_band=IntentConfidenceBand.HIGH,
        rule_id="i3.rule.nutrition.personalized.v1",
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
        legacy_generator=lambda *a, **k: {"message": "should-not-run", "language": "en"},
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=lambda **k: intent,
        missing_information_engine=lambda **k: ReadinessResult(
            status=ReadinessStatus.READY,
            intent_id=intent.intent_id,
            request_kind=intent.request_kind,
            outcomes=(),
            missing_fact_keys=(),
        ),
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
        message="create a meal plan for me",
        language="en",
    )
    assert consumed["n"] == 1
    assert i8_calls["n"] == 1
    assert result.message == "NUTRITION_OK"
    assert result.intent_id == IntentId.NUTRITION.value


def test_cr032_unrelated_reminder_preserves_dispatch(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.intelligence.contracts import (
        IntentConfidenceBand,
        IntentId,
        IntentResult,
        PostGenerationSafetyResult,
        PostGenerationSafetyStatus,
        ReadinessResult,
        ReadinessStatus,
        ReasonCode,
        RequestKind,
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

    rem_calls = {"n": 0}

    def fake_rem(*a, **k):
        rem_calls["n"] += 1
        return {"created": True}

    monkeypatch.setattr(
        "backend.app.services.intelligence.reminder_event_dispatch.dispatch_reminder_user_event",
        fake_rem,
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: "lifestyle.activity_level",
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.classify_discovery_reply",
        lambda target, message, language: DiscoveryClassification(
            DiscoveryDisposition.UNRELATED, target_key=target
        ),
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._apply_discovery_fatigue_response",
        lambda *a, **k: None,
    )

    intent = IntentResult(
        registry_version="t",
        intent_id=IntentId.REMINDER,
        request_kind=RequestKind.ACTION,
        confidence_band=IntentConfidenceBand.HIGH,
        rule_id="i3.rule.reminder.action.v1",
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
        legacy_generator=lambda *a, **k: {"message": "gen", "language": "en"},
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=lambda **k: intent,
        missing_information_engine=lambda **k: ReadinessResult(
            status=ReadinessStatus.READY,
            intent_id=intent.intent_id,
            request_kind=intent.request_kind,
            outcomes=(),
            missing_fact_keys=(),
        ),
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
        message="remind me to walk tomorrow",
        language="en",
    )
    assert rem_calls["n"] == 1
    assert "Schedule" in result.message or "برنامه" in result.message or "جدولي" in result.message


# ---- C) early return ----


def test_cr032_early_return_expire_helper(db):
    user = _user(db, "early")
    _set_marker(db, user.id, "routines.bedtime")
    assert peek_relationship_discovery_marker(db, user.id) == "routines.bedtime"
    expire_relationship_discovery_marker_on_early_return(db, user.id)
    assert peek_relationship_discovery_marker(db, user.id) is None
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() == 0
    state = db.query(models.KcQuestionPolicyState).filter_by(user_id=user.id).first()
    # No skip/reject/accepted outcome inferred from early-return content.
    assert state.consecutive_rejects == 0


def test_cr032_stream_uses_chat_core():
    import inspect
    from backend.app.routers import interact as interact_mod

    src = inspect.getsource(interact_mod.chat_stream)
    assert "chat(" in src or "await chat" in src or "chat(" in inspect.getsource(
        interact_mod
    )


def test_cr032_stage_order_unchanged():
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


def test_cr032_i3_rule_id_registered():
    from backend.app.services.intelligence.intent_registry import list_rule_ids

    assert "i3.rule.relationship_discovery_reply.v1" in list_rule_ids()
