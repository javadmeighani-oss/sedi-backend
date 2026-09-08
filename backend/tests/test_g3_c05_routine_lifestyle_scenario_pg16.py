"""G3 scenario-first integration — C05 I8 Routine/Lifestyle Bridge.

GATE=SEDI-V1-BE-FINALCERT-G3-C05-I8-ROUTINE-LIFESTYLE-BRIDGE-SCENARIO-PG16-RETEST-01
SCENARIO=SEDI-V1-REAL-FAMILY-CARE-E2E-01

Does NOT add ledger cases. Proves C05 family slice + exact 4 ratified cases.

C05 ledger → existing suite mapping (no rename/split):
  C05-01 Habits_lifestyle_into_I8TrustedContext ← bridge A/G/M/N + this file
  C05-02 Gate2_storage_authority_preserved ← bridge E/K + this file
  C05-03 No_clinical_invention_from_lifestyle ← bridge T/Q/R + this file
  C05-04 Son_SELF_routine_no_Mother_sub ← primary-user cross-I + this file

Authority: candidate ledger ratification (PASS) + Master Log §440 / §444.
"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, RetrievedKnowledgeItem
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i8.context import load_trusted_context
from backend.app.services.i8.knowledge_bridge import build_personalization, compose_grounded_action
from backend.app.services.i8.subject_context import (
    load_subject_trusted_context,
    to_i8_trusted_context_compat,
)
from backend.app.services.i8.unified_core import generate_operational_action
from backend.tests.helpers.i10_postgresql_harness import I10IsolatedPgDb, _REV_081
from backend.tests.helpers.stage_b_family_fixture import SCENARIO_ID, seed_stage_b_family


@pytest.fixture(scope="module")
def g3_pg_db_module():
    isolated = I10IsolatedPgDb.create(suffix="g3c05", revision=_REV_081)
    SessionLocal = isolated.session_factory()
    try:
        yield SessionLocal, isolated
    finally:
        isolated.close()


@pytest.fixture()
def db(g3_pg_db_module):
    SessionLocal, isolated = g3_pg_db_module
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


def _habit(db, user_id: int, name: str, *, notes: str = "secret must not leak"):
    now = datetime.utcnow()
    row = models.UserHabit(
        user_id=user_id,
        name=name,
        frequency="daily",
        target_json=None,
        status="active",
        source="manual",
        notes=notes,
        valid_to=None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _lifestyle(db, user_id: int, event_type: str):
    now = datetime.utcnow()
    row = models.UserLifestyleEvent(
        user_id=user_id,
        event_type=event_type,
        value_json=json.dumps({"label": "walked"}),
        occurred_at=now,
        source="manual",
        notes="raw notes must not leak",
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _ok_item():
    return RetrievedKnowledgeItem(
        knowledge_unit_id=1,
        canonical_unit_id="KU-ROUTINE-G3",
        immutable_version_id="v1",
        memory_item_id="m-g3",
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


def test_g3_scenario_id_canonical():
    assert SCENARIO_ID == "SEDI-V1-REAL-FAMILY-CARE-E2E-01"


def test_g3_family_identity_locks(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    assert fam.son_self_hs.subject_kind == "self"
    assert fam.son_self_hs.linked_user_id == fam.son.id
    assert fam.mother_hs.subject_kind == "managed"
    assert fam.mother_hs.linked_user_id is None
    assert fam.son_self_hs.id != fam.mother_hs.id
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0


def test_c05_01_habits_lifestyle_into_trusted_context(db):
    """C05-01 Habits_lifestyle_into_I8TrustedContext"""
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    habit = _habit(db, fam.son.id, "evening stretch")
    event = _lifestyle(db, fam.son.id, "light_walk")
    ctx = load_trusted_context(db, fam.son.id)
    assert any(h.habit_id == habit.id and h.name == "evening stretch" for h in ctx.habits)
    assert any(e.event_id == event.id and e.event_type == "light_walk" for e in ctx.lifestyle_events)
    pers = build_personalization(ctx, domain="routine")
    assert any("evening stretch" in t for t in pers.routine_terms)
    pers_l = build_personalization(ctx, domain="lifestyle")
    assert any("light_walk" in t or "light walk" in t for t in pers_l.lifestyle_terms)


def test_c05_02_gate2_storage_authority_preserved(db):
    """C05-02 Gate2_storage_authority_preserved — I8 refs only; Gate2 rows remain SoT."""
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    habit = _habit(db, fam.son.id, "morning walk", notes="private gate2 notes")
    event = _lifestyle(db, fam.son.id, "hydration")
    ctx = load_trusted_context(db, fam.son.id)
    assert {"ref_type": "user_habit", "ref_id": habit.id} in ctx.context_refs
    assert {"ref_type": "user_lifestyle_event", "ref_id": event.id} in ctx.context_refs
    # Storage authority remains Gate2 tables
    assert db.query(models.UserHabit).filter_by(id=habit.id, user_id=fam.son.id).one().notes == (
        "private gate2 notes"
    )
    assert db.query(models.UserLifestyleEvent).filter_by(id=event.id, user_id=fam.son.id).one()
    blob = json.dumps(
        {
            "habits": [h.__dict__ for h in ctx.habits],
            "lifestyle_events": [e.__dict__ for e in ctx.lifestyle_events],
            "refs": ctx.context_refs,
        },
        default=str,
    ).lower()
    assert "private gate2 notes" not in blob
    assert "raw notes must not leak" not in blob
    pers = build_personalization(ctx, domain="routine")
    assert all("KU-" not in t and "knowledge_unit" not in t.casefold() for t in pers.routine_terms)


def test_c05_03_no_clinical_invention_from_lifestyle(db):
    """C05-03 No_clinical_invention_from_lifestyle + I5 required for I8 action."""
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    grant_memory_consent(db, fam.son.id, commit=False)
    _habit(db, fam.son.id, "daily walk")
    ctx = load_trusted_context(db, fam.son.id)
    assert compose_grounded_action(
        SimpleNamespace(status=STATUS_OK, items=[]), domain="routine", ctx=ctx
    ) is None
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
    composition = compose_grounded_action(
        SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
        domain="routine",
        ctx=ctx,
    )
    text = (composition.suggestions[0].detail + composition.rationale).lower()
    for banned in ("diagnosis", "diagnose", "prescribe", "adherence", "missed habit"):
        assert banned not in text


def test_c05_04_son_self_routine_no_mother_sub(db):
    """C05-04 Son_SELF_routine_no_Mother_sub"""
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    _profile_tz(db, fam.stranger.id)
    _habit(db, fam.son.id, "son_only_stretch")
    _lifestyle(db, fam.son.id, "son_only_walk")
    _habit(db, fam.stranger.id, "stranger_habit")

    son_ctx = load_trusted_context(db, fam.son.id)
    stranger_ctx = load_trusted_context(db, fam.stranger.id)
    son_names = {h.name for h in son_ctx.habits}
    stranger_names = {h.name for h in stranger_ctx.habits}
    assert "son_only_stretch" in son_names
    assert "stranger_habit" not in son_names
    assert "son_only_stretch" not in stranger_names

    # Mother MANAGED must not inherit Son Gate2 habit/lifestyle via subject compat
    mother_subj = load_subject_trusted_context(
        db, actor_account_user_id=fam.son.id, health_subject_id=fam.mother_hs.id
    )
    mother_compat = to_i8_trusted_context_compat(mother_subj)
    assert mother_compat.habits == []
    assert mother_compat.lifestyle_events == []
    assert mother_compat.lifelong_profile is None
    assert fam.mother_hs.linked_user_id is None
    assert fam.mother_hs.subject_kind == "managed"
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0
    assert fam.son_self_hs.id != fam.mother_hs.id


def test_g3_son_routine_path_with_governed_knowledge(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    grant_memory_consent(db, fam.son.id, commit=False)
    _habit(db, fam.son.id, "evening stretch")
    with patch(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        return_value=SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
    ):
        result = generate_operational_action(
            db,
            user_id=fam.son.id,
            actor_user_id=fam.son.id,
            request="help with my daily routine",
            domain="routine",
            persist=False,
        )
    assert result.status in {"ACTION_READY", "GROUNDED_EPHEMERAL"}
    assert result.suggestions
    text = " ".join(s.detail for s in result.suggestions).lower()
    assert "diagnos" not in text
