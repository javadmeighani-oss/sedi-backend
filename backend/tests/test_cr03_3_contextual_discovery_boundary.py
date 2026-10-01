"""CR-03.3 — I3 contextual discovery authority before readiness + boundary-safe cues."""

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
    peek_relationship_discovery_marker,
    process_relationship_discovery_answer,
)
from backend.app.services.intelligence.contracts import STAGE_ORDER, IntentId, RequestKind
from backend.app.services.intelligence.intent_registry import (
    DISCOVERY_REPLY_RULE_ID,
    resolve_intent,
    resolve_intent_safe,
)
from backend.app.services.intelligence.missing_information import evaluate_readiness
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


def _empty_snapshot(owner_user_id: int = 1):
    from backend.app.services.intelligence.context_types import (
        ContextSection,
        ContextSnapshot,
    )
    from backend.app.services.intelligence.contracts import ReasonCode

    return ContextSnapshot(
        request_id="cr033",
        owner_user_id=owner_user_id,
        sections={"lifestyle": ContextSection(name="lifestyle", items=[])},
        items=[],
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(ReasonCode.CONTEXT_ASSEMBLED.value,),
        adapter_order=("lifestyle",),
    )


# ---- I3 contextual authority ----


def test_cr033_i3_answer_overrides_activity_before_readiness():
    raw = resolve_intent(
        message="I exercise three times a week",
        language="en",
    )
    assert raw.intent_id is IntentId.ACTIVITY
    assert raw.request_kind is RequestKind.PERSONALIZED_PLAN

    final = resolve_intent(
        message="I exercise three times a week",
        language="en",
        relationship_discovery_disposition="ANSWER",
    )
    assert final.intent_id is IntentId.GENERAL
    assert final.request_kind is RequestKind.INFORMATIONAL
    assert final.rule_id == DISCOVERY_REPLY_RULE_ID

    snap = _empty_snapshot()
    not_ready = evaluate_readiness(
        snapshot=snap,
        intent=raw,
        authenticated_user_id=1,
        language="en",
        message="I exercise three times a week",
    )
    ready = evaluate_readiness(
        snapshot=snap,
        intent=final,
        authenticated_user_id=1,
        language="en",
        message="I exercise three times a week",
    )
    from backend.app.services.intelligence.contracts import ReadinessStatus

    assert not_ready.status is not ReadinessStatus.READY
    assert not_ready.clarification is not None
    assert ready.status is ReadinessStatus.READY
    assert ready.clarification is None


def test_cr033_notification_origin_always_wins():
    result = resolve_intent(
        message="I exercise three times a week",
        language="en",
        has_verified_notification_origin=True,
        relationship_discovery_disposition="ANSWER",
    )
    assert result.intent_id is IntentId.NOTIFICATION_FOLLOW_UP
    assert result.rule_id == "i3.rule.notification_follow_up.origin.v1"


def test_cr033_ambiguous_preserves_non_general_raw():
    rawish = resolve_intent(
        message="what is my blood pressure?",
        language="en",
        relationship_discovery_disposition="AMBIGUOUS",
    )
    assert rawish.intent_id is IntentId.VITALS
    assert rawish.rule_id != DISCOVERY_REPLY_RULE_ID


def test_cr033_ambiguous_general_uses_discovery_rule():
    result = resolve_intent(
        message="ok sure",
        language="en",
        relationship_discovery_disposition="AMBIGUOUS",
    )
    assert result.intent_id is IntentId.GENERAL
    assert result.rule_id == DISCOVERY_REPLY_RULE_ID


def test_cr033_unrelated_preserves_raw():
    result = resolve_intent(
        message="remind me to walk tomorrow",
        language="en",
        relationship_discovery_disposition="UNRELATED",
    )
    assert result.intent_id is IntentId.REMINDER


def test_cr033_resolve_intent_safe_accepts_disposition():
    result = resolve_intent_safe(
        message="I exercise three times a week",
        language="en",
        relationship_discovery_disposition="SKIP",
    )
    assert result.rule_id == DISCOVERY_REPLY_RULE_ID
    assert result.intent_id is IntentId.GENERAL


# ---- Boundary-safe target matching ----


@pytest.mark.parametrize(
    "target,message,language",
    [
        ("lifestyle.food_habits", "I feel great", "en"),
        ("lifestyle.activity_level", "I have a runny nose", "en"),
        ("lifestyle.food_habits", "That was a great day", "en"),
        ("lifestyle.activity_level", "The app is running", "en"),
    ],
)
def test_cr033_boundary_false_positives_blocked(db, target, message, language):
    user = _user(db, f"neg-{hash(message) % 100000}")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, target)
    clf = classify_discovery_reply(target, message, language)
    assert clf.disposition is not DiscoveryDisposition.ANSWER
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
        classification=clf,
    )
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() == 0


