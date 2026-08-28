"""DB-03 Alembic migration rehearsal (isolated PostgreSQL only)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]  # backend/


def _url() -> str | None:
    return os.environ.get("DB03_REHEARSAL_DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")


def _alembic_cfg(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


@pytest.mark.skipif(not _url(), reason="No isolated TEST_DATABASE_URL / DB03_REHEARSAL_DATABASE_URL")
def test_fresh_upgrade_to_db03_head():
    url = _url()
    assert url
    # Destructive for dedicated rehearsal DB only — require explicit marker.
    if os.environ.get("DB03_ALLOW_DESTRUCTIVE_REHEARSAL") != "YES":
        pytest.skip("Set DB03_ALLOW_DESTRUCTIVE_REHEARSAL=YES for fresh upgrade rehearsal")
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert head == "071_i9_health_subject_device_packet_foundation"
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
        for required in (
            "user_consents",
            "user_consent_scopes",
            "user_period_summaries",
            "physiological_measurements",
            "care_episodes",
            "care_response_policies",
            "care_episode_links",
            "i5_source_registry_extensions",
            "i5_reference_books",
            "i5_scientific_artifacts",
            "i5_clinical_concepts",
            "i5_clinical_studies",
            "i5_study_effect_estimates",
            "i5_clinical_recommendations",
            "i5_connector_profiles",
            "i5_scientific_change_events",
            "user_lifelong_profiles",
            "user_memory_export_jobs",
            "user_memory_purge_receipts",
            "user_i7_derived_patterns",
            "i8_operational_plans",
            "i8_operational_plan_actions",
            "i8_proactive_evaluations",
        ):
            assert required in tables
        cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='memory' AND table_schema='public'"
                )
            )
        }
        for required_col in (
            "retain_until",
            "consent_id",
            "provenance_json",
            "idempotency_key",
            "period_timezone",
            "period_week_start",
            "local_period_date",
            "durable_write",
        ):
            assert required_col in cols
        assert "rag_embeddings" not in tables
        assert conn.execute(text("SELECT count(*) FROM pg_extension WHERE extname='vector'")).scalar() == 1
        # Required HR indexes
        idx = {
            r[0]
            for r in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename='physiological_measurements'")
            )
        }
        assert "ix_pm_user_measured_at" in idx
        assert "ix_pm_device_measured_at" in idx
        # Clinical windows unset
        seeded = conn.execute(
            text(
                "SELECT count(*) FROM care_response_policies "
                "WHERE ack_window_seconds IS NOT NULL OR escalation_window_seconds IS NOT NULL"
            )
        ).scalar()
        assert seeded == 0
        # Views
        views = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.views WHERE table_schema='public'")
            )
        }
        for v in (
            "vw_user_memory_overview",
            "vw_user_heart_rate_daily",
            "vw_notification_reaction_timeline",
            "vw_open_care_episodes",
            "vw_knowledge_runtime_status",
            "vw_crawler_latest_runs",
        ):
            assert v in views


@pytest.mark.skipif(not _url(), reason="No isolated TEST_DATABASE_URL / DB03_REHEARSAL_DATABASE_URL")
def test_upgrade_from_056_with_synthetic_seed():
    url = _url()
    assert url
    if os.environ.get("DB03_ALLOW_DESTRUCTIVE_REHEARSAL") != "YES":
        pytest.skip("Set DB03_ALLOW_DESTRUCTIVE_REHEARSAL=YES for 056→head rehearsal")
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "056_i5_w2_p02_conflict_safety")
    # Seed via script helpers inline (bounded synthetic)
    from backend.scripts import db03_seed_056_synthetic as seed_mod

    os.environ["TEST_DATABASE_URL"] = url
    assert seed_mod.main() == 0
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert head == "071_i9_health_subject_device_packet_foundation"
        ups = conn.execute(text("SELECT count(*) FROM user_period_summaries")).scalar()
        assert ups >= 1
        # health_data backfill may map if device present
        pm = conn.execute(text("SELECT count(*) FROM physiological_measurements")).scalar()
        assert pm >= 1
        assert conn.execute(text("SELECT count(*) FROM pg_extension WHERE extname='vector'")).scalar() == 1



@pytest.mark.skipif(not _url(), reason="No isolated TEST_DATABASE_URL / DB03_REHEARSAL_DATABASE_URL")
def test_i7_wave2_067_068_roundtrip():
    """Structural upgrade/downgrade/re-upgrade rehearsal for 068 (test DB only)."""
    url = _url()
    assert url
    if os.environ.get("DB03_ALLOW_DESTRUCTIVE_REHEARSAL") != "YES":
        pytest.skip("Set DB03_ALLOW_DESTRUCTIVE_REHEARSAL=YES for 067↔068 rehearsal")
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "067_i7_lifelong_memory_foundation")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
            "067_i7_lifelong_memory_foundation"
        )
        assert "user_memory_purge_receipts" not in {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
    command.upgrade(cfg, "068_i7_wave2_governed_memory_lifecycle")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
            "068_i7_wave2_governed_memory_lifecycle"
        )
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
        assert "user_memory_purge_receipts" in tables
        assert "user_i7_derived_patterns" in tables
    command.downgrade(cfg, "067_i7_lifelong_memory_foundation")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
            "067_i7_lifelong_memory_foundation"
        )
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
        assert "user_memory_purge_receipts" not in tables
        assert "user_i7_derived_patterns" not in tables
    command.upgrade(cfg, "068_i7_wave2_governed_memory_lifecycle")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
            "068_i7_wave2_governed_memory_lifecycle"
        )
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
        assert "user_memory_purge_receipts" in tables
        assert "user_i7_derived_patterns" in tables
