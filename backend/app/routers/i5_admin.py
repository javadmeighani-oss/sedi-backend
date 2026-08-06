"""I5-IMPL-W1-P02 — minimal read-only admin stub (no production DB wiring)."""
from __future__ import annotations

from fastapi import APIRouter

from backend.app.services.i5.knowledge_unit_service import (
    build_canonical_hash,
    build_deduplication_key,
    evaluate_runtime_eligibility,
)
from backend.app.services.i5.provenance_service import is_provenance_complete

router = APIRouter(prefix="/i5/admin", tags=["i5-admin"])

_PACKAGE = "I5-IMPL-W1-P02"


@router.get("/knowledge-units/health")
def knowledge_units_health() -> dict[str, object]:
    """Placeholder health: exercise pure KU service helpers (no DB session)."""
    dedupe = build_deduplication_key(
        "health", "placeholder", "general", "ZZ", "canonical-placeholder"
    )
    canon = build_canonical_hash(
        "placeholder statement",
        "health",
        "FACT",
        language="en",
    )
    eligibility = evaluate_runtime_eligibility(
        {"provenance_complete": False, "runtime_eligibility": "ELIGIBLE"}
    )
    return {
        "ok": True,
        "package": _PACKAGE,
        "deduplication_key_len": len(dedupe),
        "canonical_hash_len": len(canon),
        "eligibility": eligibility.value,
    }


@router.get("/provenance/health")
def provenance_health() -> dict[str, object]:
    """Placeholder health: exercise pure provenance helpers (no DB session)."""
    complete = is_provenance_complete(
        {
            "knowledge_unit_id": 1,
            "source_profile_id": 1,
            "retrieval_method": "ADMIN_HEALTH_CHECK",
        }
    )
    incomplete = is_provenance_complete(
        {"knowledge_unit_id": None, "source_profile_id": 1, "retrieval_method": ""}
    )
    return {
        "ok": True,
        "package": _PACKAGE,
        "complete_probe": complete,
        "incomplete_probe": incomplete,
    }
