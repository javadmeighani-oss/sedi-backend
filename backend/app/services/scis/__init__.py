"""SCIS — Sedi Context Intelligence Stack (SCIS-01 core retrieval foundation)."""

from __future__ import annotations

SCIS_PACKAGE = "scis"
SCIS_GATE = "SCIS-01"
CHUNKER_VERSION = "scis-ku-section-v1"
# Phase1 canonical network embedding contract (OPENAI_ONLY).
DEFAULT_EMBEDDING_PROVIDER = "openai"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_EMBEDDING_DIM = 1024
RESULT_LABEL_GLOBAL = "GLOBAL_GOVERNED_KNOWLEDGE"
RESULT_LABEL_GOVERNED = "GOVERNED"
RESULT_LABEL_PERSONAL = "PERSONAL"
PLANE_PERSONAL_FORBIDDEN = "PERSONAL_CONTEXT_NOT_IN_SCIS_01_INDEX"
# Historical Cohere identifiers (dormant; never canonical runtime).
COHERE_HISTORICAL_PROVIDER = "cohere"
COHERE_HISTORICAL_MODEL = "embed-multilingual-v3.0"
