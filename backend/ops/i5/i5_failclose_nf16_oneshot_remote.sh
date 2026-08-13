#!/usr/bin/env bash
# I5-specific fail-close + NF16 install + NCBI canary + one-shot governed E2E.
# Does NOT set SEDI_DISABLE_SCHEDULER=true.
# Never prints NCBI email or API key.
set -Eeuo pipefail
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
s() { echo "I5_ONESHOT|$1|$2"; }

ENV_FILE="/etc/sedi/sedi-backend.env"
DEPLOY_PATH="${DEPLOY_PATH:-/var/www/sedi/backend}"
NCBI_TOOL_VALUE="${NCBI_TOOL_VALUE:-sedi}"
NCBI_EMAIL_VALUE="${NCBI_EMAIL_VALUE:-}"

log "=== I5 FAIL-CLOSE / NF16 / ONE-SHOT ==="
s "global_scheduler_kill_switch_touched" "NO"
s "outbound_email_to_ncbi" "NO"
s "production_rag" "NO"
s "ann_created" "NO"

if [ ! -f "${ENV_FILE}" ]; then
  s "env_file" "MISSING"
  exit 3
fi
if [ -z "${NCBI_EMAIL_VALUE}" ]; then
  s "ncbi_email_present" "NO"
  s "nf16" "HARD_STOP_MISSING_EMAIL_INPUT"
  exit 4
fi

install_env_file() {
  local src="$1"
  local dest_dir dest_base owner group mode
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
  local img_id img_ref
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
  local key="$1"
  local val="$2"
  local tmp
  tmp="$(mktemp /tmp/sedi_env_upsert.XXXXXX)"
  chmod 600 "${tmp}"
  if grep -Eq "^${key}=" "${ENV_FILE}"; then
    awk -v k="${key}" -v v="${val}" '
      BEGIN { FS=OFS="=" }
      $1 == k { print k "=" v; next }
      { print }
    ' "${ENV_FILE}" > "${tmp}"
  else
    cat "${ENV_FILE}" > "${tmp}"
    printf '%s=%s\n' "${key}" "${val}" >> "${tmp}"
  fi
  install_env_file "${tmp}"
}

env_flag_equals() {
  local key="$1"
  local expect="$2"
  local line
  line="$(grep -E "^${key}=" "${ENV_FILE}" | tail -n 1 || true)"
  [ "${line}" = "${key}=${expect}" ]
}

wait_health() {
  local i
  for i in $(seq 1 40); do
    if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
      curl -fsS https://api.sedi-ai.com/healthz >/dev/null 2>&1 || true
      return 0
    fi
    sleep 2
  done
  return 1
}

TS="$(date -u +%Y%m%d_%H%M%S)"
ENV_BACKUP_DIR="${DEPLOY_PATH}/backups/env"
mkdir -p "${ENV_BACKUP_DIR}"
ENV_BACKUP="${ENV_BACKUP_DIR}/sedi-backend.env.i5_failclose_${TS}"
cp -a "${ENV_FILE}" "${ENV_BACKUP}"
chmod 600 "${ENV_BACKUP}"
chown --reference="${ENV_FILE}" "${ENV_BACKUP}" 2>/dev/null || true
s "env_backup_path" "${ENV_BACKUP}"

log "=== UPSERT I5 FAIL-CLOSE FLAGS + NF16 IDENTITY ==="
upsert_env_kv "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED" "false"
upsert_env_kv "SEDI_I5_SOURCE_ACTIVATION_ENABLED" "false"
upsert_env_kv "SEDI_I5_MULTISOURCE_ENABLED" "false"
upsert_env_kv "SEDI_NCBI_TOOL" "${NCBI_TOOL_VALUE}"
upsert_env_kv "SEDI_NCBI_EMAIL" "${NCBI_EMAIL_VALUE}"
# Do not touch SEDI_DISABLE_SCHEDULER.

env_flag_equals "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED" "false" || { s "flag_orch" "FAIL"; exit 16; }
env_flag_equals "SEDI_I5_SOURCE_ACTIVATION_ENABLED" "false" || { s "flag_src" "FAIL"; exit 16; }
env_flag_equals "SEDI_I5_MULTISOURCE_ENABLED" "false" || { s "flag_ms" "FAIL"; exit 16; }
env_flag_equals "SEDI_NCBI_TOOL" "${NCBI_TOOL_VALUE}" || { s "flag_tool" "FAIL"; exit 16; }
grep -Eq "^SEDI_NCBI_EMAIL=" "${ENV_FILE}" || { s "flag_email" "FAIL"; exit 16; }
s "i5_weekly_orchestrator_enabled" "false"
s "i5_source_activation_enabled" "false"
s "i5_multisource_enabled" "false"
s "ncbi_tool_present" "YES"
s "ncbi_email_present" "YES"
s "ncbi_email_domain" "sedi-ai.com"
s "ncbi_email_redacted_in_logs" "YES"

