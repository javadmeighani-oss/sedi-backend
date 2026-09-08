"""G2 scenario-first integration — C01 + C04 identity/authority slice.

GATE=SEDI-V1-BE-FINALCERT-G2-C01-C04-I5-DIRECTORY-I7-I8-SCENARIO-PG16-REVALIDATION-01
SCENARIO=SEDI-V1-REAL-FAMILY-CARE-E2E-01

Does NOT add ledger cases. Proves cross-seam locks only.
C01 20/20 and C04 4/4 remain owned by their focused suites.

C04 ledger → existing suite mapping (no rename/split):
  C04-01 Consent_gated_personalization_terms ← case1 + case3
  C04-02 PERSONAL_not_GOVERNED_promotion ← case6 + case7 + case8
  C04-03 I7_cannot_mint_I8_actions ← case8 empty-knowledge block
  C04-04 Son_Account_native_I7_V1_only ← case4 + case5
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.services.i5 import care_navigation_directory as cnd
from backend.app.services.i5.care_navigation_directory import (
    CANONICAL_AUTHORITY,
    GOVERNED_DIRECTORY_PROVIDER,
    PERSONAL_PROVIDER_CONTEXT,
    STATUS_NO_VERIFIED,
    assert_no_ungoverned_provider_authority,
    refuse_synthetic_provider_after_zero_result,
    resolve_care_navigation,
)
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, RetrievedKnowledgeItem
from backend.app.services.i6.consent_service import grant_memory_consent, revoke_memory_consent
from backend.app.services.i8.context import load_trusted_context
from backend.app.services.i8.knowledge_bridge import build_personalization, compose_grounded_action
from backend.app.services.i8.unified_core import generate_operational_action
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.tests.helpers.i10_postgresql_harness import I10IsolatedPgDb, _REV_081
from backend.tests.helpers.stage_b_family_fixture import SCENARIO_ID, seed_stage_b_family


@pytest.fixture(scope="module")
def g2_pg_db_module():
    isolated = I10IsolatedPgDb.create(suffix="g2c01c04", revision=_REV_081)
    SessionLocal = isolated.session_factory()
    try:
        yield SessionLocal, isolated
    finally:
        isolated.close()


@pytest.fixture()
def db(g2_pg_db_module):
    SessionLocal, isolated = g2_pg_db_module
    connection = isolated.engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _profile_tz(db, user_id: int) -> None:
    if db.query(models.UserProfileCore).filter_by(user_id=user_id).first():
        return
    db.add(models.UserProfileCore(user_id=user_id, timezone="UTC"))
    db.flush()


def _insert_lifelong(db, user_id: int, *, habits=None, preferences=None, consent_id=None):
    now = datetime.now(timezone.utc)
    payload = {
        "authority": "I6_FACTS_ARE_SOT",
        "profile_is_derived_only": True,
        "not_diagnosis": True,
        "habits": habits or [],
        "preferences": preferences or [],
        "goals": [],
    }
    row = models.UserLifelongProfile(
        user_id=user_id,
        version=1,
        status="active",
        structured_profile_json=json.dumps(payload, sort_keys=True),
        narrative_compact="Derived compact profile; not source of truth.",
        source_fact_ids_json="[]",
        source_event_refs_json="[]",
        consent_id=consent_id,
        generator_version="i7-v1-lifelong-profile",
        built_from_period_start=now - timedelta(days=30),
        built_from_period_end=now,
    )
    db.add(row)
    db.flush()
    return row


def _doc_item():
    return {
        "entity_type": "DOCTOR",
        "id": 101,
        "canonical_directory_key": "irimc-doc-101",
        "full_name": "Dr Verified Neurologist",
        "specialty": "Neurology",
        "city": "Tehran",
        "province": "Tehran",
        "phone": "+982100000001",
        "address": "Verified St",
        "record_state": "ACTIVE",
        "source_system_label": "irimc_member_search",
        "last_verified_at": "2026-01-01T00:00:00",
        "last_observed_at": None,
        "endorsement_disclaimer": "Directory results are informational listings only.",
        "is_clinical_authority": False,
        "is_knowledge_unit": False,
    }


def _ok_item():
    return RetrievedKnowledgeItem(
        knowledge_unit_id=1,
        canonical_unit_id="KU-ROUTINE-1",
        immutable_version_id="v1",
        memory_item_id="m1",
        memory_row_id=1,
        source_profile_id=1,
        provenance_id=1,
        raw_evidence_id=None,
        domain="lifestyle",
        language="en",
        topic_taxonomy=None,
        normalized_statement="Keep a steady daily movement pattern",
        evidence_strength="MODERATE",
        freshness_state="fresh",
        conflict_state="none",
        medical_safety_state="SAFE",
        runtime_eligibility="eligible",
        rank_score=10,
    )


def test_g2_scenario_id_canonical():
    assert SCENARIO_ID == "SEDI-V1-REAL-FAMILY-CARE-E2E-01"


def test_g2_family_identity_locks(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    assert fam.son_self_hs.subject_kind == "self"
    assert fam.son_self_hs.linked_user_id == fam.son.id
    assert fam.mother_hs.subject_kind == "managed"
    assert fam.mother_hs.linked_user_id is None
    assert fam.son_self_hs.id != fam.mother_hs.id
    assert fam.mother_hs.linked_user_id is None
    # Mother remains accountless — no fake Mother Account name/user for ALS subject
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0


def test_g2_son_i7_to_i5_to_i8_bounded_path(db, monkeypatch):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    son = fam.son
    _profile_tz(db, son.id)
    consent = grant_memory_consent(db, son.id, commit=False)
    _insert_lifelong(
        db,
        son.id,
        habits=["lifestyle.evening_stretch"],
        preferences=["preferences.quiet_mornings"],
        consent_id=consent.id,
    )

    ctx = load_trusted_context(db, son.id)
    assert ctx.lifelong_profile is not None
    pers = build_personalization(ctx, domain="routine")
    assert any("evening stretch" in t or "quiet mornings" in t for t in pers.routine_terms)

    assert PERSONAL_PROVIDER_CONTEXT != GOVERNED_DIRECTORY_PROVIDER
    assert CANONICAL_AUTHORITY == "I5_GOVERNED_CARE_DIRECTORY"

    monkeypatch.setattr(cnd._governed_directory, "search_doctors", lambda *a, **k: [_doc_item()])
    nav = resolve_care_navigation(
        db,
        "Find a neurologist specialist in Tehran",
        authenticated_user_id=son.id,
        language="en",
    )
    assert nav is not None
    assert nav.identities
    assert nav.identities[0].canonical_name == "Dr Verified Neurologist"

    with patch(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        return_value=SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
    ):
        result = generate_operational_action(
            db,
            user_id=son.id,
            actor_user_id=son.id,
            request="help with my daily routine",
            domain="routine",
            persist=False,
        )
    assert result.status in {"ACTION_READY", "GROUNDED_EPHEMERAL"}
    assert result.suggestions


def test_g2_provider_authority_boundaries(db, monkeypatch):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)

    ok, code = assert_no_ungoverned_provider_authority(
        candidate_text="Verified: Dr Personal Friend",
        verified=(),
        memory_text="Dr Personal Friend",
    )
    assert ok is False
    assert code == "UNGOVERNED_PROVIDER_CLAIM_BLOCKED"

    ok, _ = assert_no_ungoverned_provider_authority(
        candidate_text="I8 suggests booking Dr ActionOnly.",
        verified=(),
        i8_action_text="Follow up with Dr ActionOnly",
    )
    assert ok is False

    ok, _ = assert_no_ungoverned_provider_authority(
        candidate_text="RAG says Dr RagOnly",
        verified=(),
        rag_text="Dr RagOnly",
    )
    assert ok is False

    monkeypatch.setattr(cnd._governed_directory, "search_doctors", lambda *a, **k: [])
    calls = {"n": 0}

    def _gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "Dr Hallucinated Fallback", "detected_name": None}

    orch = IntelligenceOrchestrator(db=db, legacy_generator=_gen, structured_mode=False)
    result = orch.process(
        authenticated_user_id=fam.son.id,
        message="Find a specialist neurologist in Tehran",
        language="en",
    )
    assert calls["n"] == 0
    assert "NO_VERIFIED_DIRECTORY_RESULT" in result.reason_codes
    assert "Dr Hallucinated" not in result.message
    blocked, _ = refuse_synthetic_provider_after_zero_result(
        directory_status=STATUS_NO_VERIFIED,
        proposed_text="Try Dr Made Up at Sunshine Hospital.",
    )
    assert blocked is False


def test_g2_mother_managed_directory_context_no_fake_account(db, monkeypatch):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    assert fam.mother_hs.linked_user_id is None
    monkeypatch.setattr(cnd._governed_directory, "search_doctors", lambda *a, **k: [_doc_item()])
    result = resolve_care_navigation(
        db,
        "Find a neurologist specialist in Tehran for my mother",
        authenticated_user_id=fam.son.id,
        target_health_subject_id=fam.mother_hs.id,
        target_subject_kind="managed",
    )
    assert result is not None
    assert "MANAGED_SUBJECT_CONTEXT_PRESERVED" in result.identity_notes
    assert "TARGET_HEALTH_SUBJECT_REF_ONLY" in result.identity_notes
    assert fam.mother_hs.linked_user_id is None


def test_g2_wrong_account_cannot_inject_personal_context(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    grant_memory_consent(db, fam.son.id, commit=False)
    grant_memory_consent(db, fam.stranger.id, commit=False)
    _insert_lifelong(db, fam.son.id, habits=["lifestyle.son_secret"])
    _insert_lifelong(db, fam.stranger.id, habits=["lifestyle.stranger_only"])

    son_ctx = load_trusted_context(db, fam.son.id)
    stranger_ctx = load_trusted_context(db, fam.stranger.id)
    son_blob = json.dumps(list(son_ctx.lifelong_profile.habit_key_terms))
    stranger_blob = json.dumps(list(stranger_ctx.lifelong_profile.habit_key_terms))
    assert "son secret" in son_blob
    assert "stranger only" not in son_blob
    assert "stranger only" in stranger_blob
    assert "son secret" not in stranger_blob


def test_g2_i7_cannot_mint_i8_action_without_governed_knowledge(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    grant_memory_consent(db, fam.son.id, commit=False)
    _insert_lifelong(db, fam.son.id, habits=["lifestyle.evening_stretch"])
    ctx = load_trusted_context(db, fam.son.id)
    assert ctx.lifelong_profile is not None
    pers = build_personalization(ctx, domain="routine")
    assert pers.routine_terms
    with patch(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        return_value=SimpleNamespace(status="EMPTY", items=[]),
    ):
        blocked = generate_operational_action(
            db,
            user_id=fam.son.id,
            actor_user_id=fam.son.id,
            request="help with my daily routine",
            domain="routine",
            persist=False,
        )
    assert blocked.status in {"MISSING_ELIGIBLE_KNOWLEDGE", "MISSING_GROUNDED_ACTION_CONTENT"}
    assert not blocked.suggestions


def test_g2_consent_gate_and_i4_authority_preserved(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    consent = grant_memory_consent(db, fam.son.id, commit=False)
    _insert_lifelong(db, fam.son.id, habits=["lifestyle.secret_habit"], consent_id=consent.id)
    revoke_memory_consent(db, fam.son.id, commit=False)
    ctx = load_trusted_context(db, fam.son.id)
    assert ctx.lifelong_profile is None
    assert CANONICAL_AUTHORITY == "I5_GOVERNED_CARE_DIRECTORY"
    composition = compose_grounded_action(
        SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
        domain="routine",
        ctx=ctx,
    )
    text = " ".join(s.detail for s in composition.suggestions).lower()
    assert "diagnos" not in text
