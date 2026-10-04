"""Q3.2 — Personalization-readiness coordination via existing I2/I3/NBQ/I4/I6–I8.

READ-ONLY / TEST-FIRST. No new readiness engine. No production patches in this gate.
"""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import inspect
from unittest.mock import MagicMock, patch

from backend.app import models
from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import list_facts, write_fact
from backend.app.services.intelligence.adaptive_interaction import (
    REASON_RESPONSE_LENGTH_BRIEF,
    resolve_adaptive_interaction,
)
from backend.app.services.intelligence.adapters import LifestyleContextAdapter
from backend.app.services.intelligence.assembler import AuthorizedContextAssembler
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
    StageName,
)
from backend.app.services.intelligence.missing_information import (
    evaluate_readiness,
    requirements_for,
)
from backend.app.services.intelligence.next_best_question import select_next_best_question
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.app.services.intelligence.psychological_interaction import (
    InteractionNeed,
    append_discovery_question,
    classify_interaction_need,
)
from backend.app.services.intelligence.intent_registry import resolve_intent


# ---- helpers ----


def _item(
    key: str,
    value="x",
    *,
    owner: int = 1,
    may_send: bool = True,
    sensitivity: str = "medium",
    epistemic: str | None = "USER_STATED",
    consent: str = "legacy_scope",
) -> ContextItem:
    return ContextItem(
        canonical_key=key,
        section="profile",
        source=ContextSource.PROFILE,
        structured_value=value,
        display_text=f"{key.split('.', 1)[-1]}={value}",
        provenance=ContextProvenance(
            source=ContextSource.PROFILE, owner_user_id=owner, query_label="t"
        ),
        observed_at=None,
        freshness="unknown",
        sensitivity=sensitivity,  # type: ignore[arg-type]
        consent=consent,  # type: ignore[arg-type]
        may_send_to_llm=may_send,
        sort_rank=SOURCE_SORT_RANK[ContextSource.PROFILE],
        active=True,
        conflicted=False,
        epistemic_class=epistemic,
    )


def _snap(items=None, owner: int = 1) -> ContextSnapshot:
    items = list(items or [])
    return ContextSnapshot(
        request_id="q32",
        owner_user_id=owner,
        sections={"profile": ContextSection(name="profile", items=items)},
        items=items,
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("profile",),
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


def _ready(intent: IntentResult) -> ReadinessResult:
    return ReadinessResult(
        status=ReadinessStatus.READY,
        intent_id=intent.intent_id,
        request_kind=intent.request_kind,
        outcomes=(),
        missing_fact_keys=(),
        clarification=None,
    )


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.flush()
    return row


class StubAsm:
    def __init__(self, snapshot=None, projection_text="[STRUCTURED_CONTEXT]\n- interests=hiking"):
        self.snapshot = snapshot or _snap()
        self.projection_text = projection_text
        self.assemble_calls = 0

    def assemble(self, *a, **k):
        self.assemble_calls += 1
        return self.snapshot

    def build_compatibility_projection(self, snapshot):
        return MagicMock(
            text=self.projection_text,
            preferred_name=None,
            truncated=False,
        )


def _orch(
    *,
    snapshot=None,
    gen=None,
    calls=None,
    readiness=None,
    intent=None,
    safety=None,
    validate=None,
    assembler=None,
):
    calls = calls if calls is not None else {"n": 0, "kwargs": [], "messages": []}

    def _gen(uid, msg, name=None, **kw):
        calls["n"] += 1
        calls["kwargs"].append(dict(kw))
        calls["messages"].append(msg)
        return {"message": "Primary helpful answer.", "language": "en"}

    gen = gen or _gen
    intent = intent or _intent()
    readiness = readiness or _ready(intent)
    validate = validate or (
        lambda **k: PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.SAFE,
            violation_code=None,
            message=k["text"],
        )
    )
    safety = safety or (
        lambda **k: RiskAssessment(
            registry_version="t",
            level=RiskLevel.NONE,
            action=SafetyAction.CONTINUE,
            domain=RiskDomain.NONE,
            rule_id="none",
            language="en",
        )
    )
    return (
        IntelligenceOrchestrator(
            db=MagicMock(),
            legacy_generator=gen,
            structured_mode=True,
            context_assembler=assembler or StubAsm(snapshot),
            intent_resolver=lambda **k: intent,
            missing_information_engine=lambda **k: readiness,
            safety_assessor=safety,
            safety_validator=validate,
            safety_response_builder=lambda a: MagicMock(localized_message="SAFETY"),
        ),
        calls,
    )


