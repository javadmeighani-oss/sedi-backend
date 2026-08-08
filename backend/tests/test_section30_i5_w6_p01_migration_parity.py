"""I5-IMPL-W6-P01 — Alembic migration parity / upgrade-downgrade-reupgrade (PostgreSQL).

Requires DATABASE_URL / TEST_DATABASE_URL pointing at ephemeral PostgreSQL.
Does NOT use Base.metadata.create_all for schema proof.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

REQUIRED_TABLES = [
    "governed_source_profiles",
    "governed_source_profile_versions",
    "weekly_knowledge_runs",
    "weekly_knowledge_run_attempts",
    "knowledge_gaps",
    "weekly_run_source_results",
    "weekly_run_gap_results",
    "i5_governance_decisions",
    "i5_raw_evidence",
    "knowledge_units",
    "knowledge_provenance",
    "knowledge_memory_items",
    "knowledge_memory_transitions",
    "knowledge_conflicts",
    "knowledge_safety_reviews",
    "iran_doctors",
    "iran_laboratories",
    "iran_hospitals",
]

GSP_W1_COLS = [
    "registry_state",
    "runtime_eligibility",
    "block_reason",
    "owner_reference",
    "reviewer_reference",
    "approver_reference",
    "topic_coverage",
    "effective_from",
    "effective_to",
    "last_discovered_at",
    "last_checked_at",
    "last_reviewed_at",
    "canonicalization_version",
]

HEAD = "056_i5_w2_p02_conflict_safety"
BASE_052 = "052_i5_w5_iran_directory"


def _db_url() -> str:
    url = (os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        pytest.skip("DATABASE_URL/TEST_DATABASE_URL required for migration parity")
    return url


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _backend_root() -> Path:
    return _workspace_root() / "backend"


def _alembic_cfg(url: str) -> Config:
    """Bind Alembic to backend/alembic.ini (repository convention)."""
    os.environ["DATABASE_URL"] = url
    os.environ["TEST_DATABASE_URL"] = url
    backend = _backend_root()
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    # Percent-escape for ConfigParser; env.py also sets URL from env.
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def _current_revision(engine) -> str | None:
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT to_regclass('alembic_version') IS NOT NULL")
        ).scalar()
        if not exists:
            return None
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        return row[0] if row else None


def test_W6P01_MIG_T01_repository_heads_single() -> None:
    script = ScriptDirectory(str(_backend_root() / "alembic"))
    heads = script.get_heads()
    assert heads == [HEAD], heads


def test_W6P01_MIG_T02_upgrade_052_then_head_parity() -> None:
    url = _db_url()
    engine = create_engine(url)
    cfg = _alembic_cfg(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(cfg, BASE_052)
    assert _current_revision(engine) == BASE_052
    insp = inspect(engine)
    assert "governed_source_profiles" in insp.get_table_names()
    gsp_cols_052 = {c["name"] for c in insp.get_columns("governed_source_profiles")}
    assert "registry_state" not in gsp_cols_052

    command.upgrade(cfg, "head")
    assert _current_revision(engine) == HEAD
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    missing = [t for t in REQUIRED_TABLES if t not in tables]
    assert missing == [], missing
    gsp_cols = {c["name"] for c in insp.get_columns("governed_source_profiles")}
    for col in GSP_W1_COLS:
        assert col in gsp_cols, col
    # Named check presence (sample)
    ck_names = {c["name"] for c in insp.get_check_constraints("weekly_knowledge_runs")}
    assert "ck_wkr_status_vocab" in ck_names
    ku_cks = {c["name"] for c in insp.get_check_constraints("knowledge_units")}
    assert "ck_ku_eligible_requires_provenance" in ku_cks


def test_W6P01_MIG_T03_downgrade_to_052_and_reupgrade() -> None:
    url = _db_url()
    engine = create_engine(url)
    cfg = _alembic_cfg(url)
    # Assume prior test left DB at head OR reset
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(cfg, "head")
    assert _current_revision(engine) == HEAD
    command.downgrade(cfg, BASE_052)
    assert _current_revision(engine) == BASE_052
    insp = inspect(engine)
    assert "weekly_knowledge_runs" not in insp.get_table_names()
    gsp_cols = {c["name"] for c in insp.get_columns("governed_source_profiles")}
    assert "registry_state" not in gsp_cols
    command.upgrade(cfg, "head")
    assert _current_revision(engine) == HEAD
    insp = inspect(engine)
    assert "knowledge_safety_reviews" in insp.get_table_names()
    assert "knowledge_units" in insp.get_table_names()


def test_W6P01_MIG_T04_fk_gap_to_ku_exists_at_head() -> None:
    url = _db_url()
    engine = create_engine(url)
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "head")
    insp = inspect(engine)
    fks = insp.get_foreign_keys("knowledge_gaps")
    names = {fk.get("name") for fk in fks}
    assert "fk_knowledge_gaps_target_knowledge_unit_id" in names
