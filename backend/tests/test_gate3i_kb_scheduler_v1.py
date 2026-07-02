"""Gate 3I-A — Safe scheduled KB fetch (local-only tests)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.services.gate3.kb_scheduler import select_due_sources, run_scheduled_kb_fetch
from backend.app.services.gate3.knowledge_update_service import KnowledgeUpdateService


def _seed_source(db, *, slug: str, **overrides) -> models.KnowledgeSource:
    now = datetime.utcnow()
    row = models.KnowledgeSource(
        slug=slug,
        name=f"Source {slug}",
        category=overrides.pop("category", "sleep"),
        trust_level=overrides.pop("trust_level", "official"),
        source_url=overrides.pop("source_url", f"https://example.org/{slug}"),
        locale="en",
        ingestion_status=overrides.pop("ingestion_status", "active"),
        source_fetch_enabled=overrides.pop("source_fetch_enabled", True),
        allowed_domain=overrides.pop("allowed_domain", "example.org"),
        allowed_url_patterns_json=overrides.pop(
            "allowed_url_patterns_json",
            json.dumps([r"^https://example\.org/" + slug + r"$"]),
        ),
        fetch_method=overrides.pop("fetch_method", "url_fetch"),
        review_required=overrides.pop("review_required", True),
        auto_approve_low_risk=overrides.pop("auto_approve_low_risk", False),
        fetch_interval_hours=overrides.pop("fetch_interval_hours", 24),
        last_fetched_at=overrides.pop("last_fetched_at", None),
        last_checked_at=overrides.pop("last_checked_at", now),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_select_due_sources_strict_filters(db):
    good = _seed_source(db, slug="good")
    _seed_source(db, slug="disabled", source_fetch_enabled=False)
    _seed_source(db, slug="draft", ingestion_status="draft")
    _seed_source(db, slug="no-domain", allowed_domain=None)
    _seed_source(db, slug="no-pattern", allowed_url_patterns_json=json.dumps([]))
    _seed_source(db, slug="blocked-cat", category="medical_condition")
    _seed_source(db, slug="untrusted", trust_level="editorial")
    _seed_source(db, slug="misconfig-auto", category="lifestyle", auto_approve_low_risk=True)
    _seed_source(db, slug="misconfig-review", category="lifestyle", review_required=False)
    _seed_source(db, slug="manual-method", fetch_method="manual_upload")

    due = select_due_sources(db, now=datetime.utcnow(), limit=10)
    assert [s.id for s in due] == [good.id]


def test_select_due_sources_respects_due_logic(db):
    now = datetime.utcnow()
    due = _seed_source(db, slug="due", last_fetched_at=now - timedelta(hours=30), fetch_interval_hours=24)
    _seed_source(db, slug="not-due", last_fetched_at=now - timedelta(hours=2), fetch_interval_hours=24)
    out = select_due_sources(db, now=now, limit=10)
    assert [s.id for s in out] == [due.id]


def test_select_due_sources_respects_cap(db):
    s1 = _seed_source(db, slug="s1")
    s2 = _seed_source(db, slug="s2")
    out = select_due_sources(db, now=datetime.utcnow(), limit=1)
    assert len(out) == 1
    assert out[0].id in (s1.id, s2.id)


def test_scheduled_fetch_never_auto_approves_even_if_ai_says_autoapprove(db, monkeypatch):
    """
    Hard guard: run_type=scheduled_fetch must never call _activate_run.
    """
    src = _seed_source(db, slug="sched", category="lifestyle")

    # Make it due
    src.last_fetched_at = datetime.utcnow() - timedelta(days=2)
    db.commit()

    # Enable scheduler env
    monkeypatch.setenv("SEDI_KB_SCHEDULED_FETCH_ENABLED", "true")
    monkeypatch.setenv("SEDI_KB_SCHEDULED_FETCH_MAX_PER_TICK", "1")

    # Stub fetcher+parser and force AI to recommend auto_approve
    class _Parsed:
        text = "culture and lifestyle " * 200
        title = "t"
        parser_type = "text"
        content_hash = "newhash"
        parse_findings = []

    with patch("backend.app.services.gate3.knowledge_update_service.parse_content", return_value=_Parsed()):
        with patch("backend.app.services.gate3.knowledge_source_fetcher.KnowledgeSourceFetcher.fetch") as mf:
            mf.return_value = type("R", (), {"content": b"hi", "content_type": "text/plain", "final_url": src.source_url})()

            # Force AI to say auto_approve
            from backend.app.services.gate3.knowledge_ai_review_service import AIReviewResult

            fake_review = AIReviewResult(
                ai_review_status="passed",
                source_quality_score=0.95,
                parse_quality_score=0.95,
                evidence_quality_score=0.95,
                medical_risk_level="low",
                psychological_risk_level="low",
                advertising_risk_level="low",
                requires_human_review=False,
                auto_approve_allowed=True,
                recommended_action="auto_approve",
                review_findings=[],
            )
            with patch("backend.app.services.gate3.knowledge_update_service.KnowledgeAIReviewService.review", return_value=fake_review):
                # Guard against accidental activation
                with patch.object(KnowledgeUpdateService, "_activate_run", side_effect=AssertionError("activate_should_not_run")):
                    out = run_scheduled_kb_fetch(db)
                    assert out and out["fetched"] == 1

    run = db.query(models.KnowledgeIngestionRun).order_by(models.KnowledgeIngestionRun.id.desc()).first()
    assert run.run_type == "scheduled_fetch"
    assert run.review_status == "pending_review"
    assert db.query(models.KnowledgeChunk).count() == 0


def test_scheduled_fetch_no_change_does_not_create_chunks(db, monkeypatch):
    src = _seed_source(db, slug="nochange", category="sleep")
    src.content_hash = "samehash"
    src.last_fetched_at = datetime.utcnow() - timedelta(days=2)
    db.commit()

    monkeypatch.setenv("SEDI_KB_SCHEDULED_FETCH_ENABLED", "true")
    monkeypatch.setenv("SEDI_KB_SCHEDULED_FETCH_MAX_PER_TICK", "1")

    class _Parsed:
        text = "sleep " * 300
        title = "t"
        parser_type = "text"
        content_hash = "samehash"
        parse_findings = []

    with patch("backend.app.services.gate3.knowledge_update_service.parse_content", return_value=_Parsed()):
        with patch("backend.app.services.gate3.knowledge_source_fetcher.KnowledgeSourceFetcher.fetch") as mf:
            mf.return_value = type("R", (), {"content": b"hi", "content_type": "text/plain", "final_url": src.source_url})()
            out = run_scheduled_kb_fetch(db)
            assert out and out["fetched"] == 1

    run = db.query(models.KnowledgeIngestionRun).order_by(models.KnowledgeIngestionRun.id.desc()).first()
    assert run.review_status == "no_change"
    assert db.query(models.KnowledgeChunk).count() == 0

