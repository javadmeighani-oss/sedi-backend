"""CR-03.1 — Ownership, promotion success semantics, idempotency, fail-closed history, structured binding."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app import models
from backend.app.services.i6.consent_service import PERM_READ, PERM_WRITE, grant_memory_consent
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.i6.relationship_discovery import (
    process_relationship_discovery_answer,
)
from backend.app.services.i7.governed_raw import (
    build_idempotency_key,
    finalize_durable_raw_response,
    mark_durable_raw_ineligible,
    try_durable_raw_write,
)
from backend.app.services.i7.retention import is_raw_visible, query_eligible_raw
from backend.app.services.intelligence.contracts import STAGE_ORDER
from backend.app.services.knowledge.kc_fatigue_policy import mark_asked
from backend.app.services.knowledge.service import (
    apply_answer,
    create_candidate,
)


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


# ---- 1) Candidate ownership ----


def test_cr031_cross_user_confirm_yes_denied(db, monkeypatch):
    monkeypatch.delenv("SEDI_LEGACY_FACT_WRITES_ENABLED", raising=False)
    a = _user(db, "own-a")
    b = _user(db, "own-b")
    grant_memory_consent(db, b.id, commit=True)
    write_fact(db, b.id, "routines", "bedtime", "10:00 pm", commit=True)
    cand = create_candidate(
        db,
        user_id=b.id,
        source="chat",
        fact_type="bedtime",
        value_json=json.dumps({"value": "11:00 pm"}),
        confidence=0.9,
        metadata_json=json.dumps({"needs_confirmation": True}),
    )
    before_status = cand.status
    before_facts = db.query(models.UserMemoryFact).filter_by(user_id=b.id).count()
    before_kc = db.query(models.KcUserFact).count()

    result = apply_answer(
        db,
        user_id=a.id,
        candidate_id=cand.id,
        question_type="confirm_candidate",
        value="yes",
    )
    assert result.get("outcome") != "accepted"
    assert result.get("applied") == "confirm_skipped"
    db.refresh(cand)
    assert cand.status == before_status
    assert db.query(models.UserMemoryFact).filter_by(user_id=b.id).count() == before_facts
    assert _active(db, b.id, "routines", "bedtime") is not None
    assert json.loads(_active(db, b.id, "routines", "bedtime").value_json) == "10:00 pm"
    assert db.query(models.KcUserFact).count() == before_kc
    assert db.query(models.UserMemoryFact).filter_by(user_id=a.id).count() == 0


def test_cr031_cross_user_confirm_no_denied(db, monkeypatch):
    monkeypatch.delenv("SEDI_LEGACY_FACT_WRITES_ENABLED", raising=False)
    a = _user(db, "rej-a")
    b = _user(db, "rej-b")
    grant_memory_consent(db, b.id, commit=True)
    write_fact(db, b.id, "lifestyle", "activity_level", "moderate", commit=True)
    cand = create_candidate(
        db,
        user_id=b.id,
        source="chat",
        fact_type="activity_level",
        value_json=json.dumps({"value": "high"}),
        confidence=0.9,
        metadata_json=json.dumps({"needs_confirmation": True}),
    )
    result = apply_answer(
        db,
        user_id=a.id,
        candidate_id=cand.id,
        question_type="confirm_candidate",
        value="no",
    )
    assert result.get("outcome") != "rejected"
    assert result.get("applied") == "confirm_skipped"
    db.refresh(cand)
    assert cand.status == "pending"
    assert json.loads(_active(db, b.id, "lifestyle", "activity_level").value_json) == "moderate"


# ---- 2) Promotion success semantics ----


def test_cr031_successful_promotion_returns_accepted(db, monkeypatch):
    monkeypatch.delenv("SEDI_LEGACY_FACT_WRITES_ENABLED", raising=False)
    user = _user(db, "promo-ok")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "preferences", "response_length", "brief", commit=True)
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
    result = apply_answer(
        db,
        user_id=user.id,
        candidate_id=cand.id,
        question_type="confirm_candidate",
        value="yes",
    )
    assert result["outcome"] == "accepted"
    assert result["applied"] == "confirm_accepted"
    db.refresh(cand)
    assert cand.status == "accepted"
    assert json.loads(_active(db, user.id, "preferences", "response_length").value_json) == "detailed"
    assert db.query(models.KcUserFact).count() == before_kc


def test_cr031_no_consent_promotion_not_accepted(db, monkeypatch):
    monkeypatch.delenv("SEDI_LEGACY_FACT_WRITES_ENABLED", raising=False)
    user = _user(db, "promo-deny")
    # No memory consent — I6 promotion must skip; outcome must not be accepted.
    cand = create_candidate(
        db,
        user_id=user.id,
        source="chat",
        fact_type="bedtime",
        value_json=json.dumps({"value": "11:00 pm"}),
        confidence=0.9,
        metadata_json=json.dumps({"needs_confirmation": True}),
    )
    before_kc = db.query(models.KcUserFact).count()
    result = apply_answer(
        db,
        user_id=user.id,
        candidate_id=cand.id,
        question_type="confirm_candidate",
        value="yes",
    )
    assert result.get("outcome") != "accepted"
    assert result.get("applied") != "confirm_accepted"
    db.refresh(cand)
    assert cand.status == "pending"
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() == 0
    assert db.query(models.KcUserFact).count() == before_kc


# ---- 3) Auto-idempotency replay after finalize ----


def test_cr031_auto_idempotency_replay_after_finalize(db):
    user = _user(db, "idem")
    grant_memory_consent(db, user.id, permissions=(PERM_WRITE, PERM_READ), commit=True)
    draft = "DRAFT_PRIMARY"
    final = "DRAFT_PRIMARY\n\nOptional bedtime?"
    msg = "how is sleep?"

    first = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=msg,
        sedi_response=draft,
        language="en",
        actor_user_id=user.id,
        commit=True,
    )
    assert first.durable and first.memory is not None
    draft_key = first.memory.idempotency_key
    assert draft_key.startswith("auto:")
    mid = first.memory.id

    fin = finalize_durable_raw_response(
        db,
        user_id=user.id,
        memory_id=mid,
        final_response=final,
        actor_user_id=user.id,
        commit=True,
    )
    assert fin.reason == "FINALIZED"
    db.refresh(first.memory)
    assert first.memory.sedi_response == final
    expected_final_key = build_idempotency_key(
        user_id=user.id, user_message=msg, sedi_response=final, client_key=None
    )
    assert first.memory.idempotency_key == expected_final_key
    prov = json.loads(first.memory.provenance_json or "{}")
    assert prov.get("draft_idempotency_key") == draft_key

    # Replay same user_message + same draft — must hit canonical replay, no new row.
    replay = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=msg,
        sedi_response=draft,
        language="en",
        actor_user_id=user.id,
        commit=True,
    )
    assert replay.replayed is True
    assert replay.memory is not None
    assert replay.memory.id == mid
    assert db.query(models.Memory).filter_by(user_id=user.id).count() == 1

    # Re-finalize same final response — deterministic, no IntegrityError.
    fin2 = finalize_durable_raw_response(
        db,
        user_id=user.id,
        memory_id=mid,
        final_response=final,
        actor_user_id=user.id,
        commit=True,
    )
    assert fin2.reason == "FINALIZED"
    assert db.query(models.Memory).filter_by(user_id=user.id).count() == 1
    db.refresh(first.memory)
    assert first.memory.sedi_response == final
    # Session still usable
    assert db.query(models.User).filter_by(id=user.id).one().id == user.id


def test_cr031_finalize_key_collision_does_not_overwrite_history(db):
    user = _user(db, "collide")
    grant_memory_consent(db, user.id, permissions=(PERM_WRITE, PERM_READ), commit=True)
    # Historical turn already owns the final auto key.
    historical = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message="same question",
        sedi_response="FINAL_SHARED",
        language="en",
        actor_user_id=user.id,
        commit=True,
    )
    assert historical.durable
    hist_id = historical.memory.id
    hist_resp = historical.memory.sedi_response

    draft = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message="same question",
        sedi_response="DIFFERENT_DRAFT",
        language="en",
        actor_user_id=user.id,
        commit=True,
    )
    assert draft.durable
    draft_id = draft.memory.id
    assert draft_id != hist_id

    # Finalizing draft to FINAL_SHARED would collide with historical key.
    result = finalize_durable_raw_response(
        db,
        user_id=user.id,
        memory_id=draft_id,
        final_response="FINAL_SHARED",
        actor_user_id=user.id,
        commit=True,
    )
    assert result.reason == "FINALIZE_KEY_COLLISION"
    hist_row = db.query(models.Memory).filter_by(id=hist_id).one()
    assert hist_row.sedi_response == hist_resp
    assert hist_row.durable_write is True
    draft_row = db.query(models.Memory).filter_by(id=draft_id).one()
    assert draft_row.durable_write is False
    assert is_raw_visible(draft_row) is False
    eligible_ids = {r.id for r in query_eligible_raw(db, user.id)}
    assert draft_id not in eligible_ids
    assert hist_id in eligible_ids


# ---- 4) Finalization fail-closed ----


def test_cr031_finalizer_failure_marks_draft_ineligible(db):
    user = _user(db, "failfin")
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
    mid = written.memory.id
    assert mid in {r.id for r in query_eligible_raw(db, user.id)}

    marked = mark_durable_raw_ineligible(
        db,
        user_id=user.id,
        memory_id=mid,
        actor_user_id=user.id,
        reason="FINALIZE_ORCHESTRATOR_EXCEPTION",
        commit=True,
    )
    assert marked.reason == "MARKED_INELIGIBLE"
    db.refresh(written.memory)
    assert written.memory.durable_write is False
    assert is_raw_visible(written.memory) is False
    assert mid not in {r.id for r in query_eligible_raw(db, user.id)}
    assert db.query(models.Memory).filter_by(user_id=user.id).count() == 1
    # Session usable after mark
    assert db.execute  # noqa: B018 — session object present
    assert db.query(models.User).filter_by(id=user.id).one().name == "failfin"


def test_cr031_successful_finalize_parity(db):
    user = _user(db, "parity")
    grant_memory_consent(db, user.id, permissions=(PERM_WRITE, PERM_READ), commit=True)
    written = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message="hi",
        sedi_response="draft",
        language="en",
        actor_user_id=user.id,
        commit=True,
    )
    final = "draft\n\nWould you share bedtime?"
    fin = finalize_durable_raw_response(
        db,
        user_id=user.id,
        memory_id=written.memory.id,
        final_response=final,
        actor_user_id=user.id,
        commit=True,
    )
    assert fin.reason == "FINALIZED"
    db.refresh(written.memory)
    assert written.memory.sedi_response == final
    assert written.memory.id in {r.id for r in query_eligible_raw(db, user.id)}


# ---- 5) Structured-only binding + ambiguous ----


def test_cr031_structured_binding_writes(db):
    user = _user(db, "struct")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.food_habits")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="I mostly eat vegetarian meals",
        language="en",
        allow_binding=True,
    )
    fact = _active(db, user.id, "lifestyle", "food_habits")
    assert fact is not None
    assert "vegetarian" in json.loads(fact.value_json)


def test_cr031_compatibility_consumes_marker_no_bind(db):
    user = _user(db, "compat")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.food_habits")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="I mostly eat vegetarian meals",
        language="en",
        allow_binding=False,  # compatibility / caution / terminal
    )
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() == 0
    state = db.query(models.KcQuestionPolicyState).filter_by(user_id=user.id).first()
    assert state.last_question_type is None


@pytest.mark.parametrize(
    "message,language",
    [
        ("yes", "en"),
        ("yep", "en"),
        ("nope", "en"),
        ("unsure", "en"),
        ("don't know", "en"),
        ("بله", "fa"),
        ("آره", "fa"),
        ("نه", "fa"),
        ("نمی‌دانم", "fa"),
        ("نمیدونم", "fa"),
        ("نعم", "ar"),
        ("لا", "ar"),
        ("لا أعرف", "ar"),
        ("مش عارف", "ar"),
    ],
)
def test_cr031_ambiguous_open_text_no_fact(db, message, language):
    user = _user(db, f"amb-{hash(message) % 10000}")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.sleep_quality")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
    )
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() == 0
    assert db.query(models.KcFactCandidate).filter_by(user_id=user.id).count() == 0
    state = db.query(models.KcQuestionPolicyState).filter_by(user_id=user.id).first()
    assert state.last_question_type is None


def test_cr031_valid_answer_still_binds_once(db):
    user = _user(db, "valid-once")
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "lifestyle.activity_level")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="I walk about thirty minutes most days",
        language="en",
        allow_binding=True,
    )
    assert _active(db, user.id, "lifestyle", "activity_level") is not None
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="actually I run daily now",
        language="en",
        allow_binding=True,
    )
    fact = _active(db, user.id, "lifestyle", "activity_level")
    assert "thirty" in json.loads(fact.value_json)
    assert db.query(models.KcFactCandidate).filter_by(user_id=user.id).count() == 0


def test_cr031_stage_order_unchanged():
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


def test_cr031_orchestrator_structured_gate(monkeypatch):
    from backend.app.services.intelligence.orchestrator import (
        IntelligenceOrchestrator,
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
    from backend.app.services.intelligence.context_types import (
        ContextSection,
        ContextSnapshot,
    )

    calls = []

    def capture(db, *, user_id, message, language, allow_binding, classification=None):
        calls.append({"allow_binding": allow_binding, "message": message})
        return classification

    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._apply_discovery_fatigue_response",
        capture,
    )
    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.peek_relationship_discovery_marker",
        lambda db, uid: "routines.bedtime",
    )
    from backend.app.services.i6.relationship_discovery import (
        DiscoveryClassification,
        DiscoveryDisposition,
    )

    monkeypatch.setattr(
        "backend.app.services.i6.relationship_discovery.classify_discovery_reply",
        lambda target, message, language: DiscoveryClassification(
            DiscoveryDisposition.ANSWER,
            target_key=target,
            normalized_value="11:00 pm",
        ),
    )

    intent = IntentResult(
        registry_version="t",
        intent_id=IntentId.GENERAL,
        request_kind=RequestKind.INFORMATIONAL,
        confidence_band=IntentConfidenceBand.HIGH,
        rule_id="t",
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

    def _safe(**k):
        return RiskAssessment(
            registry_version="t",
            level=RiskLevel.NONE,
            action=SafetyAction.CONTINUE,
            domain=RiskDomain.NONE,
            rule_id="none",
            language="en",
        )

    orch_struct = IntelligenceOrchestrator(
        db=MagicMock(),
        legacy_generator=lambda *a, **k: {"message": "ok", "language": "en"},
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
        safety_assessor=_safe,
        safety_validator=lambda **k: PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.SAFE,
            violation_code=None,
            message=k["text"],
        ),
        safety_response_builder=lambda a: MagicMock(localized_message="S"),
    )
    orch_struct.process(authenticated_user_id=1, message="hello", language="en")
    assert calls and calls[-1]["allow_binding"] is True

    calls.clear()
    orch_compat = IntelligenceOrchestrator(
        db=MagicMock(),
        legacy_generator=lambda *a, **k: {"message": "ok", "language": "en"},
        structured_mode=False,
        context_assembler=StubAsm(),
        intent_resolver=lambda **k: intent,
        missing_information_engine=lambda **k: ReadinessResult(
            status=ReadinessStatus.READY,
            intent_id=intent.intent_id,
            request_kind=intent.request_kind,
            outcomes=(),
            missing_fact_keys=(),
        ),
        safety_assessor=_safe,
        safety_validator=lambda **k: PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.SAFE,
            violation_code=None,
            message=k["text"],
        ),
        safety_response_builder=lambda a: MagicMock(localized_message="S"),
    )
    orch_compat.process(authenticated_user_id=1, message="hello", language="en")
    assert calls and calls[-1]["allow_binding"] is False