# ---- stage / coordination order ----


def test_q32_stage_order_i4_then_i2_then_i3_before_generation():
    names = [s.value for s in STAGE_ORDER]
    assert names.index(StageName.ASSESS_SAFETY_RISK.value) < names.index(
        StageName.ASSEMBLE_AUTHORIZED_CONTEXT.value
    )
    assert names.index(StageName.ASSEMBLE_AUTHORIZED_CONTEXT.value) < names.index(
        StageName.RESOLVE_INTENT.value
    )
    assert names.index(StageName.RESOLVE_INTENT.value) < names.index(
        StageName.EVALUATE_INFORMATION_READINESS.value
    )
    assert names.index(StageName.EVALUATE_INFORMATION_READINESS.value) < names.index(
        StageName.GENERATE_WITH_LEGACY_BRAIN.value
    )


def test_q32_orchestrator_records_i2_before_i3_on_success(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )
    orch, _calls = _orch(snapshot=_snap())
    result = orch.process(authenticated_user_id=1, message="Hello", language="en")
    stages = list(result.stage_names)
    assert stages.index("assemble_authorized_context") < stages.index("resolve_intent")
    assert stages.index("evaluate_information_readiness") < stages.index(
        "generate_with_legacy_brain"
    )


# ---- A/B hard readiness before personalized plan generation ----


def test_q32_nutrition_personalized_missing_hard_clarification_skips_generator(
    monkeypatch,
):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    intent = resolve_intent(
        message="Create a personal meal plan for me",
        language="en",
        has_verified_notification_origin=False,
    )
    assert intent.intent_id is IntentId.NUTRITION
    assert intent.request_kind is RequestKind.PERSONALIZED_PLAN
    assert requirements_for(intent)

    empty = _snap([])
    readiness = evaluate_readiness(
        snapshot=empty,
        intent=intent,
        authenticated_user_id=1,
        language="en",
        message="Create a personal meal plan for me",
    )
    assert readiness.status is ReadinessStatus.NEEDS_CLARIFICATION
    assert readiness.clarification is not None
    assert readiness.clarification.localized_message
    assert readiness.missing_fact_keys

    # NBQ must not invent soft discovery while hard readiness blocks.
    assert (
        select_next_best_question(
            snapshot=empty,
            intent=intent,
            readiness=readiness,
            language="en",
            message="Create a personal meal plan for me",
        )
        is None
    )

    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "GENERIC PLAN SHOULD NOT RUN", "language": "en"}

    orch, _ = _orch(
        snapshot=empty,
        gen=gen,
        intent=intent,
        readiness=readiness,
        calls=calls,
    )
    result = orch.process(
        authenticated_user_id=1,
        message="Create a personal meal plan for me",
        language="en",
    )
    assert calls["n"] == 0
    assert result.message == readiness.clarification.localized_message
    assert ReasonCode.GENERATOR_SKIPPED_FOR_CLARIFICATION.value in result.reason_codes
    assert "?" in result.message
    assert result.message.count("?") == 1


