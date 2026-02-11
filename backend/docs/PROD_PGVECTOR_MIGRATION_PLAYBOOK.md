# Production pgvector Migration Playbook

Step-by-step rollout of pgvector + rag_embeddings with minimal risk.

---

## Preconditions

- **PostgreSQL**: pgvector requires Postgres 11+. Recommended: 14+.
- **Extension**: `vector` extension must be installable (e.g. `apt install postgresql-14-pgvector` on Debian/Ubuntu).
- **Backup**: Take a DB backup before migration.
- **Window**: Run during low-traffic period. IVFFlat index creation can lock the table briefly.

---

## Steps

### 1) Ensure vector is off

```bash
# In .env or environment
RAG_VECTOR_ENABLED=false
# Clear allowlist
RAG_VECTOR_ALLOWLIST=
```

Restart backend so all workers run with vector disabled.

### 2) Apply migration 008

```bash
sudo -u postgres psql -d sedi_db -f /path/to/backend/deployment/migrations/008_stage17_6_pgvector.sql
```

Or from repo root:

```bash
sudo -u postgres psql -d sedi_db -f deployment/migrations/008_stage17_6_pgvector.sql
```

### 3) Verify extension and table

```bash
sudo -u postgres psql -d sedi_db -c "SELECT 1 FROM pg_extension WHERE extname = 'vector';"
sudo -u postgres psql -d sedi_db -c "\d rag_embeddings"
```

### 4) Restart backend

Restart the application so it loads the new schema. Vector remains disabled.

### 5) Index one allowlisted user

```bash
# Set allowlist for one user
RAG_VECTOR_ALLOWLIST=1
RAG_VECTOR_ENABLED=true

# Restart backend, then:
curl -X POST "http://localhost:8000/ai_core/admin/index_daily_summaries?user_id=1&days=30" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN"
```

### 6) Validate rag_metrics

Trigger a lifestyle summary or chat for user 1. Then:

```bash
curl -s "http://localhost:8000/ai_core/admin/rag_metrics" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN"
```

Check that `provider_usage.vector` increments.

---

## Rollback

- Set `RAG_VECTOR_ENABLED=false` or clear `RAG_VECTOR_ALLOWLIST`.
- Restart backend.
- **Do not drop** the extension or table; keeping them is safe and allows re-enabling later.

---

## Safety Notes

- **Lock time**: Migration 008 uses `CREATE EXTENSION IF NOT EXISTS` and `CREATE TABLE IF NOT EXISTS`; locks are brief.
- **Index creation**: IVFFlat index may take a few seconds on an empty table. On large tables, increase `lists` after initial load.
- **Best window**: Low-traffic period; 5–10 minutes is typically sufficient.
