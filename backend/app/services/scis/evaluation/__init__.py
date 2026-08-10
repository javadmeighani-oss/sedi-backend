"""SCIS evaluation package."""

from backend.app.services.scis.evaluation.corpus import CORPUS_VERSION, DOCS, QUERIES
from backend.app.services.scis.evaluation.metrics import mrr, ndcg_at_k, precision_at_k, recall_at_k

__all__ = [
    "CORPUS_VERSION",
    "DOCS",
    "QUERIES",
    "mrr",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
]
