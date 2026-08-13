#!/usr/bin/env bash
# SECTION46 — Production Alembic 065→067_i7_lifelong_memory_foundation.
# Required: DEPLOY_PATH
# Uses currently running backend image + mounted 067 file from this Gate checkout.
# NO 066. NO I8. NO vector/RAG. NO ownership redesign unless required.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "S46_MIG|$1|$2"; }

cd "${DEPLOY_PATH}"
ENV_FILE="/etc/sedi/sedi-backend.env"
ROLES_ENV="${DEPLOY_PATH}/secrets/sedi-db-roles.env"
TARGET="067_i7_lifelong_memory_foundation"
EXPECTED_BEFORE="065_i5_know04_connectors_change_intelligence"
OVERRIDE_067="${DEPLOY_PATH}/ops/db03/_067_i7_lifelong_memory_foundation.py"
WRITERS_FROZEN=0
MIG_DONE=0

[ -f "${ROLES_ENV}" ] || { log "missing roles env"; exit 3; }
[ -f "${OVERRIDE_067}" ] || { log "missing 067 overlay at ${OVERRIDE_067}"; exit 7; }

restore_backend() {
  CURRENT_TAG="$(docker inspect sedi-backend --format '{{.Config.Image}}' 2>/dev/null || true)"
  IMAGE_TAG="${CURRENT_TAG##*:}"
  if [ -f compose.production.yml ] && [ -n "${IMAGE_TAG}" ]; then
    SEDI_IMAGE_TAG="${IMAGE_TAG}" docker compose -f compose.production.yml up -d --no-deps sedi-backend || true
  else
    docker start sedi-backend || true
  fi
}

on_exit() {
  rc=$?
  if [ "${WRITERS_FROZEN}" = "1" ] && [ "${MIG_DONE}" != "1" ]; then
    restore_backend || true
  fi
  exit "${rc}"
}
trap on_exit EXIT

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
psql() { docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'; }

ALEMBIC_BEFORE="$(psql 'SELECT version_num FROM alembic_version;')"
s "alembic_before" "${ALEMBIC_BEFORE}"
[ "${ALEMBIC_BEFORE}" = "${EXPECTED_BEFORE}" ] || { log "expected ${EXPECTED_BEFORE}"; exit 4; }

RUNNING_IMAGE="$(docker inspect sedi-backend --format '{{.Image}}')"
RUNNING_NAME="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
s "migration_image_id" "${RUNNING_IMAGE}"
s "migration_image_name" "${RUNNING_NAME}"
s "migration_067_overlay_mounted" "YES"

USERS_BEFORE="$(psql 'SELECT COUNT(*) FROM users;')"
MEM_BEFORE="$(psql 'SELECT COUNT(*) FROM memory;')"
UMF_BEFORE="$(psql 'SELECT COUNT(*) FROM user_memory_facts;')"
UF_BEFORE="$(psql 'SELECT COUNT(*) FROM user_facts;')"
KCUF_BEFORE="$(psql 'SELECT COUNT(*) FROM kc_user_facts;')"
UPF_BEFORE="$(psql 'SELECT COUNT(*) FROM user_profile_facts;')"
UC_BEFORE="$(psql 'SELECT COUNT(*) FROM user_consents;')"
KCE_BEFORE="$(psql 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;')"
s "users_before" "${USERS_BEFORE}"
s "memory_before" "${MEM_BEFORE}"
s "user_memory_facts_before" "${UMF_BEFORE}"
s "user_facts_before" "${UF_BEFORE}"
s "kc_user_facts_before" "${KCUF_BEFORE}"
s "user_profile_facts_before" "${UPF_BEFORE}"
s "user_consents_before" "${UC_BEFORE}"
s "kce_before" "${KCE_BEFORE}"

log "=== WRITER FREEZE ==="
docker stop sedi-backend
WRITERS_FROZEN=1
s "writers_frozen" "YES"

MIG_PY="${DEPLOY_PATH}/ops/db03/_migrate_067_once.py"
umask 077
mkdir -p "$(dirname "${MIG_PY}")"
cat > "${MIG_PY}" <<'PY'
import os, subprocess, sys
from urllib.parse import urlsplit, urlunsplit, quote
from sqlalchemy.engine import make_url

raw = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
parts = urlsplit(raw)
pw = os.environ["SEDI_MIGRATION_ADMIN_PASSWORD"]
auth = f"sedi_migration_admin:{quote(pw, safe='')}"
host = parts.hostname or ""
port = f":{parts.port}" if parts.port else ""
netloc = f"{auth}@{host}{port}"
mig_url = urlunsplit(("postgresql+psycopg2", netloc, parts.path, parts.query, parts.fragment))
u = make_url(mig_url)
assert u.username == "sedi_migration_admin", u.username
env = os.environ.copy()
env["DATABASE_URL"] = mig_url
env["TEST_DATABASE_URL"] = ""
print("S46_MIG|migration_role|sedi_migration_admin", flush=True)
print("S46_MIG|migration_command|alembic upgrade 067_i7_lifelong_memory_foundation", flush=True)
print("S46_MIG|migration_066|NO", flush=True)
rc = subprocess.call(
    ["python", "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "067_i7_lifelong_memory_foundation"],
    env=env,
)
sys.exit(rc)
PY
chmod 600 "${MIG_PY}"

MIG_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
s "migration_start_ts" "${MIG_START}"
set +e
docker run --rm --network sedi-net \
  --env-file "${ENV_FILE}" \
  --env-file "${ROLES_ENV}" \
  --env TEST_DATABASE_URL= \
  -v "${MIG_PY}:/tmp/_migrate_067_once.py:ro" \
  -v "${OVERRIDE_067}:/app/backend/alembic/versions/067_i7_lifelong_memory_foundation.py:ro" \
  --entrypoint python \
  "${RUNNING_IMAGE}" /tmp/_migrate_067_once.py
MIG_RC=$?
set -e
rm -f "${MIG_PY}"
MIG_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
s "migration_end_ts" "${MIG_END}"
s "production_migration_exit_code" "${MIG_RC}"
[ "${MIG_RC}" = "0" ] || { s "production_migration" "FAIL"; exit 20; }

ALEMBIC_AFTER="$(psql 'SELECT version_num FROM alembic_version;')"
s "production_alembic_after" "${ALEMBIC_AFTER}"
[ "${ALEMBIC_AFTER}" = "${TARGET}" ] || exit 21

s "table_user_lifelong_profiles" "$(psql "SELECT to_regclass('public.user_lifelong_profiles') IS NOT NULL;")"
s "table_user_memory_export_jobs" "$(psql "SELECT to_regclass('public.user_memory_export_jobs') IS NOT NULL;")"
s "col_memory_retain_until" "$(psql "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='memory' AND column_name='retain_until';")"
s "ck_ulp_status_vocab" "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='ck_ulp_status_vocab';")"
s "ck_umej_status_vocab" "$(psql "SELECT COUNT(*) FROM pg_constraint WHERE conname='ck_umej_status_vocab';")"
s "table_user_clinical_feature_index" "$(psql "SELECT to_regclass('public.user_clinical_feature_index') IS NOT NULL;")"
s "table_user_meal_plans" "$(psql "SELECT to_regclass('public.user_meal_plans') IS NOT NULL;")"
s "view_user_lifelong_timeline" "$(psql "SELECT to_regclass('public.user_lifelong_timeline') IS NOT NULL;")"
s "hnsw_index_count" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING hnsw%';")"
s "ivfflat_index_count" "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING ivfflat%';")"
[ "$(psql "SELECT to_regclass('public.user_lifelong_profiles') IS NOT NULL;")" = "t" ] || exit 22
[ "$(psql "SELECT to_regclass('public.user_memory_export_jobs') IS NOT NULL;")" = "t" ] || exit 22
[ "$(psql "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='memory' AND column_name='retain_until';")" = "1" ] || exit 22
[ "$(psql "SELECT to_regclass('public.user_clinical_feature_index') IS NOT NULL;")" = "f" ] || exit 23
[ "$(psql "SELECT to_regclass('public.user_meal_plans') IS NOT NULL;")" = "f" ] || exit 23
[ "$(psql "SELECT COUNT(*) FROM pg_indexes WHERE indexdef ILIKE '%USING hnsw%' OR indexdef ILIKE '%USING ivfflat%';")" = "0" ] || exit 23

