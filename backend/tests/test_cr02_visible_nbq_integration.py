"""CR-02 — Visible NBQ, fatigue, I4/I5 precedence, public API, STAGE_ORDER."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

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
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.app.services.intelligence.psychological_interaction import (
    append_discovery_question,
)
from backend.app.services.a3_session_open import build_first_intro_message


def _safe(language: str = "en") -> RiskAssessment:
    return RiskAssessment(
        registry_version="t",
        level=RiskLevel.NONE,
        action=SafetyAction.CONTINUE,
        domain=RiskDomain.NONE,
        rule_id="none",
        language=language,  # type: ignore[arg-type]
    )


def _caution() -> RiskAssessment:
    return RiskAssessment(
        registry_version="t",
        level=RiskLevel.CAUTION,
        action=SafetyAction.CONTINUE_WITH_CONSTRAINTS,
        domain=RiskDomain.GENERAL,
        rule_id="caution",
        language="en",
    )


def _terminal() -> RiskAssessment:
    return RiskAssessment(
        registry_version="t",
        level=RiskLevel.HIGH,
        action=SafetyAction.RETURN_HIGH_RESPONSE,
        domain=RiskDomain.GENERAL,
        rule_id="high",
        language="en",
    )


def _intent(iid: IntentId = IntentId.SLEEP) -> IntentResult:
    return IntentResult(
        registry_version="t",
        intent_id=iid,
        request_kind=RequestKind.INFORMATIONAL,
        confidence_band=IntentConfidenceBand.HIGH,
        rule_id="t",
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
        request_id="cr02",
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
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or _snap()

    def assemble(self, *a, **k):
        return self.snapshot

    def build_compatibility_projection(self, snapshot):
        return MagicMock(text="[CTX]", preferred_name=None, truncated=False)


def _orch(**kwargs):
    intent = kwargs.pop("intent", _intent())
    readiness = kwargs.pop("readiness", _ready(intent))
    assess = kwargs.pop("assess", lambda **k: _safe())
    validate = kwargs.pop(
        "validate",
        lambda **k: PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.SAFE, violation_code=None, message=k["text"]
        ),
    )
    gen = kwargs.pop("gen", None)
    if gen is None:
        calls = kwargs.pop("calls", {"n": 0, "guidance": None})

        def gen(uid, msg, name=None, **kw):
            calls["n"] += 1
            calls["guidance"] = kw.get("relationship_guidance")
            return {"message": "Primary helpful answer.", "language": "en"}

        kwargs.setdefault("_calls", calls)
    db = kwargs.pop("db", MagicMock())
    return IntelligenceOrchestrator(
        db=db,
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(kwargs.pop("snapshot", None)),
        intent_resolver=lambda **k: intent,
        missing_information_engine=lambda **k: readiness,
        safety_assessor=assess,
        safety_validator=validate,
        safety_response_builder=lambda a: MagicMock(
            localized_message="SAFETY-FIXED"
        ),
    ), kwargs.get("_calls")


def test_answer_precedes_exactly_one_discovery_question(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    marked = {"n": 0}

    def _mark(*a, **k):
        marked["n"] += 1

    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._mark_relationship_discovery_asked",
        _mark,
    )
    orch, calls = _orch()
    result = orch.process(
        authenticated_user_id=1, message="sleep tips please", language="en"
    )
    assert calls["n"] == 1
    assert result.message.startswith("Primary helpful answer.")
    assert result.message.count("?") >= 1
    # Exactly one appended blank-line-separated question block.
    parts = result.message.split("\n\n")
    assert len(parts) == 2
    assert "bed" in parts[1].lower() or "sleep" in parts[1].lower()
    assert marked["n"] == 1
    pub = result.public_brain_dict()
    assert set(pub.keys()) <= {"message", "language", "detected_name"}
    assert "discovery_question_id" not in pub
    assert "interaction_need" not in pub
    assert calls["guidance"] is not None
    assert "RELATIONSHIP" in calls["guidance"] or "need" in calls["guidance"].lower()


def test_hard_clarification_suppresses_discovery():
    intent = _intent(IntentId.NUTRITION)
    readiness = ReadinessResult(
        status=ReadinessStatus.NEEDS_CLARIFICATION,
        intent_id=intent.intent_id,
        request_kind=intent.request_kind,
        outcomes=(),
        missing_fact_keys=("profile.birth_year",),
        clarification=ClarificationResult(
            question_id="i3.q",
            target_key="profile.birth_year",
            template_id="tpl.birth_year.v1",
            localized_message="What is your birth year?",
        ),
    )
    calls = {"n": 0}

    def gen(*a, **k):
        calls["n"] += 1
        return {"message": "nope", "language": "en"}

    orch, _ = _orch(intent=intent, readiness=readiness, gen=gen)
    result = orch.process(
        authenticated_user_id=1, message="meal plan", language="en"
    )
    assert calls["n"] == 0
    assert result.message == "What is your birth year?"
    assert result.discovery_question_id is None


def test_i4_terminal_suppresses_discovery(monkeypatch):
    marked = {"n": 0}
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._mark_relationship_discovery_asked",
        lambda *a, **k: marked.__setitem__("n", marked["n"] + 1),
    )
    orch, _ = _orch(assess=lambda **k: _terminal())
    result = orch.process(
        authenticated_user_id=1, message="sleep tips", language="en"
    )
    assert result.message == "SAFETY-FIXED"
    assert result.discovery_question_id is None
    assert marked["n"] == 0
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]


def test_caution_path_does_not_append_visible_nbq(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    orch, calls = _orch(assess=lambda **k: _caution())
    result = orch.process(
        authenticated_user_id=1, message="sleep tips", language="en"
    )
    assert calls["n"] == 1
    assert "\n\n" not in result.message
    # Metadata may still exist from CR-01 selection; visible append suppressed.
    assert result.message == "Primary helpful answer."


def test_fatigue_blocks_repeat(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )
    marked = {"n": 0}
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._mark_relationship_discovery_asked",
        lambda *a, **k: marked.__setitem__("n", marked["n"] + 1),
    )
    orch, _ = _orch()
    result = orch.process(
        authenticated_user_id=1, message="sleep tips", language="en"
    )
    assert "\n\n" not in result.message
    assert marked["n"] == 0
    assert result.discovery_target_key == "routines.bedtime"


def test_post_validation_replacement_no_mark_asked(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    marked = {"n": 0}
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._mark_relationship_discovery_asked",
        lambda *a, **k: marked.__setitem__("n", marked["n"] + 1),
    )

    def validate(**k):
        return PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.REPLACED,
            violation_code="x",
            message="REPLACED-SAFE-TEXT",
        )

    orch, _ = _orch(validate=validate)
    result = orch.process(
        authenticated_user_id=1, message="sleep tips", language="en"
    )
    assert result.message == "REPLACED-SAFE-TEXT"
    assert marked["n"] == 0


def test_specialized_care_nav_unchanged(monkeypatch):
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
    calls = {"n": 0}

    def gen(*a, **k):
        calls["n"] += 1
        return {"message": "llm", "language": "en"}

    orch, _ = _orch(intent=_intent(IntentId.GENERAL), gen=gen)
    result = orch.process(
        authenticated_user_id=1,
        message="find a cardiologist near me",
        language="en",
    )
    assert calls["n"] == 0
    assert result.message == "care-nav-failsafe"
    assert result.discovery_question_id is None


def test_compatibility_unchanged_no_extra_llm():
    calls = {"n": 0}

    def gen(*a, **k):
        calls["n"] += 1
        return {"message": "compat", "language": "en"}

    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=False,
        safety_assessor=lambda **k: _safe(),
    )
    result = orch.process(authenticated_user_id=1, message="hello", language="en")
    assert calls["n"] == 1
    assert result.rollout_mode == "compatibility"
    assert result.discovery_question_id is None
    assert result.interaction_need is None


def test_skip_reject_updates_existing_fatigue_state(monkeypatch):
    answers = []

    class State:
        last_question_type = "relationship_discovery:routines.bedtime"

    monkeypatch.setattr(
        "backend.app.services.knowledge.kc_fatigue_policy.ensure_state",
        lambda db, uid, now: State(),
    )
    monkeypatch.setattr(
        "backend.app.services.knowledge.kc_fatigue_policy.mark_answer",
        lambda db, uid, now, outcome: answers.append(outcome),
    )
    from backend.app.services.intelligence.orchestrator import (
        _apply_discovery_fatigue_response,
    )

    _apply_discovery_fatigue_response(
        MagicMock(), user_id=1, message="بعدا", language="fa"
    )
    assert answers == ["skipped"]
    answers.clear()
    _apply_discovery_fatigue_response(
        MagicMock(), user_id=1, message="prefer not", language="en"
    )
    assert answers == ["rejected"]
    answers.clear()
    _apply_discovery_fatigue_response(
        MagicMock(), user_id=1, message="I usually sleep around eleven", language="en"
    )
    assert answers == ["accepted"]


def test_append_helper_orders_answer_then_question():
    out = append_discovery_question("Answer first.", "Optional question?")
    assert out == "Answer first.\n\nOptional question?"


def test_first_contact_current_priority_wording():
    class U:
        name = "Sara"
        preferred_language = "en"

    msg = build_first_intro_message(U())
    assert "Sedi" in msg
    assert "Sara" in msg or ", Sara" in msg
    assert "how are you feeling today" not in msg.lower()
    assert "important" in msg.lower() or "helpful" in msg.lower() or "focus" in msg.lower()

    class Ufa:
        name = "سارا"
        preferred_language = "fa"

    fa = build_first_intro_message(Ufa())
    assert "صدی" in fa
    assert "امروز حالتان چطور است" not in fa


def test_stage_order_unchanged():
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
