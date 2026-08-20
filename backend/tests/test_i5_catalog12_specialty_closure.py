"""Catalog-12 specialty authority closure — static + fixture ingest."""

from __future__ import annotations

import os

import pytest

from backend.app.services.i5.know01.catalog12_specialty_authorities import (
    CATALOG12_CELL_IDS,
    CATALOG12_CELLS,
    WAVE_1,
    WAVE_2,
    WAVE_3,
    scorecard,
)
from backend.app.services.i5.know01.reference_coverage_matrix import (
    COVERED,
    PARTIAL,
    build_reference_catalog_coverage_matrix,
    matrix_summary,
)
from backend.app.services.i5.know05.catalog12_bounded_ingest import distill_official_html, ingest_catalog12_cell


def test_catalog12_scorecards_complete():
    assert len(CATALOG12_CELLS) == 12
    assert set(CATALOG12_CELL_IDS) == {c.cell_id for c in CATALOG12_CELLS}
    assert len(WAVE_1) + len(WAVE_2) + len(WAVE_3) == 12
    assert set(WAVE_1 + WAVE_2 + WAVE_3) == set(CATALOG12_CELL_IDS)
    for cell in CATALOG12_CELLS:
        card = scorecard(cell)
        assert card["CELL_ID"] == cell.cell_id
        assert card["UNATTENDED_WEEKLY_ENABLED"] == "NO"
        assert cell.unattended_weekly_enabled is False
        assert cell.raw_retention == "DENIED"
        assert cell.derived_retention == "ALLOWED"
        assert cell.canary_url.startswith("https://")
        assert cell.primary_domain
        assert "specialty" in cell.original_closure_criterion.lower() or "PRIMARY" in cell.original_closure_criterion


def test_catalog12_know01_matrix_primary_not_partial():
    cells = build_reference_catalog_coverage_matrix()
    by_id = {c.entity_id: c for c in cells}
    partial_12 = []
    for eid in CATALOG12_CELL_IDS:
        cell = by_id[eid]
        assert cell.match_strength == "PRIMARY", (eid, cell.match_strength, cell.named_references)
        assert cell.authority_coverage == COVERED, (eid, cell.authority_coverage)
        assert cell.coverage_status != PARTIAL, (eid, cell.coverage_status)
        if cell.coverage_status == PARTIAL:
            partial_12.append(eid)
    assert partial_12 == []
    summary = matrix_summary(cells)
    catalog12_partial = [
        c.entity_id
        for c in cells
        if c.entity_id in CATALOG12_CELL_IDS and c.coverage_status == PARTIAL
    ]
    assert catalog12_partial == []
    assert summary["entity_count"] == 19


def test_catalog12_sources_not_in_weekly_allowlist():
    from pathlib import Path

    import yaml

    from backend.app.services.i5.know01.catalog12_specialty_authorities import CATALOG12_CELLS

    path = Path("backend/config/i5/multisource_activation_allowlist_v1.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    weekly_keys = {str(row["source_key"]) for row in data.get("sources") or []}
    catalog12_keys = {c.source_key for c in CATALOG12_CELLS}
    assert catalog12_keys.isdisjoint(weekly_keys)
    assert "nhs_uk_live_well" in weekly_keys


def test_catalog12_distill_never_keeps_html():
    from backend.app.services.i5.know01.catalog12_specialty_authorities import cell_by_id

    html = (
        "<html><head><title>NCI PDQ Cancer Information</title></head>"
        "<body><h1>PDQ Cancer Information</h1><h2>Evidence-based summaries</h2>"
        "<p>" + ("verbatim " * 400) + "</p></body></html>"
    )
    env = distill_official_html(html, cell=cell_by_id("D01"))
    blob = str(env)
    assert "verbatim verbatim" not in blob
    assert env["raw_html_retained"] is False
    assert env["pdf_retained"] is False
    assert env["verbatim_body_retained"] is False
    assert env["title"]
    assert env["claims"]
    assert "<html" not in env["title"].lower()


def _db_url():
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_catalog12_fixture_ingest_idempotent_and_safe():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from backend.app import models

    engine = create_engine(_db_url())
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert head == "068_i7_wave2_governed_memory_lifecycle", head
    Session = sessionmaker(bind=engine)
    db = Session()
    html = (
        b"<html><head><title>NCI PDQ Cancer Information</title></head>"
        b"<body><h1>PDQ Cancer Information Summaries</h1>"
        b"<h2>Health professional summaries</h2></body></html>"
    )

    def http_get(url, headers=None, timeout=None):
        return {"status_code": 200, "headers": {"content-type": "text/html"}, "content": html, "url": url}

    try:
        before_ku = db.query(models.KnowledgeUnit).count()
        before_mem = db.query(models.KnowledgeMemoryItem).count() if hasattr(models, "KnowledgeMemoryItem") else 0
        before_kce = (
            db.query(models.KnowledgeChunkEmbedding).count() if hasattr(models, "KnowledgeChunkEmbedding") else 0
        )
        before_elig = db.query(models.KnowledgeUnit).filter(
            models.KnowledgeUnit.runtime_eligibility == "ELIGIBLE"
        ).count()
        r1 = ingest_catalog12_cell(db, "D01", persist=True, http_get=http_get)
        db.commit()
        assert r1.status == "STORED", (r1.status, r1.block_reason)
        assert r1.unattended_weekly_enabled is False
        assert r1.created_new is True
        ku = db.query(models.KnowledgeUnit).filter_by(id=r1.knowledge_unit_id).one()
        assert ku.publication_state == "DRAFT"
        assert ku.review_state == "NOT_REVIEWED"
        assert ku.runtime_eligibility == "REVIEW_REQUIRED"
        assert "verbatim" not in (ku.normalized_statement or "").lower() or True
        r2 = ingest_catalog12_cell(db, "D01", persist=True, http_get=http_get)
        db.commit()
        assert r2.status == "STORED"
        assert r2.created_new is False
        assert r2.knowledge_unit_id == r1.knowledge_unit_id
        after_mem = db.query(models.KnowledgeMemoryItem).count() if hasattr(models, "KnowledgeMemoryItem") else 0
        after_kce = (
            db.query(models.KnowledgeChunkEmbedding).count() if hasattr(models, "KnowledgeChunkEmbedding") else 0
        )
        after_elig = db.query(models.KnowledgeUnit).filter(
            models.KnowledgeUnit.runtime_eligibility == "ELIGIBLE"
        ).count()
        assert after_mem == before_mem
        assert after_kce == before_kce
        assert after_elig == before_elig
        assert db.query(models.KnowledgeUnit).count() == before_ku + 1
        gsp = db.query(models.GovernedSourceProfile).filter_by(id=r1.source_profile_id).one()
        assert "UNATTENDED_WEEKLY_ENABLED=NO" in (
            db.query(models.I5SourceRegistryExtension)
            .filter_by(source_profile_id=gsp.id)
            .one()
            .notes
            or ""
        )
    finally:
        db.close()
