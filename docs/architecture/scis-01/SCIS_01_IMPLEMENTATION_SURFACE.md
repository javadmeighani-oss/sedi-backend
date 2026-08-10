# SCIS-01 Implementation Surface

```text
GATE = SCIS-01
PACKAGE = backend/app/services/scis/
MIGRATION = 061_scis01_pgvector_kce_foundation
CI = .github/workflows/scis-01-core-retrieval-runtime.yml
PRODUCTION_APPLY = NO
```

## Modules

| Module | Role |
|---|---|
| `contracts.py` | Request/response/provenance types |
| `chunking.py` | KU + section-aware deterministic chunker |
| `normalize.py` | FA/AR Unicode normalization for FTS |
| `embedding/providers.py` | Fake / Cohere / OpenAI providers (global only) |
| `indexing.py` | Chunk → embed → KCE (pgvector + tsvector) |
| `lexical.py` | PostgreSQL FTS (`simple` config) |
| `vector.py` | Exact `<=>` search (no HNSW/IVFFlat in V1) |
| `hybrid.py` | RRF (`k=60` TO_BE_BASELINED) |
| `eligibility.py` | KU gate + retraction/model filters |
| `provenance.py` | Provenance refs + orphan rejection |
| `retrieval.py` | Hybrid entrypoint + observability |
| `evaluation/` | Corpus + metrics |

## Invariants preserved

- Stage17 `rag_embeddings` not created
- Personal PHI not externally embedded
- RAG index rebuildable / not SoT
- Production unchanged
