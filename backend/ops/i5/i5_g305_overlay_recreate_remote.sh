#!/usr/bin/env bash
# Wipe Catalog-12 docker-cp overlay by recreating sedi-backend from the immutable
# e31d948 image. Does NOT change weekly flags. Does NOT rebuild. No migration.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_G305|$1|$2"; }

DEPLOY_PATH="${DEPLOY_PATH:-/var/www/sedi/backend}"
PIN_SHA="${PIN_SHA:-e31d948f26c9eeec8415e37626f87b3a08d03548}"
PIN_DIGEST="${PIN_DIGEST:-sha256:2889a0566a996339dd7f4ec6dc24d3c6cd31f63c2bf3c02825d25a4c10787b9b}"

wait_health() {
  local i
  for i in $(seq 1 30); do
    curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

log "=== I5 G305 OVERLAY RECREATE ==="
s "weekly_flags_mutated" "NO"
s "production_rag" "NO"
s "migration_066" "NO"

IMG="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
DIGEST="$(docker inspect sedi-backend --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
s "pre_image" "${IMG}"
s "pre_digest" "${DIGEST}"
echo "${IMG}" | grep -Fq "${PIN_SHA}" || { s "image_pin" "FAIL"; exit 3; }

PU="$(docker exec sedi-postgres printenv POSTGRES_USER)"
PD="$(docker exec sedi-postgres printenv POSTGRES_DB)"
psql() { docker exec sedi-postgres psql -U "${PU}" -d "${PD}" -tA -c "$1" | tr -d '\r'; }
BEFORE_RAW="$(psql "SELECT COUNT(*) FROM i5_raw_evidence;")"
BEFORE_KU="$(psql "SELECT COUNT(*) FROM knowledge_units;")"
BEFORE_ART="$(psql "SELECT COUNT(*) FROM i5_scientific_artifacts;")"
BEFORE_PROV="$(psql "SELECT COUNT(*) FROM knowledge_provenance;")"
BEFORE_MEM="$(psql "SELECT COUNT(*) FROM knowledge_memory_items;")"
BEFORE_KCE="$(psql "SELECT COUNT(*) FROM knowledge_chunk_embeddings;")"
BEFORE_ELIG="$(psql "SELECT COUNT(*) FROM knowledge_units WHERE runtime_eligibility='ELIGIBLE';")"
s "before_raw" "${BEFORE_RAW}"
s "before_ku" "${BEFORE_KU}"
s "before_artifact" "${BEFORE_ART}"
s "before_prov" "${BEFORE_PROV}"
s "before_memory" "${BEFORE_MEM}"
s "before_kce" "${BEFORE_KCE}"
s "before_eligible" "${BEFORE_ELIG}"

cd "${DEPLOY_PATH}"
SEDI_IMAGE_TAG="${PIN_SHA}" docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
wait_health
s "backend_health_local" "PASS"
curl -fsS https://api.sedi-ai.com/healthz >/dev/null || curl -fsS https://api.sedi-ai.com/health >/dev/null
s "backend_health_public" "PASS"

POST_IMG="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
POST_DIGEST="$(docker inspect sedi-backend --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
s "post_image" "${POST_IMG}"
s "post_digest" "${POST_DIGEST}"
echo "${POST_IMG}" | grep -Fq "${PIN_SHA}" || { s "post_image_pin" "FAIL"; exit 4; }

AFTER_RAW="$(psql "SELECT COUNT(*) FROM i5_raw_evidence;")"
AFTER_KU="$(psql "SELECT COUNT(*) FROM knowledge_units;")"
AFTER_ART="$(psql "SELECT COUNT(*) FROM i5_scientific_artifacts;")"
AFTER_PROV="$(psql "SELECT COUNT(*) FROM knowledge_provenance;")"
AFTER_MEM="$(psql "SELECT COUNT(*) FROM knowledge_memory_items;")"
AFTER_KCE="$(psql "SELECT COUNT(*) FROM knowledge_chunk_embeddings;")"
AFTER_ELIG="$(psql "SELECT COUNT(*) FROM knowledge_units WHERE runtime_eligibility='ELIGIBLE';")"
s "after_raw" "${AFTER_RAW}"
s "after_ku" "${AFTER_KU}"
s "after_artifact" "${AFTER_ART}"
s "after_prov" "${AFTER_PROV}"
s "after_memory" "${AFTER_MEM}"
s "after_kce" "${AFTER_KCE}"
s "after_eligible" "${AFTER_ELIG}"

if [ "${BEFORE_RAW}" != "${AFTER_RAW}" ] || [ "${BEFORE_KU}" != "${AFTER_KU}" ] || [ "${BEFORE_ART}" != "${AFTER_ART}" ] || [ "${BEFORE_PROV}" != "${AFTER_PROV}" ]; then
  s "corpus_unchanged" "FAIL"
  exit 5
fi
if [ "${AFTER_MEM}" != "0" ] || [ "${AFTER_KCE}" != "0" ] || [ "${AFTER_ELIG}" != "0" ]; then
  s "medical_safety" "HARD_STOP"
  exit 6
fi
s "corpus_unchanged" "PASS"

DIFF="$(docker diff sedi-backend 2>/dev/null || true)"
printf '%s\n' "${DIFF}" | sed 's/^/I5_G305|docker_diff|/' || true
if printf '%s\n' "${DIFF}" | grep -E 'catalog12_|coverage_manifest_v1.yaml' >/dev/null 2>&1; then
  s "overlay_diff_catalog12" "STILL_PRESENT"
  s "production_runtime_depends_on_mutable_overlay" "YES"
  exit 7
fi
s "overlay_diff_catalog12" "NO"
s "production_runtime_depends_on_mutable_overlay" "NO"
rm -rf /tmp/sedi_catalog12_overlay || true
s "host_overlay_stage_removed" "YES"
s "recreate_complete" "YES"
log "=== I5 G305 OVERLAY RECREATE DONE ==="
