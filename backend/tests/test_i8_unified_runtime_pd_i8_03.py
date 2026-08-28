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


def test_superseded_plan_replay_rejected(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    retrieval_calls = {"n": 0}

    def _fake(*a, **k):
        retrieval_calls["n"] += 1
        return SimpleNamespace(status=STATUS_OK, items=[_ok_item()])

    monkeypatch.setattr("backend.app.services.i8.unified_core.retrieve_governed_knowledge", _fake)
    first = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="first lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="P1",
        action_idempotency_key="A1",
    )
    second = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="second lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="P2",
        action_idempotency_key="A2",
    )
    third = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="first lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="P1",
        action_idempotency_key="A1",
    )
    plan1 = db.query(models.I8OperationalPlan).filter_by(id=first.plan_id).one()
    assert plan1.status == "SUPERSEDED"
    assert third.status == "ACTION_NOT_REPLAYABLE"
    assert third.action_id == first.action_id
    assert third.plan_id == first.plan_id
    assert retrieval_calls["n"] == 2
    assert db.query(models.I8OperationalPlan).filter_by(user_id=user.id, status="ACTIVE").count() == 1
    assert db.query(models.I8OperationalPlan).filter_by(user_id=user.id).count() == 2
    assert db.query(models.I8OperationalPlanAction).filter_by(user_id=user.id).count() == 2


def test_past_valid_until_replay_rejected(db, monkeypatch):
    user = _user(db)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    retrieval_calls = {"n": 0}

    def _fake(*a, **k):
        retrieval_calls["n"] += 1
        return SimpleNamespace(status=STATUS_OK, items=[_ok_item()])

    monkeypatch.setattr("backend.app.services.i8.unified_core.retrieve_governed_knowledge", _fake)
    first = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="valid-plan",
        action_idempotency_key="valid-act",
    )
    now = datetime.now(timezone.utc)
    action = db.query(models.I8OperationalPlanAction).filter_by(id=first.action_id).one()
    plan = db.query(models.I8OperationalPlan).filter_by(id=first.plan_id).one()
    action.valid_until = now - timedelta(hours=1)
    action.expires_at = now + timedelta(hours=24)
    plan.valid_until = action.valid_until
    plan.expires_at = action.expires_at
    db.flush()
    second = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="valid-plan",
        action_idempotency_key="valid-act",
    )
    assert db.query(models.I8OperationalPlanAction).filter_by(id=first.action_id).count() == 1
    assert second.status == "ACTION_NOT_REPLAYABLE"
    assert retrieval_calls["n"] == 1


@pytest.mark.parametrize("plan_status", ["CANCELLED", "EXPIRED"])
def test_non_replayable_plan_status_rejected(db, monkeypatch, plan_status):
    user = _user(db)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    retrieval_calls = {"n": 0}

    def _fake(*a, **k):
        retrieval_calls["n"] += 1
        return SimpleNamespace(status=STATUS_OK, items=[_ok_item()])

    monkeypatch.setattr("backend.app.services.i8.unified_core.retrieve_governed_knowledge", _fake)
    first = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key=f"plan-{plan_status}",
        action_idempotency_key=f"act-{plan_status}",
    )
    plan = db.query(models.I8OperationalPlan).filter_by(id=first.plan_id).one()
    plan.status = plan_status
    db.flush()
    second = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key=f"plan-{plan_status}",
        action_idempotency_key=f"act-{plan_status}",
    )
    assert second.status == "ACTION_NOT_REPLAYABLE"
    assert retrieval_calls["n"] == 1


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


# --- PD-I9-V1-I8-I9-GOVERNED-CONSUMER-INTEGRATION-CLOSURE-01 (I8 consumer tests) ---

from backend.app.core.device_auth import hash_device_token
from backend.app.services.i8.context import load_trusted_context
from backend.app.services.i8.knowledge_bridge import build_personalization
from backend.app.services.i9.aggregation_service import rebuild_daily_bucket, rebuild_higher_bucket_from_daily_rollups
from backend.app.services.i9.baseline_service import BASELINE_METHOD, upsert_personal_observed_baseline
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.services.i9.i8_projection_service import get_i8_governed_context_projection, projection_row_count
from backend.app.services.i9.time_buckets import bucket_bounds


