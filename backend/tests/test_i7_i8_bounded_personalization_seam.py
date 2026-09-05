"""I7→I8 bounded personalization seam — SCENARIO SEDI-V1-REAL-FAMILY-CARE-E2E-01."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, RetrievedKnowledgeItem
from backend.app.services.i6.consent_service import grant_memory_consent, revoke_memory_consent
from backend.app.services.i8.context import (
    I8_PERSONAL_CONTEXT_TERM_SLICE,
    load_trusted_context,
)
from backend.app.services.i8.knowledge_bridge import (
    build_personalization,
    compose_grounded_action,
)
from backend.app.services.i8.unified_core import generate_operational_action
from backend.tests.helpers.stage_b_family_fixture import SCENARIO_ID, seed_stage_b_family


@pytest.fixture(scope="session")
def _i7i8_tables_present():
    url = os.environ.get("TEST_DATABASE_URL")
    assert url, "TEST_DATABASE_URL required"
    engine = create_engine(url)
    try:
        insp = inspect(engine)
        assert engine.dialect.name == "postgresql", engine.dialect.name
        missing = [
            t
            for t in ("user_lifelong_profiles", "user_habits", "i8_operational_plans", "health_subjects")
            if not insp.has_table(t)
        ]
        assert not missing, missing
    finally:
        engine.dispose()


@pytest.fixture()
def db(_i7i8_tables_present):
    url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(url)
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def _profile_tz(db, user_id: int) -> None:
    if db.query(models.UserProfileCore).filter_by(user_id=user_id).first():
        return
    db.add(models.UserProfileCore(user_id=user_id, timezone="UTC"))
    db.flush()


def _insert_lifelong(
    db,
    user_id: int,
    *,
    habits=None,
    preferences=None,
    goals=None,
    version: int = 1,
    status: str = "active",
    consent_id: int | None = None,
):
    now = datetime.now(timezone.utc)
    payload = {
        "authority": "I6_FACTS_ARE_SOT",
        "profile_is_derived_only": True,
        "not_diagnosis": True,
        "generator_version": "i7-v1-lifelong-profile",
        "fact_count": 3,
        "keys": [],
        "habits": habits or [],
        "preferences": preferences or [],
        "goals": goals or [],
    }
    row = models.UserLifelongProfile(
        user_id=user_id,
        version=version,
        status=status,
        structured_profile_json=json.dumps(payload, sort_keys=True),
        narrative_compact="Derived compact profile; not source of truth.",
        source_fact_ids_json="[]",
        source_event_refs_json="[]",
        consent_id=consent_id,
        generator_version="i7-v1-lifelong-profile",
        built_from_period_start=now - timedelta(days=365),
        built_from_period_end=now,
    )
    db.add(row)
    db.flush()
    return row


def _ok_item(*, statement: str = "Keep a steady daily movement pattern") -> RetrievedKnowledgeItem:
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
        normalized_statement=statement,
        evidence_strength="MODERATE",
        freshness_state="fresh",
        conflict_state="none",
        medical_safety_state="SAFE",
        runtime_eligibility="eligible",
        rank_score=10,
    )


def _ok_retrieval(*_a, **_k):
    return SimpleNamespace(status=STATUS_OK, items=[_ok_item()])


def test_scenario_id_canonical():
    assert SCENARIO_ID == "SEDI-V1-REAL-FAMILY-CARE-E2E-01"


def test_case1_son_positive_personalization(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    son = fam.son
    _profile_tz(db, son.id)
    consent = grant_memory_consent(db, son.id, commit=False)
    prof = _insert_lifelong(
        db,
        son.id,
        habits=["lifestyle.evening_stretch"],
        preferences=["preferences.quiet_mornings"],
        consent_id=consent.id,
    )
    ctx = load_trusted_context(db, son.id)
    assert ctx.lifelong_profile is not None
    assert ctx.lifelong_profile.profile_id == prof.id
    assert "evening stretch" in ctx.lifelong_profile.habit_key_terms
    assert any(r.get("ref_type") == "user_lifelong_profile" for r in ctx.context_refs)

    pers = build_personalization(ctx, domain="routine")
    assert any("evening stretch" in t or "quiet mornings" in t for t in pers.routine_terms)

    with patch(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        side_effect=_ok_retrieval,
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
    detail = " ".join(s.detail for s in result.suggestions)
    assert "I7 profile term" in detail
    assert "evening stretch" in detail or "quiet mornings" in detail
    assert fam.mother_hs.linked_user_id is None


def test_case2_no_i7_data_safe_fallback(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    son = fam.son
    _profile_tz(db, son.id)
    grant_memory_consent(db, son.id, commit=False)
    ctx = load_trusted_context(db, son.id)
    assert ctx.lifelong_profile is None
    with patch(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        side_effect=_ok_retrieval,
    ):
        result = generate_operational_action(
            db,
            user_id=son.id,
            actor_user_id=son.id,
            request="help with my daily routine",
            domain="routine",
            persist=False,
        )
    assert result.status != "ERROR"
    detail = " ".join(s.detail for s in (result.suggestions or []))
    assert "I7 profile term" not in detail


def test_case3_revoked_consent_blocks_i7(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    son = fam.son
    _profile_tz(db, son.id)
    consent = grant_memory_consent(db, son.id, commit=False)
    _insert_lifelong(
        db,
        son.id,
        habits=["lifestyle.secret_habit"],
        preferences=["preferences.secret_pref"],
        consent_id=consent.id,
    )
    revoke_memory_consent(db, son.id, commit=False)
    ctx = load_trusted_context(db, son.id)
    assert ctx.lifelong_profile is None
    assert not any(r.get("ref_type") == "user_lifelong_profile" for r in ctx.context_refs)


def test_case4_cross_user_isolation(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    son = fam.son
    other = fam.stranger
    _profile_tz(db, son.id)
    grant_memory_consent(db, son.id, commit=False)
    grant_memory_consent(db, other.id, commit=False)
    _insert_lifelong(db, other.id, habits=["lifestyle.other_user_only"], preferences=["preferences.leak"])
    _insert_lifelong(db, son.id, habits=["lifestyle.son_stretch"])
    ctx = load_trusted_context(db, son.id)
    assert ctx.lifelong_profile is not None
    blob = json.dumps(
        {
            "habits": list(ctx.lifelong_profile.habit_key_terms),
            "prefs": list(ctx.lifelong_profile.preference_terms),
            "refs": ctx.context_refs,
        }
    )
    assert "other user only" not in blob
    assert "leak" not in blob
    assert "son stretch" in blob


def test_case5_managed_mother_isolation(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    assert fam.mother_hs.subject_kind == "managed"
    assert fam.mother_hs.linked_user_id is None
    assert fam.son_self_hs.id != fam.mother_hs.id
    assert fam.son.id != fam.mother_hs.id
    _profile_tz(db, fam.son.id)
    grant_memory_consent(db, fam.son.id, commit=False)
    _insert_lifelong(db, fam.son.id, preferences=["preferences.son_only_memory"])
    ctx = load_trusted_context(db, fam.son.id)
    assert ctx.lifelong_profile is not None
    assert "son only memory" in ctx.lifelong_profile.preference_terms
    # Mother has no Account — no lifelong profile owner substitution
    mother_profiles = (
        db.query(models.UserLifelongProfile)
        .filter(models.UserLifelongProfile.user_id == fam.mother_hs.id)
        .count()
    )
    assert mother_profiles == 0
    # No User row for mother health subject id as account owner of Son memory
    assert ctx.user_id == fam.son.id


def test_case6_provenance(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    consent = grant_memory_consent(db, fam.son.id, commit=False)
    prof = _insert_lifelong(db, fam.son.id, habits=["lifestyle.walk"], consent_id=consent.id)
    ctx = load_trusted_context(db, fam.son.id)
    refs = [r for r in ctx.context_refs if r.get("ref_type") == "user_lifelong_profile"]
    assert refs and refs[0]["ref_id"] == prof.id
    assert refs[0].get("version") == prof.version


def test_case7_boundedness(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    grant_memory_consent(db, fam.son.id, commit=False)
    many = [f"lifestyle.habit_key_{i}" for i in range(40)]
    prefs = [f"preferences.pref_key_{i}" for i in range(40)]
    _insert_lifelong(db, fam.son.id, habits=many, preferences=prefs)
    ctx = load_trusted_context(db, fam.son.id)
    assert ctx.lifelong_profile is not None
    assert len(ctx.lifelong_profile.habit_key_terms) <= I8_PERSONAL_CONTEXT_TERM_SLICE
    assert len(ctx.lifelong_profile.preference_terms) <= I8_PERSONAL_CONTEXT_TERM_SLICE
    pers = build_personalization(ctx, domain="routine")
    assert len(pers.routine_terms) <= I8_PERSONAL_CONTEXT_TERM_SLICE
    assert len(pers.lifestyle_terms) <= I8_PERSONAL_CONTEXT_TERM_SLICE


def test_case8_habit_bridge_and_i5_still_work(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    son = fam.son
    _profile_tz(db, son.id)
    grant_memory_consent(db, son.id, commit=False)
    now = datetime.utcnow()
    db.add(
        models.UserHabit(
            user_id=son.id,
            name="daily walk",
            frequency="daily",
            status="active",
            source="manual",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        models.UserGoal(
            user_id=son.id,
            category="lifestyle",
            title="sleep earlier",
            status="active",
            source="manual",
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()
    ctx = load_trusted_context(db, son.id)
    assert any(h.name == "daily walk" for h in ctx.habits)
    assert "sleep earlier" in ctx.goals
    pers = build_personalization(ctx, domain="routine")
    assert "daily walk" in pers.routine_terms
    assert "sleep earlier" in pers.goal_terms
    composition = compose_grounded_action(_ok_retrieval(), domain="routine", ctx=ctx)
    assert composition is not None
    assert "daily walk" in composition.suggestions[0].detail
    with patch(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        return_value=SimpleNamespace(status="EMPTY", items=[]),
    ):
        blocked = generate_operational_action(
            db,
            user_id=son.id,
            actor_user_id=son.id,
            request="help with my daily routine",
            domain="routine",
            persist=False,
        )
    assert blocked.status in {"MISSING_ELIGIBLE_KNOWLEDGE", "MISSING_GROUNDED_ACTION_CONTENT"}
    assert not blocked.suggestions
