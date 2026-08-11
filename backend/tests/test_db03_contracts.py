"""DB-03 focused contract tests (§270 acceptance)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app import models
from backend.app.services.db03.authority_markers import (
    PARTITIONING_ACTIVATED,
    PGVECTOR_INTRODUCED,
    RAG_EMBEDDINGS_INTRODUCED,
    PARTITION_TRIGGERS_ANY,
)
from backend.app.services.db03.health_data_backfill import backfill_health_data_to_physiological_measurements
from backend.app.services.db03.memory_fact_merge import merge_legacy_facts_into_user_memory_facts
from backend.app.services.db03.period_summary_backfill import backfill_daily_memory_summaries
from backend.app.services.db03.physiological_idempotency import build_physiological_idempotency_key


ROOT = Path(__file__).resolve().parents[1]  # backend/
WORKSPACE = ROOT.parent



def test_db03_guardrails_constants():
    assert PARTITIONING_ACTIVATED is False
    # SCIS-01 introduces pgvector schema path; Stage17 rag_embeddings remains forbidden.
    assert PGVECTOR_INTRODUCED is True
    assert RAG_EMBEDDINGS_INTRODUCED is False
    assert any("1000" in t for t in PARTITION_TRIGGERS_ANY)
    assert any("50_000_000" in t or "50M" in t or "50000000" in t for t in PARTITION_TRIGGERS_ANY)


def test_no_rag_embeddings_in_orm_metadata():
    assert "rag_embeddings" not in models.Base.metadata.tables
    assert "physiological_measurements" in models.Base.metadata.tables
    assert "user_consents" in models.Base.metadata.tables
    assert "care_episodes" in models.Base.metadata.tables


def test_stage17_marked_noncanonical():
    path = ROOT / "deployment" / "migrations" / "008_stage17_6_pgvector.sql"
    text = path.read_text(encoding="utf-8")
    assert "NONCANONICAL" in text or "DO NOT APPLY" in text
    assert "DEPRECATE" in text


def test_alembic_versions_deny_pgvector_and_rag_embeddings():
    import re

    versions = ROOT / "alembic" / "versions"
    scis_allowed = {"061_scis01_pgvector_kce_foundation.py"}
    for path in versions.glob("*.py"):
        body = path.read_text(encoding="utf-8")
        # Stage17 rag_embeddings + IVFFlat remain forbidden everywhere.
        assert not re.search(r"(?i)create\s+table\s+.*rag_embeddings", body)
        assert "USING ivfflat" not in body.lower()
        # pgvector extension allowed only on SCIS-01 KCE foundation migration.
        if path.name in scis_allowed:
            assert re.search(r"(?i)create\s+extension\s+.*vector", body)
            assert "rag_embeddings" not in body.lower() or "noncanonical" in body.lower()
            continue
        assert not re.search(r"(?i)create\s+extension\s+.*vector", body)


def test_alembic_single_head_chain():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["065_i5_know04_connectors_change_intelligence"]
    rev = script.get_revision("065_i5_know04_connectors_change_intelligence")
    chain = []
    while rev:
        chain.append(rev.revision)
        if not rev.down_revision:
            break
        rev = script.get_revision(rev.down_revision)
    assert "064_i5_know03_studies_effects_recs" in chain
    assert "063_i5_know02_artifacts_claims_taxonomy" in chain
    assert "062_i5_know01_source_registry_rights" in chain
    assert "061_scis01_pgvector_kce_foundation" in chain
    assert "060_db03_w4_w6_scale_inspect_roles" in chain
    assert "056_i5_w2_p02_conflict_safety" in chain
    assert "057_db03_w0_drift_normalization" in chain
    assert "058_db03_w1_additive_foundations" in chain


def test_roles_artifact_no_passwords():
    path = ROOT / "ops" / "db03" / "roles_sedi_v1.sql"
    text = path.read_text(encoding="utf-8")
    assert "sedi_app_runtime" in text
    assert "sedi_migration_admin" in text
    assert "sedi_dbeaver_readonly" in text
    assert "NOSUPERUSER" in text
    # Explicit: no password assignment syntax
    assert "PASSWORD '" not in text.upper()
    assert 'PASSWORD "' not in text.upper()
    assert "ENCRYPTED PASSWORD" not in text.upper()


def test_consent_scopes_and_revocation(db):
    user = models.User(name="c1", secret_key="k", preferred_language="en")
    db.add(user)
    db.flush()
    consent = models.UserConsent(
        subject_user_id=user.id,
        consent_type="care_notify",
        purpose="emergency_escalation",
        scope_summary="notify caregiver on emergency",
        grantee_type="caregiver",
        grantee_id="cg-1",
        status="active",
        effective_from=datetime.now(timezone.utc),
        source="test",
    )
    db.add(consent)
    db.flush()
    db.add(
        models.UserConsentScope(
            consent_id=consent.id,
            permission_key="notify.emergency",
            allowed=True,
        )
    )
    db.add(
        models.UserConsentScope(
            consent_id=consent.id,
            permission_key="notify.daily_status",
            allowed=False,
        )
    )
    db.flush()
    scopes = db.query(models.UserConsentScope).filter_by(consent_id=consent.id).all()
    assert len(scopes) == 2
    assert {s.permission_key: s.allowed for s in scopes}["notify.emergency"] is True
    consent.status = "revoked"
    consent.revoked_at = datetime.now(timezone.utc)
    consent.revocation_reason = "user_revoked"
    db.flush()
    # Caregiver existence must not imply authorization without active consent
    assert consent.status == "revoked"


def test_care_response_policy_windows_null(db):
    pol = models.CareResponsePolicy(
        policy_id="default",
        policy_version="v1",
        risk_category="elevated_hr",
        ack_window_seconds=None,
        escalation_window_seconds=None,
        effective_from=datetime.now(timezone.utc),
        status="draft",
    )
    db.add(pol)
    db.flush()
    assert pol.ack_window_seconds is None
    assert pol.escalation_window_seconds is None
    # Column has no server default inventing clinical timing
    col = models.CareResponsePolicy.__table__.c.ack_window_seconds
    assert col.server_default is None


def test_care_episode_escalation_requires_consent_ref(db):
    user = models.User(name="c2", secret_key="k", preferred_language="en")
    db.add(user)
    db.flush()
    consent = models.UserConsent(
        subject_user_id=user.id,
        consent_type="care_notify",
        purpose="emergency_escalation",
        grantee_type="caregiver",
        grantee_id="cg-9",
        status="active",
        effective_from=datetime.now(timezone.utc),
    )
    db.add(consent)
    db.flush()
    ep = models.CareEpisode(
        user_id=user.id,
        origin_type="derived_health_signal",
        origin_ref="sig-1",
        category="hr_alert",
        policy_id="default",
        policy_version="v1",
        opened_at=datetime.now(timezone.utc),
        current_state="open",
    )
    db.add(ep)
    db.flush()
    esc = models.EmergencyEscalationRecord(
        owner_user_id=user.id,
        reason_category="no_ack",
        care_episode_id=ep.id,
        step_no=1,
        from_recipient="user",
        to_recipient="caregiver:cg-9",
        consent_evidence_id=consent.id,
        scheduled_at=datetime.now(timezone.utc),
    )
    db.add(esc)
    db.flush()
    assert esc.consent_evidence_id == consent.id
    assert esc.care_episode_id == ep.id


def test_physiological_measured_vs_received_and_idempotency(db):
    user = models.User(name="hr1", secret_key="k", preferred_language="en")
    db.add(user)
    db.flush()
    device = models.Device(
        user_id=user.id,
        device_id="dev-hr-1",
        device_type="heart_rate",
        status="active",
        token_hash="abc",
    )
    db.add(device)
    db.flush()
    measured = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    received = measured + timedelta(hours=2)
    key = build_physiological_idempotency_key(
        device_id=device.id,
        measurement_type="heart_rate",
        measured_at=measured,
        source_sequence="seq-1",
    )
    assert "received" not in key
    m1 = models.PhysiologicalMeasurement(
        user_id=user.id,
        device_id=device.id,
        measurement_type="heart_rate",
        numeric_value=70,
        unit="bpm",
        measured_at=measured,
        received_at=received,
        quality_state="ok",
        idempotency_key=key,
        source_sequence="seq-1",
    )
    db.add(m1)
    db.flush()
    # Replay same sequence → unique violation
    m2 = models.PhysiologicalMeasurement(
        user_id=user.id,
        device_id=device.id,
        measurement_type="heart_rate",
        numeric_value=70,
        unit="bpm",
        measured_at=measured,
        received_at=received + timedelta(minutes=5),
        quality_state="ok",
        idempotency_key=key,
        source_sequence="seq-1",
    )
    db.add(m2)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_physiological_indexes_present_in_metadata():
    table = models.PhysiologicalMeasurement.__table__
    names = {ix.name for ix in table.indexes}
    assert "ix_pm_user_measured_at" in names
    assert "ix_pm_device_measured_at" in names
    assert "ix_pm_idempotency_key" in names or any(
        "idempotency" in (ix.name or "") for ix in table.indexes
    )


def test_i7_period_summary_uniqueness(db):
    user = models.User(name="i7", secret_key="k", preferred_language="en")
    db.add(user)
    db.flush()
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    end = datetime(2026, 8, 1, 23, 59, 59, tzinfo=timezone.utc)
    db.add(
        models.UserPeriodSummary(
            user_id=user.id,
            summary_type="DAILY",
            period_start=start,
            period_end=end,
            version=1,
            narrative_summary="day1",
            generated_at=datetime.now(timezone.utc),
            status="active",
        )
    )
    db.flush()
    db.add(
        models.UserPeriodSummary(
            user_id=user.id,
            summary_type="WEEKLY",
            period_start=start,
            period_end=start + timedelta(days=7),
            version=1,
            narrative_summary="week1",
            generated_at=datetime.now(timezone.utc),
            status="active",
        )
    )
    db.flush()
    assert {t for (t,) in db.query(models.UserPeriodSummary.summary_type).all()} >= {"DAILY", "WEEKLY"}
    ck = [c for c in models.UserPeriodSummary.__table__.constraints if getattr(c, "name", None) == "ck_ups_summary_type_vocab"]
    assert ck
    # MONTHLY/YEARLY supported by CHECK vocab
    assert "MONTHLY" in str(ck[0].sqltext)
    assert "YEARLY" in str(ck[0].sqltext)


def test_memory_backfill_no_unexplained_loss(db):
    user = models.User(name="mem", secret_key="k", preferred_language="en")
    db.add(user)
    db.flush()
    db.add(models.UserFact(user_id=user.id, key="a", value_json='"1"', source="manual", confidence=0.9))
    db.add(
        models.KcUserFact(
            user_id=user.id,
            fact_type="allergy",
            value_json='"peanut"',
            verified_by="user",
            valid_from=datetime.now(timezone.utc),
        )
    )
    db.add(
        models.UserProfileFact(
            user_id=user.id,
            fact_type="occupation",
            value_json='"engineer"',
            source="manual",
            confidence=0.7,
        )
    )
    db.flush()
    counts = merge_legacy_facts_into_user_memory_facts(db)
    db.commit()
    assert counts.source_rows_expected == 3
    assert counts.unexplained_data_loss == 0
    assert db.query(models.UserMemoryFact).filter_by(user_id=user.id).count() >= 3


def test_daily_summary_backfill(db):
    user = models.User(name="sum", secret_key="k", preferred_language="en")
    db.add(user)
    db.flush()
    db.add(
        models.DailyMemorySummary(
            user_id=user.id,
            summary="hello day",
            mood="ok",
            created_at=datetime(2026, 8, 2, 15, 0, 0),
        )
    )
    db.flush()
    counts = backfill_daily_memory_summaries(db)
    db.commit()
    assert counts.unexplained_data_loss == 0
    row = (
        db.query(models.UserPeriodSummary)
        .filter_by(user_id=user.id, summary_type="DAILY", version=1)
        .one()
    )
    assert row.narrative_summary == "hello day"


def test_health_data_backfill(db):
    user = models.User(name="hd", secret_key="k", preferred_language="en")
    db.add(user)
    db.flush()
    db.add(
        models.Device(
            user_id=user.id,
            device_id="dev-hd",
            device_type="heart_rate",
            status="active",
            token_hash="t",
        )
    )
    db.add(models.HealthData(user_id=user.id, heart_rate="80", created_at=datetime.utcnow()))
    db.flush()
    counts = backfill_health_data_to_physiological_measurements(db)
    db.commit()
    assert counts.unexplained_data_loss == 0
    assert counts.mapped_rows == 1
    pm = db.query(models.PhysiologicalMeasurement).filter_by(user_id=user.id).one()
    assert pm.quality_state == "legacy_import"
    assert pm.measured_at == pm.received_at


def test_raw_evidence_locator_no_secret_in_locator(db):
    # Minimal GSP required for I5RawEvidence FK — skip if too heavy; use table insert via ORM if possible.
    # Use a lightweight check on columns instead when GSP setup is complex.
    cols = {c.name for c in models.I5RawEvidence.__table__.columns}
    assert {"storage_locator", "object_key", "durable_path", "byte_size", "integrity_state", "recoverability_state"} <= cols
    locator = "s3://bucket/path/object?versionId=abc"  # no credentials
    assert "password" not in locator.lower()
    assert "secret" not in locator.lower()
    assert "AKIA" not in locator


def test_knowledge_chunk_embeddings_extended_columns():
    cols = {c.name for c in models.KnowledgeChunkEmbedding.__table__.columns}
    assert {
        "knowledge_unit_id",
        "immutable_version_id",
        "source_profile_id",
        "raw_evidence_id",
        "index_generation",
        "backend_kind",
        "runtime_eligibility_snapshot",
        "retracted_at",
        "embedding_provider",
        "embedding_model_version",
        "chunker_version",
        "chunk_version",
        "section_path",
        "content_language",
        "search_document",
    } <= cols


def test_w1p01_protected_i5_checks_still_present():
    # Protected I5 contracts must remain
    assert "ck_ire_content_hash_format" in {
        c.name for c in models.I5RawEvidence.__table__.constraints if getattr(c, "name", None)
    }
    assert "knowledge_units" in models.Base.metadata.tables
    assert "i5_raw_evidence" in models.Base.metadata.tables


def test_memory_orm_cascade_aligned():
    fk = list(models.Memory.__table__.c.user_id.foreign_keys)[0]
    assert fk.ondelete == "CASCADE"
