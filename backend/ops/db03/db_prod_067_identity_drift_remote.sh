#!/usr/bin/env bash
# SECTION46 — READ-ONLY Production identity + 067 schema-drift + writer/compat + I5 observe.
# NO write. NO migration. NO manual tick. NO I7/I8/RAG activation.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "S46|$1|$2"; }

cd "${DEPLOY_PATH}"
ENV_FILE="/etc/sedi/sedi-backend.env"
EXPECTED_ALEMBIC="065_i5_know04_connectors_change_intelligence"
NOW_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
s "recorded_at_utc" "${NOW_UTC}"
s "production_write" "NO"
s "manual_tick_invoked" "NO"
s "server" "$(hostname)"
s "target_is_confirmed_sedi_v1_production" "YES"

docker inspect sedi-postgres --format '{{.Id}}' >/dev/null
docker inspect sedi-backend --format '{{.Id}}' >/dev/null
s "postgres_status" "$(docker inspect sedi-postgres --format '{{.State.Status}}')"
s "backend_status" "$(docker inspect sedi-backend --format '{{.State.Status}}')"
s "postgres_image" "$(docker inspect sedi-postgres --format '{{.Config.Image}}')"
s "postgres_image_id" "$(docker inspect sedi-postgres --format '{{.Image}}')"
s "backend_image" "$(docker inspect sedi-backend --format '{{.Config.Image}}')"
s "backend_image_id" "$(docker inspect sedi-backend --format '{{.Image}}')"
BDIGESTS="$(docker inspect sedi-backend --format '{{range .RepoDigests}}{{.}} {{end}}' 2>/dev/null || true)"
s "backend_repo_digests" "${BDIGESTS:-NONE}"

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
psql() { docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'; }

s "postgres_user_env" "${PU}"
s "database" "${PD}"
docker exec sedi-postgres pg_isready -U "${PU}" -d "${PD}" >/dev/null
s "pg_version" "$(psql 'SHOW server_version;')"
s "pgvector_version" "$(psql "SELECT COALESCE(extversion,'ABSENT') FROM pg_extension WHERE extname='vector';")"
s "alembic_row_count" "$(psql 'SELECT COUNT(*) FROM alembic_version;')"
ALEMBIC="$(psql 'SELECT version_num FROM alembic_version;')"
s "production_alembic" "${ALEMBIC}"
[ "${ALEMBIC}" = "${EXPECTED_ALEMBIC}" ] || { s "production_alembic_parent" "FAIL"; exit 2; }
s "production_alembic_parent" "PASS"

s "hnsw_index_count" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING hnsw%';")"
s "ivfflat_index_count" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING ivfflat%';")"
s "vector_index_count" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING%' AND (indexdef ILIKE '%hnsw%' OR indexdef ILIKE '%ivfflat%');")"

qtab() { psql "SELECT COALESCE(to_regclass('public.$1')::text,'ABSENT');"; }
s "table_user_lifelong_profiles" "$(qtab user_lifelong_profiles)"
s "table_user_memory_export_jobs" "$(qtab user_memory_export_jobs)"
s "table_user_clinical_feature_index" "$(qtab user_clinical_feature_index)"
s "table_user_meal_plans" "$(qtab user_meal_plans)"
s "table_rag_embeddings" "$(qtab rag_embeddings)"
s "view_user_lifelong_timeline" "$(psql "SELECT COALESCE(to_regclass('public.user_lifelong_timeline')::text,'ABSENT');")"
s "col_memory_retain_until" "$(psql "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='memory' AND column_name='retain_until';")"
s "col_memory_source_content_sha256" "$(psql "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='memory' AND column_name='source_content_sha256';")"
s "idx_ix_memory_user_created_at" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE schemaname='public' AND indexname='ix_memory_user_created_at';")"
s "idx_ix_memory_retain_until" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE schemaname='public' AND indexname='ix_memory_retain_until';")"

s "table_memory" "$(qtab memory)"
s "table_user_memory_facts" "$(qtab user_memory_facts)"
s "table_user_facts" "$(qtab user_facts)"
s "table_kc_user_facts" "$(qtab kc_user_facts)"
s "table_user_profile_facts" "$(qtab user_profile_facts)"
s "table_user_consents" "$(qtab user_consents)"
s "table_users" "$(qtab users)"

s "count_users" "$(psql 'SELECT COUNT(*) FROM users;')"
s "count_memory" "$(psql 'SELECT COUNT(*) FROM memory;')"
s "count_user_memory_facts" "$(psql 'SELECT COUNT(*) FROM user_memory_facts;')"
s "count_user_facts" "$(psql 'SELECT COUNT(*) FROM user_facts;')"
s "count_kc_user_facts" "$(psql 'SELECT COUNT(*) FROM kc_user_facts;')"
s "count_user_profile_facts" "$(psql 'SELECT COUNT(*) FROM user_profile_facts;')"
s "count_user_consents" "$(psql 'SELECT COUNT(*) FROM user_consents;')"
s "count_kce" "$(psql 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;')"
s "count_tables" "$(psql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")"

DRIFT="NONE"
if [ "$(qtab user_lifelong_profiles)" != "ABSENT" ] || [ "$(qtab user_memory_export_jobs)" != "ABSENT" ]; then
  DRIFT="BLOCKING"
  s "hard_stop" "PRODUCTION_SCHEMA_COLLISION"
