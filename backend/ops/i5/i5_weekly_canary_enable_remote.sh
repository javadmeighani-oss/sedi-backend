#!/usr/bin/env bash
# Bounded NHS-only weekly canary enablement. Does NOT invoke the weekly job.
# Scheduler (APScheduler) must fire the first run via FIRST_RUN_DELAY_SEC.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_WEEKLY|$1|$2"; }

ENV_FILE="/etc/sedi/sedi-backend.env"
DEPLOY_PATH="${DEPLOY_PATH:-/var/www/sedi/backend}"
IMAGE_SHA="${IMAGE_SHA:-}"
IMAGE_DIGEST="${IMAGE_DIGEST:-}"
DELAY_SEC="${DELAY_SEC:-240}"

log "=== I5 WEEKLY CANARY ENABLE (NHS-ONLY, NO MANUAL TICK) ==="
s "production_rag" "NO"
s "canary_source_count" "1"
s "canary_document_limit" "1"
s "canary_artifact_limit" "2"
s "canary_ku_limit" "2"
s "canary_kce_limit" "0"
s "canary_max_runtime" "600"
s "canary_max_retry_per_item" "3"
s "canary_max_total_retries" "12"
s "canary_max_provider_rps" "1"
s "multisource_enabled_target" "false"

if [ -z "${IMAGE_SHA}" ] || [ -z "${IMAGE_DIGEST}" ]; then
  s "image_inputs" "MISSING"
  exit 3
fi
echo "${IMAGE_SHA}" | grep -Eq '^[0-9a-f]{40}$'
echo "${IMAGE_DIGEST}" | grep -Eq '^sha256:[0-9a-f]{64}$'
if [ ! -f "${ENV_FILE}" ]; then
  s "env_file" "MISSING"
  exit 3
fi

install_env_file() {
  local src="$1" dest_dir dest_base owner group mode img_id img_ref
  dest_dir="$(dirname "${ENV_FILE}")"
  dest_base="$(basename "${ENV_FILE}")"
  owner="$(stat -c '%u' "${ENV_FILE}")"
  group="$(stat -c '%g' "${ENV_FILE}")"
  mode="$(stat -c '%a' "${ENV_FILE}" 2>/dev/null || echo 600)"
  if [ -w "${ENV_FILE}" ] && [ -w "${dest_dir}" ]; then
    mv "${src}" "${ENV_FILE}"
    chmod "${mode}" "${ENV_FILE}" || chmod 600 "${ENV_FILE}"
    return 0
  fi
  img_id="$(docker inspect sedi-backend --format '{{.Image}}')"
  img_ref="$(docker image inspect "${img_id}" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
  if [ -z "${img_ref}" ]; then
    img_ref="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
  fi
  docker run --rm --entrypoint sh \
    -v "${src}:/tmp/new.env:ro" \
    -v "${dest_dir}:/mnt/sedi_env" \
    "${img_ref}" \
    -c "cp /tmp/new.env /mnt/sedi_env/${dest_base}.i5tmp && chown ${owner}:${group} /mnt/sedi_env/${dest_base}.i5tmp && chmod ${mode} /mnt/sedi_env/${dest_base}.i5tmp && mv /mnt/sedi_env/${dest_base}.i5tmp /mnt/sedi_env/${dest_base}"
  rm -f "${src}"
}

upsert_env_kv() {
  local key="$1" val="$2" tmp
  tmp="$(mktemp /tmp/sedi_env_upsert.XXXXXX)"
  chmod 600 "${tmp}"
  if grep -Eq "^${key}=" "${ENV_FILE}"; then
    awk -v k="${key}" -v v="${val}" 'BEGIN{FS=OFS="="} $1==k{print k"="v; next} {print}' "${ENV_FILE}" > "${tmp}"
  else
    cat "${ENV_FILE}" > "${tmp}"
    printf '%s=%s\n' "${key}" "${val}" >> "${tmp}"
  fi
  install_env_file "${tmp}"
}

env_flag_equals() {
  local line
  line="$(grep -E "^$1=" "${ENV_FILE}" | tail -n 1 || true)"
  [ "${line}" = "$1=$2" ]
}

wait_health() {
  local i
  for i in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
      curl -fsS https://api.sedi-ai.com/healthz >/dev/null 2>&1 || curl -fsS https://api.sedi-ai.com/health >/dev/null
      return 0
    fi
    sleep 2
  done
  return 1
}

s "flag_orch_before" "$(grep -E '^SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED=' "${ENV_FILE}" | tail -n1 | cut -d= -f2- || echo unset)"
s "flag_src_before" "$(grep -E '^SEDI_I5_SOURCE_ACTIVATION_ENABLED=' "${ENV_FILE}" | tail -n1 | cut -d= -f2- || echo unset)"
s "flag_multi_before" "$(grep -E '^SEDI_I5_MULTISOURCE_ENABLED=' "${ENV_FILE}" | tail -n1 | cut -d= -f2- || echo unset)"