@pytest.mark.parametrize(
    "target,message,language,domain,key",
    [
        ("lifestyle.food_habits", "I eat vegetarian meals", "en", "lifestyle", "food_habits"),
        ("lifestyle.activity_level", "I walk every day", "en", "lifestyle", "activity_level"),
        (
            "routines.exercise_schedule",
            "I run three times a week",
            "en",
            "routines",
            "exercise_schedule",
        ),
        (
            "lifestyle.sleep_quality",
            "کیفیت خوابم خوب نیست",
            "fa",
            "lifestyle",
            "sleep_quality",
        ),
        (
            "lifestyle.activity_level",
            "روزها پیاده‌روی می‌کنم",
            "fa",
            "lifestyle",
            "activity_level",
        ),
        (
            "lifestyle.food_habits",
            "أنا نباتي وآكل في المنزل",
            "ar",
            "lifestyle",
            "food_habits",
        ),
        (
            "routines.exercise_schedule",
            "أتمرن ثلاث مرات في الأسبوع",
            "ar",
            "routines",
            "exercise_schedule",
        ),
    ],
)
def test_cr033_boundary_positives_preserved(db, target, message, language, domain, key):
    user = _user(db, f"pos-{hash(message) % 100000}")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, target)
    clf = classify_discovery_reply(target, message, language)
    assert clf.disposition is DiscoveryDisposition.ANSWER
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
        classification=clf,
    )
    assert _active(db, user.id, domain, key) is not None


# ---- Orchestrator: stale clarification eliminated + I8=0 ----