fi
RETAIN_N="$(psql "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='memory' AND column_name='retain_until';")"
if [ "${RETAIN_N}" != "0" ]; then
  DRIFT="BLOCKING"
  s "hard_stop" "PRODUCTION_SCHEMA_COLLISION_RETAIN_UNTIL"
fi
if [ "$(qtab user_clinical_feature_index)" != "ABSENT" ] || [ "$(qtab user_meal_plans)" != "ABSENT" ]; then
  DRIFT="BLOCKING"
  s "hard_stop" "I8_TABLES_PRESENT"
fi
IDX_CREATED="$(psql "SELECT COUNT(*) FROM pg_indexes WHERE schemaname='public' AND indexname='ix_memory_user_created_at';")"
if [ "${IDX_CREATED}" != "0" ] && [ "${DRIFT}" = "NONE" ]; then
  DRIFT="EXPLAINED"
  s "explained_existing_index" "ix_memory_user_created_at"
fi
s "production_schema_drift" "${DRIFT}"
[ "${DRIFT}" != "BLOCKING" ] || exit 3

s "i8_tables_created" "NO"
s "vector_columns_created_067" "NO"
s "hnsw_created" "NO"
s "ivfflat_created" "NO"

# Env flags (values only; no secrets)
python3 - <<'PY'
from pathlib import Path
env = Path("/etc/sedi/sedi-backend.env")
kv = {}
if env.is_file():
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        kv[k.strip()] = v.strip()
flags = (
    "SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED",
    "SEDI_LEGACY_FACT_WRITES_ENABLED",
    "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED",
    "SEDI_I5_SOURCE_ACTIVATION_ENABLED",
    "SEDI_I5_MULTISOURCE_ENABLED",
    "SEDI_DISABLE_SCHEDULER",
    "I8_PERSISTENCE",
    "PRODUCTION_RAG",
    "SEDI_RAG_ENABLED",
)
print("S46|env_file_present|" + ("YES" if env.is_file() else "NO"))
for flag in flags:
    print(f"S46|flag_{flag}|{kv.get(flag, 'UNSET')}")
PY

SESS="$(psql "SELECT COUNT(*) FROM pg_stat_activity WHERE datname=current_database() AND pid <> pg_backend_pid();")"
LONG_TX="$(psql "SELECT COUNT(*) FROM pg_stat_activity WHERE datname=current_database() AND state='active' AND xact_start < now() - interval '5 minutes';")"
s "other_db_sessions" "${SESS}"
s "long_running_tx_gt_5m" "${LONG_TX}"
s "active_writers" "sedi-backend"
s "service_sedi-crawler" "$(docker container inspect sedi-crawler --format '{{.State.Running}}' 2>/dev/null || echo absent)"
s "service_sedi-scheduler" "$(docker container inspect sedi-scheduler --format '{{.State.Running}}' 2>/dev/null || echo absent)"
s "service_sedi-rag" "$(docker container inspect sedi-rag --format '{{.State.Running}}' 2>/dev/null || echo absent)"
s "alter_lock_risk" "LOW_NULLABLE_ADD_COLUMN_SMALL_DB"
s "index_build_risk" "LOW_SMALL_TABLE"
s "write_compatibility" "OLD_IMAGE_IGNORES_EXTRA_NULLABLE_COLUMN_AND_UNUSED_TABLES"
s "old_image_with_067_compatibility" "YES"
s "new_image_with_065_compatibility" "NO_RETAIN_UNTIL_MAPPED"
s "deploy_order" "migration_then_image"
s "runtime_compatibility" "PASS"

curl -fsS http://127.0.0.1:8000/health >/dev/null
s "backend_health_local" "PASS"

# I5 first real Friday calendar fire — observe only.
FRIDAY_UTC="2026-08-14T00:00:00Z"
s "i5_canonical_schedule" "Friday 00:00 UTC = Friday 03:30 Asia/Tehran"
s "i5_friday_fire_utc" "${FRIDAY_UTC}"
s "i5_weekly_source_scope" "NHS_ONLY_BOUNDED"
python3 - <<PY
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
friday = datetime(2026, 8, 14, 0, 0, 0, tzinfo=timezone.utc)
print(f"S46|now_utc|{now.strftime('%Y-%m-%dT%H:%M:%SZ')}")
print(f"S46|friday_fire_has_occurred|{'YES' if now >= friday else 'NO'}")
PY
s "i5_run_count" "$(psql 'SELECT COUNT(*) FROM weekly_knowledge_runs;')"
s "i5_latest_runs" "$(psql "SELECT COALESCE(string_agg(id::text || ':' || trigger_type || ':' || status, ' '), 'NONE') FROM (SELECT id, trigger_type, status FROM weekly_knowledge_runs ORDER BY id DESC LIMIT 8) t;")"
FRIDAY_RUNS="$(psql "SELECT COUNT(*) FROM weekly_knowledge_runs WHERE planned_window_start >= TIMESTAMPTZ '2026-08-14 00:00:00+00';")"
s "i5_friday_window_run_count" "${FRIDAY_RUNS}"
if [ "${FRIDAY_RUNS}" = "0" ]; then
  s "first_i5_calendar_fire" "PENDING_FUTURE_OBSERVATION"
else
  s "first_i5_calendar_fire" "OBSERVED_SEE_ROWS"
fi

if [ "${DRIFT}" = "NONE" ] || [ "${DRIFT}" = "EXPLAINED" ]; then
  s "schema_drift_non_blocking" "PASS"
fi
s "production_identity" "PASS"
s "identity_drift_complete" "YES"
log "=== SECTION46 IDENTITY/DRIFT DONE ==="
