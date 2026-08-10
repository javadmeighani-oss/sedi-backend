"""RRF hybrid fusion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# TO_BE_BASELINED — standard RRF constant from literature; measured in eval harness.
RRF_K = 60


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