def _i9_device(db, owner: models.User, device_id: str) -> models.Device:
    dev = models.Device(
        user_id=owner.id,
        device_id=device_id,
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token(f"tok-{device_id}"),
    )
    db.add(dev)
    db.flush()
    return dev


def _i9_pm(db, *, subject, device, value, measured_at, key):
    row = models.PhysiologicalMeasurement(
        health_subject_id=subject.id,
        user_id=subject.linked_user_id,
        device_id=device.id,
        measurement_type="heart_rate",
        numeric_value=value,
        unit="bpm",
        measured_at=measured_at,
        received_at=datetime.now(timezone.utc),
        idempotency_key=key,
        ingestion_status="accepted",
    )
    db.add(row)
    db.flush()
    return row


def _i9_seed_hr(db, subject, device, ref, days_values: dict[int, list[float]]):
    d_start, _ = bucket_bounds("daily", ref=ref)
    for offset, values in days_values.items():
        day_start = d_start - timedelta(days=offset)
        for i, v in enumerate(values):
            _i9_pm(
                db,
                subject=subject,
                device=device,
                value=v,
                measured_at=day_start + timedelta(hours=10, minutes=i),
                key=f"i8-gate-{offset}-{i}-{v}",
            )


@pytest.fixture
def i9_family(db):
    user = _user(db, "i8-i9-user")
    user.phone = "+989100000201"
    subject = ensure_self_subject_for_account(db, user.id)
    father = create_managed_subject_without_account(
        db, account_user_id=user.id, display_name="Father", access_role="CAREGIVER"
    )
    device = _i9_device(db, user, "I8I9Dev001")
    return {"user": user, "subject": subject, "father": father, "device": device}


def test_g01_daily_hr_rollup_in_i8_context(db, i9_family, monkeypatch):
    user = i9_family["user"]
    subj = i9_family["subject"]
    dev = i9_family["device"]
    ref = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _i9_pm(db, subject=subj, device=dev, value=82.0, measured_at=d_start + timedelta(hours=1), key="g01")
    rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    ctx = load_trusted_context(db, user.id)
    assert ctx.physiological_context is not None
    assert ctx.physiological_context.daily_rollup is not None
    assert ctx.physiological_context.daily_rollup.avg_value == 82.0
    assert ctx.physiological_context.daily_rollup.bucket_kind == "daily"


def test_g02_weekly_hr_rollup_in_i8_context(db, i9_family):
    user = i9_family["user"]
    subj = i9_family["subject"]
    dev = i9_family["device"]
    ref = datetime(2026, 12, 8, 12, 0, tzinfo=timezone.utc)
    _i9_seed_hr(db, subj, dev, ref, {i: [70.0 + i] for i in range(7)})
    rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    rebuild_higher_bucket_from_daily_rollups(
        db, subject=subj, measurement_type="heart_rate", bucket_kind="weekly", ref=ref
    )
    ctx = load_trusted_context(db, user.id)
    assert ctx.physiological_context.weekly_rollup is not None
    assert ctx.physiological_context.weekly_rollup.bucket_kind == "weekly"


def test_g03_personal_observed_baseline_in_i8_context(db, i9_family):
    user = i9_family["user"]
    subj = i9_family["subject"]
    dev = i9_family["device"]
    ref = datetime(2026, 12, 10, 12, 0, tzinfo=timezone.utc)
    _i9_seed_hr(db, subj, dev, ref, {i: [70.0 + i] for i in range(7)})
    upsert_personal_observed_baseline(db, subject=subj, ref=ref)
    ctx = load_trusted_context(db, user.id)
    bl = ctx.physiological_context.personal_observed_baseline
    assert bl is not None
    assert bl.baseline_method == BASELINE_METHOD
    assert bl.valid_day_count == 7


