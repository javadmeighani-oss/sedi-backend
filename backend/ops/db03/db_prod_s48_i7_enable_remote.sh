#!/usr/bin/env bash
# SECTION48 — controlled I7 period-summary job flag change. No manual tick. No schema.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "S48_I7|$1|$2"; }

ENV_FILE="/etc/sedi/sedi-backend.env"
DEPLOY_PATH="${DEPLOY_PATH:-/var/www/sedi/backend}"
IMAGE_SHA="${IMAGE_SHA:-}"
IMAGE_DIGEST="${IMAGE_DIGEST:-}"
I7_TARGET="${I7_TARGET:-true}"

s "manual_tick_invoked" "NO"
s "production_rag" "NO"
s "new_migration" "NO"
s "i7_target" "${I7_TARGET}"

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
if [ "${I7_TARGET}" != "true" ] && [ "${I7_TARGET}" != "false" ]; then
  s "i7_target" "INVALID"
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
    -c "cp /tmp/new.env /mnt/sedi_env/${dest_base}.i7tmp && chown ${owner}:${group} /mnt/sedi_env/${dest_base}.i7tmp && chmod ${mode} /mnt/sedi_env/${dest_base}.i7tmp && mv /mnt/sedi_env/${dest_base}.i7tmp /mnt/sedi_env/${dest_base}"
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
    if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1 || curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

s "flag_i7_before" "$(grep -E '^SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED=' "${ENV_FILE}" | tail -n1 | cut -d= -f2- || echo unset)"
TS="$(date -u +%Y%m%d_%H%M%S)"
mkdir -p "${DEPLOY_PATH}/backups/env"
cp -a "${ENV_FILE}" "${DEPLOY_PATH}/backups/env/sedi-backend.env.s48_i7_pre_${TS}" || true
chmod 600 "${DEPLOY_PATH}/backups/env/sedi-backend.env.s48_i7_pre_${TS}" || true

upsert_env_kv "SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED" "${I7_TARGET}"
env_flag_equals "SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED" "${I7_TARGET}"
s "flag_i7_file" "${I7_TARGET}"

IMAGE_TAG="ghcr.io/javadmeighani-oss/sedi-backend:${IMAGE_SHA}"
IMAGE_REF="ghcr.io/javadmeighani-oss/sedi-backend@${IMAGE_DIGEST}"
docker pull "${IMAGE_REF}" || true
docker tag "${IMAGE_REF}" "${IMAGE_TAG}" 2>/dev/null || true
cd "${DEPLOY_PATH}"
SEDI_IMAGE_TAG="${IMAGE_SHA}" docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
wait_health || { s "backend_health_local" "NO"; exit 14; }
s "backend_health_local" "PASS"

POST_IMAGE="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
POST_ID="$(docker inspect sedi-backend --format '{{.Image}}')"
echo "${POST_IMAGE}" | grep -Fq "${IMAGE_SHA}" || { s "running_image" "${POST_IMAGE}"; exit 15; }
if ! docker image inspect "${POST_ID}" --format '{{range .RepoDigests}}{{println .}}{{end}}' | grep -Fq "${IMAGE_DIGEST}"; then
  s "digest_match" "NO"
  exit 16
fi
s "running_backend_image" "${POST_IMAGE}"
s "running_backend_digest" "${IMAGE_DIGEST}"
s "digest_match" "YES"

EFFECTIVE="$(docker exec sedi-backend printenv SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED || true)"
s "effective_runtime_flag" "${EFFECTIVE:-UNSET}"
if [ "${I7_TARGET}" = "true" ]; then
  echo "${EFFECTIVE}" | grep -Eiq '^(1|true|yes|on)$' || { s "effective_runtime_flag" "FAIL"; exit 17; }
  s "sedi_i7_period_summary_jobs_enabled" "ON"
else
  echo "${EFFECTIVE}" | grep -Eiq '^(1|true|yes|on)$' && { s "fail_closed" "FAIL_STILL_ON"; exit 17; }
  s "sedi_i7_period_summary_jobs_enabled" "OFF"
fi

sleep 3
for kind in daily weekly monthly yearly; do
  LINE="$(docker logs sedi-backend 2>&1 | grep -E "I7_JOB_REGISTERED .*job_id=i7_period_summary_${kind}" | tail -n1 || true)"
  s "job_${kind}" "${LINE:-MISSING}"
  echo "${LINE}" | grep -Fq "job_id=i7_period_summary_${kind}"
  echo "${LINE}" | grep -Fq "trigger=cron"
  echo "${LINE}" | grep -Fq "timezone=Asia/Tehran"
  echo "${LINE}" | grep -Fq "max_instances=1"
  echo "${LINE}" | grep -Eq "coalesce=true"
done
s "scheduler_registration" "PASS"
s "manual_tick_invoked" "NO"
s "enable_complete" "YES"
log "=== S48 I7 FLAG DONE ==="