USERS_AFTER="$(psql 'SELECT COUNT(*) FROM users;')"
MEM_AFTER="$(psql 'SELECT COUNT(*) FROM memory;')"
UMF_AFTER="$(psql 'SELECT COUNT(*) FROM user_memory_facts;')"
UF_AFTER="$(psql 'SELECT COUNT(*) FROM user_facts;')"
KCUF_AFTER="$(psql 'SELECT COUNT(*) FROM kc_user_facts;')"
UPF_AFTER="$(psql 'SELECT COUNT(*) FROM user_profile_facts;')"
UC_AFTER="$(psql 'SELECT COUNT(*) FROM user_consents;')"
KCE_AFTER="$(psql 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;')"
s "users_after" "${USERS_AFTER}"
s "memory_after" "${MEM_AFTER}"
s "user_memory_facts_after" "${UMF_AFTER}"
s "user_facts_after" "${UF_AFTER}"
s "kc_user_facts_after" "${KCUF_AFTER}"
s "user_profile_facts_after" "${UPF_AFTER}"
s "user_consents_after" "${UC_AFTER}"
s "kce_after" "${KCE_AFTER}"
[ "${USERS_BEFORE}" = "${USERS_AFTER}" ] || { s "unexpected_data_loss" "users"; exit 24; }
[ "${MEM_BEFORE}" = "${MEM_AFTER}" ] || { s "unexpected_data_loss" "memory"; exit 24; }
[ "${UMF_BEFORE}" = "${UMF_AFTER}" ] || { s "unexpected_data_loss" "user_memory_facts"; exit 24; }
[ "${UF_BEFORE}" = "${UF_AFTER}" ] || { s "unexpected_data_loss" "user_facts"; exit 24; }
[ "${KCUF_BEFORE}" = "${KCUF_AFTER}" ] || { s "unexpected_data_loss" "kc_user_facts"; exit 24; }
[ "${UPF_BEFORE}" = "${UPF_AFTER}" ] || { s "unexpected_data_loss" "user_profile_facts"; exit 24; }
[ "${UC_BEFORE}" = "${UC_AFTER}" ] || { s "unexpected_data_loss" "user_consents"; exit 24; }
[ "${KCE_BEFORE}" = "${KCE_AFTER}" ] || { s "unexpected_data_loss" "kce"; exit 24; }
s "no_user_row_deletion" "PASS"
s "no_legacy_fact_row_deletion" "PASS"
s "no_canonical_fact_loss" "PASS"
s "unexpected_data_loss" "0"

restore_backend
sleep 5
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS http://127.0.0.1:8000/health >/dev/null
WRITERS_FROZEN=0
MIG_DONE=1
s "backend_health_local" "PASS"
s "production_runtime_db_compatibility" "PASS"
s "production_migration_067" "PASS"
s "i7_jobs_enabled" "NO"
s "i8_persistence" "NO"
s "production_rag" "NO"
s "migration_066" "NO"
log "=== PRODUCTION MIGRATE 067 DONE ==="
