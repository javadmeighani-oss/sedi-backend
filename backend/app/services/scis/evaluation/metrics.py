"""SCIS evaluation metrics (TO_BE_BASELINED thresholds)."""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Set


def recall_at_k(relevant: Set[int], retrieved: Sequence[int], k: int) -> float:
    if not relevant:
        return 0.0
    top = list(retrieved)[:k]
    hit = sum(1 for x in top if x in relevant)
    return hit / len(relevant)


def precision_at_k(relevant: Set[int], retrieved: Sequence[int], k: int) -> float:
    top = list(retrieved)[:k]
    if not top:
        return 0.0
    hit = sum(1 for x in top if x in relevant)
    return hit / len(top)


def mrr(relevant: Set[int], retrieved: Sequence[int]) -> float:
    for i, x in enumerate(retrieved, start=1):
        if x in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(relevant: Set[int], retrieved: Sequence[int], k: int) -> float:
    top = list(retrieved)[:k]
    dcg = 0.0
    for i, x in enumerate(top, start=1):
        rel = 1.0 if x in relevant else 0.0
        dcg += rel / math.log2(i + 1)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return (dcg / idcg) if idcg else 0.0


def mean(values: Iterable[float]) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0
