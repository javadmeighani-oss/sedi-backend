"""I5 final-closure retrieval evaluation (non-PHI, no RAG activation)."""

from __future__ import annotations

from backend.app.services.i5.g305_retrieval_eval import EVAL_QUERIES, query_set_hash, run_eval
from backend.app.services.db03.authority_markers import SCIS_01_PGVECTOR_PRODUCTION_APPLIED
from backend.app.services.i5.know05.modes import production_activation_flags


def test_eval_query_set_covers_frozen_specialty_tracks():
    tracks = {q["track"] for q in EVAL_QUERIES}
    required = {
        "ALS",
        "MS",
        "cardiovascular",
        "diabetes",
        "mental",
        "neurology",
        "oncology",
        "respiratory",
        "renal",
        "msk",
        "dermatology",
        "ophthalmology",
        "oral",
        "womens",
        "pediatrics",
        "infectious",
        "palliative",
        "occupational",
        "lifestyle",
    }
    assert required <= tracks
    assert len(EVAL_QUERIES) >= 18
    assert len(query_set_hash()) == 64


def test_diagnostic_token_overlap_is_not_architecture_failure():
    summary = run_eval(db=None)
    assert summary["query_count"] == len(EVAL_QUERIES)
    assert summary["serving_empty_count"] == summary["query_count"]
    assert summary["serving_nonempty_count"] == 0
    assert summary["safety_respected_count"] == summary["query_count"]
    assert summary["provenance_missing_count"] == 0
    assert summary["knowledge_depth_problem"] is True
    # Architecture is adequate if diagnostic matching finds some specialty-correct rows.
    assert summary["diagnostic_correct_specialty_count"] >= 8
    assert summary["retrieval_architecture_problem"] is False


def test_production_rag_and_ann_remain_off():
    flags = production_activation_flags()
    assert flags.get("production_rag_activated") is False
    assert SCIS_01_PGVECTOR_PRODUCTION_APPLIED is False