def test_g04_no_raw_measurement_in_projection(db, i9_family):
    user = i9_family["user"]
    subj = i9_family["subject"]
    dev = i9_family["device"]
    ref = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _i9_pm(db, subject=subj, device=dev, value=99.0, measured_at=d_start + timedelta(hours=1), key="g04")
    rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    projection = get_i8_governed_context_projection(db, account_user_id=user.id)
    blob = repr(projection)
    assert "PhysiologicalMeasurement" not in blob
    assert "idempotency_key" not in blob
    assert "DevicePacket" not in blob


def test_g07_projection_bounded_max_rows(db, i9_family):
    user = i9_family["user"]
    subj = i9_family["subject"]
    dev = i9_family["device"]
    ref = datetime(2026, 12, 15, 12, 0, tzinfo=timezone.utc)
    _i9_seed_hr(db, subj, dev, ref, {i: [68.0 + i] for i in range(7)})
    rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    rebuild_higher_bucket_from_daily_rollups(
        db, subject=subj, measurement_type="heart_rate", bucket_kind="weekly", ref=ref
    )
    upsert_personal_observed_baseline(db, subject=subj, ref=ref)
    projection = get_i8_governed_context_projection(db, account_user_id=user.id)
    assert projection_row_count(projection) <= 3


def test_g08_i6_consent_blocks_personalized_action(db, i9_family, monkeypatch):
    user = i9_family["user"]
    _profile_tz(db, user.id)
    db.commit()
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
    )
    result = generate_operational_action(
        db, user_id=user.id, actor_user_id=user.id, request="healthy lunch", domain="nutrition", persist=True
    )
    assert result.status == "CONSENT_REQUIRED"
    assert result.persisted is False


def test_g09_multi_user_subject_isolation(db):
    u1 = _user(db, "iso-u1")
    u2 = _user(db, "iso-u2")
    s1 = ensure_self_subject_for_account(db, u1.id)
    s2 = ensure_self_subject_for_account(db, u2.id)
    d1 = _i9_device(db, u1, "IsoDev1")
    d2 = _i9_device(db, u2, "IsoDev2")
    ref = datetime(2026, 12, 5, 12, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _i9_pm(db, subject=s1, device=d1, value=60.0, measured_at=d_start + timedelta(hours=1), key="iso1")
    _i9_pm(db, subject=s2, device=d2, value=90.0, measured_at=d_start + timedelta(hours=1), key="iso2")
    rebuild_daily_bucket(db, subject=s1, measurement_type="heart_rate", ref=ref)
    rebuild_daily_bucket(db, subject=s2, measurement_type="heart_rate", ref=ref)
    p1 = get_i8_governed_context_projection(db, account_user_id=u1.id)
    p2 = get_i8_governed_context_projection(db, account_user_id=u2.id)
    assert p1.daily_rollup.avg_value == 60.0
    assert p2.daily_rollup.avg_value == 90.0
    assert p1.health_subject_id == s1.id
    assert p2.health_subject_id == s2.id


def test_g10_caregiver_no_managed_subject_physiology_in_i8_context(db, i9_family):
    user = i9_family["user"]
    father = i9_family["father"]
    dev = i9_family["device"]
    ref = datetime(2026, 12, 6, 12, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _i9_pm(db, subject=father, device=dev, value=55.0, measured_at=d_start + timedelta(hours=1), key="g10")
    rebuild_daily_bucket(db, subject=father, measurement_type="heart_rate", ref=ref)
    projection = get_i8_governed_context_projection(db, account_user_id=user.id)
    assert projection.daily_rollup is None or projection.health_subject_id != father.id


def test_g11_caregiver_user_id_never_substituted(db, i9_family):
    user = i9_family["user"]
    father = i9_family["father"]
    assert father.linked_user_id is None
    projection = get_i8_governed_context_projection(db, account_user_id=user.id)
    if projection.health_subject_id is not None:
        assert projection.health_subject_id != father.id
        subj = db.query(models.HealthSubject).filter_by(id=projection.health_subject_id).one()
        assert subj.linked_user_id == user.id


def test_g13_context_refs_contain_i9_provenance(db, i9_family, monkeypatch):
    user = i9_family["user"]
    subj = i9_family["subject"]
    dev = i9_family["device"]
    ref = datetime(2026, 12, 7, 12, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _i9_pm(db, subject=subj, device=dev, value=75.0, measured_at=d_start + timedelta(hours=1), key="g13")
    rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
    )
    result = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="healthy lunch",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="g13-plan",
        action_idempotency_key="g13-act",
    )
    assert result.status == "ACTION_PERSISTED"
    row = db.query(models.I8OperationalPlanAction).filter_by(id=result.action_id).one()
    refs = json.loads(row.context_refs_json or "[]")
    rollup_refs = [r for r in refs if r.get("ref_type") == "physiological_measurement_rollup"]
    assert len(rollup_refs) >= 1
    assert rollup_refs[0]["health_subject_id"] == subj.id
    assert rollup_refs[0]["measurement_type"] == "heart_rate"


def test_g14_persisted_context_refs_no_raw_arrays(db, i9_family, monkeypatch):
    user = i9_family["user"]
    subj = i9_family["subject"]
    dev = i9_family["device"]
    ref = datetime(2026, 12, 9, 12, 0, tzinfo=timezone.utc)
    _i9_seed_hr(db, subj, dev, ref, {i: [70.0 + i] for i in range(7)})
    rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    upsert_personal_observed_baseline(db, subject=subj, ref=ref)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
    )
    result = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="wellbeing tips",
        domain="wellbeing",
        persist=True,
        plan_idempotency_key="g14-plan",
        action_idempotency_key="g14-act",
    )
    row = db.query(models.I8OperationalPlanAction).filter_by(id=result.action_id).one()
    blob = row.context_refs_json or ""
    assert "daily_medians" not in blob
    assert "idempotency_key" not in blob
    assert "DevicePacket" not in blob


