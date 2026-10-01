"""CR-03.4 — Single-truth discovery extraction: skip generic KC on discovery reply only."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.relationship_discovery import (
    DiscoveryClassification,
    DiscoveryDisposition,
    classify_discovery_reply,
    peek_relationship_discovery_marker,
    process_relationship_discovery_answer,
)
from backend.app.services.intelligence.contracts import STAGE_ORDER
from backend.app.services.intelligence.orchestrator import (
    _generator_accepts_kwarg,
)
from backend.app.services.knowledge.kc_fatigue_policy import mark_asked


MSG_SLEEP_FA = "خوابم بد"


def _user(db, name: str, *, language: str = "fa") -> models.User:
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


def _mock_gpt_ok():
    completion = MagicMock()
    completion.output_text = "متوجه شدم."
    return patch(
        "backend.app.core.conversation.prompts.client.responses.create",
        return_value=completion,
    )


# ---- F10 concrete regression ----


def test_cr034_f10_discovery_reply_single_memory_capture(db):
    """Governed discovery + Brain generation: one I6 fact; zero generic KC promotion."""
    from backend.app.core.conversation.brain import ConversationBrain
    from backend.app.services.intelligence.intent_registry import (
        DISCOVERY_REPLY_RULE_ID,
        resolve_intent_safe,
    )
    from backend.app.services.intelligence.missing_information import evaluate_readiness
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

    user = _user(db, "f10-sleep")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.sleep_quality")
    assert peek_relationship_discovery_marker(db, user.id) == "lifestyle.sleep_quality"

    clf = classify_discovery_reply("lifestyle.sleep_quality", MSG_SLEEP_FA, "fa")
    assert clf.disposition is DiscoveryDisposition.ANSWER
    governed_value = clf.normalized_value

    class StubAsm:
        def assemble(self, *a, **k):
            return ContextSnapshot(
                request_id="f10",
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

    brain_calls = []

    def tracking_brain_generator(
        user_id,
        user_message,
        user_name=None,
        **kwargs,
    ):
        brain_calls.append(dict(kwargs))
        brain = ConversationBrain(db, language="fa")
        return brain.process_message(
            user_id,
            user_message,
            user_name,
            **kwargs,
        )

    orch = IntelligenceOrchestrator(
        db=db,
        legacy_generator=tracking_brain_generator,
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

    with _mock_gpt_ok(), patch(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        return_value=False,
    ):
        result = orch.process(
            authenticated_user_id=user.id,
            message=MSG_SLEEP_FA,
            language="fa",
        )

    assert "I3_RELATIONSHIP_DISCOVERY_REPLY" in result.reason_codes
    assert brain_calls and brain_calls[0].get("skip_generic_kc_extraction") is True

    facts = (
        db.query(models.UserMemoryFact)
        .filter_by(user_id=user.id, domain="lifestyle", key="sleep_quality")
        .all()
    )
    active = [f for f in facts if f.fact_status == "active" and f.soft_invalidated_at is None]
    assert len(active) == 1
    fact = active[0]
    assert fact.provenance_class == "USER_STATED"
    assert fact.source == "relationship_discovery"
    assert json.loads(fact.value_json) == governed_value
    assert json.loads(fact.value_json) != "poor"

    kc_sleep = (
        db.query(models.KcFactCandidate)
        .filter_by(user_id=user.id, fact_type="sleep_quality")
        .count()
    )
    assert kc_sleep == 0
    assert db.query(models.KcUserFact).filter_by(user_id=user.id).count() == 0
    assert peek_relationship_discovery_marker(db, user.id) is None


def test_cr034_normal_kc_path_without_marker(db):
    """No discovery marker: generic KC extraction still runs for خوابم بد."""
    from backend.app.core.conversation.brain import ConversationBrain

    user = _user(db, "kc-ctrl")
    grant_memory_consent(db, user.id, commit=True)
    assert peek_relationship_discovery_marker(db, user.id) is None

    brain = ConversationBrain(db, language="fa")
    with _mock_gpt_ok():
        brain.process_message(
            user.id,
            MSG_SLEEP_FA,
            structured_context_projection="[STRUCTURED_CONTEXT]\n- [lifestyle] note=none",
            use_structured_context=True,
            use_intelligence_safety=True,
            skip_generic_kc_extraction=False,
        )

    kc = (
        db.query(models.KcFactCandidate)
        .filter_by(user_id=user.id, fact_type="sleep_quality")
        .count()
    )
    umf = (
        db.query(models.UserMemoryFact)
        .filter_by(user_id=user.id, domain="lifestyle", key="sleep_quality")
        .all()
    )
    assert kc >= 1 or len(umf) >= 1
    if umf:
        assert all(f.source != "relationship_discovery" for f in umf)


def test_cr034_stale_marker_unrelated_keeps_generic_kc_enabled(db, monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.intelligence.intent_registry import resolve_intent_safe
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

    user = _user(db, "stale-kc", language="en")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.sleep_quality")

    seen = {}

    def gen(uid, msg, name=None, **kw):
        seen.update(kw)
        return {"message": "vitals-ok", "language": "en"}

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
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._apply_discovery_fatigue_response",
        lambda *a, **k: DiscoveryClassification(
            DiscoveryDisposition.UNRELATED, target_key="lifestyle.sleep_quality"
        ),
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: "lifestyle.sleep_quality",
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.classify_discovery_reply",
        lambda target, message, language: DiscoveryClassification(
            DiscoveryDisposition.UNRELATED, target_key=target
        ),
    )

    orch = IntelligenceOrchestrator(
        db=db,
        legacy_generator=gen,
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
        authenticated_user_id=user.id,
        message="what is my blood pressure?",
        language="en",
    )
    assert result.intent_id == "vitals"
    assert seen.get("skip_generic_kc_extraction") is False
    assert "I3_RELATIONSHIP_DISCOVERY_REPLY" not in result.reason_codes


# ---- Propagation / single-call ----


def test_cr034_generator_accepts_kwarg_helper():
    def plain(a, b, *, x=1):
        return None

    def with_skip(a, b, *, skip_generic_kc_extraction=False):
        return None

    def with_star(a, b, **kwargs):
        return None

    assert _generator_accepts_kwarg(plain, "skip_generic_kc_extraction") is False
    assert _generator_accepts_kwarg(with_skip, "skip_generic_kc_extraction") is True
    assert _generator_accepts_kwarg(with_star, "skip_generic_kc_extraction") is True
    assert _generator_accepts_kwarg(with_skip, "relationship_guidance") is False


def test_cr034_discovery_reply_passes_skip_true(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.intelligence.intent_registry import resolve_intent_safe
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
    orch.process(
        authenticated_user_id=1,
        message="I exercise three times a week",
        language="en",
    )
    assert len(seen) == 1
    assert seen[0].get("skip_generic_kc_extraction") is True
    assert "relationship_guidance" in seen[0]


def test_cr034_normal_turn_skip_false_default(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.intelligence.intent_registry import resolve_intent_safe
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

    seen = []

    def gen(uid, msg, name=None, **kw):
        seen.append(dict(kw))
        return {"message": "ok", "language": "en"}

    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
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
    orch.process(authenticated_user_id=1, message="hello there", language="en")
    assert len(seen) == 1
    assert seen[0].get("skip_generic_kc_extraction") is False


def test_cr034_legacy_stub_without_kwarg_called_once(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.intelligence.intent_registry import resolve_intent_safe
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

    calls = {"n": 0}

    def legacy_stub(
        uid,
        msg,
        name=None,
        *,
        notification_context=None,
        structured_context_projection=None,
        structured_preferred_name=None,
        use_structured_context=False,
        use_intelligence_safety=False,
        safety_constraints=None,
        relationship_guidance=None,
    ):
        calls["n"] += 1
        return {"message": "legacy", "language": "en"}

    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
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
        legacy_generator=legacy_stub,
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
    result = orch.process(authenticated_user_id=1, message="hello there", language="en")
    assert calls["n"] == 1
    assert result.message == "legacy"


def test_cr034_generator_typeerror_no_retry(monkeypatch):
    from backend.app.services.intelligence.orchestrator import (
        IntelligenceOrchestrator,
        OrchestrationError,
    )
    from backend.app.services.intelligence.intent_registry import resolve_intent_safe
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

    calls = {"n": 0}

    def boom(uid, msg, name=None, **kw):
        calls["n"] += 1
        raise TypeError("unexpected internal failure")

    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
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
        legacy_generator=boom,
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
    with pytest.raises(Exception):
        orch.process(authenticated_user_id=1, message="hello there", language="en")
    assert calls["n"] == 1


def test_cr034_brain_skip_prevents_kc_after_relationship_write(db):
    """Service seam: relationship bind then Brain(skip=True) must not create KC sleep candidate."""
    from backend.app.core.conversation.brain import ConversationBrain

    user = _user(db, "bind-then-skip")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.sleep_quality")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=MSG_SLEEP_FA,
        language="fa",
        allow_binding=True,
    )
    fact = _active(db, user.id, "lifestyle", "sleep_quality")
    assert fact is not None
    assert fact.source == "relationship_discovery"
    assert fact.provenance_class == "USER_STATED"
    governed = json.loads(fact.value_json)

    brain = ConversationBrain(db, language="fa")
    with _mock_gpt_ok():
        brain.process_message(
            user.id,
            MSG_SLEEP_FA,
            structured_context_projection="[STRUCTURED_CONTEXT]\n- [lifestyle] note=none",
            use_structured_context=True,
            use_intelligence_safety=True,
            skip_generic_kc_extraction=True,
        )

    assert (
        db.query(models.KcFactCandidate)
        .filter_by(user_id=user.id, fact_type="sleep_quality")
        .count()
        == 0
    )
    assert db.query(models.KcUserFact).filter_by(user_id=user.id).count() == 0
    active = _active(db, user.id, "lifestyle", "sleep_quality")
    assert active is not None
    assert json.loads(active.value_json) == governed
    assert active.source == "relationship_discovery"


def test_cr034_stage_order_unchanged():
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
