#!/usr/bin/env bash
# Read-only Production preflight before backend image alignment.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_PREFLIGHT|$1|$2"; }

ENV_FILE="/etc/sedi/sedi-backend.env"
log "=== KNOW05 PRODUCTION PREFLIGHT (READ-ONLY) ==="
curl -fsS http://127.0.0.1:8000/healthz >/dev/null
s "backend_health_local" "PASS"
curl -fsS https://api.sedi-ai.com/healthz >/dev/null || curl -fsS https://api.sedi-ai.com/health >/dev/null
s "backend_health_public" "PASS"

IMG="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
DIGEST="$(docker inspect sedi-backend --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
ID="$(docker inspect sedi-backend --format '{{.Image}}')"
s "current_backend_image" "${IMG}"
s "current_backend_image_digest" "${DIGEST:-$ID}"
s "rollback_backend_image" "${IMG}"
s "rollback_backend_digest" "${DIGEST:-$ID}"

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
ALEMBIC="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT version_num FROM alembic_version;")"
PGV="$(docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "SELECT extversion FROM pg_extension WHERE extname='vector';")"
s "production_alembic" "${ALEMBIC}"
s "production_pgvector_version" "${PGV}"
echo "${ALEMBIC}" | grep -q 065 || exit 4

flag_val() { grep -E "^$1=" "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || true; }
s "i5_weekly_orchestrator_enabled" "$(flag_val SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED)"
s "i5_source_activation_enabled" "$(flag_val SEDI_I5_SOURCE_ACTIVATION_ENABLED)"
s "i5_multisource_enabled" "$(flag_val SEDI_I5_MULTISOURCE_ENABLED)"
s "sedi_disable_scheduler" "$(flag_val SEDI_DISABLE_SCHEDULER)"
s "ncbi_tool_present" "$([ -n "$(flag_val SEDI_NCBI_TOOL)" ] && echo YES || echo NO)"
s "ncbi_email_present" "$([ -n "$(flag_val SEDI_NCBI_EMAIL)" ] && echo YES || echo NO)"
s "ncbi_email_domain" "sedi-ai.com"

docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA <<'SQL' | tee /tmp/i5_preflight_counts.txt
SELECT 'raw='||COUNT(*) FROM i5_raw_evidence;
SELECT 'artifact='||COUNT(*) FROM i5_scientific_artifacts;
SELECT 'ku='||COUNT(*) FROM knowledge_units;
SELECT 'prov='||COUNT(*) FROM knowledge_provenance;
SELECT 'memory='||COUNT(*) FROM knowledge_memory_items;
SELECT 'kce='||COUNT(*) FROM knowledge_chunk_embeddings;
SELECT 'cells='||COUNT(*) FROM i5_knowledge_coverage_cells;
SELECT 'cells_partial='||COUNT(*) FROM i5_knowledge_coverage_cells WHERE cell_state='PARTIAL';
SELECT 'eligible='||COUNT(*) FROM knowledge_units WHERE runtime_eligibility='ELIGIBLE';
SQL

s "preflight_complete" "YES"
