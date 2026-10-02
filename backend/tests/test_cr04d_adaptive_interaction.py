"""CR-04D — Adaptive interaction from confirmed I6 preferences (single generator)."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from unittest.mock import MagicMock

import pytest

from backend.app import models
from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.intelligence.adaptive_interaction import (
    REASON_LISTEN_BEFORE_ADVICE,
    REASON_RESPONSE_LENGTH_BRIEF,
    REASON_RESPONSE_LENGTH_DETAILED,
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
)
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.app.services.intelligence.psychological_interaction import (
    InteractionNeed,
    classify_interaction_need,
)


# ---- helpers ----


def _intent(
    intent_id: IntentId = IntentId.GENERAL, kind: RequestKind = RequestKind.INFORMATIONAL
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


def _pref_item(
    key: str,
    value,
    *,
    epistemic: str | None = "USER_STATED",
    sensitivity: str = "medium",
    may_send: bool = False,
    active: bool = True,
    conflicted: bool = False,
    owner: int = 1,
    consent: str = "legacy_scope",
) -> ContextItem:
    return ContextItem(
        canonical_key=key,
        section="profile",
        source=ContextSource.PROFILE,
        structured_value=value,
        display_text=f"{key}={value}",
        provenance=ContextProvenance(
            source=ContextSource.PROFILE, owner_user_id=owner, query_label="t"
        ),
        observed_at=None,
        freshness="unknown",
        sensitivity=sensitivity,  # type: ignore[arg-type]
        consent=consent,  # type: ignore[arg-type]
        may_send_to_llm=may_send,
        sort_rank=SOURCE_SORT_RANK[ContextSource.PROFILE],
        active=active,
        conflicted=conflicted,
        epistemic_class=epistemic,
    )


def _snap(items=None, owner: int = 1) -> ContextSnapshot:
    items = list(items or [])
    return ContextSnapshot(
        request_id="cr04d",
        owner_user_id=owner,
        sections={"profile": ContextSection(name="profile", items=items)},
        items=items,
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(ReasonCode.CONTEXT_ASSEMBLED.value,),
        adapter_order=("profile",),
    )


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.flush()
    return row


class StubAsm:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or _snap()

    def assemble(self, *a, **k):
        return self.snapshot

    def build_compatibility_projection(self, snapshot):
        return MagicMock(text="[CTX]", preferred_name=None, truncated=False)


def _orch(*, snapshot=None, gen=None, calls=None, readiness=None, validate=None, intent=None):
    calls = calls if calls is not None else {"n": 0, "kwargs": []}

    def _gen(uid, msg, name=None, **kw):
        calls["n"] += 1
        calls["kwargs"].append(dict(kw))
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
    return (
        IntelligenceOrchestrator(
            db=MagicMock(),
            legacy_generator=gen,
            structured_mode=True,
            context_assembler=StubAsm(snapshot),
            intent_resolver=lambda **k: intent,
            missing_information_engine=lambda **k: readiness,
            safety_assessor=lambda **k: RiskAssessment(
                registry_version="t",
                level=RiskLevel.NONE,
                action=SafetyAction.CONTINUE,
                domain=RiskDomain.NONE,
                rule_id="none",
                language="en",
            ),
            safety_validator=validate,
            safety_response_builder=lambda a: MagicMock(localized_message="SAFETY"),
        ),
        calls,
    )


# ---- pure resolver ----


def test_cr04d_user_stated_brief_accepted():
    snap = _snap(
        [
            _pref_item(
                "preferences.response_length",
                '"brief"',
                epistemic="USER_STATED",
                may_send=False,
            )
        ]
    )
    result = resolve_adaptive_interaction(snap)
    assert result.response_length == "brief"
    assert REASON_RESPONSE_LENGTH_BRIEF in result.reason_codes
    assert result.listen_before_advice is False
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "response_length" not in proj.text
    assert "brief" not in proj.text


def test_cr04d_user_confirmed_detailed_accepted():
    snap = _snap(
        [
            _pref_item(
                "preferences.response_length",
                '"detailed"',
                epistemic="USER_CONFIRMED",
                may_send=False,
            )
        ]
    )
    result = resolve_adaptive_interaction(snap)
    assert result.response_length == "detailed"
    assert REASON_RESPONSE_LENGTH_DETAILED in result.reason_codes
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "response_length" not in proj.text
    assert "detailed" not in proj.text


def test_cr04d_user_stated_listen_true_accepted():
    snap = _snap(
        [
            _pref_item(
                "preferences.listen_before_advice",
                "true",
                epistemic="USER_STATED",
                may_send=False,
            )
        ]
    )
    result = resolve_adaptive_interaction(snap)
    assert result.listen_before_advice is True
    assert REASON_LISTEN_BEFORE_ADVICE in result.reason_codes
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "listen_before_advice" not in proj.text
    assert "true" not in proj.text.lower()


def test_cr04d_system_derived_ignored():
    snap = _snap(
        [
            _pref_item(
                "preferences.response_length",
                '"brief"',
                epistemic="SYSTEM_DERIVED",
                may_send=False,
            )
        ]
    )
    result = resolve_adaptive_interaction(snap)
    assert result.response_length is None
    assert result.reason_codes == ()
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "response_length" not in proj.text
    assert "brief" not in proj.text


def test_cr04d_unknown_provenance_ignored():
    snap = _snap(
        [
            _pref_item(
                "preferences.response_length",
                '"brief"',
                epistemic="UNKNOWN",
                may_send=False,
            ),
            _pref_item(
                "preferences.listen_before_advice",
                "true",
                epistemic=None,
                may_send=False,
            ),
        ]
    )
    result = resolve_adaptive_interaction(snap)
    assert result.response_length is None
    assert result.listen_before_advice is False
    assert result.reason_codes == ()
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "response_length" not in proj.text
    assert "listen_before_advice" not in proj.text
    assert "brief" not in proj.text


def test_cr04d_row_high_critical_ignored():
    snap = _snap(
        [
            _pref_item(
                "preferences.response_length",
                '"brief"',
                sensitivity="high",
                may_send=False,
            ),
            _pref_item(
                "preferences.listen_before_advice",
                "true",
                sensitivity="critical",
                may_send=False,
            ),
        ]
    )
    result = resolve_adaptive_interaction(snap)
    assert result.response_length is None
    assert result.listen_before_advice is False
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "response_length" not in proj.text
    assert "listen_before_advice" not in proj.text
    assert "brief" not in proj.text


def test_cr04d_unknown_response_length_ignored():
    snap = _snap(
        [
            _pref_item(
                "preferences.response_length",
                '"verbose"',
                epistemic="USER_STATED",
                may_send=False,
            )
        ]
    )
    assert resolve_adaptive_interaction(snap).response_length is None
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "response_length" not in proj.text
    assert "verbose" not in proj.text


def test_cr04d_listen_false_no_directive():
    for value in ("false", "False", "0", "no", "null"):
        snap = _snap(
            [
                _pref_item(
                    "preferences.listen_before_advice",
                    value,
                    epistemic="USER_STATED",
                    may_send=False,
                )
            ]
        )
        result = resolve_adaptive_interaction(snap)
        assert result.listen_before_advice is False
        assert REASON_LISTEN_BEFORE_ADVICE not in result.reason_codes


def test_cr04d_adaptive_only_raw_projection_blocked_with_non_adaptive_preserved(db):
    user = _user(db, "cr04d1-proj")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(
        db,
        user.id,
        "preferences",
        "response_length",
        "brief",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    write_fact(
        db,
        user.id,
        "preferences",
        "listen_before_advice",
        True,
        provenance_class="USER_CONFIRMED",
        sensitivity_class="standard",
        commit=True,
    )
    write_fact(
        db,
        user.id,
        "work",
        "occupation",
        "designer",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    by_key = {i.canonical_key: i for i in items}
    brief = by_key["preferences.response_length"]
    listen = by_key["preferences.listen_before_advice"]
    work = by_key["work.occupation"]

    assert brief.may_send_to_llm is False
    assert listen.may_send_to_llm is False
    assert work.may_send_to_llm is True

    snap = ContextSnapshot(
        request_id="cr04d1",
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
    assert "brief" not in proj.text.lower()
    assert "designer" in proj.text
    assert "occupation" in proj.text


# ---- I2 adapter projection ----


def test_cr04d_adapter_epistemic_and_row_sensitivity_fail_closed(db):
    user = _user(db, "cr04d-sens")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(
        db,
        user.id,
        "preferences",
        "response_length",
        "brief",
        provenance_class="USER_STATED",
        sensitivity_class="high",
        commit=True,
    )
    write_fact(
        db,
        user.id,
        "preferences",
        "listen_before_advice",
        True,
        provenance_class="USER_CONFIRMED",
        sensitivity_class="critical",
        commit=True,
    )
    write_fact(
        db,
        user.id,
        "social",
        "support_network",
        "friends nearby",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    by_key = {i.canonical_key: i for i in items}
    brief = by_key["preferences.response_length"]
    listen = by_key["preferences.listen_before_advice"]
    social = by_key["social.support_network"]

    assert brief.epistemic_class == "USER_STATED"
    assert brief.sensitivity == "high"
    assert brief.may_send_to_llm is False

    assert listen.epistemic_class == "USER_CONFIRMED"
    assert listen.sensitivity == "critical"
    assert listen.may_send_to_llm is False

    # Domain-high remains high even when row says standard.
    assert social.sensitivity == "high"
    assert social.may_send_to_llm is False
    assert social.epistemic_class == "USER_STATED"

    snap = _snap([brief, listen, social], owner=user.id)
    adaptive = resolve_adaptive_interaction(snap)
    assert adaptive.response_length is None
    assert adaptive.listen_before_advice is False
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "response_length" not in proj.text
    assert "listen_before_advice" not in proj.text
    assert "brief" not in proj.text


def test_cr04d_adapter_safe_prefs_adapt_without_raw_llm_projection(db):
    user = _user(db, "cr04d-ok")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(
        db,
        user.id,
        "preferences",
        "response_length",
        "detailed",
        provenance_class="USER_CONFIRMED",
        sensitivity_class="standard",
        commit=True,
    )
    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    pref = next(i for i in items if i.canonical_key == "preferences.response_length")
    assert pref.sensitivity == "medium"
    assert pref.may_send_to_llm is False
    assert pref.epistemic_class == "USER_CONFIRMED"
    snap = _snap([pref], owner=user.id)
    adaptive = resolve_adaptive_interaction(snap)
    assert adaptive.response_length == "detailed"
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "response_length" not in proj.text
    assert "detailed" not in proj.text


# ---- persona + need precedence ----


def test_cr04d_persona_brief_detailed_listen_change_guidance():
    base = PersonaPolicyV1.relationship_guidance_block("general", "en")
    brief = PersonaPolicyV1.relationship_guidance_block(
        "general", "en", response_length="brief"
    )
    detailed = PersonaPolicyV1.relationship_guidance_block(
        "general", "en", response_length="detailed"
    )
    listen = PersonaPolicyV1.relationship_guidance_block(
        "general", "en", listen_before_advice=True
    )
    assert "Current need: GENERAL" in brief
    assert brief.index("Current need:") < brief.lower().index("concise")
    assert "concise" in brief.lower()
    assert "useful detail" in detailed.lower()
    assert "acknowledge/listen" in listen.lower() or "acknowledge" in listen.lower()
    assert base != brief
    assert base != detailed
    assert base != listen
    # No preference leaves baseline unchanged.
    assert PersonaPolicyV1.relationship_guidance_block("general", "en") == base


def test_cr04d_current_need_remains_first_with_adaptive():
    block = PersonaPolicyV1.relationship_guidance_block(
        "decide",
        "en",
        response_length="brief",
        listen_before_advice=True,
    )
    lines = [ln for ln in block.splitlines() if ln.strip()]
    assert lines[0].startswith("[RELATIONSHIP_GUIDANCE]")
    assert "Current need: DECIDE" in lines[1]
    assert "concise" in block.lower()


# ---- orchestrator wiring ----


def test_cr04d_orchestrator_applies_brief_and_single_generator(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )
    snap = _snap(
        [
            _pref_item(
                "preferences.response_length",
                '"brief"',
                epistemic="USER_STATED",
            )
        ]
    )
    orch, calls = _orch(snapshot=snap)
    result = orch.process(
        authenticated_user_id=1, message="Tell me about sleep", language="en"
    )
    assert calls["n"] == 1
    guidance = calls["kwargs"][0].get("relationship_guidance") or ""
    assert "concise" in guidance.lower()
    assert "Current need:" in guidance
    assert REASON_RESPONSE_LENGTH_BRIEF in result.reason_codes
    # Safe reason codes only — never expose the raw preference value as a code.
    assert "brief" not in result.reason_codes
    assert all(not c.endswith("=brief") for c in result.reason_codes)


def test_cr04d_orchestrator_confirmed_detailed_and_listen(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )
    snap = _snap(
        [
            _pref_item(
                "preferences.response_length",
                '"detailed"',
                epistemic="USER_CONFIRMED",
            ),
            _pref_item(
                "preferences.listen_before_advice",
                "true",
                epistemic="USER_STATED",
            ),
        ]
    )
    orch, calls = _orch(snapshot=snap)
    result = orch.process(
        authenticated_user_id=1, message="Tell me about sleep", language="en"
    )
    assert calls["n"] == 1
    guidance = calls["kwargs"][0].get("relationship_guidance") or ""
    assert "useful detail" in guidance.lower()
    assert "acknowledge" in guidance.lower() or "listen" in guidance.lower()
    assert REASON_RESPONSE_LENGTH_DETAILED in result.reason_codes
    assert REASON_LISTEN_BEFORE_ADVICE in result.reason_codes


def test_cr04d_be_heard_still_works(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    snap = _snap(
        [
            _pref_item(
                "preferences.response_length",
                '"brief"',
                epistemic="USER_STATED",
            )
        ]
    )
    orch, calls = _orch(snapshot=snap)
    result = orch.process(
        authenticated_user_id=1,
        message="I feel overwhelmed and just need to talk",
        language="en",
    )
    assert calls["n"] == 1
    need = classify_interaction_need(
        message="I feel overwhelmed and just need to talk",
        intent=_intent(),
        language="en",
    )
    assert need is InteractionNeed.BE_HEARD
    guidance = calls["kwargs"][0].get("relationship_guidance") or ""
    assert "BE_HEARD" in guidance
    assert guidance.index("Current need: BE_HEARD") < guidance.lower().index("concise")
    # Visible NBQ append must not run for BE_HEARD (no discovery question suffix).
    assert result.message == "Primary helpful answer."


def test_cr04d_i4_terminal_unchanged(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )
    snap = _snap(
        [
            _pref_item(
                "preferences.response_length",
                '"brief"',
                epistemic="USER_STATED",
            )
        ]
    )

    def replace_validator(**k):
        return PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.REPLACED,
            violation_code="r",
            message="I4_REPLACEMENT_TEXT",
        )

    orch, calls = _orch(snapshot=snap, validate=replace_validator)
    result = orch.process(
        authenticated_user_id=1, message="Tell me about sleep", language="en"
    )
    assert calls["n"] == 1
    assert result.message == "I4_REPLACEMENT_TEXT"


def test_cr04d_clarification_path_skips_generator(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    intent = _intent(IntentId.SLEEP)
    readiness = ReadinessResult(
        status=ReadinessStatus.NEEDS_CLARIFICATION,
        intent_id=intent.intent_id,
        request_kind=intent.request_kind,
        outcomes=(),
        missing_fact_keys=("routines.bedtime",),
        clarification=ClarificationResult(
            question_id="i3.q",
            target_key="routines.bedtime",
            template_id="tpl.bedtime.v1",
            localized_message="What time do you usually go to bed?",
        ),
    )
    snap = _snap(
        [
            _pref_item(
                "preferences.response_length",
                '"brief"',
                epistemic="USER_STATED",
            )
        ]
    )
    orch, calls = _orch(snapshot=snap, readiness=readiness, intent=intent)
    result = orch.process(
        authenticated_user_id=1, message="Help with sleep", language="en"
    )
    assert calls["n"] == 0
    assert result.message == "What time do you usually go to bed?"
    assert REASON_RESPONSE_LENGTH_BRIEF not in result.reason_codes


def test_cr04d_specialized_nutrition_path_skips_generator(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )

    class _NutritionResult:
        user_message = "NUTRITION_PRIMARY"
        status = "READY"
        grounded = True
        fail_safe = False
        action_id = 7

    monkeypatch.setattr(
        "backend.app.services.i8.nutrition_primary_path.execute_primary_nutrition_action",
        lambda *a, **k: _NutritionResult(),
    )
    intent = _intent(IntentId.NUTRITION)
    snap = _snap(
        [
            _pref_item(
                "preferences.response_length",
                '"brief"',
                epistemic="USER_STATED",
            )
        ]
    )
    orch, calls = _orch(snapshot=snap, intent=intent)
    result = orch.process(
        authenticated_user_id=1, message="Create a meal plan", language="en"
    )
    assert calls["n"] == 0
    assert result.message == "NUTRITION_PRIMARY"
    assert "NUTRITION_PRIMARY_PATH" in result.reason_codes
    assert REASON_RESPONSE_LENGTH_BRIEF not in result.reason_codes


def test_cr04d_stage_order_unchanged():
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


def test_cr04d_no_preference_guidance_unchanged(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: None,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )
    baseline = PersonaPolicyV1.relationship_guidance_block("general", "en")
    orch, calls = _orch(snapshot=_snap())
    orch.process(authenticated_user_id=1, message="Hello", language="en")
    assert calls["n"] == 1
    guidance = calls["kwargs"][0].get("relationship_guidance") or ""
    # Need may be general for Hello; adaptive lines absent.
    assert "concise" not in guidance.lower()
    assert "useful detail" not in guidance.lower()
    assert "Response length preference" not in guidance
    assert "Interaction preference" not in guidance
    assert "Current need:" in guidance
    assert baseline.splitlines()[0] in guidance


# ---- regression ----


def test_cr04d_cr04a_b_c_regression_smoke():
    from backend.tests.test_cr04a_multilingual_semantic_quality import (
        _cases,
        _load_corpus,
        test_cr04a_corpus_schema,
        test_cr04a_semantic_contract,
    )
    from backend.tests import test_cr04b_contextual_user_understanding as cr04b
    from backend.tests import test_cr04c_i7_longitudinal_understanding as cr04c
    from backend.app.services.intelligence.next_best_question import (
        select_next_best_question,
    )

    corpus = _load_corpus()
    test_cr04a_corpus_schema(corpus)
    for case in _cases()[:3]:
        test_cr04a_semantic_contract(case)

    intent = cr04b._intent(IntentId.GENERAL)
    d = select_next_best_question(
        snapshot=cr04b._snap([]),
        intent=intent,
        readiness=cr04b._ready(intent),
        language="en",
        message="My night shifts are making sleep difficult",
    )
    assert d is not None
    assert d.target_key == "work.work_schedule"

    cr04c.test_cr04c_no_runtime_wiring_in_orchestrator_or_i8()
    from backend.app.services.intelligence import orchestrator as orch_mod
    import inspect

    orch_src = inspect.getsource(orch_mod)
    assert "rebuild_lifelong_profile" not in orch_src
    assert "resolve_adaptive_interaction" in orch_src
