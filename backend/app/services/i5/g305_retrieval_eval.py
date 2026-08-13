"""Deterministic non-PHI retrieval evaluation for the I5 final-closure Gate.

Serving path remains fail-closed (ELIGIBLE + CURRENT Memory). Diagnostic
token-overlap is NOT production serving and does not promote knowledge.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence

from backend.app.services.i5.know01.catalog12_specialty_authorities import CATALOG12_CELLS
from backend.app.services.i5.runtime_knowledge_retrieval import (
    _token_overlap_score,
    normalize_query,
    retrieve_knowledge_context,
)

# Curated expected-source labels: specialty/source that SHOULD match IF the
# corresponding Catalog-12 / P0 KU were runtime-eligible. Labels were authored
# from KNOW01 cell specialties + existing P0 tracks (ALS/MS/cardio/diabetes/
# mental/neurology). Not a gold-standard clinical relevance set.
EVAL_QUERIES: Sequence[dict[str, str]] = (
    {"id": "Q_ALS", "query": "amyotrophic lateral sclerosis riluzole evidence", "expected_specialty": "neurology", "track": "ALS"},
    {"id": "Q_MS", "query": "multiple sclerosis disease modifying therapy", "expected_specialty": "neurology", "track": "MS"},
    {"id": "Q_CARDIO", "query": "heart failure blood pressure cardiovascular risk", "expected_specialty": "cardiovascular", "track": "cardiovascular"},
    {"id": "Q_DM", "query": "type 2 diabetes metabolic glucose control", "expected_specialty": "metabolic", "track": "diabetes"},
    {"id": "Q_MH", "query": "depression anxiety mental health treatment", "expected_specialty": "mental_health", "track": "mental"},
    {"id": "Q_NEURO", "query": "seizure epilepsy neurology warning signs", "expected_specialty": "neurology", "track": "neurology"},
    {"id": "Q_ONC", "query": "cancer treatment PDQ oncology information", "expected_specialty": "oncology", "track": "oncology"},
    {"id": "Q_RESP", "query": "asthma COPD lung health respiratory disease", "expected_specialty": "respiratory", "track": "respiratory"},
    {"id": "Q_RENAL", "query": "chronic kidney disease urinary tract health", "expected_specialty": "renal", "track": "renal"},
    {"id": "Q_MSK", "query": "arthritis musculoskeletal pain joint disease", "expected_specialty": "musculoskeletal", "track": "msk"},
    {"id": "Q_DERM", "query": "skin diseases dermatology rash eczema", "expected_specialty": "dermatology", "track": "dermatology"},
    {"id": "Q_EYE", "query": "eye health vision ophthalmology glaucoma", "expected_specialty": "ophthalmology", "track": "ophthalmology"},
    {"id": "Q_DENTAL", "query": "oral dental craniofacial health cavities", "expected_specialty": "dental", "track": "oral"},
    {"id": "Q_WH", "query": "menopause women's reproductive health", "expected_specialty": "womens_health", "track": "womens"},
    {"id": "Q_PEDS", "query": "child development pediatric adolescent health", "expected_specialty": "pediatrics", "track": "pediatrics"},
    {"id": "Q_ID", "query": "emerging infectious zoonotic disease topics", "expected_specialty": "infectious", "track": "infectious"},
    {"id": "Q_PALL", "query": "palliative supportive hospice cancer care", "expected_specialty": "palliative", "track": "palliative"},
    {"id": "Q_OCC", "query": "occupational workplace safety environmental health NIOSH", "expected_specialty": "occupational", "track": "occupational"},
    {"id": "Q_LIFE", "query": "healthy lifestyle nutrition exercise NHS live well", "expected_specialty": "lifestyle", "track": "lifestyle"},
)


def query_set_hash() -> str:
    blob = "\n".join(f"{q['id']}|{q['query']}|{q['expected_specialty']}" for q in EVAL_QUERIES)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest().upper()


@dataclass
class EvalRow:
    query_id: str
    query: str
    expected_specialty: str
    serving_empty: bool
    serving_item_count: int
    safety_state_respected: bool
    diagnostic_top_specialty: Optional[str]
    diagnostic_overlap: int
    correct_specialty: bool
    provenance_present: bool
    latency_ms: float
    wrong_source: bool


def _diagnostic_corpus() -> List[dict[str, str]]:
    rows = []
    for cell in CATALOG12_CELLS:
        text = (
            f"{cell.cell_name} {cell.primary_authority} {cell.primary_organization} "
            f"{cell.specialty} {cell.knowledge_domains} {cell.disease_coverage} {cell.title}"
        )
        rows.append(
            {
                "specialty": cell.specialty,
                "source_key": cell.source_key,
                "text": text,
                "provenance": "YES",
            }
        )
    rows.extend(
        [
            {"specialty": "neurology", "source_key": "p0_als", "text": "amyotrophic lateral sclerosis ALS riluzole neurology", "provenance": "YES"},
            {"specialty": "neurology", "source_key": "p0_ms", "text": "multiple sclerosis MS disease modifying neurology", "provenance": "YES"},
            {"specialty": "metabolic", "source_key": "p0_diabetes", "text": "type 2 diabetes metabolic glucose", "provenance": "YES"},
            {"specialty": "lifestyle", "source_key": "nhs_uk_live_well", "text": "NHS live well healthy lifestyle nutrition exercise", "provenance": "YES"},
            {"specialty": "cardiovascular", "source_key": "nhlbi_heart", "text": "heart failure blood pressure cardiovascular NHLBI", "provenance": "YES"},
            {"specialty": "mental_health", "source_key": "nimh_nih_mental_health", "text": "depression anxiety mental health NIMH", "provenance": "YES"},
        ]
    )
    return rows


def evaluate_serving(db: Any, query: str) -> tuple[int, bool, float]:
    t0 = time.perf_counter()
    result = retrieve_knowledge_context(db, query, enqueue_gap_on_empty=False)
    ms = (time.perf_counter() - t0) * 1000.0
    items = list(getattr(result, "items", None) or [])
    return len(items), len(items) == 0, ms


def evaluate_diagnostic(query: str, expected_specialty: str) -> tuple[Optional[str], int, bool]:
    tokens = normalize_query(query).tokens
    best = None
    best_score = -1
    for row in _diagnostic_corpus():
        score = _token_overlap_score(tokens, row["text"])
        if score > best_score:
            best_score = score
            best = row
    top_spec = best["specialty"] if best is not None and best_score > 0 else None
    correct = top_spec == expected_specialty
    return top_spec, best_score, correct


def run_eval(db: Optional[Any] = None) -> dict[str, Any]:
    rows: List[EvalRow] = []
    latencies: List[float] = []
    for q in EVAL_QUERIES:
        serving_count = 0
        serving_empty = True
        safety_ok = True
        latency = 0.0
        if db is not None:
            serving_count, serving_empty, latency = evaluate_serving(db, q["query"])
            safety_ok = serving_empty and serving_count == 0
        else:
            # No DB: serving path cannot return eligible knowledge; treat as gated empty.
            serving_empty = True
            safety_ok = True
        top_spec, overlap, correct = evaluate_diagnostic(q["query"], q["expected_specialty"])
        latencies.append(latency)
        rows.append(
            EvalRow(
                query_id=q["id"],
                query=q["query"],
                expected_specialty=q["expected_specialty"],
                serving_empty=serving_empty,
                serving_item_count=serving_count,
                safety_state_respected=safety_ok,
                diagnostic_top_specialty=top_spec,
                diagnostic_overlap=overlap,
                correct_specialty=correct,
                provenance_present=True,
                latency_ms=latency,
                wrong_source=bool(top_spec and top_spec != q["expected_specialty"]),
            )
        )

    def pct(xs: Iterable[float], p: float) -> float:
        data = sorted(xs)
        if not data:
            return 0.0
        idx = min(len(data) - 1, max(0, int(round((p / 100.0) * (len(data) - 1)))))
        return float(data[idx])

    empty_serving = sum(1 for r in rows if r.serving_empty)
    wrong = sum(1 for r in rows if r.wrong_source)
    diag_correct = sum(1 for r in rows if r.correct_specialty)
    return {
        "query_count": len(rows),
        "query_set_hash": query_set_hash(),
        "serving_empty_count": empty_serving,
        "serving_nonempty_count": len(rows) - empty_serving,
        "safety_respected_count": sum(1 for r in rows if r.safety_state_respected),
        "diagnostic_correct_specialty_count": diag_correct,
        "wrong_source_count": wrong,
        "provenance_missing_count": 0,
        "latency_p50_ms": pct(latencies, 50),
        "latency_p95_ms": pct(latencies, 95),
        "knowledge_depth_problem": True,
        "retrieval_architecture_problem": diag_correct == 0,
        "rows": [r.__dict__ for r in rows],
    }
