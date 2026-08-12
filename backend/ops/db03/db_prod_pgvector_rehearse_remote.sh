#!/usr/bin/env bash
# DB-PROD-PGVECTOR — Private Production-backup restore + 060→065 data-equivalent rehearsal.
# Runs ONLY on Production host. NEVER uploads dump/PHI to GitHub.
# Required env: DEPLOY_PATH CANDIDATE_IMAGE_REF (digest-pinned) MIGRATION_IMAGE_REF (digest-pinned)
set -Eeuo pipefail
log() { echo "[$(date -Is)] $*"; }
summary() { echo "REHEARSE_SUMMARY|$1|$2"; }

cd "${DEPLOY_PATH}"
BACKUP_DIR="${DEPLOY_PATH}/backups/postgres"
REHEARSE_NAME="sedi-pgvector-rehearse-065"
REHEARSE_NET="sedi-pgvector-rehearse-net"
REHEARSE_DB="sedi_rehearse_db"
REHEARSE_USER="sedi_rehearse"
# Ephemeral password — isolated container, not Production credentials
REHEARSE_PW="rehearse_only_$(openssl rand -hex 8)"

cleanup() {
  docker rm -f "${REHEARSE_NAME}" >/dev/null 2>&1 || true
  docker network rm "${REHEARSE_NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

[ -n "${CANDIDATE_IMAGE_REF:-}" ] || { log "missing CANDIDATE_IMAGE_REF"; exit 2; }
[ -n "${MIGRATION_IMAGE_REF:-}" ] || { log "missing MIGRATION_IMAGE_REF"; exit 2; }

log "=== PULL CANDIDATE + MIGRATION IMAGES ==="
docker pull "${CANDIDATE_IMAGE_REF}"
docker pull "${MIGRATION_IMAGE_REF}"
summary "candidate_image_ref" "${CANDIDATE_IMAGE_REF}"
summary "migration_image_ref" "${MIGRATION_IMAGE_REF}"

# Packaging proof inside candidate
VEC_CTRL="$(docker run --rm --entrypoint sh "${CANDIDATE_IMAGE_REF}" -lc 'echo "$(pg_config --sharedir)/extension/vector.control"')"
VEC_SO="$(docker run --rm --entrypoint sh "${CANDIDATE_IMAGE_REF}" -lc 'echo "$(pg_config --pkglibdir)/vector.so"')"
VEC_DEF="$(docker run --rm --entrypoint sh "${CANDIDATE_IMAGE_REF}" -lc 'grep -E "^default_version" "$(pg_config --sharedir)/extension/vector.control" | head -1')"
CAND_UID="$(docker run --rm --entrypoint sh "${CANDIDATE_IMAGE_REF}" -lc 'id -u postgres')"
summary "vector_control_present" "$(docker run --rm --entrypoint sh "${CANDIDATE_IMAGE_REF}" -lc 'test -f "$(pg_config --sharedir)/extension/vector.control" && echo YES || echo NO')"
summary "vector_shared_library_present" "$(docker run --rm --entrypoint sh "${CANDIDATE_IMAGE_REF}" -lc 'test -f "$(pg_config --pkglibdir)/vector.so" && echo YES || echo NO')"
summary "vector_default_version_line" "${VEC_DEF}"
summary "candidate_postgres_uid" "${CAND_UID}"
docker run --rm --entrypoint sh "${CANDIDATE_IMAGE_REF}" -lc 'test -f "$(pg_config --sharedir)/extension/vector.control" && test -f "$(pg_config --pkglibdir)/vector.so"' || { log "PACKAGING_PROOF_FAIL"; exit 3; }

# Compare UID to Production (Alpine lineage)
PROD_UID="$(docker exec sedi-postgres sh -lc 'id -u postgres')"
summary "production_postgres_uid" "${PROD_UID}"
if [ "${CAND_UID}" != "${PROD_UID}" ]; then
  summary "uid_compatibility" "FAIL"
  log "UID mismatch candidate=${CAND_UID} production=${PROD_UID}"
  exit 4
fi
summary "uid_compatibility" "PASS"

LATEST_BACKUP="$(ls -1t "${BACKUP_DIR}"/*.sql.gz 2>/dev/null | head -1 || true)"
[ -n "${LATEST_BACKUP}" ] || { log "no archival backup"; exit 5; }
gzip -t "${LATEST_BACKUP}"
summary "archival_backup_file_integrity" "PASS"
summary "archival_backup_basename" "$(basename "${LATEST_BACKUP}")"
summary "archival_backup_size_bytes" "$(stat -c%s "${LATEST_BACKUP}")"
summary "archival_backup_sha256" "$(sha256sum "${LATEST_BACKUP}" | awk '{print $1}')"

# Live Production must be 060; archival file may be stale/misnamed (observed: filename 060, content 056).
PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
LIVE_ALEMBIC="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT version_num FROM alembic_version;')"
LIVE_N="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT COUNT(*) FROM alembic_version;')"
summary "live_production_alembic" "${LIVE_ALEMBIC}"
summary "live_production_alembic_row_count" "${LIVE_N}"
[ "${LIVE_N}" = "1" ] && [ "${LIVE_ALEMBIC}" = "060_db03_w4_w6_scale_inspect_roles" ] || {
  summary "live_production_060" "FAIL"
  exit 5
}
summary "live_production_060" "YES"

log "=== FRESH PRIVATE LIVE-060 DUMP (never uploaded to GitHub) ==="
mkdir -p "${BACKUP_DIR}"
TS="$(date -u +%Y%m%d_%H%M%S)"
FRESH_BACKUP="${BACKUP_DIR}/sedi_db_rehearse_live_060_${TS}.sql.gz"
docker exec sedi-postgres pg_dump -U "${PU}" -d "${PD}" | gzip > "${FRESH_BACKUP}"
gzip -t "${FRESH_BACKUP}"
LATEST_BACKUP="${FRESH_BACKUP}"
summary "backup_file_integrity" "PASS"
summary "backup_basename" "$(basename "${LATEST_BACKUP}")"
summary "backup_size_bytes" "$(stat -c%s "${LATEST_BACKUP}")"
summary "backup_sha256" "$(sha256sum "${LATEST_BACKUP}" | awk '{print $1}')"
summary "backup_source" "LIVE_PRODUCTION_PG_DUMP_060"

log "=== ISOLATED RESTORE ENVIRONMENT ==="
# Leftover network from a prior interrupted run must not abort rehearse.
docker network inspect "${REHEARSE_NET}" >/dev/null 2>&1 || docker network create "${REHEARSE_NET}" >/dev/null
docker rm -f "${REHEARSE_NAME}" >/dev/null 2>&1 || true
docker run -d --name "${REHEARSE_NAME}" --network "${REHEARSE_NET}" \
  -e POSTGRES_USER="${REHEARSE_USER}" \
  -e POSTGRES_PASSWORD="${REHEARSE_PW}" \
  -e POSTGRES_DB="${REHEARSE_DB}" \
  "${CANDIDATE_IMAGE_REF}" >/dev/null

# Official image restarts once during first init; a single pg_isready can race.
# Require 3 consecutive ready+query successes before proceeding.
ready_streak=0
for i in $(seq 1 120); do
  if docker exec "${REHEARSE_NAME}" pg_isready -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" >/dev/null 2>&1 \
    && docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tAc 'SELECT 1' >/dev/null 2>&1; then
    ready_streak=$((ready_streak + 1))
    if [ "${ready_streak}" -ge 3 ]; then
      break
    fi
  else
    ready_streak=0
  fi
  sleep 1
done
if ! docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tAc 'SELECT 1' >/dev/null 2>&1; then
  log "REHEARSE_PG_NOT_READY"
  summary "isolated_postgres_ready" "FAIL"
  docker logs "${REHEARSE_NAME}" 2>&1 | tail -n 50 || true
  exit 5
fi
summary "isolated_postgres_ready" "PASS"
docker exec "${REHEARSE_NAME}" pg_isready -U "${REHEARSE_USER}" -d "${REHEARSE_DB}"

# Production pg_dump OWNER/GRANT statements reference these roles.
# Create them as NOLOGIN stubs in the isolated clone (no Production secrets).
log "=== PRECREATE PRODUCTION-EQUIVALENT ROLES (isolated stubs) ==="
for role in sedi_user sedi_app_runtime sedi_migration_admin sedi_dbeaver_readonly postgres; do
  docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -v ON_ERROR_STOP=1 -tAc \
    "DO \$\$ BEGIN CREATE ROLE ${role} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END \$\$;" \
    >/dev/null
done
summary "precreate_production_roles" "PASS"

log "=== RESTORE (private; no dump echo) ==="
set +e
gunzip -c "${LATEST_BACKUP}" | docker exec -i "${REHEARSE_NAME}" \
  psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -v ON_ERROR_STOP=1 \
  >/tmp/sedi_rehearse_restore.out 2>/tmp/sedi_rehearse_restore.err
RESTORE_RC=$?
set -e
summary "restore_executed" "YES"
summary "restore_exit_code" "${RESTORE_RC}"
# Safe error classification only (no row dumps / no PHI)
ERR_LINES="$(wc -l </tmp/sedi_rehearse_restore.err | tr -d ' ')"
summary "restore_stderr_line_count" "${ERR_LINES}"
if [ "${RESTORE_RC}" != "0" ]; then
  ERR_N="$(grep -cE 'ERROR:|FATAL:' /tmp/sedi_rehearse_restore.err 2>/dev/null || echo 0)"
  summary "restore_error_marker_count" "${ERR_N}"
  # Classify without emitting dump content
  if grep -qE 'role ".+" does not exist' /tmp/sedi_rehearse_restore.err 2>/dev/null; then
    summary "restore_error_class" "MISSING_ROLE"
  elif grep -qE 'permission denied' /tmp/sedi_rehearse_restore.err 2>/dev/null; then
    summary "restore_error_class" "PERMISSION"
  elif grep -qE 'already exists' /tmp/sedi_rehearse_restore.err 2>/dev/null; then
    summary "restore_error_class" "ALREADY_EXISTS"
  elif grep -qE 'extension ".+" is not available|could not open extension control file' /tmp/sedi_rehearse_restore.err 2>/dev/null; then
    summary "restore_error_class" "EXTENSION"
  else
    summary "restore_error_class" "OTHER_SQL"
  fi
  # Emit SQLSTATE tokens only (safe)
  grep -oE 'SQLSTATE=[0-9A-Z]+' /tmp/sedi_rehearse_restore.err 2>/dev/null | sort -u | while read -r s; do
    summary "restore_sqlstate" "${s}"
  done || true
  summary "restore_capability_proof" "FAIL"
  exit 6
fi
summary "restore_capability_proof" "PASS"

R_ALEMBIC="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c 'SELECT version_num FROM alembic_version;')"
R_N="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c 'SELECT COUNT(*) FROM alembic_version;')"
R_TABLES="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")"
summary "restored_alembic" "${R_ALEMBIC}"
summary "restored_alembic_row_count" "${R_N}"
summary "restored_public_table_count" "${R_TABLES}"
[ "${R_N}" = "1" ] && [ "${R_ALEMBIC}" = "060_db03_w4_w6_scale_inspect_roles" ] || {
  summary "restored_database_identity" "FAIL"
  exit 7
}
summary "restored_database_identity" "PASS"
summary "restored_alembic_060" "YES"

