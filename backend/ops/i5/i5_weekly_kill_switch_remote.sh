#!/usr/bin/env bash
# I5 weekly kill-switch: flags false, delay cleared, general scheduler remains ON.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_WEEKLY|$1|$2"; }

ENV_FILE="/etc/sedi/sedi-backend.env"
DEPLOY_PATH="${DEPLOY_PATH:-/var/www/sedi/backend}"
IMAGE_SHA="${IMAGE_SHA:-}"
IMAGE_DIGEST="${IMAGE_DIGEST:-}"
REENABLE="${REENABLE:-NO}"

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
wait_health() {
  local i
  for i in $(seq 1 30); do
    curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}
recreate() {
  local IMAGE_TAG="ghcr.io/javadmeighani-oss/sedi-backend:${IMAGE_SHA}"
  cd "${DEPLOY_PATH}"
  SEDI_IMAGE_TAG="${IMAGE_SHA}" docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
  wait_health
}

log "=== I5 WEEKLY KILL SWITCH ==="
s "general_sedi_scheduler_kill" "NO"
upsert_env_kv "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED" "false"
upsert_env_kv "SEDI_I5_SOURCE_ACTIVATION_ENABLED" "false"
upsert_env_kv "SEDI_I5_MULTISOURCE_ENABLED" "false"
upsert_env_kv "SEDI_I5_WEEKLY_ORCHESTRATOR_INTERVAL_MIN" "10080"
upsert_env_kv "SEDI_I5_WEEKLY_FIRST_RUN_DELAY_SEC" ""
upsert_env_kv "SEDI_DISABLE_SCHEDULER" "false"
recreate
s "backend_health_local" "PASS"

docker exec -i sedi-backend python - <<'PY'
from backend.app.services.i5.weekly_orchestrator import run_dormant_scheduled_tick
o = run_dormant_scheduled_tick()
print(f"I5_WEEKLY|i5_weekly_tick_outcome|{o.outcome}")
print(f"I5_WEEKLY|network_executed|{str(o.network_executed).lower()}")
print(f"I5_WEEKLY|production_write|{str(o.production_write).lower()}")
if o.outcome != "DORMANT_NO_OP" or o.network_executed or o.production_write:
    raise SystemExit("kill_switch_not_dormant")
print("I5_WEEKLY|i5_weekly_job_enabled|false")
print("I5_WEEKLY|i5_scheduler_kill_switch_proof|PASS")
PY

if [ "${REENABLE}" != "YES" ]; then
  s "weekly_unattended_enabled" "NO"
  s "kill_complete" "YES"
  exit 0
fi

log "=== RE-ENABLE BOUNDED WEEKLY (NO FIRST-RUN DELAY; INTERVAL 10080) ==="
upsert_env_kv "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED" "true"
upsert_env_kv "SEDI_I5_SOURCE_ACTIVATION_ENABLED" "true"
upsert_env_kv "SEDI_I5_MULTISOURCE_ENABLED" "false"
upsert_env_kv "SEDI_I5_WEEKLY_ORCHESTRATOR_INTERVAL_MIN" "10080"
upsert_env_kv "SEDI_I5_WEEKLY_FIRST_RUN_DELAY_SEC" ""
upsert_env_kv "SEDI_DISABLE_SCHEDULER" "false"
recreate
s "backend_health_local" "PASS"
LOG="$(docker logs sedi-backend 2>&1 | grep -E 'weekly_international_knowledge_crawler registered' | tail -n1 || true)"
s "reenable_register_line" "${LOG}"
echo "${LOG}" | grep -Eq 'first_run_delay_sec=none'
echo "${LOG}" | grep -Eq 'interval_min=10080'
s "weekly_unattended_enabled" "YES"
s "production_i5_weekly_orchestrator_enabled" "true"
s "production_i5_source_activation_enabled" "true"
s "production_i5_multisource_enabled" "false"
s "kill_then_reenable_complete" "YES"
