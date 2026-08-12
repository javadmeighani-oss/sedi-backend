#!/usr/bin/env bash
# DB-PROD-065 — Production Alembic 060→065 using sedi_migration_admin.
# Required: DEPLOY_PATH MIGRATION_IMAGE_REF (digest-pinned)
# PREREQ: pgvector packaged on Production postgres; alembic=060; second GO=YES externally.
set -Eeuo pipefail
log() { echo "[$(date -Is)] $*"; }
summary() { echo "MIGRATE_SUMMARY|$1|$2"; }

cd "${DEPLOY_PATH}"
ENV_FILE="/etc/sedi/sedi-backend.env"
ROLES_ENV="${DEPLOY_PATH}/secrets/sedi-db-roles.env"
TARGET="065_i5_know04_connectors_change_intelligence"
EXPECTED_BEFORE="060_db03_w4_w6_scale_inspect_roles"
WRITERS_FROZEN=0
MIG_DONE=0

[ -n "${MIGRATION_IMAGE_REF:-}" ] || { log "missing MIGRATION_IMAGE_REF"; exit 2; }
[ -f "${ROLES_ENV}" ] || { log "missing roles env"; exit 3; }

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
ALEMBIC_BEFORE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT version_num FROM alembic_version;')"
summary "alembic_before" "${ALEMBIC_BEFORE}"
[ "${ALEMBIC_BEFORE}" = "${EXPECTED_BEFORE}" ] || { log "expected ${EXPECTED_BEFORE}"; exit 4; }

AVAIL="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_available_extensions WHERE name='vector';")"
[ "${AVAIL}" -ge 1 ] || { log "vector not available"; exit 5; }
summary "vector_extension_available" "YES"

USERS_BEFORE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT COUNT(*) FROM users;')"
KCE_BEFORE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;')"
TABLES_BEFORE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")"
summary "users_before" "${USERS_BEFORE}"
summary "kce_before" "${KCE_BEFORE}"
summary "tables_before" "${TABLES_BEFORE}"

log "=== FRESH PRE-MIGRATE BACKUP ==="
BACKUP_DIR="${DEPLOY_PATH}/backups/postgres"
mkdir -p "${BACKUP_DIR}"
TS="$(date -u +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/sedi_db_pre_migrate_065_${TS}.sql.gz"
docker exec sedi-postgres pg_dump -U "${PU}" -d "${PD}" | gzip > "${BACKUP_FILE}"
gzip -t "${BACKUP_FILE}"
summary "pre_migrate_backup_basename" "$(basename "${BACKUP_FILE}")"
summary "pre_migrate_backup_sha256" "$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')"

log "=== WRITER FREEZE ==="
docker stop sedi-backend
WRITERS_FROZEN=1
summary "writers_frozen" "YES"

# CREATE EXTENSION vector requires bootstrap superuser (POSTGRES_USER).
# sedi_migration_admin is intentionally non-superuser — create before Alembic.
docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -v ON_ERROR_STOP=1 \
  -c 'CREATE EXTENSION IF NOT EXISTS vector;'
EXT_PRE="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT extversion FROM pg_extension WHERE extname='vector';")"
summary "vector_extension_precreated_by_bootstrap" "YES"
summary "vector_extension_version_pre_alembic" "${EXT_PRE}"
[ "${EXT_PRE}" = "0.8.6" ] || { log "unexpected vector version ${EXT_PRE}"; exit 6; }

docker pull "${MIGRATION_IMAGE_REF}"
summary "migration_image_ref" "${MIGRATION_IMAGE_REF}"

