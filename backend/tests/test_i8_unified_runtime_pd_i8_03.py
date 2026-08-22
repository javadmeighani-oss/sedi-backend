"""PD-I8-03 unified I8 runtime foundation tests."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, RetrievedKnowledgeItem
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.i8.constants import PRESENTATION_JSON_MAX_BYTES
from backend.app.services.i8.local_day import (
    I8InvalidTimezoneError,
    I8TimezoneRequiredError,
    local_day_utc_span_seconds,
    resolve_local_day_window,
)
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i8.unified_core import generate_operational_action, infer_domain, _validate_presentation


def _user(db, name: str = "i8-u") -> models.User:
    row = models.User(name=name, secret_key="k", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _profile_tz(db, user_id: int, timezone: str = "America/New_York") -> None:
    db.add(models.UserProfileCore(user_id=user_id, timezone=timezone))
    db.flush()


def _ok_item(*, statement: str = "Eat balanced meals") -> RetrievedKnowledgeItem:
    return RetrievedKnowledgeItem(
        knowledge_unit_id=1,
        canonical_unit_id="KU-1",
        immutable_version_id="v1",
        memory_item_id="m1",
        memory_row_id=1,
        source_profile_id=1,
        provenance_id=1,
        raw_evidence_id=None,
        domain="nutrition",
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


def _grant_and_seed(db, user_id: int) -> None:
    grant_memory_consent(db, user_id, commit=True)
    write_fact(db, user_id, "lifestyle", "diet_notes", "home cooking", commit=True)


@pytest.fixture(scope="session")
def _i8_tables_present():
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DB03_REHEARSAL_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    engine = create_engine(url)
    try:
        if engine.dialect.name == "postgresql" and not inspect(engine).has_table("i8_operational_plans"):
            pytest.skip("i8_operational_plans not present (alembic 069 required)")
    finally:
        engine.dispose()


@pytest.fixture()
def db(_i8_tables_present):
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DB03_REHEARSAL_DATABASE_URL")
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


@pytest.fixture(autouse=True)
def _require_i8_tables(_i8_tables_present):
    return True


def test_orm_tables_registered():
    assert "i8_operational_plans" in models.Base.metadata.tables
    assert "i8_operational_plan_actions" in models.Base.metadata.tables
    plan = models.I8OperationalPlan.__table__
    assert "uq_i8_plan_id_user" in {c.name for c in plan.constraints if getattr(c, "name", None)}


def test_infer_domains():
    assert infer_domain("what should I eat for lunch") == "nutrition"
    assert infer_domain("morning walk plan") == "exercise"
    assert infer_domain("breakfast and walk") == "cross_domain"


def test_local_day_window_valid_timezone(db):
    user = _user(db)
    _profile_tz(db, user.id, "America/Los_Angeles")
    db.commit()
    window = resolve_local_day_window(db, user.id)
    assert window.timezone_snapshot == "America/Los_Angeles"
    assert window.user_local_date is not None
    assert window.expires_at > window.valid_until


def test_local_day_missing_timezone_fail_closed(db):
    user = _user(db)
    db.commit()
    with pytest.raises(I8TimezoneRequiredError):
        resolve_local_day_window(db, user.id)


def test_local_day_invalid_timezone_fail_closed(db):
    user = _user(db)
    _profile_tz(db, user.id, "Not/A_Real_Zone")
    db.commit()
    with pytest.raises(I8InvalidTimezoneError):
        resolve_local_day_window(db, user.id)


def test_local_day_dst_spring_forward_23h(db):
    user = _user(db)
    _profile_tz(db, user.id, "America/New_York")
    db.commit()
    now_utc = datetime(2026, 3, 8, 17, 0, tzinfo=timezone.utc)
    window = resolve_local_day_window(db, user.id, now_utc=now_utc)
    assert window.timezone_snapshot == "America/New_York"
    assert window.user_local_date.isoformat() == "2026-03-08"
    assert local_day_utc_span_seconds(window) == 23 * 3600
    assert window.expires_at == window.valid_until + timedelta(hours=36)


def test_local_day_dst_fall_back_25h(db):
    user = _user(db)
    _profile_tz(db, user.id, "America/New_York")
    db.commit()
    now_utc = datetime(2026, 11, 1, 16, 0, tzinfo=timezone.utc)
    window = resolve_local_day_window(db, user.id, now_utc=now_utc)
    assert window.user_local_date.isoformat() == "2026-11-01"
    assert local_day_utc_span_seconds(window) == 25 * 3600
    assert window.expires_at == window.valid_until + timedelta(hours=36)


def test_local_day_normal_24h(db):
    user = _user(db)
    _profile_tz(db, user.id, "America/New_York")
    db.commit()
    now_utc = datetime(2026, 6, 15, 16, 0, tzinfo=timezone.utc)
    window = resolve_local_day_window(db, user.id, now_utc=now_utc)
    assert window.user_local_date.isoformat() == "2026-06-15"
    assert local_day_utc_span_seconds(window) == 24 * 3600


def test_timezone_required_blocks_plan_persist(db, monkeypatch):
    user = _user(db)
    db.commit()
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
    )
    result = generate_operational_action(
        db, user_id=user.id, actor_user_id=user.id, request="healthy lunch", domain="nutrition", persist=True
    )
    assert result.status == "TIMEZONE_REQUIRED"
    assert result.persisted is False
    assert db.query(models.I8OperationalPlan).filter_by(user_id=user.id).count() == 0


def test_presentation_cap_rejected():
    big = {"payload": "x" * (PRESENTATION_JSON_MAX_BYTES + 100)}
    with pytest.raises(ValueError):
        _validate_presentation(big)


def test_jwt_identity_mismatch(db):
    user = _user(db)
    db.commit()
    result = generate_operational_action(
        db, user_id=user.id, actor_user_id=user.id + 1, request="meal", domain="nutrition", persist=False
    )
    assert result.status == "AUTH_IDENTITY_MISMATCH"


def test_disease_aware_fail_closed_safe_retrieval_not_applicability(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    cond = models.MedicalCondition(name="Type 2 Diabetes i8-test-a", code="I8T2DA")
    db.add(cond)
    db.flush()
    db.add(models.UserCondition(user_id=user.id, condition_id=cond.id))
    db.commit()
    _grant_and_seed(db, user.id)
    item = _ok_item()
    assert item.medical_safety_state == "SAFE"
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[item]),
    )
    result = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="healthy lunch ideas",
        domain="nutrition",
        persist=False,
    )
    assert result.status == "UNSUPPORTED_CLINICAL_APPLICABILITY"
    assert result.clarification_required is True
    assert result.persisted is False


def test_allergy_hard_constraint(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.add(
        models.UserProfileFact(
            user_id=user.id,
            fact_type="allergy",
            value_json='"peanut"',
            source="manual",
        )
    )
    db.commit()
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
    )
    result = generate_operational_action(
        db, user_id=user.id, actor_user_id=user.id, request="peanut snack", domain="nutrition", persist=False
    )
    assert result.status == "ALLERGY_HARD_CONSTRAINT"


def test_restriction_enforcement(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.add(
        models.UserRestriction(
            user_id=user.id,
            restriction_type="diet",
            title="no caffeine",
            status="active",
            source="manual",
        )
    )
    db.commit()
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
    )
    result = generate_operational_action(
        db, user_id=user.id, actor_user_id=user.id, request="extra caffeine today", domain="lifestyle", persist=False
    )
    assert result.status == "RESTRICTION_BLOCKED"


def test_therapeutic_fail_closed(db):
    user = _user(db)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    result = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="increase dose of my medication",
        domain="wellbeing",
        persist=False,
    )
    assert result.status == "THERAPEUTIC_FAIL_CLOSED"


def test_post_composition_allergy_blocks_grounded_content(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.add(
        models.UserProfileFact(
            user_id=user.id,
            fact_type="allergy",
            value_json='"peanut"',
            source="manual",
        )
    )
    db.commit()
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item(statement="Try a peanut snack today")]),
    )
    result = generate_operational_action(
        db, user_id=user.id, actor_user_id=user.id, request="healthy lunch", domain="nutrition", persist=False
    )
    assert result.status == "ALLERGY_HARD_CONSTRAINT"
    assert result.persisted is False


def test_post_composition_restriction_blocks_grounded_content(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.add(
        models.UserRestriction(
            user_id=user.id,
            restriction_type="diet",
            title="no caffeine",
            status="active",
            source="manual",
        )
    )
    db.commit()
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item(statement="Have extra caffeine today")]),
    )
    result = generate_operational_action(
        db, user_id=user.id, actor_user_id=user.id, request="morning routine", domain="routine", persist=False
    )
    assert result.status == "RESTRICTION_BLOCKED"
    assert result.persisted is False


def test_post_composition_therapeutic_blocks_grounded_content(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(
            status=STATUS_OK, items=[_ok_item(statement="You should increase dose of your medication")]
        ),
    )
    result = generate_operational_action(
        db, user_id=user.id, actor_user_id=user.id, request="wellbeing tips", domain="wellbeing", persist=False
    )
    assert result.status == "THERAPEUTIC_FAIL_CLOSED"
    assert result.persisted is False


def test_i5_gateway_used_grounded_refs_aligned(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    called = {"n": 0}
    item = _ok_item(statement="Choose whole grains and vegetables for lunch")

    def _fake(db, **kwargs):
        called["n"] += 1
        return SimpleNamespace(status=STATUS_OK, items=[item])

    monkeypatch.setattr("backend.app.services.i8.unified_core.retrieve_governed_knowledge", _fake)
    result = generate_operational_action(
        db, user_id=user.id, actor_user_id=user.id, request="healthy lunch", domain="nutrition", persist=True
    )
    assert called["n"] == 1
    assert result.status == "ACTION_PERSISTED"
    assert result.knowledge_refs
    assert len(result.knowledge_refs) == 1
    assert result.knowledge_refs[0]["knowledge_unit_id"] == item.knowledge_unit_id
    assert item.normalized_statement in result.summary
    assert "Governed I5-grounded" not in result.rationale
    assert "Action derived from governed knowledge" in result.rationale
    assert "normalized_statement" not in json.dumps(result.knowledge_refs)
    row = db.query(models.I8OperationalPlanAction).filter_by(id=result.action_id).one()
    persisted_blob = json.dumps(
        {
            "summary_text": row.summary_text,
            "presentation_json": row.presentation_json,
            "knowledge_refs_json": row.knowledge_refs_json,
            "context_refs_json": row.context_refs_json,
        }
    )
    assert item.normalized_statement not in persisted_blob
    assert row.summary_text == "Governed nutrition action"


I8_RAW_I5_SENTINEL = "I8_RAW_I5_SENTINEL_REPAIR02"


def test_raw_i5_sentinel_ephemeral_yes_db_no(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    statement = f"{I8_RAW_I5_SENTINEL} choose vegetables for lunch"
    item = _ok_item(statement=statement)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[item]),
    )
    result = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="healthy lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="sentinel-plan",
        action_idempotency_key="sentinel-act",
    )
    assert result.status == "ACTION_PERSISTED"
    assert I8_RAW_I5_SENTINEL in result.summary
    assert result.knowledge_refs[0]["knowledge_unit_id"] == item.knowledge_unit_id
    row = db.query(models.I8OperationalPlanAction).filter_by(id=result.action_id).one()
    db_fields = f"{row.summary_text}|{row.presentation_json}|{row.knowledge_refs_json}|{row.context_refs_json or ''}"
    assert I8_RAW_I5_SENTINEL not in db_fields
    assert str(item.knowledge_unit_id) in row.knowledge_refs_json
    assert item.immutable_version_id in row.knowledge_refs_json


def test_reactive_domains(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
    )
    for domain, req in (
        ("nutrition", "lunch ideas"),
        ("exercise", "walk today"),
        ("routine", "daily routine"),
        ("lifestyle", "hydration"),
        ("wellbeing", "reduce stress"),
        ("cross_domain", "breakfast and walk"),
    ):
        result = generate_operational_action(
            db,
            user_id=user.id,
            actor_user_id=user.id,
            request=req,
            domain=domain,
            persist=True,
            plan_idempotency_key=f"plan-{domain}",
            action_idempotency_key=f"act-{domain}",
        )
        assert result.status == "ACTION_PERSISTED", domain
        assert result.action_id is not None


def test_idempotency_no_duplicate(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    called = {"n": 0}

    def _fake(*a, **k):
        called["n"] += 1
        return SimpleNamespace(status=STATUS_OK, items=[_ok_item()])

    monkeypatch.setattr("backend.app.services.i8.unified_core.retrieve_governed_knowledge", _fake)
    kwargs = dict(
        user_id=user.id,
        actor_user_id=user.id,
        request="same lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="idem-plan-1",
        action_idempotency_key="idem-act-1",
    )
    first = generate_operational_action(db, **kwargs)
    second = generate_operational_action(db, **kwargs)
    assert first.plan_id == second.plan_id
    assert first.action_id == second.action_id
    assert called["n"] == 1
    assert db.query(models.I8OperationalPlan).filter_by(user_id=user.id).count() == 1
    assert db.query(models.I8OperationalPlanAction).filter_by(user_id=user.id).count() == 1


I8_KU_V1_SENTINEL = "I8_KU_V1_SENTINEL"
I8_KU_V2_SENTINEL = "I8_KU_V2_SENTINEL"


def _ku_item(*, ku_id: int, version: str, sentinel: str) -> RetrievedKnowledgeItem:
    return RetrievedKnowledgeItem(
        knowledge_unit_id=ku_id,
        canonical_unit_id=f"KU-{ku_id}",
        immutable_version_id=version,
        memory_item_id=f"m{ku_id}",
        memory_row_id=ku_id,
        source_profile_id=1,
        provenance_id=ku_id,
        raw_evidence_id=None,
        domain="nutrition",
        language="en",
        topic_taxonomy=None,
        normalized_statement=f"{sentinel} choose a balanced meal",
        evidence_strength="MODERATE",
        freshness_state="fresh",
        conflict_state="none",
        medical_safety_state="SAFE",
        runtime_eligibility="eligible",
        rank_score=10,
    )


def test_idempotent_replay_provenance_ku_v1_not_v2(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    retrieval_calls = {"n": 0}

    def _fake(db, **kwargs):
        retrieval_calls["n"] += 1
        if retrieval_calls["n"] == 1:
            return SimpleNamespace(status=STATUS_OK, items=[_ku_item(ku_id=101, version="v1", sentinel=I8_KU_V1_SENTINEL)])
        return SimpleNamespace(status=STATUS_OK, items=[_ku_item(ku_id=202, version="v2", sentinel=I8_KU_V2_SENTINEL)])

    monkeypatch.setattr("backend.app.services.i8.unified_core.retrieve_governed_knowledge", _fake)
    kwargs = dict(
        user_id=user.id,
        actor_user_id=user.id,
        request="healthy lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="replay-plan-P",
        action_idempotency_key="replay-act-A",
    )
    first = generate_operational_action(db, **kwargs)
    assert first.status == "ACTION_PERSISTED"
    assert I8_KU_V1_SENTINEL in first.summary
    assert I8_KU_V2_SENTINEL not in first.summary
    assert first.knowledge_refs[0]["knowledge_unit_id"] == 101
    assert first.knowledge_refs[0]["immutable_version_id"] == "v1"

    row = db.query(models.I8OperationalPlanAction).filter_by(id=first.action_id).one()
    assert "101" in row.knowledge_refs_json
    assert "v1" in row.knowledge_refs_json
    assert I8_KU_V1_SENTINEL not in row.summary_text
    assert I8_KU_V2_SENTINEL not in row.knowledge_refs_json

    second = generate_operational_action(db, **kwargs)
    assert retrieval_calls["n"] == 1
    assert second.plan_id == first.plan_id
    assert second.action_id == first.action_id
    assert second.knowledge_refs[0]["knowledge_unit_id"] == 101
    assert second.knowledge_refs[0]["immutable_version_id"] == "v1"
    assert I8_KU_V2_SENTINEL not in second.summary
    assert I8_KU_V2_SENTINEL not in json.dumps(second.knowledge_refs)
    assert I8_KU_V1_SENTINEL not in second.summary
    assert db.query(models.I8OperationalPlan).filter_by(user_id=user.id).count() == 1
    assert db.query(models.I8OperationalPlanAction).filter_by(user_id=user.id).count() == 1


def test_cross_user_idempotent_replay_isolated(db, monkeypatch):
    user_a = _user(db, "replay-a")
    user_b = _user(db, "replay-b")
    _profile_tz(db, user_a.id)
    _profile_tz(db, user_b.id)
    db.commit()
    _grant_and_seed(db, user_a.id)
    _grant_and_seed(db, user_b.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ku_item(ku_id=101, version="v1", sentinel=I8_KU_V1_SENTINEL)]),
    )
    first = generate_operational_action(
        db,
        user_id=user_a.id,
        actor_user_id=user_a.id,
        request="lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="shared-P",
        action_idempotency_key="shared-A",
    )
    second = generate_operational_action(
        db,
        user_id=user_b.id,
        actor_user_id=user_b.id,
        request="lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="shared-P",
        action_idempotency_key="shared-A",
    )
    assert first.action_id != second.action_id
    assert first.plan_id != second.plan_id
    assert db.query(models.I8OperationalPlanAction).filter_by(user_id=user_b.id).count() == 1


def test_cross_user_action_rejected(db):
    user_a = _user(db, "a")
    user_b = _user(db, "b")
    _profile_tz(db, user_a.id)
    db.commit()
    repo = I8OperationalRepository()
    window = resolve_local_day_window(db, user_a.id)
    plan = repo.create_plan(
        db,
        user_id=user_a.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="reactive",
        plan_idempotency_key="p-a",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.flush()
    with pytest.raises(IntegrityError):
        repo.create_action(
            db,
            user_id=user_b.id,
            plan_id=plan.id,
            action_domain="nutrition",
            action_type="meal_suggestion",
            action_idempotency_key="bad",
            summary_text="x",
            presentation_json="{}",
            knowledge_refs_json="[]",
            safety_state="SAFE",
            valid_from=window.valid_from,
            valid_until=window.valid_until,
            expires_at=window.expires_at,
        )
        db.commit()
    db.rollback()


def test_supersession_one_active_plan(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
    )
    window = resolve_local_day_window(db, user.id)
    generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="first",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="plan-1",
        action_idempotency_key="act-1",
    )
    generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="second",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="plan-2",
        action_idempotency_key="act-2",
    )
    active = (
        db.query(models.I8OperationalPlan)
        .filter_by(user_id=user.id, user_local_date=window.user_local_date, status="ACTIVE")
        .count()
    )
    assert active == 1


def test_no_direct_vector_imports_in_i8_services():
    import backend.app.services.i8.unified_core as core
    import backend.app.services.i8.knowledge_bridge as kb

    for mod in (core, kb):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "pgvector" not in src.lower()
        assert "ivfflat" not in src.lower()
        assert "local_rag" not in src
        assert "vector_provider" not in src