def _orch_stubs(monkeypatch, *, peek_target, classify_fn=None, readiness_engine=None):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
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
    from backend.app.services.intelligence.intent_registry import resolve_intent_safe
    from backend.app.services.intelligence.missing_information import evaluate_readiness

    i8_ex = {"n": 0}
    i8_nu = {"n": 0}
    rem = {"n": 0}
    binds = []

    def boom_ex(*a, **k):
        i8_ex["n"] += 1
        raise AssertionError("I8 exercise must not run")

    class FakeNutrition:
        user_message = "NUTRITION_OK"
        status = "READY"
        grounded = True
        fail_safe = False
        action_id = 7

    def fake_nu(*a, **k):
        i8_nu["n"] += 1
        return FakeNutrition()

    def fake_rem(*a, **k):
        rem["n"] += 1
        return {"created": True}

    monkeypatch.setattr(
        "backend.app.services.i8.exercise_primary_path.execute_primary_exercise_action",
        boom_ex,
    )
    monkeypatch.setattr(
        "backend.app.services.i8.exercise_primary_path.is_activity_operational_intent",
        lambda iid: True,
    )
    monkeypatch.setattr(
        "backend.app.services.i8.nutrition_primary_path.execute_primary_nutrition_action",
        fake_nu,
    )
    monkeypatch.setattr(
        "backend.app.services.i8.nutrition_primary_path.is_nutrition_operational_intent",
        lambda iid: True,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.reminder_event_dispatch.dispatch_reminder_user_event",
        fake_rem,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: peek_target,
    )
    if classify_fn is not None:
        monkeypatch.setattr(
            "backend.app.services.i6.relationship_discovery.classify_discovery_reply",
            classify_fn,
        )

    def capture_bind(db, *, user_id, message, language, allow_binding, classification=None):
        binds.append(
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
        legacy_generator=lambda *a, **k: {"message": "gen-ok", "language": "en"},
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=resolve_intent_safe,
        missing_information_engine=readiness_engine or evaluate_readiness,
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
    return orch, i8_ex, i8_nu, rem, binds


def test_cr033_orchestrator_discovery_answer_ready_no_activity_clarification(monkeypatch):
    from backend.app.services.intelligence.contracts import IntentId
    from backend.app.services.i6.relationship_discovery import (
        DiscoveryClassification,
        DiscoveryDisposition,
    )

    def clf(target, message, language):
        return DiscoveryClassification(
            DiscoveryDisposition.ANSWER,
            target_key=target,
            normalized_value="three times a week",
        )

    orch, i8_ex, _, _, binds = _orch_stubs(
        monkeypatch,
        peek_target="routines.exercise_schedule",
        classify_fn=clf,
    )
    result = orch.process(
        authenticated_user_id=1,
        message="I exercise three times a week",
        language="en",
    )
    assert result.intent_id == IntentId.GENERAL.value
    assert "I3_RELATIONSHIP_DISCOVERY_REPLY" in result.reason_codes
    assert i8_ex["n"] == 0
    assert any(b["allow_binding"] is True for b in binds)
    assert result.message == "gen-ok"


def _ready_engine(**k):
    from backend.app.services.intelligence.contracts import ReadinessResult, ReadinessStatus

    intent = k["intent"]
    return ReadinessResult(
        status=ReadinessStatus.READY,
        intent_id=intent.intent_id,
        request_kind=intent.request_kind,
        outcomes=(),
        missing_fact_keys=(),
        clarification=None,
    )


def test_cr033_fallthrough_vitals_no_food_fact(monkeypatch):
    from backend.app.services.intelligence.contracts import IntentId
    from backend.app.services.i6.relationship_discovery import (
        DiscoveryClassification,
        DiscoveryDisposition,
    )

    def clf(target, message, language):
        return DiscoveryClassification(
            DiscoveryDisposition.UNRELATED, target_key=target
        )

    orch, _, _, _, binds = _orch_stubs(
        monkeypatch,
        peek_target="lifestyle.food_habits",
        classify_fn=clf,
        readiness_engine=_ready_engine,
    )
    result = orch.process(
        authenticated_user_id=1,
        message="what is my blood pressure?",
        language="en",
    )
    assert result.intent_id == IntentId.VITALS.value
    assert all(b["allow_binding"] is False for b in binds)
    assert "I3_RELATIONSHIP_DISCOVERY_REPLY" not in result.reason_codes


def test_cr033_fallthrough_symptom_preserves_routing(monkeypatch):
    from backend.app.services.intelligence.contracts import IntentId
    from backend.app.services.i6.relationship_discovery import (
        DiscoveryClassification,
        DiscoveryDisposition,
    )

    def clf(target, message, language):
        return DiscoveryClassification(
            DiscoveryDisposition.UNRELATED, target_key=target
        )

    orch, _, _, _, binds = _orch_stubs(
        monkeypatch,
        peek_target="lifestyle.activity_level",
        classify_fn=clf,
        readiness_engine=_ready_engine,
    )
    result = orch.process(
        authenticated_user_id=1,
        message="I have a fever",
        language="en",
    )
    assert result.intent_id == IntentId.SYMPTOM.value
    assert all(b["allow_binding"] is False for b in binds)


def test_cr033_fallthrough_reminder_dispatch(monkeypatch):
    from backend.app.services.intelligence.contracts import IntentId
    from backend.app.services.i6.relationship_discovery import (
        DiscoveryClassification,
        DiscoveryDisposition,
    )

    def clf(target, message, language):
        return DiscoveryClassification(
            DiscoveryDisposition.UNRELATED, target_key=target
        )

    orch, _, _, rem, binds = _orch_stubs(
        monkeypatch,
        peek_target="lifestyle.activity_level",
        classify_fn=clf,
        readiness_engine=_ready_engine,
    )
    result = orch.process(
        authenticated_user_id=1,
        message="remind me to walk tomorrow",
        language="en",
    )
    assert result.intent_id == IntentId.REMINDER.value
    assert rem["n"] == 1
    assert all(b["allow_binding"] is False for b in binds)


def test_cr033_fallthrough_nutrition_plan_preserves_i8(monkeypatch):
    from backend.app.services.intelligence.contracts import IntentId
    from backend.app.services.i6.relationship_discovery import (
        DiscoveryClassification,
        DiscoveryDisposition,
    )

    def clf(target, message, language):
        return DiscoveryClassification(
            DiscoveryDisposition.UNRELATED, target_key=target
        )

    orch, _, i8_nu, _, binds = _orch_stubs(
        monkeypatch,
        peek_target="lifestyle.food_habits",
        classify_fn=clf,
        readiness_engine=_ready_engine,
    )
    result = orch.process(
        authenticated_user_id=1,
        message="create a meal plan for me",
        language="en",
    )
    assert result.intent_id == IntentId.NUTRITION.value
    assert i8_nu["n"] == 1
    assert result.message == "NUTRITION_OK"
    assert all(b["allow_binding"] is False for b in binds)


def test_cr033_notification_origin_with_marker_disposition():
    """Verified notification origin beats discovery ANSWER disposition."""
    from backend.app.services.intelligence.contracts import IntentId

    result = resolve_intent_safe(
        message="I exercise three times a week",
        language="en",
        has_verified_notification_origin=True,
        relationship_discovery_disposition="ANSWER",
    )
    assert result.intent_id is IntentId.NOTIFICATION_FOLLOW_UP
    assert result.rule_id == "i3.rule.notification_follow_up.origin.v1"


def test_cr033_stage_order_unchanged():
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


def test_cr033_no_intent_result_fabrication_in_orchestrator_source():
    import inspect
    from backend.app.services.intelligence import orchestrator as orch_mod

    src = inspect.getsource(orch_mod.IntelligenceOrchestrator.process)
    assert 'rule_id="i3.rule.relationship_discovery_reply.v1"' not in src
    assert "IntentResult(" not in src or "IntentResult(" not in src.split(
        "CR-03.3: observe"
    )[1]
