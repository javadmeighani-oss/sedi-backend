"""Focused tests for I5 multi-source weekly activation + coverage manifest."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.i5.coverage_manifest_loader import (
    EXPECTED_ENTITY_COUNT,
    load_coverage_manifest,
    source_mapped_count,
)
from backend.app.services.i5.multisource_activation import (
    active_allowlist_rows,
    activate_multisource_allowlist,
    load_multisource_allowlist,
    load_multisource_weekly_candidates,
    multisource_enabled,
)


def test_coverage_manifest_19_entities_including_als_ms():
    data = load_coverage_manifest()
    ids = [e["id"] for e in data["entities"]]
    assert len(ids) == EXPECTED_ENTITY_COUNT
    assert "D18" in ids and "D19" in ids
    als = next(e for e in data["entities"] if e["id"] == "D18")
    ms = next(e for e in data["entities"] if e["id"] == "D19")
    assert als.get("alias") == "ALS"
    assert ms.get("alias") == "MS"
    mapped, total = source_mapped_count()
    assert mapped == total == 19


def test_multisource_allowlist_publisher_diversity_and_exact_urls():
    rows = active_allowlist_rows()
    assert len(rows) >= 4
    families = {r["publisher_family"] for r in rows}
    assert len(families) >= 4
    for row in rows:
        assert row["exact_url"].startswith("https://")
        assert row["activation"] in {True, "YES", "Yes", "true"}
        assert row["rights_terms_state"] in {"OGL", "PUBLIC_DOMAIN", "APPROVED", "ACCEPTABLE"}
        assert row["robots_access_state"] == "ALLOWED"


def test_multisource_env_default_off(monkeypatch):
    monkeypatch.delenv("SEDI_I5_MULTISOURCE_ENABLED", raising=False)
    assert multisource_enabled() is False
    monkeypatch.setenv("SEDI_I5_MULTISOURCE_ENABLED", "true")
    assert multisource_enabled() is True


def test_activate_multisource_and_load_candidates_offline(db, monkeypatch):
    from backend.app import models

    monkeypatch.setenv("SEDI_I5_MULTISOURCE_ENABLED", "true")
    result = activate_multisource_allowlist(db, models)
    assert result.fetch_enabled_count >= 4
    assert len(set(result.activated_source_keys)) == result.fetch_enabled_count
    enabled = (
        db.query(models.KnowledgeSource)
        .filter(models.KnowledgeSource.source_fetch_enabled.is_(True))
        .all()
    )
    assert {ks.slug for ks in enabled} == set(result.activated_source_keys)

    # Injecting a non-allowlist enabled source must be disabled by activator semantics on re-run
    rogue = models.KnowledgeSource(
        slug="rogue_not_allowlisted",
        name="rogue",
        category="lifestyle",
        trust_level="official",
        source_url="https://example.com/",
        locale="en",
        freshness_policy_days=7,
        ingestion_status="draft",
        source_fetch_enabled=True,
        allowed_domain="example.com",
        fetch_method="html_page",
        review_required=True,
        auto_approve_low_risk=False,
        robots_allowed=True,
    )
    db.add(rogue)
    db.flush()
    activate_multisource_allowlist(db, models)
    db.refresh(rogue)
    assert rogue.source_fetch_enabled is False

    candidates = load_multisource_weekly_candidates(db, models)
    assert len(candidates) >= 4
    keys = {c.canonical_key for c in candidates}
    assert "nhs_uk_live_well" in keys
    assert "medlineplus_consumer_health" in keys
    # One source must not overwrite another's identity
    assert len(keys) >= 4


def test_allowlist_file_exists_and_matches_loader():
    root = Path(__file__).resolve().parents[2]
    path = root / "config" / "i5" / "multisource_activation_allowlist_v1.yaml"
    assert path.is_file()
    data = load_multisource_allowlist()
    assert data["allowlist_version"] == "i5-multisource-v1"
    assert isinstance(data["sources"], list)


def test_rights_fail_closed_rejects_unknown_rights(monkeypatch, db):
    from backend.app import models
    from backend.app.services.i5 import multisource_activation as ms
    from backend.app.services.i5.governed_weekly_runtime import GovernedWeeklyRuntimeError

    original = ms.active_allowlist_rows

    def bad_rows():
        rows = original()
        rows = [dict(r) for r in rows]
        rows[0]["rights_terms_state"] = "UNKNOWN_BAD"
        return rows

    monkeypatch.setattr(ms, "active_allowlist_rows", bad_rows)
    with pytest.raises(GovernedWeeklyRuntimeError):
        ms.activate_multisource_allowlist(db, models)
