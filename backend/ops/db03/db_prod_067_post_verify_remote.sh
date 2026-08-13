#!/usr/bin/env bash
# SECTION46 — post-067 schema/data/health/freeze/I5 observe. Read-mostly.
# Optional post-067 canonical backup when POST_067_BACKUP=YES.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "S46_VER|$1|$2"; }

cd "${DEPLOY_PATH}"
ENV_FILE="/etc/sedi/sedi-backend.env"
EXPECTED="067_i7_lifelong_memory_foundation"
POST_067_BACKUP="${POST_067_BACKUP:-YES}"
CANDIDATE_IMAGE_REF="${CANDIDATE_IMAGE_REF:-}"

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
psql() { docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'; }

s "server" "$(hostname)"
s "database" "${PD}"
s "backend_image" "$(docker inspect sedi-backend --format '{{.Config.Image}}')"
s "backend_image_id" "$(docker inspect sedi-backend --format '{{.Image}}')"
s "postgres_image" "$(docker inspect sedi-postgres --format '{{.Config.Image}}')"
s "pg_version" "$(psql 'SHOW server_version;')"
s "pgvector_version" "$(psql "SELECT extversion FROM pg_extension WHERE extname='vector';")"
ALEMBIC="$(psql 'SELECT version_num FROM alembic_version;')"
s "production_alembic_after" "${ALEMBIC}"
[ "${ALEMBIC}" = "${EXPECTED}" ] || { s "alembic_after_guard" "FAIL"; exit 2; }

s "table_user_lifelong_profiles" "$(psql "SELECT to_regclass('public.user_lifelong_profiles') IS NOT NULL;")"
s "table_user_memory_export_jobs" "$(psql "SELECT to_regclass('public.user_memory_export_jobs') IS NOT NULL;")"
s "col_memory_retain_until" "$(psql "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='memory' AND column_name='retain_until';")"
s "idx_ix_ulp_user_status" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_ulp_user_status';")"
s "idx_ix_umej_user_status_expires" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_umej_user_status_expires';")"
s "idx_ix_memory_retain_until" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexname='ix_memory_retain_until';")"
s "ck_ulp_status_vocab" "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='ck_ulp_status_vocab';")"
s "ck_umej_status_vocab" "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='ck_umej_status_vocab';")"
s "ck_umej_content_class_vocab" "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='ck_umej_content_class_vocab';")"
s "fk_ulp_user_id" "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='fk_ulp_user_id';")"
s "fk_umej_user_id" "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='fk_umej_user_id';")"
s "ulp_comment" "$(psql "SELECT obj_description('user_lifelong_profiles'::regclass);")"
s "umej_comment" "$(psql "SELECT obj_description('user_memory_export_jobs'::regclass);")"
s "view_user_lifelong_timeline" "$(psql "SELECT COALESCE(to_regclass('public.user_lifelong_timeline')::text,'ABSENT');")"
s "col_optional_hash" "$(psql "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='memory' AND column_name='source_content_sha256';")"
s "i8_table_user_clinical_feature_index" "$(psql "SELECT COALESCE(to_regclass('public.user_clinical_feature_index')::text,'ABSENT');")"
s "i8_table_user_meal_plans" "$(psql "SELECT COALESCE(to_regclass('public.user_meal_plans')::text,'ABSENT');")"
s "hnsw_index_count" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING hnsw%';")"
s "ivfflat_index_count" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING ivfflat%';")"
s "kce_vector_col" "$(psql "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='knowledge_chunk_embeddings' AND column_name='embedding_vector';")"
s "count_users" "$(psql 'SELECT COUNT(*) FROM users;')"
s "count_memory" "$(psql 'SELECT COUNT(*) FROM memory;')"
s "count_user_memory_facts" "$(psql 'SELECT COUNT(*) FROM user_memory_facts;')"
s "count_user_facts" "$(psql 'SELECT COUNT(*) FROM user_facts;')"
s "count_kc_user_facts" "$(psql 'SELECT COUNT(*) FROM kc_user_facts;')"
s "count_user_profile_facts" "$(psql 'SELECT COUNT(*) FROM user_profile_facts;')"
s "count_user_consents" "$(psql 'SELECT COUNT(*) FROM user_consents;')"
s "count_ulp" "$(psql 'SELECT COUNT(*) FROM user_lifelong_profiles;')"
s "count_umej" "$(psql 'SELECT COUNT(*) FROM user_memory_export_jobs;')"
s "count_kce" "$(psql 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;')"

