"""PD-I8-04A proactive evaluation ledger + orchestrator foundation tests."""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, RetrievedKnowledgeItem
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.i8.constants import (
    EVALUATION_LIFECYCLE_STATUSES,
    EVALUATION_OUTCOMES,
    TRIGGER_FAMILIES,
)
from backend.app.services.i8.evaluation_identity import build_evaluation_identity_key
from backend.app.services.i8.proactive_orchestrator import evaluate_proactive_trigger
from backend.app.services.i8.semantic_envelope import (
    SemanticEnvelopeError,
    build_semantic_action_envelope,
    validate_semantic_envelope,
)


ROOT = Path(__file__).resolve().parents[1]


def _db_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DB03_REHEARSAL_DATABASE_URL")


def _alembic_cfg(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def test_migration_070_static_audit():
    versions = ROOT / "alembic" / "versions"
    files = list(versions.glob("070*.py"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "070_i8_proactive_evaluation_ledger" in body
    assert re.search(r"down_revision.*069_i8_operational_plan_state_foundation", body)
    assert "i8_proactive_evaluations" in body
    assert "uq_i8_eval_user_identity" in body
    assert "ACTION_CREATED" in body and "NO_ACTION" in body
    assert "FAILED_RETRYABLE" in body and "FAILED_TERMINAL" in body
    body_069 = (versions / "069_i8_operational_plan_state_foundation.py").read_text(encoding="utf-8")
    assert "i8_proactive_evaluations" not in body_069


def test_alembic_single_head_is_070():
    from alembic.script import ScriptDirectory

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["076_i10_care_network_delivery_foundation"]


def test_evaluation_identity_families():
    assert TRIGGER_FAMILIES == frozenset({"event", "schedule", "future_i9"})
    event_a = build_evaluation_identity_key(
        trigger_family="event", user_id=1, source_owner="gate2", source_ref="evt-1"
    )
    event_b = build_evaluation_identity_key(
        trigger_family="event", user_id=1, source_owner="gate2", source_ref="evt-1"
    )
    assert event_a == event_b
    assert event_a != build_evaluation_identity_key(
        trigger_family="event", user_id=2, source_owner="gate2", source_ref="evt-1"
    )
    sched = build_evaluation_identity_key(
        trigger_family="schedule",
        user_id=1,
        schedule_rule_id="morning_check",
        user_local_date=date(2026, 8, 22),
    )
    assert len(sched) == 64
    i9 = build_evaluation_identity_key(
        trigger_family="future_i9",
        user_id=1,
        signal_type="sleep_debt",
        signal_occurrence_id="occ-9",
    )
    assert len(i9) == 64
    with pytest.raises(ValueError):
        build_evaluation_identity_key(trigger_family="event", user_id=1)


def test_semantic_envelope_rejects_sn_and_raw_i5():
    ok = build_semantic_action_envelope(
        user_id=1,
        domain="nutrition",
        action_type="meal_suggestion",
        sanitized_presentation_meaning="Governed nutrition action",
        safety_state="SAFE",
        knowledge_refs=[{"knowledge_unit_id": 1}],
    )
    validate_semantic_envelope(ok)
    with pytest.raises(SemanticEnvelopeError):
        validate_semantic_envelope({**ok, "notification_title": "Hi"})
    with pytest.raises(SemanticEnvelopeError):
        validate_semantic_envelope({**ok, "title": "Nope"})
    with pytest.raises(SemanticEnvelopeError):
        build_semantic_action_envelope(
            user_id=1,
            domain="nutrition",
            action_type="meal_suggestion",
            sanitized_presentation_meaning="contains diagnosis: diabetes",
            safety_state="SAFE",
            knowledge_refs=[],
        )
    assert EVALUATION_OUTCOMES == frozenset({"ACTION_CREATED", "NO_ACTION"})
    assert "FAILED_RETRYABLE" in EVALUATION_LIFECYCLE_STATUSES


def test_orm_evaluation_table_registered():
    assert "i8_proactive_evaluations" in models.Base.metadata.tables
    cols = {c.name for c in models.I8ProactiveEvaluation.__table__.columns}
    assert {
        "user_id",
        "trigger_family",
        "evaluation_identity_key",
        "lifecycle_status",
        "outcome",
        "plan_id",
        "action_id",
    } <= cols


@pytest.fixture(scope="session")
def _i8_070_tables_present():
    url = _db_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    engine = create_engine(url)
    try:
        if engine.dialect.name == "postgresql" and not inspect(engine).has_table(
            "i8_proactive_evaluations"
        ):
            pytest.skip("i8_proactive_evaluations not present (alembic 070 required)")
    finally:
        engine.dispose()


@pytest.fixture()
def db(_i8_070_tables_present):
    url = _db_url()
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


def _user(db, name: str = "i8-p") -> models.User:
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


def _empty_retrieval(*_a, **_k):
    return SimpleNamespace(status=STATUS_OK, items=[])


def _grant_and_seed(db, user_id: int) -> None:
    grant_memory_consent(db, user_id, commit=True)
    write_fact(db, user_id, "lifestyle", "diet_notes", "home cooking", commit=True)


def test_db_uniqueness_on_evaluation_identity(db):
    user = _user(db, "uniq")
    db.add(
        models.I8ProactiveEvaluation(
            user_id=user.id,
            trigger_family="event",
            evaluation_identity_key="same-key",
            lifecycle_status="COMPLETED",
            outcome="NO_ACTION",
        )
    )
    db.flush()
    db.add(
        models.I8ProactiveEvaluation(
            user_id=user.id,
            trigger_family="event",
            evaluation_identity_key="same-key",
            lifecycle_status="IN_PROGRESS",
            outcome=None,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_no_action_path_durable(db, monkeypatch):
    user = _user(db, "noact")
    _profile_tz(db, user.id)
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        _empty_retrieval,
    )
    first = evaluate_proactive_trigger(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        trigger_family="event",
        request="what should I eat",
        source_owner="test",
        source_ref="no-action-1",
    )
    assert first.outcome == "NO_ACTION"
    assert first.lifecycle_status == "COMPLETED"
    assert first.plan_id is None and first.action_id is None
    assert db.query(models.I8ProactiveEvaluation).filter_by(user_id=user.id).count() == 1
    assert db.query(models.I8OperationalPlan).filter_by(user_id=user.id).count() == 0

    second = evaluate_proactive_trigger(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        trigger_family="event",
        request="what should I eat",
        source_owner="test",
        source_ref="no-action-1",
    )
    assert second.reused is True
    assert second.status == "EVALUATION_REUSED"
    assert db.query(models.I8ProactiveEvaluation).filter_by(user_id=user.id).count() == 1


def test_action_created_and_idempotent_replay(db, monkeypatch):
    user = _user(db, "act")
    _profile_tz(db, user.id)
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        _ok_retrieval,
    )
    first = evaluate_proactive_trigger(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        trigger_family="schedule",
        request="suggest a lunch plan",
        schedule_rule_id="midday",
        user_local_date=date(2026, 8, 22),
    )
    assert first.outcome == "ACTION_CREATED"
    assert first.plan_id is not None and first.action_id is not None
    assert first.semantic_envelope is not None
    assert "notification_title" not in first.semantic_envelope
    assert db.query(models.I8OperationalPlanAction).filter_by(user_id=user.id).count() == 1

    second = evaluate_proactive_trigger(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        trigger_family="schedule",
        request="suggest a lunch plan",
        schedule_rule_id="midday",
        user_local_date=date(2026, 8, 22),
    )
    assert second.reused is True
    assert second.evaluation_id == first.evaluation_id
    assert db.query(models.I8ProactiveEvaluation).filter_by(user_id=user.id).count() == 1
    assert db.query(models.I8OperationalPlanAction).filter_by(user_id=user.id).count() == 1


def test_terminal_failure_not_silently_duplicated(db, monkeypatch):
    user = _user(db, "term")
    _profile_tz(db, user.id)
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        _ok_retrieval,
    )
    first = evaluate_proactive_trigger(
        db,
        user_id=user.id,
        actor_user_id=user.id + 999,
        trigger_family="event",
        request="diagnose my hypertension",
        source_owner="test",
        source_ref="term-1",
    )
    assert first.lifecycle_status == "FAILED_TERMINAL"
    assert first.outcome is None
    second = evaluate_proactive_trigger(
        db,
        user_id=user.id,
        actor_user_id=user.id + 999,
        trigger_family="event",
        request="diagnose my hypertension",
        source_owner="test",
        source_ref="term-1",
    )
    assert second.reused is True
    assert second.status == "EVALUATION_TERMINAL"
    assert db.query(models.I8ProactiveEvaluation).filter_by(user_id=user.id).count() == 1


def test_retryable_reopens_same_identity(db):
    user = _user(db, "retry")
    identity = build_evaluation_identity_key(
        trigger_family="event", user_id=user.id, source_owner="x", source_ref="retry-1"
    )
    row = models.I8ProactiveEvaluation(
        user_id=user.id,
        trigger_family="event",
        evaluation_identity_key=identity,
        lifecycle_status="FAILED_RETRYABLE",
        outcome=None,
    )
    db.add(row)
    db.flush()
    result = evaluate_proactive_trigger(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        trigger_family="event",
        request="hydration reminder",
        source_owner="x",
        source_ref="retry-1",
    )
    assert db.query(models.I8ProactiveEvaluation).filter_by(user_id=user.id).count() == 1
    assert result.evaluation_id == row.id
    assert result.lifecycle_status in {"FAILED_RETRYABLE", "COMPLETED", "FAILED_TERMINAL"}


def test_pd_i8_04b_schedule_adapter_reaches_ledger(db, monkeypatch):
    """PD-I8-04B: TrustedTrigger schedule adapter → existing orchestrator → 070 ledger."""
    from backend.app.services.i8.schedule_adapter import adapt_trusted_schedule_trigger
    from backend.app.services.i8.schedule_rules import SCHEDULE_RULE_DAILY_WELLBEING_CHECK
    from backend.app.services.i8.trusted_trigger import (
        TRUSTED_PRODUCER_I8_SCHEDULE_SCAN_V1,
        TrustedTriggerV1,
    )

    user = _user(db, "sched04b")
    _profile_tz(db, user.id)
    _grant_and_seed(db, user.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        _empty_retrieval,
    )
    trigger = TrustedTriggerV1(
        producer_id=TRUSTED_PRODUCER_I8_SCHEDULE_SCAN_V1,
        user_id=user.id,
        trigger_family="schedule",
        schedule_rule_id=SCHEDULE_RULE_DAILY_WELLBEING_CHECK,
        user_local_date=date(2026, 8, 22),
        producer_attempt_id="ci-attempt-1",
    )
    first = adapt_trusted_schedule_trigger(db, trigger)
    assert first.outcome == "NO_ACTION"
    assert first.lifecycle_status == "COMPLETED"
    assert db.query(models.I8ProactiveEvaluation).filter_by(user_id=user.id).count() == 1
    second = adapt_trusted_schedule_trigger(db, trigger)
    assert second.reused is True
    assert db.query(models.I8ProactiveEvaluation).filter_by(user_id=user.id).count() == 1


def test_pd_i8_04b_flag_off_scan_zero_evaluation(monkeypatch, db):
    from backend.app.services.i8.feature_flags import I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG
    from backend.app.services.i8.schedule_scan import run_i8_proactive_schedule_scan

    monkeypatch.delenv(I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG, raising=False)
    before = db.query(models.I8ProactiveEvaluation).count()
    stats = run_i8_proactive_schedule_scan(db)
    assert stats.flag_enabled is False
    assert stats.trigger_attempts == 0
    assert stats.evaluation_success == 0
    assert db.query(models.I8ProactiveEvaluation).count() == before


@pytest.mark.skipif(not _db_url(), reason="No TEST_DATABASE_URL")
def test_069_to_070_upgrade_rehearsal():
    if os.environ.get("DB03_ALLOW_DESTRUCTIVE_REHEARSAL") != "YES":
        pytest.skip("Set DB03_ALLOW_DESTRUCTIVE_REHEARSAL=YES")
    url = _db_url()
    assert url
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "069_i8_operational_plan_state_foundation")
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert head == "069_i8_operational_plan_state_foundation"
        assert not inspect(engine).has_table("i8_proactive_evaluations")
    command.upgrade(cfg, "070_i8_proactive_evaluation_ledger")
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert head == "070_i8_proactive_evaluation_ledger"
        assert inspect(engine).has_table("i8_proactive_evaluations")
        uniques = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'i8_proactive_evaluations'::regclass AND contype = 'u'"
                )
            )
        }
        assert "uq_i8_eval_user_identity" in uniques
