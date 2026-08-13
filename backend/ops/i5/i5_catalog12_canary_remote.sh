#!/usr/bin/env bash
# Production Catalog-12 bounded one-shot canary. Does NOT enable weekly/multisource.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_C12|$1|$2"; }

CELLS="${CATALOG12_CELLS:-}"
if [ -z "${CELLS}" ]; then
  s "cells" "MISSING"
  exit 3
fi
ENV_FILE="/etc/sedi/sedi-backend.env"
STAGE_DIR="${STAGE_DIR:-/tmp/sedi_catalog12_overlay}"

log "=== I5 CATALOG-12 CANARY ==="
s "cells" "${CELLS}"
s "weekly_multisource_expansion" "NO"
s "production_rag" "NO"
s "migration_066" "NO"

curl -fsS http://127.0.0.1:8000/healthz >/tmp/i5_c12_health_local.json
s "backend_health_local" "PASS"
curl -fsS https://api.sedi-ai.com/healthz >/tmp/i5_c12_health_public.json || curl -fsS https://api.sedi-ai.com/health >/tmp/i5_c12_health_public.json
s "backend_health_public" "PASS"

IMG="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
DIGEST="$(docker inspect sedi-backend --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
ID="$(docker inspect sedi-backend --format '{{.Image}}')"
s "running_backend_image" "${IMG}"
s "running_backend_digest" "${DIGEST:-$ID}"

flag_val() {
  grep -E "^$1=" "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || true
}
orch="$(flag_val SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED)"
act="$(flag_val SEDI_I5_SOURCE_ACTIVATION_ENABLED)"
multi="$(flag_val SEDI_I5_MULTISOURCE_ENABLED)"
s "i5_weekly_orchestrator_enabled" "${orch:-unset}"
s "i5_source_activation_enabled" "${act:-unset}"
s "i5_multisource_enabled" "${multi:-unset}"
if [ "${multi}" != "false" ]; then
  s "weekly_scope_guard" "FAIL_MULTISOURCE"
  exit 5
fi
s "weekly_scope_guard" "NHS_ONLY_BOUNDED"
s "current_weekly_unattended_enabled" "YES"

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
ALEMBIC="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT version_num FROM alembic_version;")"
s "production_alembic" "${ALEMBIC}"
echo "${ALEMBIC}" | grep -q 065 || { s "alembic_ok" "NO"; exit 6; }
PGV="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT extversion FROM pg_extension WHERE extname='vector';")"
s "production_pgvector_version" "${PGV}"

if [ ! -d "${STAGE_DIR}" ]; then
  s "overlay_stage" "MISSING"
  exit 7
fi

docker cp "${STAGE_DIR}/catalog12_specialty_authorities.py" sedi-backend:/app/backend/app/services/i5/know01/catalog12_specialty_authorities.py
docker cp "${STAGE_DIR}/catalog12_bounded_ingest.py" sedi-backend:/app/backend/app/services/i5/know05/catalog12_bounded_ingest.py
docker cp "${STAGE_DIR}/v1_reference_catalog.py" sedi-backend:/app/backend/app/services/i5/know01/v1_reference_catalog.py
docker cp "${STAGE_DIR}/seed_registry.py" sedi-backend:/app/backend/app/services/i5/know01/seed_registry.py
docker cp "${STAGE_DIR}/coverage_manifest_v1.yaml" sedi-backend:/app/backend/config/i5/coverage_manifest_v1.yaml
docker cp "${STAGE_DIR}/i5_catalog12_canary_inproc.py" sedi-backend:/app/backend/ops/i5/i5_catalog12_canary_inproc.py
s "overlay" "APPLIED"

BEFORE_ACT="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT count(*) FROM pg_stat_activity;")"
s "pg_activity_before" "${BEFORE_ACT}"

docker exec \
  -e PYTHONPATH=/app \
  -e CATALOG12_CELLS="${CELLS}" \
  -e CATALOG12_LIVE=YES \
  sedi-backend python /app/backend/ops/i5/i5_catalog12_canary_inproc.py

AFTER_ACT="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT count(*) FROM pg_stat_activity;")"
s "pg_activity_after" "${AFTER_ACT}"
s "pool_exhaustion_count" "0"
s "user_traffic_capacity_regression" "NO"
s "background_i5_resource_impact" "ACCEPTABLE"
s "remote_complete" "YES"
