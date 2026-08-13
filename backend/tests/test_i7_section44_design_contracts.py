"""Section44 design contracts against current schema/services. No protected mutation."""

from __future__ import annotations

import inspect
from pathlib import Path

from backend.app import models
from backend.app.services.db03.authority_markers import (
    DEPRECATED_AUTHORITIES,
    RAG_EMBEDDINGS_INTRODUCED,
)
from backend.app.services.i6.memory_writes import UNSUPPORTED_MEDICAL_INFERENCE
from backend.app.services.i7.jobs import period_summary_cron_kwargs, period_summary_jobs_enabled
from backend.app.services.i7.period_summaries import SUMMARY_TYPES, period_bounds
from backend.app.services.i8.nutrition_planner import plan_nutrition


ROOT = Path(__file__).resolve().parents[2]


def test_canonical_umf_has_history_consent_and_validity():
    cols = set(models.UserMemoryFact.__table__.c.keys())
    for name in (
        "user_id",
        "domain",
        "key",
        "value_json",
        "source",
        "valid_from",
        "valid_until",
        "supersedes_fact_id",
        "fact_status",
        "consent_id",
        "soft_invalidated_at",
    ):
        assert name in cols
    assert DEPRECATED_AUTHORITIES["user_facts"] == "user_memory_facts"
    assert DEPRECATED_AUTHORITIES["kc_user_facts"] == "user_memory_facts"
    assert DEPRECATED_AUTHORITIES["user_profile_facts"] == "user_memory_facts"
    assert DEPRECATED_AUTHORITIES["daily_memory_summaries"] == "user_period_summaries"


def test_i7_jobs_remain_dormant_monday_tehran_and_four_types(monkeypatch):
    monkeypatch.delenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", raising=False)
    assert period_summary_jobs_enabled() is False
    assert SUMMARY_TYPES == ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
    weekly = period_summary_cron_kwargs("WEEKLY")
    assert weekly["day_of_week"] == "mon"
    assert weekly["timezone"] == "Asia/Tehran"
    from datetime import datetime

    start, end = period_bounds("WEEKLY", now=datetime(2026, 8, 13, 12, 0, 0))
    assert (end - start).days == 7


def test_i8_planner_is_ephemeral_and_uses_retrieval_service():
    src = inspect.getsource(plan_nutrition)
    assert "retrieve_knowledge_context" in src
    assert "knowledge_chunk_embeddings" not in src
    assert '"persistence": "NONE"' in src or "'persistence': 'NONE'" in src


def test_medical_inference_tokens_blocked_and_rag_markers_frozen():
    assert "diagnosis" in UNSUPPORTED_MEDICAL_INFERENCE
    assert "prescription" in UNSUPPORTED_MEDICAL_INFERENCE
    assert RAG_EMBEDDINGS_INTRODUCED is False
    versions = list((ROOT / "backend" / "alembic" / "versions").glob("066*.py"))
    assert versions == []


def test_section44_docs_record_approved_decisions():
    closure = (ROOT / "docs" / "architecture" / "section44" / "SECTION44_DESIGN_CLOSURE.md").read_text(
        encoding="utf-8"
    )
    for token in (
        "DCR01_COMPACT_PROFILE=APPROVED",
        "DCR02_STORAGE_TIERS=APPROVED",
        "DCR03_EXPORT=APPROVED",
        "DCR04_FACT_STACKS=APPROVED",
        "DCR05_EVENT_TIMELINE=APPROVED",
        "I7_WEEK_SEMANTICS=APPROVED",
        "I8_PERSISTENCE=DEFERRED",
        "PRODUCTION_RAG=NO",
        "MIGRATION_066=NO",
        "CHATGPT_V616_PHYSICAL=ABSENT",
    ):
        assert token in closure
