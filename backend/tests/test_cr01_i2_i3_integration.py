"""CR-01 — I1/I3 orchestrator NBQ integration (foundation only)."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.app.services.intelligence.context_types import (
    ContextItem,
    ContextProvenance,
    ContextSection,
    ContextSnapshot,
    ContextSource,
    SOURCE_SORT_RANK,
)
from backend.app.services.intelligence.contracts import (
    STAGE_ORDER,
    ClarificationResult,
    IntentConfidenceBand,
    IntentId,
    IntentResult,
    ReadinessResult,
    ReadinessStatus,
    ReasonCode,
    RequestKind,
    RiskAssessment,
    RiskDomain,
    RiskLevel,
    SafetyAction,
)
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator


def _safe_assessment(language: str = "en") -> RiskAssessment:
    return RiskAssessment(
        registry_version="test",
        level=RiskLevel.NONE,
        action=SafetyAction.CONTINUE,
        domain=RiskDomain.NONE,
        rule_id="none",
        language=language,  # type: ignore[arg-type]
    )


def _intent(intent_id: IntentId) -> IntentResult:
    return IntentResult(
        registry_version="test",
        intent_id=intent_id,
        request_kind=RequestKind.INFORMATIONAL,
        confidence_band=IntentConfidenceBand.HIGH,
        rule_id="test",
    )


def _ready(intent: IntentResult) -> ReadinessResult:
    return ReadinessResult(
        status=ReadinessStatus.READY,
        intent_id=intent.intent_id,
        request_kind=intent.request_kind,
        outcomes=(),
        missing_fact_keys=(),
    )


def _snap(items=None) -> ContextSnapshot:
    items = list(items or [])
    return ContextSnapshot(
        request_id="cr01-orch",
        owner_user_id=1,
        sections={"lifestyle": ContextSection(name="lifestyle", items=items)},
        items=items,
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(ReasonCode.CONTEXT_ASSEMBLED.value,),
        adapter_order=("lifestyle",),
    )


class StubAsm:
    def __init__(self, snapshot: ContextSnapshot | None = None):
        self.snapshot = snapshot or _snap()

    def assemble(self, *a, **k):
        return self.snapshot

    def build_compatibility_projection(self, snapshot):
        return MagicMock(
            text="[STRUCTURED_CONTEXT]",
            preferred_name=None,
            truncated=False,
        )


def test_cr01_nbq_metadata_on_structured_normal_path():
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "hello-out", "language": "en"}

    intent = _intent(IntentId.SLEEP)
    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=lambda **k: intent,
        missing_information_engine=lambda **k: _ready(intent),
        safety_assessor=lambda **k: _safe_assessment(),
    )
    result = orch.process(
        authenticated_user_id=1, message="how is sleep", language="en"
    )
    assert calls["n"] == 1
    assert result.message == "hello-out"
    assert result.discovery_question_id is not None
    assert result.discovery_target_key == "routines.bedtime"
    # Not injected into user-visible message.
    assert "bed" not in result.message.lower() or result.message == "hello-out"
    pub = result.public_brain_dict()
    assert set(pub.keys()) <= {"message", "language", "detected_name"}
    assert "discovery_question_id" not in pub
    assert "discovery_target_key" not in pub
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]


def test_cr01_hard_clarification_suppresses_nbq_and_skips_generator():
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "should-not", "language": "en"}

    intent = _intent(IntentId.NUTRITION)
    readiness = ReadinessResult(
        status=ReadinessStatus.NEEDS_CLARIFICATION,
        intent_id=intent.intent_id,
        request_kind=intent.request_kind,
        outcomes=(),
        missing_fact_keys=("profile.birth_year",),
        clarification=ClarificationResult(
            question_id="i3.q.nut.birth_year.v1",
            target_key="profile.birth_year",
            template_id="tpl.birth_year.v1",
            localized_message="What is your birth year?",
        ),
    )
    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=lambda **k: intent,
        missing_information_engine=lambda **k: readiness,
        safety_assessor=lambda **k: _safe_assessment(),
    )
    result = orch.process(
        authenticated_user_id=1, message="meal plan for me", language="en"
    )
    assert calls["n"] == 0
    assert result.message == "What is your birth year?"
    assert result.discovery_question_id is None
    assert result.discovery_target_key is None
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]


def test_cr01_safety_sensitive_intent_no_nbq_metadata():
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "symptom-out", "language": "en"}

    intent = _intent(IntentId.SYMPTOM)
    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=lambda **k: intent,
        missing_information_engine=lambda **k: _ready(intent),
        safety_assessor=lambda **k: _safe_assessment(),
    )
    result = orch.process(
        authenticated_user_id=1, message="I have a headache", language="en"
    )
    assert calls["n"] == 1
    assert result.discovery_question_id is None
    assert result.discovery_target_key is None


def test_cr01_compatibility_mode_unchanged_no_nbq():
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "compat-ok", "language": "en"}

    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=False,
        safety_assessor=lambda **k: _safe_assessment(),
    )
    result = orch.process(
        authenticated_user_id=1, message="hello sleep", language="en"
    )
    assert calls["n"] == 1
    assert result.rollout_mode == "compatibility"
    assert result.discovery_question_id is None
    assert result.discovery_target_key is None
    assert ReasonCode.INTENT_RESOLUTION_SKIPPED_COMPATIBILITY.value in result.reason_codes
    pub = result.public_brain_dict()
    assert set(pub.keys()) <= {"message", "language", "detected_name"}
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]


def test_cr01_specialized_care_nav_path_preserves_skip_no_nbq(monkeypatch):
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "llm", "language": "en"}

    intent = _intent(IntentId.GENERAL)

    monkeypatch.setattr(
        "backend.app.services.i5.care_navigation_directory.is_care_navigation_query",
        lambda _m: True,
    )

    class FakeNav:
        status = "NO_VERIFIED"
        user_message = "care-nav-failsafe"

    monkeypatch.setattr(
        "backend.app.services.i5.care_navigation_directory.resolve_care_navigation",
        lambda *a, **k: FakeNav(),
    )
    monkeypatch.setattr(
        "backend.app.services.i5.care_navigation_directory.fail_safe_user_message",
        lambda *a, **k: "care-nav-failsafe",
    )
    monkeypatch.setattr(
        "backend.app.services.i5.care_navigation_directory.STATUS_VERIFIED",
        "VERIFIED",
    )
    monkeypatch.setattr(
        "backend.app.services.i5.care_navigation_directory.STATUS_NO_VERIFIED",
        "NO_VERIFIED",
    )

    orch = IntelligenceOrchestrator(
        db=MagicMock(),
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=lambda **k: intent,
        missing_information_engine=lambda **k: _ready(intent),
        safety_assessor=lambda **k: _safe_assessment(),
    )
    result = orch.process(
        authenticated_user_id=1,
        message="find a cardiologist near me",
        language="en",
    )
    assert calls["n"] == 0
    assert result.message == "care-nav-failsafe"
    assert result.discovery_question_id is None
    assert result.discovery_target_key is None
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]


def test_cr01_stage_order_unchanged():
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


def test_cr01_existing_fact_in_snapshot_skips_that_nbq_key():
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "ok", "language": "en"}

    intent = _intent(IntentId.SLEEP)
    item = ContextItem(
        canonical_key="routines.bedtime",
        section="lifestyle",
        source=ContextSource.LIFESTYLE,
        structured_value='"23:00"',
        display_text="bedtime=23:00",
        provenance=ContextProvenance(
            source=ContextSource.LIFESTYLE, owner_user_id=1, query_label="t"
        ),
        observed_at=None,
        freshness="unknown",
        sensitivity="medium",
        consent="legacy_scope",
        may_send_to_llm=True,
        sort_rank=SOURCE_SORT_RANK[ContextSource.LIFESTYLE],
    )
    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(_snap([item])),
        intent_resolver=lambda **k: intent,
        missing_information_engine=lambda **k: _ready(intent),
        safety_assessor=lambda **k: _safe_assessment(),
    )
    result = orch.process(
        authenticated_user_id=1, message="sleep tips", language="en"
    )
    assert result.discovery_target_key == "routines.wake_time"