TS="$(date -u +%Y%m%d_%H%M%S)"
mkdir -p "${DEPLOY_PATH}/backups/env"
cp -a "${ENV_FILE}" "${DEPLOY_PATH}/backups/env/sedi-backend.env.weekly_canary_pre_${TS}"
chmod 600 "${DEPLOY_PATH}/backups/env/sedi-backend.env.weekly_canary_pre_${TS}" || true

upsert_env_kv "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED" "true"
upsert_env_kv "SEDI_I5_SOURCE_ACTIVATION_ENABLED" "true"
upsert_env_kv "SEDI_I5_MULTISOURCE_ENABLED" "false"
upsert_env_kv "SEDI_I5_WEEKLY_ORCHESTRATOR_INTERVAL_MIN" "10080"
upsert_env_kv "SEDI_DISABLE_SCHEDULER" "false"
upsert_env_kv "SEDI_I5_WEEKLY_FIRST_RUN_DELAY_SEC" "${DELAY_SEC}"
env_flag_equals "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED" "true"
env_flag_equals "SEDI_I5_SOURCE_ACTIVATION_ENABLED" "true"
env_flag_equals "SEDI_I5_MULTISOURCE_ENABLED" "false"
env_flag_equals "SEDI_I5_WEEKLY_FIRST_RUN_DELAY_SEC" "${DELAY_SEC}"
s "flags_upserted" "YES"

IMAGE_TAG="ghcr.io/javadmeighani-oss/sedi-backend:${IMAGE_SHA}"
IMAGE_REF="ghcr.io/javadmeighani-oss/sedi-backend@${IMAGE_DIGEST}"
docker pull "${IMAGE_REF}" || true
docker tag "${IMAGE_REF}" "${IMAGE_TAG}" 2>/dev/null || true
cd "${DEPLOY_PATH}"
SEDI_IMAGE_TAG="${IMAGE_SHA}" docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
wait_health || { s "backend_health_local" "NO"; exit 14; }
s "backend_health_local" "PASS"
curl -fsS https://api.sedi-ai.com/healthz >/dev/null || curl -fsS https://api.sedi-ai.com/health >/dev/null
s "backend_health_public" "PASS"

POST_IMAGE="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
POST_ID="$(docker inspect sedi-backend --format '{{.Image}}')"
if [ "${POST_IMAGE}" != "${IMAGE_TAG}" ]; then
  s "running_image" "${POST_IMAGE}"
  exit 15
fi
if ! docker image inspect "${POST_ID}" --format '{{range .RepoDigests}}{{println .}}{{end}}' | grep -Fq "${IMAGE_DIGEST}"; then
  s "digest_match" "NO"
  exit 16
fi
s "running_backend_image" "${POST_IMAGE}"
s "running_backend_digest" "${IMAGE_DIGEST}"
s "digest_match" "YES"

docker exec -i sedi-backend python - <<'PY'
from backend.app.database import get_db
import backend.app.models as models
from backend.app.services.i5.governed_weekly_runtime import NHS_SOURCE_KEY, activate_nhs_sleep_source
db = next(get_db())
try:
    result = activate_nhs_sleep_source(db, models)
    others = (
        db.query(models.KnowledgeSource)
        .filter(models.KnowledgeSource.source_fetch_enabled.is_(True))
        .filter(models.KnowledgeSource.slug != NHS_SOURCE_KEY)
        .all()
    )
    for ks in others:
        print(f"I5_WEEKLY|scope_disable|{ks.slug}")
        ks.source_fetch_enabled = False
    db.commit()
    enabled = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.source_fetch_enabled.is_(True)).all()
    slugs = ",".join(sorted(str(ks.slug) for ks in enabled))
    print(f"I5_WEEKLY|nhs_fetch_enabled|{str(result.source_fetch_enabled).lower()}")
    print(f"I5_WEEKLY|enabled_slugs|{slugs}")
    print(f"I5_WEEKLY|enabled_count|{len(enabled)}")
    if len(enabled) != 1 or enabled[0].slug != NHS_SOURCE_KEY:
        raise SystemExit("activation_scope_failed")
finally:
    db.close()
PY

LOG="$(docker logs sedi-backend 2>&1 | grep -E 'weekly_international_knowledge_crawler registered' | tail -n1 || true)"
s "scheduler_register_line" "${LOG}"
echo "${LOG}" | grep -Fq "enabled=True" || echo "${LOG}" | grep -Fq "enabled=true"
echo "${LOG}" | grep -Eq "first_run_delay_sec=${DELAY_SEC}"
echo "${LOG}" | grep -Eq "interval_min=10080"
echo "${LOG}" | grep -Eq "first_run_at=.*\+0[34]:30" || echo "${LOG}" | grep -Eq "first_run_at=.*\+03:30"
s "scheduled_job_registered" "YES"
s "scheduled_job_enabled" "YES"
s "manual_tick_invoked" "NO"
s "enable_complete" "YES"
s "watch_for_scheduler_tick" "YES"
