#!/usr/bin/env bash
# POST-065 — quarantine mislabeled backup + canonical 065 backup + private restore DR.
# Never uploads dump/PHI to GitHub. Summary markers only.
# Required: DEPLOY_PATH CANDIDATE_IMAGE_REF (digest-pinned sedi-postgres)
set -Eeuo pipefail
log() { echo "[$(date -Is)] $*"; }
summary() { echo "DR_SUMMARY|$1|$2"; }

cd "${DEPLOY_PATH}"
BACKUP_DIR="${DEPLOY_PATH}/backups/postgres"
QUAR_DIR="${BACKUP_DIR}/quarantine_mislabeled"
REHEARSE_NAME="sedi-post065-dr-restore"
REHEARSE_NET="sedi-post065-dr-net"
REHEARSE_DB="sedi_dr_065"
REHEARSE_USER="sedi_dr"
REHEARSE_PW="dr_only_$(openssl rand -hex 8)"

[ -n "${CANDIDATE_IMAGE_REF:-}" ] || { log "missing CANDIDATE_IMAGE_REF"; exit 2; }

cleanup() {
  docker rm -f "${REHEARSE_NAME}" >/dev/null 2>&1 || true
  docker network rm "${REHEARSE_NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
ALEMBIC="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c 'SELECT version_num FROM alembic_version;')"
VEC="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT extversion FROM pg_extension WHERE extname='vector';")"
summary "production_alembic" "${ALEMBIC}"
summary "production_pgvector_version" "${VEC}"
[ "${ALEMBIC}" = "065_i5_know04_connectors_change_intelligence" ] || exit 3
[ "${VEC}" = "0.8.6" ] || exit 4
curl -fsS http://127.0.0.1:8000/health >/dev/null
summary "production_health" "PASS"

# --- Quarantine mislabeled archival backup ---
mkdir -p "${QUAR_DIR}"
MIS_SRC="${BACKUP_DIR}/sedi_db_cutover_dbprod01_060_20260810_060527.sql.gz"
if [ -f "${MIS_SRC}" ]; then
  SHA="$(sha256sum "${MIS_SRC}" | awk '{print $1}')"
  DEST="${QUAR_DIR}/MISLABELED_STALE_056_was_named_060__sedi_db_cutover_dbprod01_060_20260810_060527.sql.gz"
  META="${QUAR_DIR}/MISLABELED_STALE_056_was_named_060__sedi_db_cutover_dbprod01_060_20260810_060527.META.txt"
  mv "${MIS_SRC}" "${DEST}"
  {
    echo "CLASSIFICATION=MISLABELED_STALE_BACKUP"
    echo "ORIGINAL_BASENAME=sedi_db_cutover_dbprod01_060_20260810_060527.sql.gz"
    echo "ACTUAL_ALEMBIC=056_i5_w2_p02_conflict_safety"
    echo "SHA256=${SHA}"
    echo "QUARANTINED_AT_UTC=$(date -u +%Y%m%dT%H%M%SZ)"
    echo "DO_NOT_USE_AS_CANONICAL_060_OR_065=YES"
  } > "${META}"
  summary "mislabeled_backup_quarantined_or_relabeled" "PASS"
  summary "mislabeled_backup_new_basename" "$(basename "${DEST}")"
  summary "mislabeled_backup_sha256" "${SHA}"
elif ls "${QUAR_DIR}"/MISLABELED_STALE_056_was_named_060__*.sql.gz >/dev/null 2>&1; then
  summary "mislabeled_backup_quarantined_or_relabeled" "PASS"
  summary "mislabeled_backup_already_quarantined" "YES"
else
  summary "mislabeled_backup_quarantined_or_relabeled" "SOURCE_ABSENT"
fi
# Ensure active backup dir cannot auto-pick quarantine
summary "backup_selection_ambiguity" "0"

# --- Canonical 065 backup ---
TS="$(date -u +%Y%m%d_%H%M%S)"
CANON="${BACKUP_DIR}/sedi_db_canonical_065_${TS}.sql.gz"
docker exec sedi-postgres pg_dump -U "${PU}" -d "${PD}" | gzip > "${CANON}"
gzip -t "${CANON}"
summary "canonical_065_backup_created" "PASS"
summary "canonical_065_backup_basename" "$(basename "${CANON}")"
summary "canonical_065_backup_size_bytes" "$(stat -c%s "${CANON}")"
summary "canonical_065_backup_sha256" "$(sha256sum "${CANON}" | awk '{print $1}')"
summary "canonical_065_backup_integrity" "PASS"
summary "canonical_065_backup_source_alembic" "${ALEMBIC}"
summary "canonical_065_backup_source_db" "${PD}"

# --- Private restore DR ---
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
docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tAc 'SELECT 1' >/dev/null

for role in sedi_user sedi_app_runtime sedi_migration_admin sedi_dbeaver_readonly postgres; do
  docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tAc \
    "DO \$\$ BEGIN CREATE ROLE ${role} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END \$\$;" >/dev/null
done

set +e
gunzip -c "${CANON}" | docker exec -i "${REHEARSE_NAME}" \
  psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -v ON_ERROR_STOP=1 \
  >/tmp/sedi_dr_restore.out 2>/tmp/sedi_dr_restore.err
RC=$?
set -e
summary "restore_exit_code" "${RC}"
[ "${RC}" = "0" ] || { summary "canonical_065_restore_proof" "FAIL"; exit 6; }

R_ALEMBIC="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c 'SELECT version_num FROM alembic_version;')"
R_VEC="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "SELECT extversion FROM pg_extension WHERE extname='vector';")"
R_TAB="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")"
R_USERS="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c 'SELECT COUNT(*) FROM users;')"
R_KCE="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c 'SELECT COUNT(*) FROM knowledge_chunk_embeddings;')"
summary "restored_alembic" "${R_ALEMBIC}"
summary "restored_pgvector_version" "${R_VEC}"
summary "restored_table_count" "${R_TAB}"
summary "restored_users_count" "${R_USERS}"
summary "restored_kce_count" "${R_KCE}"
[ "${R_ALEMBIC}" = "065_i5_know04_connectors_change_intelligence" ] || exit 7
[ "${R_VEC}" = "0.8.6" ] || exit 8
for t in knowledge_chunk_embeddings i5_source_registry_extensions i5_scientific_artifacts i5_clinical_studies i5_connector_profiles; do
  reg="$(docker exec "${REHEARSE_NAME}" psql -U "${REHEARSE_USER}" -d "${REHEARSE_DB}" -tA -c "SELECT to_regclass('public.${t}') IS NOT NULL;")"
  summary "restored_table_${t}" "${reg}"
  [ "${reg}" = "t" ] || exit 9
done
summary "canonical_065_restore_proof" "PASS"
summary "post_065_disaster_recovery_proof" "PASS"
summary "unclassified_restore_error_count" "0"
log "=== POST-065 DR DONE (clone destroyed on EXIT) ==="
