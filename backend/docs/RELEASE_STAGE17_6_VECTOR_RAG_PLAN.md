# Release Stage 17.6 – Vector RAG Upgrade Path

Design and rollout plan for embeddings-based retrieval using PostgreSQL pgvector. Off by default.

---

## Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_VECTOR_ENABLED` | false | Enable vector retrieval; else keyword only |
| `RAG_VECTOR_MODEL` | text-embedding-3-small | Embedding model (config) |
| `RAG_VECTOR_TOP_K` | 6 | Max chunks from vector search |
| `RAG_VECTOR_REBUILD` | false | Allow indexing; must be true for reindex endpoint |
| `RAG_VECTOR_BATCH_SIZE` | 200 | Batch size for embedding API calls |

---

## Why pgvector

- **Single DB**: No extra infrastructure; Postgres already in use
- **ACID**: Consistent with existing data model
- **Operational simplicity**: One backup, one connection pool
- **Cost**: No external vector DB fees

---

## Data to Embed (Priority Order)

| Phase | Data | Value |
|-------|------|-------|
| 1 | Daily summaries | Highest – rich narrative per day |
| 2 | User facts | Key-value facts, lifestyle context |
| 2 | User profile knowledge (baseline) | Stable user context |
| 3 | Memory turns | Recent conversations (optional; higher volume) |

**Exclusions**: Only embed accepted candidates (not pending); skip raw device payloads.

---

## Cost Control Plan

- **Phase 1**: Embed daily summaries only; cap refresh to once per day per summary
- **content_hash**: Skip re-embedding when content unchanged
- **Batch size**: `RAG_VECTOR_BATCH_SIZE=200` for embedding API calls
- **No auto-index**: Indexing triggered manually or via admin endpoint during rollout

---

## Rollout Phases

| Phase | Description | RAG_VECTOR_ENABLED | Data Embedded |
|-------|-------------|--------------------|---------------|
| **0** | Keyword only (current) | false | – |
| **1** | Vector enabled, summaries only | true | daily_summary |
| **2** | Add facts + profile | true | + user_fact, user_profile_knowledge |
| **3** | Add memory turns | true | + memory_turn |

---

## Monitoring (Stage 17.7)

### RAG Metrics Endpoint

`GET /ai_core/admin/rag_metrics` — Admin-only (requires `X-Admin-Token` when `ADMIN_TOKEN` set).

Returns:
```json
{
  "ok": true,
  "data": {
    "total_requests": 100,
    "provider_usage": {"keyword": 95, "vector": 5},
    "vector_fallbacks": 3,
    "errors": 0,
    "latency": {"avg_ms": 45.2, "p50_ms": 38, "p95_ms": 120, "buckets": {"<50": 60, "<100": 30, ...}},
    "last_updated_at": "2026-02-11T12:00:00"
  }
}
```

### Thresholds to Watch

- **vector_fallbacks spike**: High fallback rate (e.g. >10% of vector attempts) suggests pgvector issues or empty index.
- **errors > 0**: Retrieval failures; investigate logs.
- **latency.p95_ms > 500**: Consider tuning top_k or indexing.
- **provider_usage.vector == 0** when vector enabled: Vector path not being used (check RAG_VECTOR_ENABLED).

---

## Rollback

Set `RAG_VECTOR_ENABLED=false`; provider router uses keyword provider. No schema changes required for rollback.

---

## Indexing (Manual During Rollout)

Indexing does NOT run automatically by default. To populate embeddings:

1. Set `RAG_VECTOR_REBUILD=true`
2. Call `POST /ai_core/admin/reindex_embeddings?user_id=<id>` (requires `X-Admin-Token` if `ADMIN_TOKEN` set)
3. Run per-user or in batch during rollout
