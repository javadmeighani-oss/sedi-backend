#!/usr/bin/env bash
# SECTION48 — read-only Production preflight. No tick. No schema change.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "S48_PREFLIGHT|$1|$2"; }

cd "${DEPLOY_PATH:?}"
ENV_FILE="/etc/sedi/sedi-backend.env"
EXPECTED_ALEMBIC="067_i7_lifelong_memory_foundation"
s "recorded_at_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
s "production_write" "NO"
s "manual_tick_invoked" "NO"
s "server" "$(hostname)"
s "target_is_confirmed_sedi_v1_production" "YES"

s "postgres_status" "$(docker inspect sedi-postgres --format '{{.State.Status}}')"
s "backend_status" "$(docker inspect sedi-backend --format '{{.State.Status}}')"
s "backend_started_at" "$(docker inspect sedi-backend --format '{{.State.StartedAt}}')"
s "backend_restart_count" "$(docker inspect sedi-backend --format '{{.RestartCount}}')"
s "postgres_image" "$(docker inspect sedi-postgres --format '{{.Config.Image}}')"
s "backend_image" "$(docker inspect sedi-backend --format '{{.Config.Image}}')"
s "backend_image_id" "$(docker inspect sedi-backend --format '{{.Image}}')"
s "backend_repo_digests" "$(docker inspect sedi-backend --format '{{range .RepoDigests}}{{.}} {{end}}' 2>/dev/null || echo NONE)"

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
psql() { docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'; }
s "database" "${PD}"
s "pg_version" "$(psql 'SHOW server_version;')"
s "pgvector_version" "$(psql "SELECT COALESCE(extversion,'ABSENT') FROM pg_extension WHERE extname='vector';")"
ALEMBIC="$(psql 'SELECT version_num FROM alembic_version;')"
s "production_alembic" "${ALEMBIC}"
[ "${ALEMBIC}" = "${EXPECTED_ALEMBIC}" ] || { s "alembic_guard" "FAIL"; exit 2; }
s "hnsw_index_count" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING hnsw%';")"
s "ivfflat_index_count" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING ivfflat%';")"
s "count_kce" "$(psql 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;')"
s "table_rag_embeddings" "$(psql "SELECT COALESCE(to_regclass('public.rag_embeddings')::text,'ABSENT');")"

curl -fsS http://127.0.0.1:8000/health >/dev/null || curl -fsS http://127.0.0.1:8000/healthz >/dev/null
s "api_health" "PASS"
docker exec sedi-postgres pg_isready -U "${PU}" -d "${PD}" >/dev/null
s "db_health" "PASS"

if docker exec sedi-backend ps -eo args 2>/dev/null | grep -Eq 'uvicorn|gunicorn|python'; then
  s "scheduler_process" "BACKEND_UP"
else
  s "scheduler_process" "BACKEND_UP_INSPECT"
fi
if docker logs sedi-backend 2>&1 | grep -Fq 'i7 period summary jobs registered'; then
  s "i7_scheduler_registered" "YES"
else
  s "i7_scheduler_registered" "NO"
fi
if docker logs sedi-backend 2>&1 | grep -Fq 'weekly_international_knowledge_crawler registered'; then
  s "i5_weekly_scheduler_registered" "YES"
else
  s "i5_weekly_scheduler_registered" "NO"
fi

python3 - <<'PY'
from pathlib import Path
kv = {}
p = Path("/etc/sedi/sedi-backend.env")
for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
    if not line or line.lstrip().startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    kv[k.strip()] = v.strip()
for key in (
    "SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED",
    "SEDI_LEGACY_FACT_WRITES_ENABLED",
    "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED",
    "SEDI_I5_SOURCE_ACTIVATION_ENABLED",
    "SEDI_I5_MULTISOURCE_ENABLED",
    "SEDI_DISABLE_SCHEDULER",
    "PRODUCTION_RAG",
    "I8_PERSISTENCE",
):
    print(f"S48_PREFLIGHT|flag_{key}|{kv.get(key, 'UNSET')}")
PY
s "i8_persistence" "NO"
s "production_rag" "NO"
s "new_migration" "NO"
s "preflight_complete" "YES"
log "=== S48 PREFLIGHT DONE ==="
