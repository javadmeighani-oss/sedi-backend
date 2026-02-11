# Release Stage 17.8 – Vector RAG Phase 1 Pilot

Real vector indexing and retrieval for DailyMemorySummary only. Safe pilot rollout.

---

## Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_VECTOR_ENABLED` | false | Enable vector retrieval |
| `RAG_VECTOR_ALLOWLIST` | "" | Comma-separated user_ids; empty => nobody uses vector |
| `RAG_VECTOR_REBUILD` | false | Re-embed unchanged content when true |
| `RAG_VECTOR_BATCH_SIZE` | 200 | Batch size for embedding API |
| `RAG_VECTOR_MODEL` | text-embedding-3-small | OpenAI embedding model |
| `RAG_VECTOR_DIM` | 1536 | Vector dimension |
| `RAG_VECTOR_MIN_SCORE` | 0.2 | Minimum similarity score for retrieval |
| `RAG_VECTOR_P95_MAX_MS` | 500 | Circuit breaker: p95 latency threshold (ms) |
| `RAG_VECTOR_ERROR_MAX` | 5 | Circuit breaker: max errors in last 50 requests |
| `RAG_VECTOR_FALLBACK_TTL_SECONDS` | 600 | Circuit breaker: fallback duration (10 min) |

---

## Guardrails (Stage 17.9)

If p95 latency exceeds `RAG_VECTOR_P95_MAX_MS` OR errors in last 50 requests exceed `RAG_VECTOR_ERROR_MAX`, the circuit breaker trips. All vector traffic falls back to keyword for `RAG_VECTOR_FALLBACK_TTL_SECONDS`. Process-local; resets on restart.

---

## Breaker Endpoint

```bash
curl -s "http://localhost:8000/ai_core/admin/rag_breaker" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN"
```

Returns: `is_tripped`, `tripped_until`, `last_reason`, `thresholds`.

---

## Step-by-Step Rollout

### 1. Apply migration 008 (pgvector)

```bash
psql -f backend/deployment/migrations/008_stage17_6_pgvector.sql
```

### 2. Set environment variables

```bash
RAG_VECTOR_ENABLED=true
RAG_VECTOR_ALLOWLIST=1
OPENAI_API_KEY=...
```

### 3. Run admin indexing for one user

```bash
curl -X POST "http://localhost:8000/ai_core/admin/index_daily_summaries?user_id=1&days=30" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN"
```

### 4. Verify rag_metrics

```bash
curl -s "http://localhost:8000/ai_core/admin/rag_metrics" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN"
```

Trigger a lifestyle summary or chat for user 1. Check that `provider_usage.vector` increments.

### 5. Expand allowlist gradually

```bash
RAG_VECTOR_ALLOWLIST=1,2,3
```

For batch indexing:

```bash
curl -X POST "http://localhost:8000/ai_core/admin/index_daily_summaries_all?days=30&limit=50&offset=0" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN"
```

---

## Admin Endpoints

- **POST /ai_core/admin/index_daily_summaries?user_id=...&days=30** – Index one user
- **POST /ai_core/admin/index_daily_summaries_all?days=30&limit=50&offset=0** – Batch index
- **GET /ai_core/admin/rag_metrics** – Metrics snapshot
- **GET /ai_core/admin/rag_breaker** – Circuit breaker state

---

## Rollback

- Set `RAG_VECTOR_ENABLED=false` – all users use keyword
- Or clear `RAG_VECTOR_ALLOWLIST` – vector path not used

---

## Data Scope

- **Indexed**: DailyMemorySummary only, last 30 days
- **Retrieved**: rag_embeddings where source_type='daily_summary'
