"""I5-KNOW-05 PostgreSQL rehearsal — coverage→gap + RAG coherence (requires TEST_DATABASE_URL)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.services.i5.enums import CoverageCellState
from backend.app.services.i5.know02.taxonomy import ensure_dimension, upsert_coverage_cell
from backend.app.services.i5.know05.modes import Know05Mode
from backend.app.services.i5.know05.orchestrator import run_know05_cycle
from backend.app.services.i5.know05.rag_coherence import audit_rag_coherence
from backend.app import models


def _db_url():
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_know05_dry_run_coverage_gaps_and_rag_zeroes():
    engine = create_engine(_db_url())
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if head != "068_i7_wave2_governed_memory_lifecycle":
            pytest.skip(f"alembic head {head} != 067")

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        concept = (
            db.query(models.I5ClinicalConcept)
            .filter_by(concept_key="ALS")
            .first()
        )
        if concept is None:
            concept = models.I5ClinicalConcept(
                concept_key="ALS",
                preferred_name="Amyotrophic lateral sclerosis",
                normalized_name="amyotrophic lateral sclerosis",
                concept_type="DISEASE",
            )
            db.add(concept)
            db.flush()
        ensure_dimension(db, "PHARMACOLOGICAL_TREATMENT")
        upsert_coverage_cell(
            db,
            concept_id=concept.id,
            dimension_code="PHARMACOLOGICAL_TREATMENT",
            cell_state=CoverageCellState.MISSING.value,
            evidence_class="GUIDELINE",
            detail="know05-fixture",
        )
        db.flush()

        result = run_know05_cycle(
            db,
            mode=Know05Mode.DRY_RUN,
            window_tag="know05-test",
            persist_ledger=True,
        )
        db.commit()
        assert result.existing_weekly_governance_reused is True
        assert result.gaps_created + result.gaps_reused >= 1
        assert result.production_flags["production_weekly"] is False
        assert result.weekly_run_id is not None

        # Idempotent second pass
        result2 = run_know05_cycle(
            db,
            mode=Know05Mode.DRY_RUN,
            window_tag="know05-test",
            persist_ledger=True,
        )
        assert result2.gaps_created == 0
        assert result2.gaps_reused >= 1

        report = audit_rag_coherence(db)
        report.assert_zero_states()
        assert report.production_rag_applied is False
        assert report.rag_activated is False
    finally:
        db.close()