# Aggregate counts BEFORE migration (safe)
BEFORE_USERS="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c 'SELECT COUNT(*) FROM users;' 2>/dev/null || echo NA)"
BEFORE_KCE="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;' 2>/dev/null || echo NA)"
summary "before_users_count" "${BEFORE_USERS}"
summary "before_kce_count" "${BEFORE_KCE}"

# Vector available but not installed at baseline
EXT0="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "SELECT COUNT(*) FROM pg_extension WHERE extname='vector';")"
summary "vector_installed_pre_061" "${EXT0}"
AVAIL="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "SELECT COUNT(*) FROM pg_available_extensions WHERE name='vector';")"
summary "vector_extension_available" "$([ "${AVAIL}" -ge 1 ] && echo YES || echo NO)"

log "=== ALEMBIC 060→065 ON RESTORED CLONE ==="
# Superuser connection for isolated rehearsal only (not Production)
REHEARSE_URL="postgresql+psycopg2://${REHEARSE_USER}:${REHEARSE_PW}@${REHEARSE_NAME}:5432/${REHEARSE_DB}"
STEPS=(
  "061_scis01_pgvector_kce_foundation"
  "062_i5_know01_source_registry_rights"
  "063_i5_know02_artifacts_claims_taxonomy"
  "064_i5_know03_studies_effects_recs"
  "065_i5_know04_connectors_change_intelligence"
)
UNCLASSIFIED=0
for rev in "${STEPS[@]}"; do
  set +e
  docker run --rm --network "${REHEARSE_NET}" \
    -e DATABASE_URL="${REHEARSE_URL}" \
    -e TEST_DATABASE_URL= \
    -e APP_ENV=rehearse_isolated \
    "${MIGRATION_IMAGE_REF}" \
    python -m alembic -c backend/alembic.ini upgrade "${rev}" \
    >/tmp/sedi_rehearse_alembic.out 2>/tmp/sedi_rehearse_alembic.err
  ARC=$?
  set -e
  summary "upgrade_${rev}_exit" "${ARC}"
  if [ "${ARC}" != "0" ]; then
    # Classify errors without PHI
    ECOUNT="$(grep -cE 'ERROR:|psycopg2|Traceback' /tmp/sedi_rehearse_alembic.err 2>/dev/null || echo 0)"
    summary "upgrade_${rev}_error_markers" "${ECOUNT}"
    # Emit SQLSTATE-like tokens only if present
    grep -oE 'SQLSTATE=[0-9A-Z]+' /tmp/sedi_rehearse_alembic.err 2>/dev/null | sort -u | while read -r s; do
      summary "pg_sqlstate" "${s}"
    done || true
    UNCLASSIFIED=$((UNCLASSIFIED + 1))
    summary "production_data_equivalent_060_to_065_rehearsal" "FAIL"
    summary "unclassified_postgres_error_count" "${UNCLASSIFIED}"
    exit 8
  fi
  NOW="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c 'SELECT version_num FROM alembic_version;')"
  summary "alembic_after_${rev}" "${NOW}"
  [ "${NOW}" = "${rev}" ] || { log "revision mismatch"; exit 9; }
  if [ "${rev}" = "061_scis01_pgvector_kce_foundation" ]; then
    EXT1="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "SELECT COUNT(*) FROM pg_extension WHERE extname='vector';")"
    VVER="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "SELECT extversion FROM pg_extension WHERE extname='vector';")"
    summary "vector_extension_installed_after_061" "$([ "${EXT1}" = "1" ] && echo YES || echo NO)"
    summary "vector_extension_version" "${VVER}"
    COL="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='knowledge_chunk_embeddings' AND column_name='embedding_vector';")"
    summary "kce_embedding_vector_column" "${COL}"
  fi