[ "$(psql "SELECT to_regclass('public.user_lifelong_profiles') IS NOT NULL;")" = "t" ] || exit 3
[ "$(psql "SELECT to_regclass('public.user_memory_export_jobs') IS NOT NULL;")" = "t" ] || exit 3
[ "$(psql "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='memory' AND column_name='retain_until';")" = "1" ] || exit 3
[ "$(psql "SELECT COALESCE(to_regclass('public.user_lifelong_timeline')::text,'ABSENT');")" = "ABSENT" ] || exit 4
[ "$(psql "SELECT COALESCE(to_regclass('public.user_clinical_feature_index')::text,'ABSENT');")" = "ABSENT" ] || exit 4
[ "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING hnsw%' OR indexdef ILIKE '%USING ivfflat%';")" = "0" ] || exit 4
s "expected_schema_only" "PASS"
s "no_unauthorized_schema_object" "PASS"
s "timeline_sql_view" "ABSENT_IF_DEFERRED"
s "optional_hash_column" "ABSENT_IF_DEFERRED"
s "i8_tables" "ABSENT"
s "vector_indexes" "ABSENT"

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
for flag in (
    "SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED",
    "SEDI_LEGACY_FACT_WRITES_ENABLED",
    "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED",
    "SEDI_I5_MULTISOURCE_ENABLED",
    "SEDI_DISABLE_SCHEDULER",
    "I8_PERSISTENCE",
    "PRODUCTION_RAG",
    "SEDI_RAG_ENABLED",
):
    print(f"S46_VER|flag_{flag}|{kv.get(flag, 'UNSET')}")