def test_q32_activity_personalized_missing_hard_clarification_skips_generator(
    monkeypatch,
):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    intent = resolve_intent(
        message="Create a personal exercise plan for me",
        language="en",
        has_verified_notification_origin=False,
    )
    assert intent.intent_id is IntentId.ACTIVITY
    assert intent.request_kind is RequestKind.PERSONALIZED_PLAN

    empty = _snap([])
    readiness = evaluate_readiness(
        snapshot=empty,
        intent=intent,
        authenticated_user_id=1,
        language="en",
        message="Create a personal exercise plan for me",
    )
    assert readiness.status is ReadinessStatus.NEEDS_CLARIFICATION
    assert readiness.clarification is not None

    assert (
        select_next_best_question(
            snapshot=empty,
            intent=intent,
            readiness=readiness,
            language="en",
            message="Create a personal exercise plan for me",
        )
        is None
    )

    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "GENERIC ACTIVITY PLAN", "language": "en"}

    orch, _ = _orch(
        snapshot=empty, gen=gen, intent=intent, readiness=readiness, calls=calls
    )
    result = orch.process(
        authenticated_user_id=1,
        message="Create a personal exercise plan for me",
        language="en",
    )
    assert calls["n"] == 0
    assert result.message == readiness.clarification.localized_message
    assert ReasonCode.GENERATOR_SKIPPED_FOR_CLARIFICATION.value in result.reason_codes


# ---- C known context reused via I2 projection ----


def test_q32_known_context_reused_in_i2_projection(db):
    user = _user(db, "q32-known")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(
        db, user.id, "preferences", "interests", "hiking",
        provenance_class="USER_STATED", commit=True,
    )
    write_fact(
        db, user.id, "work", "occupation", "designer",
        provenance_class="USER_STATED", commit=True,
    )
    write_fact(
        db, user.id, "work", "work_schedule", "day shift",
        provenance_class="USER_STATED", commit=True,
    )
    write_fact(
        db, user.id, "barriers", "time_constraints", "limited time",
        provenance_class="USER_STATED", sensitivity_class="standard", commit=True,
    )
    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    proj = AuthorizedContextAssembler().build_compatibility_projection(
        ContextSnapshot(
            request_id="q32-known",
            owner_user_id=user.id,
            sections={"lifestyle": ContextSection(name="lifestyle", items=items)},
            items=items,
            preferred_name=None,
            conflict_count=0,
            truncated_count=0,
            reason_codes=(),
            adapter_order=("lifestyle",),
        )
    )
    assert "hiking" in proj.text
    assert "designer" in proj.text
    assert "day shift" in proj.text
    assert "limited time" in proj.text


# ---- D known fact not re-asked ----