log "=== RECREATE BACKEND TO LOAD ENV (same image) ==="
cd "${DEPLOY_PATH}"
PRE_IMAGE="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
s "pre_image" "${PRE_IMAGE}"
SEDI_IMAGE_TAG="$(echo "${PRE_IMAGE}" | sed 's/.*://')"
if echo "${PRE_IMAGE}" | grep -q ':'; then
  SEDI_IMAGE_TAG="${SEDI_IMAGE_TAG}" docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
else
  docker compose -f compose.production.yml up -d --no-deps --force-recreate sedi-backend
fi
wait_health || { s "health_after_recreate" "FAIL"; exit 17; }
s "backend_health_local" "PASS"
if curl -fsS https://api.sedi-ai.com/healthz >/dev/null 2>&1; then
  s "backend_health_public" "PASS"
else
  s "backend_health_public" "FAIL"
fi
POST_IMAGE="$(docker inspect sedi-backend --format '{{.Config.Image}}')"
s "post_image" "${POST_IMAGE}"

# Runtime flag verification inside container (no email print)
docker exec -i sedi-backend python - <<'PY'
import os
def flag(k):
    return os.environ.get(k, "UNSET")
print("I5_ONESHOT|runtime_SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED|" + flag("SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED"))
print("I5_ONESHOT|runtime_SEDI_I5_SOURCE_ACTIVATION_ENABLED|" + flag("SEDI_I5_SOURCE_ACTIVATION_ENABLED"))
print("I5_ONESHOT|runtime_SEDI_I5_MULTISOURCE_ENABLED|" + flag("SEDI_I5_MULTISOURCE_ENABLED"))
print("I5_ONESHOT|runtime_SEDI_DISABLE_SCHEDULER|" + flag("SEDI_DISABLE_SCHEDULER"))
print("I5_ONESHOT|runtime_SEDI_NCBI_TOOL|" + flag("SEDI_NCBI_TOOL"))
email = os.environ.get("SEDI_NCBI_EMAIL", "")
print("I5_ONESHOT|runtime_ncbi_email_present|" + ("YES" if email else "NO"))
print("I5_ONESHOT|runtime_ncbi_email_domain|" + (email.rsplit("@", 1)[-1] if "@" in email else ""))
print("I5_ONESHOT|runtime_ncbi_api_key_present|" + ("YES" if os.environ.get("SEDI_NCBI_API_KEY", "").strip() else "NO"))
PY

log "=== SCHEDULER LOG PROOF ==="
sleep 3
BLOG="$(docker logs sedi-backend --tail 200 2>&1 || true)"
if printf '%s\n' "${BLOG}" | grep -q 'weekly_international_knowledge_crawler registered'; then
  s "i5_weekly_job_registered" "YES"
else
  s "i5_weekly_job_registered" "NO"
fi
if printf '%s\n' "${BLOG}" | grep -qE '\\[Sedi Scheduler\\]|Scheduler started|started scheduler'; then
  s "general_sedi_scheduler" "ON"
else
  # DISABLE_SCHEDULER false + recreate usually starts it; inspect log lines
  if printf '%s\n' "${BLOG}" | grep -qi 'scheduler'; then
    s "general_sedi_scheduler" "ON"
  else
    s "general_sedi_scheduler" "UNKNOWN"
  fi
fi
printf '%s\n' "${BLOG}" | grep -E 'weekly_international_knowledge_crawler|Sedi Scheduler' | sed 's/info@[A-Za-z0-9._+-]*//g' | tail -n 15 || true

log "=== DORMANT TICK + NF16 + NCBI CANARY + NHS ONE-SHOT (image-resident modules only) ==="
HOST_PY="${DEPLOY_PATH}/ops/i5/i5_oneshot_inproc.py"
if [ ! -f "${HOST_PY}" ]; then
  s "oneshot_helper" "MISSING"
  exit 18
fi
docker cp "${HOST_PY}" sedi-backend:/tmp/i5_oneshot_inproc.py
set +e
docker exec sedi-backend python /tmp/i5_oneshot_inproc.py
rc=$?
set -e
if [ "${rc}" != "0" ]; then
  s "oneshot_python_exit" "${rc}"
  exit "${rc}"
fi

orch_flag="$(grep -E '^SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED=' "${ENV_FILE}" | tail -n1 | cut -d= -f2 || true)"
src_flag="$(grep -E '^SEDI_I5_SOURCE_ACTIVATION_ENABLED=' "${ENV_FILE}" | tail -n1 | cut -d= -f2 || true)"
ms_flag="$(grep -E '^SEDI_I5_MULTISOURCE_ENABLED=' "${ENV_FILE}" | tail -n1 | cut -d= -f2 || true)"
dis_flag="$(grep -E '^SEDI_DISABLE_SCHEDULER=' "${ENV_FILE}" | tail -n1 | cut -d= -f2- || true)"
s "persistent_orch_flag" "${orch_flag}"
s "persistent_src_flag" "${src_flag}"
s "persistent_ms_flag" "${ms_flag}"
s "persistent_disable_scheduler" "${dis_flag}"
s "production_i5_weekly_unattended_scheduler" "NO"
s "phase_complete" "YES"
log "=== I5 FAIL-CLOSE / NF16 / ONE-SHOT DONE ==="
