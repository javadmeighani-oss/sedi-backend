"""CR-03 — Relationship discovery binding, conflict staging, I7 invalidation, history parity."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app import models
from backend.app.services.candidate_promotion_service import LIFESTYLE_SCALAR_MAP
from backend.app.services.i6.consent_service import PERM_READ, PERM_WRITE, grant_memory_consent
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.i6.relationship_discovery import (
    SUPPORTED_TARGETS,
    consume_relationship_discovery_marker,
    normalize_discovery_value,
    process_relationship_discovery_answer,
)
from backend.app.services.i7.governed_raw import (
    build_idempotency_key,
    finalize_durable_raw_response,
    try_durable_raw_write,
)
from backend.app.services.intelligence.contracts import (
    STAGE_ORDER,
    PostGenerationSafetyResult,
    PostGenerationSafetyStatus,
    RiskAssessment,
    RiskDomain,
    RiskLevel,
    SafetyAction,
)
from backend.app.services.intelligence.next_best_question import select_next_best_question
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.app.services.knowledge.kc_fatigue_policy import mark_asked
from backend.app.services.knowledge.service import accept_candidate, reject_candidate
from backend.app.services.intelligence.context_types import (
    ContextSection,
    ContextSnapshot,
)
from backend.app.services.intelligence.contracts import (
    IntentConfidenceBand,
    IntentId,
    IntentResult,
    ReadinessResult,
    ReadinessStatus,
    ReasonCode,
    RequestKind,
)


def _user(db, name: str = "cr03") -> models.User:
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


def _intent(iid: IntentId = IntentId.GENERAL) -> IntentResult:
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


def _snap() -> ContextSnapshot:
    return ContextSnapshot(
        request_id="cr03",
        owner_user_id=1,
        sections={"lifestyle": ContextSection(name="lifestyle", items=[])},
        items=[],
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(ReasonCode.CONTEXT_ASSEMBLED.value,),
        adapter_order=("lifestyle",),
    )


def _safe() -> RiskAssessment:
    return RiskAssessment(
        registry_version="t",
        level=RiskLevel.NONE,
        action=SafetyAction.CONTINUE,
        domain=RiskDomain.NONE,
        rule_id="none",
        language="en",
    )


# ---- A) discovery binding ----


def test_cr03_general_nbq_targets_response_length():
    g = _intent(IntentId.GENERAL)
    d = select_next_best_question(
        snapshot=_snap(), intent=g, readiness=_ready(g), language="en"
    )
    assert d is not None
    # CR-04F.1: GENERAL progressive Tier-A starts with interests.
    assert d.target_key == "preferences.interests"
    assert "interaction_style" not in d.target_key
    assert d.question_id == "nbq.q.general.preferences.interests.v1"


def test_cr03_supported_answer_writes_i6_user_stated(db):
    user = _user(db, "bind-ok")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "routines.bedtime")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="I usually go to bed at 11:00 pm",
        language="en",
        allow_binding=True,
    )
    fact = _active(db, user.id, "routines", "bedtime")
    assert fact is not None
    assert fact.provenance_class == "USER_STATED"
    assert fact.source == "relationship_discovery"
    assert "11" in json.loads(fact.value_json)
    state = (
        db.query(models.KcQuestionPolicyState)
        .filter_by(user_id=user.id)
        .first()
    )
    assert state is not None
    assert state.last_question_type is None


def test_cr03_response_length_normalization(db):
    user = _user(db, "rl")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "preferences.response_length")
    process_relationship_discovery_answer(
        db, user_id=user.id, message="brief please", language="en", allow_binding=True
    )
    fact = _active(db, user.id, "preferences", "response_length")
    assert fact is not None
    assert json.loads(fact.value_json) == "brief"


def test_cr03_no_consent_no_write_marker_consumed(db):
    user = _user(db, "nocon")
    _set_marker(db, user.id, "lifestyle.food_habits")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="I mostly eat vegetarian meals",
        language="en",
        allow_binding=True,
    )
    assert _active(db, user.id, "lifestyle", "food_habits") is None
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() == 0
    state = db.query(models.KcQuestionPolicyState).filter_by(user_id=user.id).first()
    assert state.last_question_type is None


def test_cr03_unsupported_target_no_write(db):
    user = _user(db, "unsup")
    grant_memory_consent(db, user.id, commit=True)
    assert "social.support_network" not in SUPPORTED_TARGETS
    _set_marker(db, user.id, "social.support_network")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="I live with my partner and two kids",
        language="en",
        allow_binding=True,
    )
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() == 0
    state = db.query(models.KcQuestionPolicyState).filter_by(user_id=user.id).first()
    assert state.last_question_type is None


def test_cr03_skip_reject_no_write(db):
    user = _user(db, "skip")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.activity_level")
    process_relationship_discovery_answer(
        db, user_id=user.id, message="not now", language="en", allow_binding=True
    )
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() == 0
    state = db.query(models.KcQuestionPolicyState).filter_by(user_id=user.id).first()
    assert state.last_question_type is None
    assert state.consecutive_rejects >= 1


def test_cr03_marker_one_shot_later_turn_cannot_rebind(db):
    user = _user(db, "oneshot")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "routines.wake_time")
    process_relationship_discovery_answer(
        db, user_id=user.id, message="I wake at 7:00 am", language="en", allow_binding=True
    )
    assert _active(db, user.id, "routines", "wake_time") is not None
    # Unrelated later turn — no marker, cannot re-answer discovery.
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="actually I wake at 9:00 am",
        language="en",
        allow_binding=True,
    )
    fact = _active(db, user.id, "routines", "wake_time")
    assert "7" in json.loads(fact.value_json)
    assert db.query(models.KcFactCandidate).filter_by(user_id=user.id).count() == 0


def test_cr03_user_isolation(db):
    a = _user(db, "iso-a")
    b = _user(db, "iso-b")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    _set_marker(db, a.id, "lifestyle.sleep_quality")
    process_relationship_discovery_answer(
        db, user_id=a.id, message="My sleep has been restless", language="en", allow_binding=True
    )
    assert _active(db, a.id, "lifestyle", "sleep_quality") is not None
    assert _active(db, b.id, "lifestyle", "sleep_quality") is None
    assert db.query(models.UserMemoryFact).filter_by(user_id=b.id).count() == 0


# ---- B) conflict ----


def test_cr03_same_value_refresh_no_duplicate(db):
    user = _user(db, "same")
    grant_memory_consent(db, user.id, commit=True)
    first = write_fact(
        db,
        user.id,
        "routines",
        "bedtime",
        "11:00 pm",
        provenance_class="USER_STATED",
        source="relationship_discovery",
        commit=True,
    )
    _set_marker(db, user.id, "routines.bedtime")
    process_relationship_discovery_answer(
        db, user_id=user.id, message="11:00 pm", language="en", allow_binding=True
    )
    active = _active(db, user.id, "routines", "bedtime")
    assert active is not None
    assert active.id == first.id
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() == 1
    assert db.query(models.KcFactCandidate).filter_by(user_id=user.id).count() == 0


def test_cr03_different_value_stages_candidate_no_silent_overwrite(db):
    user = _user(db, "conflict")
    grant_memory_consent(db, user.id, commit=True)
    old = write_fact(
        db,
        user.id,
        "routines",
        "bedtime",
        "10:00 pm",
        provenance_class="USER_STATED",
        source="manual",
        commit=True,
    )
    _set_marker(db, user.id, "routines.bedtime")
    process_relationship_discovery_answer(
        db, user_id=user.id, message="I go to bed at 11:30 pm", language="en", allow_binding=True
    )
    still = _active(db, user.id, "routines", "bedtime")
    assert still is not None
    assert still.id == old.id
    assert json.loads(still.value_json) == "10:00 pm"
    cands = db.query(models.KcFactCandidate).filter_by(user_id=user.id).all()
    assert len(cands) == 1
    meta = json.loads(cands[0].metadata_json or "{}")
    assert meta.get("needs_confirmation") is True
    assert cands[0].status == "pending"
    assert cands[0].fact_type == "bedtime"


def test_cr03_confirm_candidate_frozen_promotes_i6_zero_kc_user_fact(db, monkeypatch):
    monkeypatch.delenv("SEDI_LEGACY_FACT_WRITES_ENABLED", raising=False)
    user = _user(db, "confirm")
    grant_memory_consent(db, user.id, commit=True)
    old = write_fact(
        db,
        user.id,
        "preferences",
        "response_length",
        "brief",
        provenance_class="USER_STATED",
        source="manual",
        commit=True,
    )
    assert "response_length" in LIFESTYLE_SCALAR_MAP
    from backend.app.services.knowledge.service import create_candidate

    cand = create_candidate(
        db,
        user_id=user.id,
        source="chat",
        fact_type="response_length",
        value_json=json.dumps({"value": "detailed"}),
        confidence=0.9,
        metadata_json=json.dumps({"needs_confirmation": True}),
    )
    before_kc = db.query(models.KcUserFact).count()
    out = accept_candidate(db, cand.id, verified_by="user")
    assert out is None
    assert db.query(models.KcUserFact).count() == before_kc
    db.refresh(cand)
    assert cand.status == "accepted"
    active = _active(db, user.id, "preferences", "response_length")
    assert active is not None
    assert active.id != old.id
    assert json.loads(active.value_json) == "detailed"
    assert active.provenance_class == "USER_CONFIRMED"
    db.refresh(old)
    assert old.fact_status == "superseded"


def test_cr03_reject_leaves_canonical_unchanged(db):
    user = _user(db, "rej")
    grant_memory_consent(db, user.id, commit=True)
    old = write_fact(
        db,
        user.id,
        "lifestyle",
        "activity_level",
        "moderate",
        commit=True,
    )
    from backend.app.services.knowledge.service import create_candidate

    cand = create_candidate(
        db,
        user_id=user.id,
        source="chat",
        fact_type="activity_level",
        value_json=json.dumps({"value": "high"}),
        confidence=0.9,
        metadata_json=json.dumps({"needs_confirmation": True}),
    )
    assert reject_candidate(db, cand.id) is True
    db.refresh(cand)
    assert cand.status == "rejected"
    still = _active(db, user.id, "lifestyle", "activity_level")
    assert still.id == old.id
    assert json.loads(still.value_json) == "moderate"


# ---- C) I7 invalidation ----


def test_cr03_new_fact_invalidates_i7(db):
    from backend.app.services.i7.lifelong_profile import rebuild_lifelong_profile

    user = _user(db, "i7new")
    grant_memory_consent(db, user.id, commit=True)
    # Seed a prior fact so a profile can be built, then write a brand-new key.
    write_fact(db, user.id, "lifestyle", "mood", "calm", commit=True)
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    assert profile.status == "active"
    write_fact(db, user.id, "lifestyle", "food_habits", "tea mornings", commit=True)
    db.refresh(profile)
    assert profile.status == "stale"


def test_cr03_correction_still_invalidates(db):
    from backend.app.services.i7.lifelong_profile import rebuild_lifelong_profile

    user = _user(db, "i7corr")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "food_habits", "tea", commit=True)
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "food_habits", "coffee", commit=True)
    db.refresh(profile)
    assert profile.status == "stale"


def test_cr03_same_value_refresh_no_i7_invalidation(db):
    from backend.app.services.i7.lifelong_profile import rebuild_lifelong_profile

    user = _user(db, "i7same")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "food_habits", "tea", commit=True)
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    assert profile.status == "active"
    write_fact(db, user.id, "lifestyle", "food_habits", "tea", commit=True)
    db.refresh(profile)
    assert profile.status == "active"


# ---- D) durable final response parity ----


def test_cr03_finalize_exact_response_and_auto_idempotency(db):
    user = _user(db, "fin")
    grant_memory_consent(db, user.id, permissions=(PERM_WRITE, PERM_READ), commit=True)
    written = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message="hi",
        sedi_response="RAW DRAFT",
        language="en",
        actor_user_id=user.id,
        commit=True,
    )
    assert written.durable and written.memory is not None
    mid = written.memory.id
    old_key = written.memory.idempotency_key
    assert old_key.startswith("auto:")
    final = "RAW DRAFT\n\nOptional: bedtime?"
    result = finalize_durable_raw_response(
        db,
        user_id=user.id,
        memory_id=mid,
        final_response=final,
        actor_user_id=user.id,
        commit=True,
    )
    assert result.reason == "FINALIZED"
    db.refresh(written.memory)
    assert written.memory.sedi_response == final
    expected = build_idempotency_key(
        user_id=user.id, user_message="hi", sedi_response=final, client_key=None
    )
    assert written.memory.idempotency_key == expected
    assert written.memory.idempotency_key != old_key
    assert db.query(models.Memory).filter_by(user_id=user.id).count() == 1
    prov = json.loads(written.memory.provenance_json or "{}")
    assert isinstance(prov.get("finalizations"), list)
    assert len(prov["finalizations"]) >= 1


def test_cr03_client_idempotency_preserved(db):
    user = _user(db, "clientk")
    grant_memory_consent(db, user.id, permissions=(PERM_WRITE, PERM_READ), commit=True)
    written = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message="hi",
        sedi_response="draft",
        language="en",
        actor_user_id=user.id,
        idempotency_key="abc123",
        commit=True,
    )
    assert written.memory.idempotency_key == "client:abc123"
    finalize_durable_raw_response(
        db,
        user_id=user.id,
        memory_id=written.memory.id,
        final_response="draft + nbq",
        actor_user_id=user.id,
        commit=True,
    )
    db.refresh(written.memory)
    assert written.memory.idempotency_key == "client:abc123"
    assert written.memory.sedi_response == "draft + nbq"


def test_cr03_finalize_cross_user_rejected(db):
    a = _user(db, "fin-a")
    b = _user(db, "fin-b")
    grant_memory_consent(db, a.id, permissions=(PERM_WRITE, PERM_READ), commit=True)
    written = try_durable_raw_write(
        db,
        user_id=a.id,
        user_message="hi",
        sedi_response="draft",
        language="en",
        actor_user_id=a.id,
        commit=True,
    )
    bad = finalize_durable_raw_response(
        db,
        user_id=b.id,
        memory_id=written.memory.id,
        final_response="hijack",
        actor_user_id=b.id,
        commit=True,
    )
    assert bad.reason == "NOT_FOUND_OR_NOT_OWNED"
    mismatch = finalize_durable_raw_response(
        db,
        user_id=a.id,
        memory_id=written.memory.id,
        final_response="hijack2",
        actor_user_id=b.id,
        commit=True,
    )
    assert mismatch.reason == "AUTH_IDENTITY_MISMATCH"
    db.refresh(written.memory)
    assert written.memory.sedi_response == "draft"


def test_cr03_no_consent_creates_no_raw_row(db):
    user = _user(db, "noraw")
    result = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message="hi",
        sedi_response="hello",
        language="en",
        actor_user_id=user.id,
        commit=True,
    )
    assert result.durable is False
    assert result.reason == "NO_CONSENT"
    assert db.query(models.Memory).filter_by(user_id=user.id).count() == 0


def test_cr03_orchestrator_final_response_parity_with_nbq_and_i4_replace(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )

    class StubAsm:
        def assemble(self, *a, **k):
            return _snap()

        def build_compatibility_projection(self, snapshot):
            return MagicMock(text="[CTX]", preferred_name=None, truncated=False)

    intent = _intent(IntentId.SLEEP)
    finalized = {}

    def gen(uid, msg, name=None, **kw):
        return {
            "message": "PRIMARY SLEEP ANSWER",
            "language": "en",
            "durable_memory_id": 99,
        }

    def finalize(db, *, user_id, memory_id, final_response, actor_user_id=None, commit=True):
        finalized["user_id"] = user_id
        finalized["memory_id"] = memory_id
        finalized["final_response"] = final_response
        return MagicMock(reason="FINALIZED")

    monkeypatch.setattr(
        "backend.app.services.i7.governed_raw.finalize_durable_raw_response",
        finalize,
    )

    orch = IntelligenceOrchestrator(
        db=MagicMock(),
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=lambda **k: intent,
        missing_information_engine=lambda **k: _ready(intent),
        safety_assessor=lambda **k: _safe(),
        safety_validator=lambda **k: PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.SAFE,
            violation_code=None,
            message=k["text"],
        ),
        safety_response_builder=lambda a: MagicMock(localized_message="SAFETY"),
    )
    result = orch.process(authenticated_user_id=1, message="sleep tips", language="en")
    pub = result.public_brain_dict()
    assert "durable_memory_id" not in pub
    assert "memory_id" not in pub
    assert finalized.get("memory_id") == 99
    assert finalized.get("final_response") == result.message
    assert "PRIMARY SLEEP ANSWER" in result.message
    # NBQ appended for SLEEP when fatigue permits
    assert result.message != "PRIMARY SLEEP ANSWER"
    assert finalized["final_response"] == result.message

    # I4 replacement path
    finalized.clear()

    def replace_validator(**k):
        return PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.REPLACED,
            violation_code="r",
            message="I4_REPLACEMENT_TEXT",
        )

    orch2 = IntelligenceOrchestrator(
        db=MagicMock(),
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=lambda **k: intent,
        missing_information_engine=lambda **k: _ready(intent),
        safety_assessor=lambda **k: _safe(),
        safety_validator=replace_validator,
        safety_response_builder=lambda a: MagicMock(localized_message="SAFETY"),
    )
    # Suppress NBQ so replacement is clean
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: False,
    )
    result2 = orch2.process(authenticated_user_id=1, message="sleep tips", language="en")
    assert result2.message == "I4_REPLACEMENT_TEXT"
    assert finalized.get("final_response") == "I4_REPLACEMENT_TEXT"


def test_cr03_stage_order_unchanged():
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


def test_cr03_normalize_never_unbounded():
    huge = "x" * 5000
    out = normalize_discovery_value("lifestyle.food_habits", huge)
    assert out is not None
    assert len(out) <= 200
    assert normalize_discovery_value("preferences.response_length", "maybe") is None
    assert normalize_discovery_value("preferences.response_length", "مفصل‌تر") == "detailed"
    assert normalize_discovery_value("preferences.response_length", "کوتاه") == "brief"