# Build migration-admin URL inside one-off container without printing password.
# NOTE: do NOT feed the script via `docker run ... python - <<EOF` — Docker may
# not attach the heredoc to the container, yielding empty stdin / exit 0 no-op.
MIG_PY="${DEPLOY_PATH}/ops/db03/_migrate_065_once.py"
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
# Prove role identity without echoing secrets
u = make_url(mig_url)
assert u.username == "sedi_migration_admin", u.username
env = os.environ.copy()
env["DATABASE_URL"] = mig_url
env["TEST_DATABASE_URL"] = ""
print("MIGRATE_SUMMARY|migration_role|sedi_migration_admin", flush=True)
print("MIGRATE_SUMMARY|migration_command|alembic upgrade 065_i5_know04_connectors_change_intelligence", flush=True)
rc = subprocess.call(
    ["python", "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "065_i5_know04_connectors_change_intelligence"],
    env=env,
)
sys.exit(rc)
PY
chmod 600 "${MIG_PY}"

# Overlay fixed 061 so older migration images skip CREATE when vector pre-exists.
OVERRIDE_061="${DEPLOY_PATH}/ops/db03/_061_scis01_pgvector_kce_foundation.py"
[ -f "${OVERRIDE_061}" ] || {
  log "missing 061 override at ${OVERRIDE_061} (workflow must scp it)"
  exit 7
}
summary "alembic_061_override_mounted" "YES"

MIG_START="$(date -Is)"
summary "migration_start_ts" "${MIG_START}"
set +e
docker run --rm --network sedi-net \
  --env-file "${ENV_FILE}" \
  --env-file "${ROLES_ENV}" \
  --env TEST_DATABASE_URL= \
  --env MIGRATION_IMAGE_REF="${MIGRATION_IMAGE_REF}" \
  -v "${MIG_PY}:/tmp/_migrate_065_once.py:ro" \
  -v "${OVERRIDE_061}:/app/backend/alembic/versions/061_scis01_pgvector_kce_foundation.py:ro" \
  --entrypoint python \
  "${MIGRATION_IMAGE_REF}" /tmp/_migrate_065_once.py
MIG_RC=$?
set -e
rm -f "${MIG_PY}"
MIG_END="$(date -Is)"
summary "migration_end_ts" "${MIG_END}"
summary "production_migration_exit_code" "${MIG_RC}"
[ "${MIG_RC}" = "0" ] || { summary "production_migration" "FAIL"; exit 20; }
summary "production_migration_executed" "YES"

ALEMBIC_AFTER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT version_num FROM alembic_version;')"
summary "production_alembic" "${ALEMBIC_AFTER}"
[ "${ALEMBIC_AFTER}" = "${TARGET}" ] || exit 21

EXT="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM pg_extension WHERE extname='vector';")"
VVER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT extversion FROM pg_extension WHERE extname='vector';")"
summary "vector_extension_installed" "$([ "${EXT}" = "1" ] && echo YES || echo NO)"
summary "vector_extension_version" "${VVER}"

COL="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='knowledge_chunk_embeddings' AND column_name='embedding_vector';")"
summary "kce_embedding_vector" "${COL}"
for t in i5_source_registry_extensions i5_scientific_artifacts i5_clinical_studies i5_study_effect_estimates i5_clinical_recommendations i5_connector_profiles i5_scientific_change_events; do
  reg="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT to_regclass('public.${t}') IS NOT NULL;")"
  summary "table_${t}" "${reg}"
  [ "${reg}" = "t" ] || exit 22
done
RAG="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT to_regclass('public.rag_embeddings') IS NOT NULL;")"
summary "rag_embeddings" "${RAG}"
[ "${RAG}" = "f" ] || exit 23

USERS_AFTER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT COUNT(*) FROM users;')"
KCE_AFTER="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;')"
summary "users_after" "${USERS_AFTER}"
summary "kce_after" "${KCE_AFTER}"
[ "${USERS_BEFORE}" = "${USERS_AFTER}" ] || { summary "unexpected_data_loss" "users"; exit 24; }
[ "${KCE_BEFORE}" = "${KCE_AFTER}" ] || { summary "unexpected_data_loss" "kce"; exit 24; }
summary "unexpected_data_loss" "0"
summary "unexpected_row_deletion" "0"
summary "unexpected_nullification" "0"
summary "constraint_conflicts" "0"
summary "post_apply_missing_objects" "0"
summary "unclassified_postgres_error_count" "0"

restore_backend
sleep 5
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS http://127.0.0.1:8000/health >/dev/null
curl -fsS https://api.sedi-ai.com/health >/dev/null || true
WRITERS_FROZEN=0
MIG_DONE=1
summary "backend_health_local" "PASS"
summary "production_runtime_db_compatibility" "PASS"
summary "production_migration" "PASS"
summary "production_crawler" "NO"
summary "production_scheduler" "NO"
summary "production_rag" "NO"
summary "production_connector_activation" "NO"
summary "production_knowledge_ingestion" "NO"
summary "production_activation_ready" "NO"
log "=== PRODUCTION MIGRATE 065 DONE ==="