def test_g15_presentation_no_raw_physiological_history(db, i9_family, monkeypatch):
    user = i9_family["user"]
    subj = i9_family["subject"]
    dev = i9_family["device"]
    ref = datetime(2026, 12, 11, 12, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _i9_pm(db, subject=subj, device=dev, value=88.0, measured_at=d_start + timedelta(hours=1), key="g15")
    rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    _profile_tz(db, user.id)
    db.commit()
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
    )
    result = generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request="lunch ideas",
        domain="nutrition",
        persist=True,
        plan_idempotency_key="g15-plan",
        action_idempotency_key="g15-act",
    )
    row = db.query(models.I8OperationalPlanAction).filter_by(id=result.action_id).one()
    assert "88.0" not in (row.presentation_json or "")
    assert "physiological_measurement_rollup" not in (row.presentation_json or "")


def test_g16_knowledge_rag_path_excludes_i9_observations(db, i9_family):
    user = i9_family["user"]
    subj = i9_family["subject"]
    dev = i9_family["device"]
    ref = datetime(2026, 12, 12, 12, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _i9_pm(db, subject=subj, device=dev, value=77.0, measured_at=d_start + timedelta(hours=1), key="g16")
    rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    ctx = load_trusted_context(db, user.id)
    pers = build_personalization(ctx, domain="nutrition")
    assert pers.is_empty() is False or not ctx.goals
    blob = repr(pers)
    assert "physiological" not in blob.lower()
    assert "rollup" not in blob.lower()
    assert "baseline_value" not in blob


def test_g17_existing_safety_therapeutic_unchanged(db, monkeypatch):
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


def test_g18_idempotent_replay_unchanged(db, monkeypatch):
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
        plan_idempotency_key="g18-plan",
        action_idempotency_key="g18-act",
    )
    first = generate_operational_action(db, **kwargs)
    second = generate_operational_action(db, **kwargs)
    assert first.plan_id == second.plan_id
    assert first.action_id == second.action_id
    assert called["n"] == 1


def test_g25_future_i9_trigger_not_activated():
    from backend.app.services.i8 import constants as i8_constants
    from backend.app.services.i8 import trusted_trigger as tt

    assert "future_i9" in i8_constants.TRIGGER_FAMILIES
    src = open(tt.__file__, encoding="utf-8").read()
    assert "physiological_context" not in src
    assert "i8_projection" not in src