def test_q32_known_fact_not_reasked():
    intent = _intent(IntentId.GENERAL)
    d = select_next_best_question(
        snapshot=_snap([_item("preferences.interests", "hiking")]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="What should I do this weekend?",
    )
    assert d is None or d.target_key != "preferences.interests"


# ---- E Soft missing: answer first, at most one NBQ ----


def test_q32_soft_missing_answer_first_one_nbq(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    intent = _intent(IntentId.GENERAL)
    empty = _snap([])
    directive = select_next_best_question(
        snapshot=empty,
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="Hello",
    )
    assert directive is not None
    assert directive.target_key == "preferences.interests"

    orch, calls = _orch(snapshot=empty, intent=intent)
    result = orch.process(authenticated_user_id=1, message="Hello", language="en")
    assert calls["n"] == 1
    # Primary answer first; exactly one discovery question appended by system.
    assert result.message.startswith("Primary helpful answer.")
    assert directive.localized_question in result.message
    assert result.message.count("?") == 1
    # Guidance forbids LLM inventing an extra discovery ask when NBQ scheduled.
    guidance = calls["kwargs"][0].get("relationship_guidance") or ""
    assert "Do not ask an additional discovery" in guidance


def test_q32_append_discovery_helper_is_answer_then_one_question():
    text = append_discovery_question("Here is help.", "What are your interests?")
    assert text.startswith("Here is help.")
    assert text.endswith("What are your interests?")
    assert text.count("?") == 1


# ---- F General factual: no hard forced profiling ----


def test_q32_general_factual_no_hard_clarification_generator_runs(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )
    intent = _intent(IntentId.GENERAL, RequestKind.INFORMATIONAL)
    # Informational GENERAL has no hard I3 requirements.
    assert requirements_for(intent) == ()
    readiness = evaluate_readiness(
        snapshot=_snap([]),
        intent=intent,
        authenticated_user_id=1,
        language="en",
        message="What is vitamin D used for in the body?",
    )
    assert readiness.status is ReadinessStatus.READY
    assert readiness.clarification is None

    orch, calls = _orch(snapshot=_snap([]), intent=intent, readiness=readiness)
    result = orch.process(
        authenticated_user_id=1,
        message="What is vitamin D used for in the body?",
        language="en",
    )
    assert calls["n"] == 1
    assert ReasonCode.GENERATOR_SKIPPED_FOR_CLARIFICATION.value not in result.reason_codes
    # With fatigue closed, no soft append either — answer-only for this turn.
    assert result.message == "Primary helpful answer."


# ---- G BE_HEARD precedence ----


def test_q32_be_heard_suppresses_visible_nbq(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    msg = "I feel overwhelmed and just need to talk"
    need = classify_interaction_need(
        message=msg, intent=_intent(), language="en"
    )
    assert need is InteractionNeed.BE_HEARD

    orch, calls = _orch(snapshot=_snap([]))
    result = orch.process(authenticated_user_id=1, message=msg, language="en")
    assert calls["n"] == 1
    assert result.message == "Primary helpful answer."
    guidance = calls["kwargs"][0].get("relationship_guidance") or ""
    assert "BE_HEARD" in guidance


# ---- H I4 safety precedence ----


def test_q32_i4_terminal_skips_assemble_and_generator(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    asm = StubAsm(_snap())

    def emergency(**_k):
        return RiskAssessment(
            registry_version="t",
            level=RiskLevel.EMERGENCY,
            action=SafetyAction.RETURN_EMERGENCY_RESPONSE,
            domain=RiskDomain.MEDICAL_EMERGENCY,
            rule_id="emergency",
            language="en",
        )

    orch, calls = _orch(
        assembler=asm,
        safety=emergency,
        calls={"n": 0, "kwargs": [], "messages": []},
    )
    # Builder path uses safety_response_builder
    result = orch.process(
        authenticated_user_id=1,
        message="I am having severe chest pain right now",
        language="en",
    )
    assert calls["n"] == 0
    assert asm.assemble_calls == 0
    assert result.message == "SAFETY"
    stages = list(result.stage_names)
    assert "assess_safety_risk" in stages
    # Assembly skipped on terminal safety.
    assert any(
        s == "assemble_authorized_context" for s in stages
    )  # recorded as skipped
    idx = stages.index("assemble_authorized_context")
    # Still before generate; generate skipped.
    assert "generate_with_legacy_brain" in stages


# ---- I Adaptive path reused (not profile dump) ----


def test_q32_adaptive_path_not_profile_dump(db):
    user = _user(db, "q32-adapt")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(
        db, user.id, "preferences", "response_length", "brief",
        provenance_class="USER_STATED", commit=True,
    )
    write_fact(
        db, user.id, "preferences", "listen_before_advice", True,
        provenance_class="USER_CONFIRMED", commit=True,
    )
    write_fact(
        db, user.id, "preferences", "interests", "hiking",
        provenance_class="USER_STATED", commit=True,
    )
    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    snap = ContextSnapshot(
        request_id="q32-adapt",
        owner_user_id=user.id,
        sections={"profile": ContextSection(name="profile", items=items)},
        items=items,
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("lifestyle",),
    )
    adaptive = resolve_adaptive_interaction(snap)
    assert adaptive.response_length == "brief"
    assert adaptive.listen_before_advice is True
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "response_length" not in proj.text
    assert "listen_before_advice" not in proj.text
    assert "hiking" in proj.text
    guidance = PersonaPolicyV1.relationship_guidance_block(
        "general",
        "en",
        response_length=adaptive.response_length,
        listen_before_advice=adaptive.listen_before_advice,
    )
    assert "concise" in guidance.lower()
    assert REASON_RESPONSE_LENGTH_BRIEF in adaptive.reason_codes


# ---- J Ownership seams (no parallel engines) ----


def test_q32_ownership_boundaries_no_parallel_engine():
    # I3 readiness / NBQ / adaptive are functions — not a PersonalizationReadiness class.
    import backend.app.services.intelligence.missing_information as mi
    import backend.app.services.intelligence.next_best_question as nbq
    import backend.app.services.intelligence.adaptive_interaction as adapt

    assert hasattr(mi, "evaluate_readiness")
    assert hasattr(nbq, "select_next_best_question")
    assert hasattr(adapt, "resolve_adaptive_interaction")
    assert not hasattr(mi, "PersonalizationReadiness")
    assert not hasattr(nbq, "PersonalizationReadiness")

    orch_src = inspect.getsource(IntelligenceOrchestrator.process)
    assert "PersonalizationReadiness" not in orch_src
    assert "select_next_best_question" in orch_src
    assert "resolve_adaptive_interaction" in orch_src
    assert "evaluate_readiness" in orch_src or "_missing_information_engine" in orch_src

    # I8 nutrition/exercise primary paths remain I8-owned after READY.
    assert "execute_primary_nutrition_action" in orch_src
    assert "execute_primary_exercise_action" in orch_src
    # Reminder/follow-up stays request-local; I10 scheduler consumes reminder fields.
    assert "I10" in orch_src or "reminder" in orch_src.lower()


def test_q32_i6_fact_ownership_not_duplicated_by_assemble(db):
    user = _user(db, "q32-own")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(
        db, user.id, "preferences", "interests", "hiking",
        provenance_class="USER_STATED", commit=True,
    )
    before = len(list(list_facts(db, user.id)))
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        AuthorizedContextAssembler().assemble(
            db, authenticated_user_id=user.id, request_id="q32-own"
        )
    assert len(list(list_facts(db, user.id))) == before


def test_q32_i7_derived_flags_not_canonical_i6():
    from backend.app.services.i7.derived_continuity import parse_bounded_continuity
    from backend.app import models as m

    row = MagicMock(spec=m.UserPeriodSummary)
    row.structured_summary_json = (
        '{"bounded_continuity":{"topic":"evening walk","not_i6_fact":true,'
        '"not_transcript":true,"not_i9":true}}'
    )
    bc = parse_bounded_continuity(row)
    assert bc.get("not_i6_fact") is True
    assert bc.get("not_transcript") is True


# ---- K max one system question ----


def test_q32_hard_and_soft_never_both_in_one_turn(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    intent = _intent(IntentId.NUTRITION, RequestKind.PERSONALIZED_PLAN)
    readiness = ReadinessResult(
        status=ReadinessStatus.NEEDS_CLARIFICATION,
        intent_id=intent.intent_id,
        request_kind=intent.request_kind,
        outcomes=(),
        missing_fact_keys=("lifestyle.goal",),
        clarification=ClarificationResult(
            question_id="i3.goal",
            target_key="lifestyle.goal.*",
            template_id="tpl.goal.v1",
            localized_message="What is your main nutrition goal right now?",
        ),
    )
    # Soft NBQ suppressed when not READY.
    assert (
        select_next_best_question(
            snapshot=_snap([]),
            intent=intent,
            readiness=readiness,
            language="en",
            message="Create a personal meal plan for me",
        )
        is None
    )
    orch, calls = _orch(
        snapshot=_snap([]),
        intent=intent,
        readiness=readiness,
        calls={"n": 0, "kwargs": [], "messages": []},
    )
    result = orch.process(
        authenticated_user_id=1,
        message="Create a personal meal plan for me",
        language="en",
    )
    assert calls["n"] == 0
    assert result.message.count("?") == 1
