"""PD-I8-03 unified I8 runtime foundation tests."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app import models
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, RetrievedKnowledgeItem
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.i8.constants import PRESENTATION_JSON_MAX_BYTES
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i8.unified_core import generate_operational_action, infer_domain, _validate_presentation


def _user(db, name: str = "i8-u") -> models.User:
    row = models.User(name=name, secret_key="k", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _ok_item() -> RetrievedKnowledgeItem:
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
        normalized_statement="Eat balanced meals",
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


@pytest.fixture(autouse=True)
def _skip_without_i8_tables(db):
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        insp = __import__("sqlalchemy").inspect(bind)
        if not insp.has_table("i8_operational_plans"):
            pytest.skip("i8_operational_plans not present (alembic 069 required)")


def test_orm_tables_registered():
    assert "i8_operational_plans" in models.Base.metadata.tables
    assert "i8_operational_plan_actions" in models.Base.metadata.tables
    plan = models.I8OperationalPlan.__table__
    assert "uq_i8_plan_id_user" in {c.name for c in plan.constraints if getattr(c, "name", None)}


def test_infer_domains():
    assert infer_domain("what should I eat for lunch") == "nutrition"
    assert infer_domain("morning walk plan") == "exercise"
    assert infer_domain("breakfast and walk") == "cross_domain"


def test_local_day_window(db):
    user = _user(db)
    db.commit()
    window = resolve_local_day_window(db, user.id)
    assert window.user_local_date is not None
    assert window.expires_at > window.valid_until


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


def test_allergy_hard_constraint(db, monkeypatch):
    user = _user(db)
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


def test_i5_gateway_used_not_vector(db, monkeypatch):
    user = _user(db)
    db.commit()
    _grant_and_seed(db, user.id)
    called = {"n": 0}

    def _fake(db, **kwargs):
        called["n"] += 1
        return SimpleNamespace(status=STATUS_OK, items=[_ok_item()])

    monkeypatch.setattr("backend.app.services.i8.unified_core.retrieve_governed_knowledge", _fake)
    result = generate_operational_action(
        db, user_id=user.id, actor_user_id=user.id, request="healthy lunch", domain="nutrition", persist=True
    )
    assert called["n"] == 1
    assert result.status == "ACTION_PERSISTED"
    assert result.knowledge_refs
    assert "normalized_statement" not in json.dumps(result.knowledge_refs)


def test_reactive_domains(db, monkeypatch):
    user = _user(db)
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
    db.commit()
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item()]),
    )
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
    assert db.query(models.I8OperationalPlan).filter_by(user_id=user.id).count() == 1
    assert db.query(models.I8OperationalPlanAction).filter_by(user_id=user.id).count() == 1


def test_cross_user_action_rejected(db):
    user_a = _user(db, "a")
    user_b = _user(db, "b")
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
