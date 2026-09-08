"""RRF hybrid fusion + deterministic post-RRF ranking (CASE15)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

# TO_BE_BASELINED — standard RRF constant from literature; measured in eval harness.
RRF_K = 60

# Explicit CASE15 owner label — no neural / LLM / network reranker.
DETERMINISTIC_POST_RRF_RERANKER = "deterministic_post_rrf"


@dataclass
class RankedCandidate:
    chunk_id: int
    branch: str
    rank: int
    score: float
    payload: dict


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[RankedCandidate]],
    *,
    k: int = RRF_K,
) -> List[Tuple[int, float, dict]]:
    """Fuse multiple ranked lists by chunk_id.

    Returns list of (chunk_id, fusion_score, merged_payload) sorted by score desc.
    Dedup is by chunk_id (one entry per chunk). Does not resurrect omitted candidates.
    """
    scores: Dict[int, float] = {}
    payloads: Dict[int, dict] = {}
    branch_ranks: Dict[int, dict] = {}

    for lst in ranked_lists:
        for cand in lst:
            scores[cand.chunk_id] = scores.get(cand.chunk_id, 0.0) + 1.0 / (k + cand.rank)
            meta = branch_ranks.setdefault(cand.chunk_id, {})
            meta[f"{cand.branch}_rank"] = cand.rank
            meta[f"{cand.branch}_score"] = cand.score
            base = payloads.get(cand.chunk_id, {})
            merged = {**base, **cand.payload, **meta}
            merged["branches"] = sorted(set(list(base.get("branches", [])) + [cand.branch]))
            payloads[cand.chunk_id] = merged

    fused = [(cid, scores[cid], payloads[cid]) for cid in scores]
    fused.sort(key=lambda x: (-x[1], x[0]))
    return fused


def _stable_tie_key(chunk_id: int, payload: dict) -> Tuple[int, int, int]:
    """Stable secondary keys only — no clinical relevance invention."""
    ku_raw = payload.get("knowledge_unit_id")
    try:
        ku_id = int(ku_raw) if ku_raw is not None else 0
    except (TypeError, ValueError):
        ku_id = 0
    # Prefer more branches only as a deterministic tie signal already present in fusion.
    branch_count = len(payload.get("branches") or [])
    return (-branch_count, ku_id, int(chunk_id))


def deterministic_post_rrf_rank(
    fused: Sequence[Tuple[int, float, dict]],
    *,
    top_k: Optional[int] = None,
) -> List[Tuple[int, float, dict]]:
    """Deterministic post-RRF ranking over already governance-eligible fused candidates.

    Rules (CASE15):
    - input must already be eligibility-filtered / fused (no resurrection)
    - ordering is pure local sort — no network, LLM, neural model, or randomness
    - does not mutate authority / eligibility / ownership fields in payloads
    - preserves chunk_id dedup from RRF
    - optional top_k bound
    """
    # Re-sort explicitly so post-RRF is an owned, testable step (not implicit RRF order only).
    ranked = sorted(
        list(fused),
        key=lambda row: (-float(row[1]), *_stable_tie_key(int(row[0]), row[2] or {})),
    )
    # Defense-in-depth dedup: first occurrence of chunk_id wins (already unique from RRF).
    seen: set[int] = set()
    out: List[Tuple[int, float, dict]] = []
    for cid, score, payload in ranked:
        chunk_id = int(cid)
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        # Shallow copy payload so callers cannot mutate shared fusion state via ranking.
        out.append((chunk_id, float(score), dict(payload or {})))
        if top_k is not None and len(out) >= max(0, int(top_k)):
            break
    return out
