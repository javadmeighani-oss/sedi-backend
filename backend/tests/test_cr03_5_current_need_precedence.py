"""CR-03.5 — Current user request > relationship discovery (F11)."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.relationship_discovery import (
    DiscoveryClassification,
    DiscoveryDisposition,
    classify_discovery_reply,
    is_explicit_new_request,
    peek_relationship_discovery_marker,
    process_relationship_discovery_answer,
)
from backend.app.services.intelligence.contracts import (
    STAGE_ORDER,
    IntentId,
    RequestKind,
)
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


def _fact_count(db, user_id: int) -> int:
    return db.query(models.UserMemoryFact).filter_by(user_id=user_id).count()


# ---- Helper / classifier ----


def test_cr035_please_alone_not_new_request():
    assert is_explicit_new_request("please", "en") is False
    assert is_explicit_new_request("brief please", "en") is False


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
            "lifestyle.activity_level",
            "How active should I be?",
            "en",
            IntentId.ACTIVITY,
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
    ],
)
def test_cr035_same_domain_new_request_unrelated(
    db, target, message, language, expected_intent
):
    user = _user(db, f"sd-{hash(message) % 100000}")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, target)

    assert is_explicit_new_request(message, language) is True
    clf = classify_discovery_reply(target, message, language)
    assert clf.disposition is DiscoveryDisposition.UNRELATED

    final = resolve_intent(
        message=message,
        language=language,
        relationship_discovery_disposition=clf.disposition.value,
    )
    assert final.intent_id is expected_intent
    assert final.rule_id != DISCOVERY_REPLY_RULE_ID
    if expected_intent is IntentId.NUTRITION:
        assert final.request_kind is RequestKind.PERSONALIZED_PLAN
    if message == "Help me exercise more":
        assert final.request_kind is RequestKind.PERSONALIZED_PLAN

    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
        classification=clf,
    )
    assert _fact_count(db, user.id) == 0
    assert peek_relationship_discovery_marker(db, user.id) is None


# ---- Mixed / protected intents ----


def test_cr035_mixed_sleep_answer_and_symptom_preserves_symptom(db, monkeypatch):
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

    msg = "خوابم بد است و سردرد دارم"
    user = _user(db, "mix-sym", language="fa")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.sleep_quality")

    clf = classify_discovery_reply("lifestyle.sleep_quality", msg, "fa")
    # May be ANSWER (sleep fit) or UNRELATED; either way I3 must not become discovery reply.
    raw = resolve_intent(message=msg, language="fa")
    assert raw.intent_id is IntentId.SYMPTOM
    final = resolve_intent(
        message=msg,
        language="fa",
        relationship_discovery_disposition=clf.disposition.value,
    )
    assert final.intent_id is IntentId.SYMPTOM
    assert final.rule_id != DISCOVERY_REPLY_RULE_ID

    seen = {}

    def gen(uid, message, name=None, **kw):
        seen.update(kw)
        return {"message": "symptom-ok", "language": "fa"}

    class StubAsm:
        def assemble(self, *a, **k):
            return ContextSnapshot(
                request_id="x",
                owner_user_id=user.id,
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

    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )

    orch = IntelligenceOrchestrator(
        db=db,
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
            language="fa",
        ),
        safety_validator=lambda **k: PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.SAFE,
            violation_code=None,
            message=k["text"],
        ),
        safety_response_builder=lambda a: MagicMock(localized_message="S"),
    )
    result = orch.process(
        authenticated_user_id=user.id,
        message=msg,
        language="fa",
    )
    assert result.intent_id == IntentId.SYMPTOM.value
    assert "I3_RELATIONSHIP_DISCOVERY_REPLY" not in result.reason_codes
    assert seen.get("skip_generic_kc_extraction") is False
    assert _active(db, user.id, "lifestyle", "sleep_quality") is None
    assert peek_relationship_discovery_marker(db, user.id) is None


def test_cr035_medication_preserves_over_food_marker(db):
    user = _user(db, "med-food")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.food_habits")
    msg = "what medication should I take?"
    clf = classify_discovery_reply("lifestyle.food_habits", msg, "en")
    assert clf.disposition is DiscoveryDisposition.UNRELATED
    final = resolve_intent(
        message=msg,
        language="en",
        relationship_discovery_disposition=clf.disposition.value,
    )
    assert final.intent_id is IntentId.MEDICATION
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=msg,
        language="en",
        allow_binding=True,
        classification=clf,
    )
    assert _active(db, user.id, "lifestyle", "food_habits") is None
    assert peek_relationship_discovery_marker(db, user.id) is None


def test_cr035_vitals_preserves_over_activity_marker(db):
    user = _user(db, "vit-act")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.activity_level")
    msg = "what is my blood pressure?"
    clf = classify_discovery_reply("lifestyle.activity_level", msg, "en")
    assert clf.disposition is DiscoveryDisposition.UNRELATED
    final = resolve_intent(
        message=msg,
        language="en",
        relationship_discovery_disposition=clf.disposition.value,
    )
    assert final.intent_id is IntentId.VITALS
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=msg,
        language="en",
        allow_binding=True,
        classification=clf,
    )
    assert _active(db, user.id, "lifestyle", "activity_level") is None
    assert peek_relationship_discovery_marker(db, user.id) is None


def test_cr035_reminder_preserves_dispatch(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.intelligence.contracts import (
        PostGenerationSafetyResult,
        PostGenerationSafetyStatus,
        ReadinessResult,
        ReadinessStatus,
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

    rem = {"n": 0}

    def fake_rem(*a, **k):
        rem["n"] += 1
        return {"created": True}

    monkeypatch.setattr(
        "backend.app.services.intelligence.reminder_event_dispatch.dispatch_reminder_user_event",
        fake_rem,
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: "routines.exercise_schedule",
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
        legacy_generator=lambda *a, **k: {"message": "gen", "language": "en"},
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=resolve_intent_safe,
        missing_information_engine=lambda **k: ReadinessResult(
            status=ReadinessStatus.READY,
            intent_id=k["intent"].intent_id,
            request_kind=k["intent"].request_kind,
            outcomes=(),
            missing_fact_keys=(),
            clarification=None,
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
    assert result.intent_id == IntentId.REMINDER.value
    assert rem["n"] == 1
    assert "I3_RELATIONSHIP_DISCOVERY_REPLY" not in result.reason_codes


def test_cr035_notification_origin_always_wins():
    result = resolve_intent(
        message="How much sleep should I get?",
        language="en",
        has_verified_notification_origin=True,
        relationship_discovery_disposition="ANSWER",
    )
    assert result.intent_id is IntentId.NOTIFICATION_FOLLOW_UP
    assert result.rule_id == "i3.rule.notification_follow_up.origin.v1"


def test_cr035_i8_nutrition_eligible_on_plan_request(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.intelligence.contracts import (
        PostGenerationSafetyResult,
        PostGenerationSafetyStatus,
        ReadinessResult,
        ReadinessStatus,
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

    i8 = {"n": 0}

    class FakeNutrition:
        user_message = "NUTRITION_OK"
        status = "READY"
        grounded = True
        fail_safe = False
        action_id = 7

    def fake_i8(*a, **k):
        i8["n"] += 1
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
        legacy_generator=lambda *a, **k: {"message": "no", "language": "en"},
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=resolve_intent_safe,
        missing_information_engine=lambda **k: ReadinessResult(
            status=ReadinessStatus.READY,
            intent_id=k["intent"].intent_id,
            request_kind=k["intent"].request_kind,
            outcomes=(),
            missing_fact_keys=(),
            clarification=None,
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
        message="Please create a nutrition plan for me",
        language="en",
    )
    assert result.intent_id == IntentId.NUTRITION.value
    assert i8["n"] == 1
    assert result.message == "NUTRITION_OK"


def test_cr035_i8_exercise_eligible_on_help_exercise(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.intelligence.contracts import (
        PostGenerationSafetyResult,
        PostGenerationSafetyStatus,
        ReadinessResult,
        ReadinessStatus,
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

    i8 = {"n": 0}

    class FakeEx:
        user_message = "EXERCISE_OK"
        status = "READY"
        grounded = True
        fail_safe = False
        action_id = 3

    def fake_i8(*a, **k):
        i8["n"] += 1
        return FakeEx()

    monkeypatch.setattr(
        "backend.app.services.i8.exercise_primary_path.execute_primary_exercise_action",
        fake_i8,
    )
    monkeypatch.setattr(
        "backend.app.services.i8.exercise_primary_path.is_activity_operational_intent",
        lambda iid: True,
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: "lifestyle.activity_level",
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
        legacy_generator=lambda *a, **k: {"message": "no", "language": "en"},
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=resolve_intent_safe,
        missing_information_engine=lambda **k: ReadinessResult(
            status=ReadinessStatus.READY,
            intent_id=k["intent"].intent_id,
            request_kind=k["intent"].request_kind,
            outcomes=(),
            missing_fact_keys=(),
            clarification=None,
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
        message="Help me exercise more",
        language="en",
    )
    assert result.intent_id == IntentId.ACTIVITY.value
    assert i8["n"] == 1


# ---- Pure discovery still works ----


@pytest.mark.parametrize(
    "target,message,language,domain,key",
    [
        ("lifestyle.sleep_quality", "خوابم بد", "fa", "lifestyle", "sleep_quality"),
        (
            "lifestyle.food_habits",
            "I eat vegetarian meals",
            "en",
            "lifestyle",
            "food_habits",
        ),
        (
            "lifestyle.activity_level",
            "I walk every day",
            "en",
            "lifestyle",
            "activity_level",
        ),
        (
            "routines.exercise_schedule",
            "I exercise three times a week",
            "en",
            "routines",
            "exercise_schedule",
        ),
        (
            "preferences.response_length",
            "brief please",
            "en",
            "preferences",
            "response_length",
        ),
    ],
)
def test_cr035_pure_discovery_answers_still_bind(
    db, target, message, language, domain, key
):
    user = _user(db, f"pure-{hash(message) % 100000}", language=language)
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, target)
    clf = classify_discovery_reply(target, message, language)
    assert clf.disposition is DiscoveryDisposition.ANSWER
    final = resolve_intent(
        message=message,
        language=language,
        relationship_discovery_disposition=clf.disposition.value,
    )
    assert final.rule_id == DISCOVERY_REPLY_RULE_ID
    assert final.intent_id is IntentId.GENERAL
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
    assert fact.provenance_class == "USER_STATED"
    assert peek_relationship_discovery_marker(db, user.id) is None


def test_cr035_pure_discovery_sets_skip_kc(monkeypatch):
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

    seen = []

    def gen(uid, msg, name=None, **kw):
        seen.append(dict(kw))
        return {"message": "ok", "language": "en"}

    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: "routines.exercise_schedule",
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.classify_discovery_reply",
        lambda target, message, language: DiscoveryClassification(
            DiscoveryDisposition.ANSWER,
            target_key=target,
            normalized_value="three times a week",
        ),
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._apply_discovery_fatigue_response",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "backend.app.services.i8.exercise_primary_path.is_activity_operational_intent",
        lambda iid: False,
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
        message="I exercise three times a week",
        language="en",
    )
    assert result.intent_id == IntentId.GENERAL.value
    assert "I3_RELATIONSHIP_DISCOVERY_REPLY" in result.reason_codes
    assert len(seen) == 1
    assert seen[0].get("skip_generic_kc_extraction") is True


def test_cr035_stage_order_unchanged():
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
