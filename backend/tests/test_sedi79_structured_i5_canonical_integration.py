"""SEDI-79 — Structured chat → canonical I5 retrieve_knowledge_context wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.app.core.conversation.brain import (
    ConversationBrain,
    _maybe_append_structured_governed_knowledge,
)
from backend.app.services.intelligence.context_types import (
    ContextSection,
    ContextSnapshot,
)
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
from backend.app.services.intelligence.orchestrator import (
    IntelligenceOrchestrator,
    allow_governed_knowledge_decision,
)
from backend.app.services.intelligence.psychological_interaction import InteractionNeed


def _safe() -> RiskAssessment:
    return RiskAssessment(
        registry_version="t",
        level=RiskLevel.NONE,
        action=SafetyAction.CONTINUE,
        domain=RiskDomain.NONE,
        rule_id="none",
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


def _intent(
    iid: IntentId = IntentId.HEALTH,
    kind: RequestKind = RequestKind.INFORMATIONAL,
) -> IntentResult:
    return IntentResult(
        registry_version="t",
        intent_id=iid,
        request_kind=kind,
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


class _StubAsm:
    def assemble(self, *a, **k):
        return ContextSnapshot(
            request_id="sedi79",
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
        return MagicMock(text="[STRUCTURED_CONTEXT]", preferred_name=None, truncated=False)


def _orch(*, intent=None, assess=None, gen=None, structured_mode=True):
    intent = intent or _intent()
    captured = {"allow": None, "guidance": None, "n": 0}

    if gen is None:

        def gen(uid, msg, name=None, **kw):
            captured["n"] += 1
            captured["allow"] = kw.get("allow_governed_knowledge")
            captured["guidance"] = kw.get("relationship_guidance")
            return {"message": "ok", "language": "en"}

    orch = IntelligenceOrchestrator(
        db=MagicMock(),
        legacy_generator=gen,
        structured_mode=structured_mode,
        context_assembler=_StubAsm(),
        intent_resolver=lambda **k: intent,
        missing_information_engine=lambda **k: _ready(intent),
        safety_assessor=assess or (lambda **k: _safe()),
        safety_validator=lambda **k: PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.SAFE,
            violation_code=None,
            message=k["text"],
        ),
        safety_response_builder=lambda a: MagicMock(localized_message="SAFETY-FIXED"),
    )
    return orch, captured


# ---------------------------------------------------------------------------
# Decision owner (I1 using I3/I4 signals)
# ---------------------------------------------------------------------------


def test_decision_i4_terminal_false():
    assert (
        allow_governed_knowledge_decision(
            terminal_safety=True,
            message="blood pressure medication dose",
            language="en",
            intent=_intent(IntentId.MEDICATION),
            interaction_need=InteractionNeed.UNDERSTAND,
        )
        is False
    )


def test_decision_pure_be_heard_no_retrieval():
    assert (
        allow_governed_knowledge_decision(
            terminal_safety=False,
            message="I feel overwhelmed and just need to talk",
            language="en",
            intent=_intent(IntentId.GENERAL),
            interaction_need=InteractionNeed.BE_HEARD,
        )
        is False
    )


def test_decision_be_heard_plus_factual_intent_allows():
    assert (
        allow_governed_knowledge_decision(
            terminal_safety=False,
            message="I feel anxious — what does evidence say about sleep hygiene?",
            language="en",
            intent=_intent(IntentId.SLEEP),
            interaction_need=InteractionNeed.BE_HEARD,
        )
        is True
    )


def test_decision_health_ask_allows():
    assert (
        allow_governed_knowledge_decision(
            terminal_safety=False,
            message="What is a normal blood pressure range?",
            language="en",
            intent=_intent(IntentId.HEALTH),
            interaction_need=InteractionNeed.UNDERSTAND,
        )
        is True
    )


def test_decision_mental_wellbeing_classifier_allows():
    assert (
        allow_governed_knowledge_decision(
            terminal_safety=False,
            message="evidence-based tips for anxiety and mental wellbeing",
            language="en",
            intent=_intent(IntentId.GENERAL),
            interaction_need=InteractionNeed.UNDERSTAND,
        )
        is True
    )


def test_decision_greeting_and_general_false():
    assert (
        allow_governed_knowledge_decision(
            terminal_safety=False,
            message="hello there",
            language="en",
            intent=_intent(IntentId.GENERAL),
            interaction_need=InteractionNeed.GENERAL,
        )
        is False
    )


def test_decision_reminder_intent_false():
    assert (
        allow_governed_knowledge_decision(
            terminal_safety=False,
            message="remind me about my medication",
            language="en",
            intent=_intent(IntentId.REMINDER, RequestKind.ACTION),
            interaction_need=InteractionNeed.ACT,
        )
        is False
    )


# ---------------------------------------------------------------------------
# Orchestrator wiring
# ---------------------------------------------------------------------------


def test_structured_health_ask_passes_allow_true(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    orch, captured = _orch(intent=_intent(IntentId.HEALTH))
    orch.process(
        authenticated_user_id=1,
        message="What is a normal blood pressure range?",
        language="en",
    )
    assert captured["n"] == 1
    assert captured["allow"] is True
    assert captured["guidance"] is not None


def test_structured_pure_be_heard_passes_allow_false(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    orch, captured = _orch(intent=_intent(IntentId.GENERAL))
    orch.process(
        authenticated_user_id=1,
        message="I feel overwhelmed and just need to talk",
        language="en",
    )
    assert captured["n"] == 1
    assert captured["allow"] is False
    assert captured["guidance"] is not None


def test_structured_be_heard_factual_passes_allow_true(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    orch, captured = _orch(intent=_intent(IntentId.SLEEP))
    orch.process(
        authenticated_user_id=1,
        message="I feel anxious — evidence on sleep hygiene?",
        language="en",
    )
    assert captured["n"] == 1
    assert captured["allow"] is True


def test_i4_terminal_zero_generation_and_no_allow(monkeypatch):
    orch, captured = _orch(assess=lambda **k: _terminal())
    result = orch.process(
        authenticated_user_id=1,
        message="blood pressure medication dose",
        language="en",
    )
    assert result.message == "SAFETY-FIXED"
    assert captured["n"] == 0
    assert captured["allow"] is None


def test_compat_flag_off_does_not_set_allow_true():
    orch, captured = _orch(structured_mode=False, intent=_intent(IntentId.HEALTH))
    orch.process(
        authenticated_user_id=1,
        message="What is a normal blood pressure range?",
        language="en",
    )
    assert captured["n"] == 1
    # Compat path must not enable structured I5 gate.
    assert captured["allow"] in (None, False)


def test_i6_adaptive_prefs_guidance_preserved_with_i5_allow(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    orch, captured = _orch(intent=_intent(IntentId.SLEEP))
    orch.process(
        authenticated_user_id=1,
        message="sleep tips please",
        language="en",
    )
    assert captured["allow"] is True
    assert captured["guidance"]
    g = captured["guidance"].lower()
    assert "relationship" in g or "need" in g or "listen" in g or "response" in g


# ---------------------------------------------------------------------------
# Brain: single I5 retrieval, no pack duplication, no LocalRAG/Stage17
# ---------------------------------------------------------------------------


def test_structured_helper_exactly_one_retrieve_knowledge_context():
    calls = {"n": 0}

    class _FakeRetrieval:
        status = "OK"

        def to_dict(self):
            return {"status": "OK", "items": [], "knowledge_snippets": [], "exclusions": []}

    def _retrieve(*a, **k):
        calls["n"] += 1
        return _FakeRetrieval()

    messages = [{"role": "system", "content": "base"}]
    with (
        patch(
            "backend.app.services.i5.runtime_knowledge_retrieval.retrieve_knowledge_context",
            _retrieve,
        ),
        patch(
            "backend.app.services.gate3.care_intelligence.build_care_context",
        ) as build_care,
        patch(
            "backend.app.core.conversation.brain._maybe_append_local_rag_context",
        ) as local_rag,
        patch(
            "backend.app.core.conversation.brain._maybe_append_rag_context_v1",
        ) as stage17,
    ):
        _maybe_append_structured_governed_knowledge(
            messages, MagicMock(), 1, "blood pressure evidence", "en"
        )
        assert calls["n"] == 1
        build_care.assert_not_called()
        local_rag.assert_not_called()
        stage17.assert_not_called()
    assert any("CARE_CONTEXT" in m.get("content", "") for m in messages)


def test_brain_structured_allow_true_single_i5_no_duplication(monkeypatch, db):
    from backend.app.models import User

    db.rollback()
    user = User(name="S79", secret_key="s79i5", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)

    calls = {"retrieve": 0}

    class _FakeRetrieval:
        status = "OK"

        def to_dict(self):
            return {
                "status": "OK",
                "items": [],
                "knowledge_snippets": [],
                "exclusions": [],
                "query_id": "q",
                "trace_id": "t",
            }

    def _retrieve(*a, **k):
        calls["retrieve"] += 1
        return _FakeRetrieval()

    monkeypatch.setattr(
        "backend.app.services.i5.runtime_knowledge_retrieval.retrieve_knowledge_context",
        _retrieve,
    )
    monkeypatch.setattr(
        "backend.app.core.conversation.prompts.resolve_openai_chat_model",
        lambda: "test-model",
    )
    monkeypatch.setattr(
        "backend.app.core.conversation.prompts.create_primary_chat_response",
        lambda messages: MagicMock(output_text="grounded educational reply"),
    )

    with (
        patch(
            "backend.app.services.gate3.care_intelligence.build_care_context",
        ) as build_care,
        patch(
            "backend.app.core.conversation.brain._maybe_append_local_rag_context",
        ) as local_rag,
        patch(
            "backend.app.core.conversation.brain._maybe_append_rag_context_v1",
        ) as stage17,
        patch(
            "backend.app.core.conversation.brain._maybe_append_gate3_care_context",
        ) as gate3_care,
    ):
        brain = ConversationBrain(db, language="en")
        out = brain.process_message(
            user.id,
            "What is a normal blood pressure range?",
            use_structured_context=True,
            structured_context_projection="[STRUCTURED_CONTEXT]",
            use_intelligence_safety=True,
            allow_governed_knowledge=True,
        )
        assert out.get("message")
        assert calls["retrieve"] == 1
        build_care.assert_not_called()
        local_rag.assert_not_called()
        stage17.assert_not_called()
        gate3_care.assert_not_called()


def test_brain_structured_allow_false_zero_retrieval(monkeypatch, db):
    from backend.app.models import User

    db.rollback()
    user = User(name="S79b", secret_key="s79i5b", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)

    calls = {"retrieve": 0}

    def _retrieve(*a, **k):
        calls["retrieve"] += 1
        raise AssertionError("retrieve_knowledge_context must not run")

    monkeypatch.setattr(
        "backend.app.services.i5.runtime_knowledge_retrieval.retrieve_knowledge_context",
        _retrieve,
    )
    monkeypatch.setattr(
        "backend.app.core.conversation.prompts.resolve_openai_chat_model",
        lambda: "test-model",
    )
    monkeypatch.setattr(
        "backend.app.core.conversation.prompts.create_primary_chat_response",
        lambda messages: MagicMock(output_text="listening reply"),
    )

    brain = ConversationBrain(db, language="en")
    out = brain.process_message(
        user.id,
        "I feel overwhelmed and just need to talk",
        use_structured_context=True,
        structured_context_projection="[STRUCTURED_CONTEXT]",
        use_intelligence_safety=True,
        allow_governed_knowledge=False,
    )
    assert out.get("message")
    assert calls["retrieve"] == 0


def test_no_duplicate_retrieve_in_source_wiring():
    """Guard: structured helper calls retrieve once; orchestrator does not import a second path."""
    import inspect

    from backend.app.core.conversation import brain as brain_mod
    from backend.app.services.intelligence import orchestrator as orch_mod

    src = inspect.getsource(brain_mod._maybe_append_structured_governed_knowledge)
    assert src.count("retrieve_knowledge_context(") == 1
    assert "build_care_context" not in src
    assert "local_rag" not in src.lower()
    assert "stage17" not in src.lower()
    orch_src = inspect.getsource(orch_mod.allow_governed_knowledge_decision)
    assert "retrieve_knowledge_context" not in orch_src