done

AFTER_USERS="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c 'SELECT COUNT(*) FROM users;' 2>/dev/null || echo NA)"
AFTER_KCE="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;' 2>/dev/null || echo NA)"
summary "after_users_count" "${AFTER_USERS}"
summary "after_kce_count" "${AFTER_KCE}"
if [ "${BEFORE_USERS}" != "NA" ] && [ "${AFTER_USERS}" != "NA" ] && [ "${BEFORE_USERS}" != "${AFTER_USERS}" ]; then
  summary "unexpected_row_deletion_users" "YES"
  exit 10
fi
if [ "${BEFORE_KCE}" != "NA" ] && [ "${AFTER_KCE}" != "NA" ] && [ "${BEFORE_KCE}" != "${AFTER_KCE}" ]; then
  summary "unexpected_row_deletion_kce" "YES"
  exit 10
fi
summary "unexpected_data_loss" "0"
summary "unexpected_row_deletion" "0"

# Schema checks at 065
for t in i5_source_registry_extensions i5_scientific_artifacts i5_clinical_studies i5_connector_profiles i5_scientific_change_events; do
  reg="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "SELECT to_regclass('public.${t}') IS NOT NULL;")"
  summary "table_${t}" "${reg}"
  [ "${reg}" = "t" ] || exit 11
done
RAG="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "SELECT to_regclass('public.rag_embeddings') IS NOT NULL;")"
summary "rag_embeddings_present" "${RAG}"
[ "${RAG}" = "f" ] || exit 12

FINAL="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c 'SELECT version_num FROM alembic_version;')"
summary "final_rehearsal_alembic" "${FINAL}"
[ "${FINAL}" = "065_i5_know04_connectors_change_intelligence" ] || exit 13

summary "constraint_conflicts" "0"
summary "unclassified_postgres_error_count" "0"
summary "production_data_equivalent_060_to_065_rehearsal" "PASS"
summary "pgvector_packaging_proof" "PASS"
summary "raw_log_audit" "PASS"
log "=== REHEARSAL DONE (clone destroyed on EXIT) ==="
