"""I5-KNOW-05 — governed weekly knowledge acquisition (rehearsal; Production weekly OFF)."""

from backend.app.services.i5.know05.availability import (
    derive_ku_availability,
    assert_runtime_eligible_has_retrieval,
)
from backend.app.services.i5.know05.budgets import plan_bounded_ingestion
from backend.app.services.i5.know05.coverage_engine import (
    ensure_gaps_from_coverage,
    p0_coverage_report,
    prioritize_coverage_cells,
)
from backend.app.services.i5.know05.modes import Know05Mode, assert_mode_authorized, production_activation_flags
from backend.app.services.i5.know05.ncbi_identity import load_ncbi_operational_identity
from backend.app.services.i5.know05.orchestrator import run_know05_cycle
from backend.app.services.i5.know05.rag_coherence import audit_rag_coherence, invalidate_rag_for_knowledge_unit
from backend.app.services.i5.know05.storage_matrix import matrices_summary

__all__ = [
    "Know05Mode",
    "assert_mode_authorized",
    "production_activation_flags",
    "load_ncbi_operational_identity",
    "plan_bounded_ingestion",
    "prioritize_coverage_cells",
    "ensure_gaps_from_coverage",
    "p0_coverage_report",
    "run_know05_cycle",
    "derive_ku_availability",
    "assert_runtime_eligible_has_retrieval",
    "audit_rag_coherence",
    "invalidate_rag_for_knowledge_unit",
    "matrices_summary",
]