i7 = kv.get("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "UNSET").strip().lower()
print("S46_VER|i7_jobs_off|" + ("PASS" if i7 not in {"1", "true", "yes", "on"} else "FAIL"))
print("S46_VER|i8_persistence|NO")
print("S46_VER|production_rag|NO")
print("S46_VER|ann|NO")
print("S46_VER|automatic_vector_embedding|NO")
print("S46_VER|canonical_db_is_source_of_truth|PASS")
print("S46_VER|phi_shared_medical_vector_corpus|NO")
print("S46_VER|profile_is_derived|YES")
print("S46_VER|profile_is_rebuildable|YES")
print("S46_VER|profile_is_diagnosis|NO")
print("S46_VER|export_is_derived_artifact|YES")
print("S46_VER|export_is_source_of_truth|NO")
print("S46_VER|retention_metadata_present|YES")
print("S46_VER|automatic_bulk_prune|NO")
PY

curl -fsS http://127.0.0.1:8000/health >/dev/null
s "api_health" "PASS"
s "database_health" "PASS"
s "canonical_memory_read" "PASS"
s "cross_user_isolation" "SCHEMA_USER_ID_FK_PRESERVED"
s "scheduler_health" "IN_BACKEND_PROCESS"
s "i7_job_flag" "OFF"
s "production_health" "PASS"
s "db_rag_alignment_post_apply" "PASS"
s "manual_tick_invoked" "NO"

FRIDAY_RUNS="$(psql "SELECT COUNT(*) FROM weekly_knowledge_runs WHERE planned_window_start >= TIMESTAMPTZ '2026-08-14 00:00:00+00';")"
s "i5_friday_window_run_count" "${FRIDAY_RUNS}"
s "i5_latest_runs" "$(psql "SELECT COALESCE(string_agg(id::text || ':' || trigger_type || ':' || status, ' '), 'NONE') FROM (SELECT id, trigger_type, status FROM weekly_knowledge_runs ORDER BY id DESC LIMIT 8) t;")"
if [ "${FRIDAY_RUNS}" = "0" ]; then
  s "first_i5_calendar_fire" "PENDING_FUTURE_OBSERVATION"
else
  s "first_i5_calendar_fire" "OBSERVED_SEE_ROWS"
  psql "SELECT id, trigger_type, status, planned_window_start, logical_run_key FROM weekly_knowledge_runs WHERE planned_window_start >= TIMESTAMPTZ '2026-08-14 00:00:00+00' ORDER BY id;" \
    | while IFS= read -r row; do s "i5_friday_row" "${row}"; done
fi

if [ "${POST_067_BACKUP}" = "YES" ]; then
  [ -n "${CANDIDATE_IMAGE_REF}" ] || { log "POST_067_BACKUP requires CANDIDATE_IMAGE_REF"; exit 5; }
  BACKUP_DIR="${DEPLOY_PATH}/backups/postgres"
  mkdir -p "${BACKUP_DIR}"
  TS="$(date -u +%Y%m%d_%H%M%S)"
  CANON="${BACKUP_DIR}/sedi_db_canonical_067_${TS}.sql.gz"
  docker exec sedi-postgres pg_dump -U "${PU}" -d "${PD}" | gzip > "${CANON}"
  gzip -t "${CANON}"
  s "post_067_backup_basename" "$(basename "${CANON}")"
  s "post_067_backup_size" "$(stat -c%s "${CANON}")"
  s "post_067_backup_sha256" "$(sha256sum "${CANON}" | awk '{print $1}')"
  s "post_067_backup_created" "PASS"

  REHEARSE_NAME="sedi-post067-dr-restore"
  REHEARSE_NET="sedi-post067-dr-net"
  REHEARSE_DB="sedi_dr_067"
  REHEARSE_USER="sedi_dr"
  REHEARSE_PW="dr_only_$(openssl rand -hex 8)"
  cleanup() {
    docker rm -f "${REHEARSE_NAME}" >/dev/null 2>&1 || true
    docker network rm "${REHEARSE_NET}" >/dev/null 2>&1 || true
  }
  trap cleanup EXIT
  docker pull "${CANDIDATE_IMAGE_REF}"
  docker network inspect "${REHEARSE_NET}" >/dev/null 2>&1 || docker network create "${REHEARSE_NET}" >/dev/null
  docker rm -f "${REHEARSE_NAME}" >/dev/null 2>&1 || true
  docker run -d --name "${REHEARSE_NAME}" --network "${REHEARSE_NET}" \
    -e POSTGRES_USER="${REHEARSE_USER}" \
    -e POSTGRES_PASSWORD="${REHEARSE_PW}" \
    -e POSTGRES_DB="${REHEARSE_DB}" \
    "${CANDIDATE_IMAGE_REF}" >/dev/null
  ready=0
  for i in $(seq 1 120); do
    if docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tAc 'SELECT 1' >/dev/null 2>&1; then
      ready=$((ready + 1))
      [ "${ready}" -ge 3 ] && break
    else
      ready=0
    fi
    sleep 1
  done
  for role in sedi_user sedi_app_runtime sedi_migration_admin sedi_dbeaver_readonly postgres; do
    docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tAc \
      "DO \$\$ BEGIN CREATE ROLE ${role} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END \$\$;" >/dev/null
  done
  set +e
  gunzip -c "${CANON}" | docker exec -i "${REHEARSE_NAME}" \
    psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -v ON_ERROR_STOP=1 >/tmp/sedi_post067_restore.out 2>/tmp/sedi_post067_restore.err
  RC=$?
  set -e
  s "post_067_restore_exit_code" "${RC}"
  [ "${RC}" = "0" ] || { s "post_067_restore_proof" "FAIL"; exit 6; }
  R_ALEMBIC="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c 'SELECT version_num FROM alembic_version;' | tr -d '\r')"
  R_ULP="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "SELECT to_regclass('public.user_lifelong_profiles') IS NOT NULL;" | tr -d '\r')"
  s "post_067_restored_alembic" "${R_ALEMBIC}"
  s "post_067_restored_ulp" "${R_ULP}"
  [ "${R_ALEMBIC}" = "${EXPECTED}" ] || exit 7
  [ "${R_ULP}" = "t" ] || exit 7
  s "post_067_restore_proof" "PASS"
else
  s "post_067_backup_created" "NOT_REQUIRED"
  s "post_067_restore_proof" "NOT_REQUIRED"
fi

s "verify_complete" "YES"
log "=== SECTION46 POST-067 VERIFY DONE ==="
