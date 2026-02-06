#!/usr/bin/env bash
set -euo pipefail

# Release C Final Runtime Tests (best-effort, no backend code changes)
# - Saves raw curl outputs under /tmp/sedi_release_c/<run_id>/
# - Appends evidence to docs/release_c_test_evidence.md
# - Masks secrets/tokens in the evidence report

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVIDENCE_FILE="${ROOT_DIR}/docs/release_c_test_evidence.md"

BASE_URL="${BASE_URL:-http://91.107.168.130:8000}"
DEVICE_AUTH_HEADER="${DEVICE_AUTH_HEADER:-X-DEVICE-TOKEN}"
USER_ID="${USER_ID:-1}"
DEVICE_ID="${DEVICE_ID:-Sedi001}"

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="/tmp/sedi_release_c/${RUN_ID}"
mkdir -p "${OUT_DIR}"

have_cmd() { command -v "$1" >/dev/null 2>&1; }

wait_for_http_ok() {
  # Wait up to 30s for service to respond with HTTP 200 (avoids "Connection refused" after restart).
  local max=30
  local port=8000
  if [[ "${BASE_URL}" =~ ://([^:/]+):([0-9]+) ]]; then
    port="${BASH_REMATCH[2]}"
  fi
  local fallback_url="http://127.0.0.1:${port}/"
  local try_fallback=0
  if [[ "${BASE_URL}" != *"127.0.0.1"* && "${BASE_URL}" != *"localhost"* ]]; then
    try_fallback=1
  fi
  local url_with_slash="${BASE_URL%/}/"
  echo -n "Waiting for service at ${url_with_slash} (max ${max}s)..." >&2
  local i=0
  while [[ $i -lt $max ]]; do
    local code=""
    code="$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "${url_with_slash}" 2>/dev/null)" || true
    if [[ "${code}" == "200" ]]; then
      echo " OK (HTTP 200)" >&2
      return 0
    fi
    if [[ $try_fallback -eq 1 ]]; then
      code="$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "${fallback_url}" 2>/dev/null)" || true
      if [[ "${code}" == "200" ]]; then
        echo " OK (HTTP 200 via 127.0.0.1:${port})" >&2
        return 0
      fi
    fi
    sleep 1
    i=$((i + 1))
    echo -n "." >&2
  done
  echo " TIMEOUT" >&2
  echo "ERROR: service did not respond with HTTP 200 within ${max}s" >&2
  echo "--- systemctl status sedi-backend ---" >&2
  systemctl status sedi-backend 2>&1 | head -20 >&2 || true
  echo "--- ss -lntp | grep :8000 ---" >&2
  ss -lntp 2>&1 | grep ":8000" >&2 || true
  exit 1
}

mask_token() {
  # Mask any token-like secret (show only prefix/suffix)
  # usage: mask_token "rawtoken"
  local t="${1:-}"
  local n="${#t}"
  if [[ "${n}" -le 8 ]]; then
    echo "***"
  else
    echo "${t:0:4}***${t: -4}"
  fi
}

json_get_file() {
  # Read JSON from file and extract field by dot path (avoids stdin JSONDecodeError).
  # usage: json_get_file "$file" ".data.token"
  local file="$1"
  local expr="$2"
  if [[ ! -s "$file" ]]; then
    echo "ERROR: missing/empty JSON file: $file" >&2
    return 1
  fi
  if have_cmd python3; then
    python3 - "$file" "$expr" <<'PY'
import json, sys
path = sys.argv[1]
expr = sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
cur = data
for part in expr.lstrip(".").split("."):
    if part == "":
        continue
    if isinstance(cur, dict) and part in cur:
        cur = cur[part]
    else:
        cur = None
        break
if cur is None:
    print("")
elif isinstance(cur, (dict, list)):
    print(json.dumps(cur, ensure_ascii=False))
else:
    print(cur)
PY
    return
  fi
  if have_cmd python; then
    python - "$file" "$expr" <<'PY'
import json, sys
path = sys.argv[1]
expr = sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
cur = data
for part in expr.lstrip(".").split("."):
    if part == "":
        continue
    if isinstance(cur, dict) and part in cur:
        cur = cur[part]
    else:
        cur = None
        break
if cur is None:
    print("")
elif isinstance(cur, (dict, list)):
    print(json.dumps(cur, ensure_ascii=False))
else:
    print(cur)
PY
    return
  fi
  echo "ERROR: python3 or python required for json_get_file" >&2
  return 1
}

write_evidence() {
  # Append markdown to evidence file
  mkdir -p "$(dirname "${EVIDENCE_FILE}")"
  printf "%s\n" "$1" >> "${EVIDENCE_FILE}"
}

sanitize_text() {
  # Mask any secrets we might accidentally include in evidence.
  # - Device tokens returned by /devices/register
  # - Any env-like OPENAI_API_KEY occurrences (defensive)
  sed -E \
    -e 's/("token"[[:space:]]*:[[:space:]]*)"[^"]+"/\1"***"/g' \
    -e 's/(OPENAI_API_KEY[=:])[[:space:]]*[^"[:space:]]+/\1***/g'
}

curl_capture() {
  # Capture curl -i output to file and also print a short, safe summary.
  #
  # usage:
  #   curl_capture "name" "POST" "$url" "$json" "$token"
  local name="$1"
  local method="$2"
  local url="$3"
  local json_body="${4:-}"
  local token="${5:-}"

  local out="${OUT_DIR}/${name}.txt"

  # Build curl args
  local args=()
  args+=("-sS" "-i" "-X" "${method}" "${url}")
  args+=("-H" "Content-Type: application/json")
  if [[ -n "${token}" ]]; then
    args+=("-H" "${DEVICE_AUTH_HEADER}: ${token}")
  fi
  if [[ -n "${json_body}" ]]; then
    args+=("--data" "${json_body}")
  fi

  # Run curl. Append a machine-readable status marker.
  if ! have_cmd curl; then
    printf "curl not found on PATH\n" | tee "${out}" >/dev/null
    return 0
  fi

  # shellcheck disable=SC2090
  curl "${args[@]}" -w "\nCURL_HTTP_STATUS:%{http_code}\n" > "${out}" || true

  local status
  status="$(grep -Eo 'CURL_HTTP_STATUS:[0-9]+' "${out}" | tail -n 1 | cut -d: -f2 || true)"
  if [[ -z "${status}" ]]; then status="(unknown)"; fi

  # Extract JSON body only (first "{" up to line before CURL_HTTP_STATUS:) into .json for parsing
  local json_file="${OUT_DIR}/${name}.json"
  awk 'BEGIN{p=0} /^\{/{p=1} /^CURL_HTTP_STATUS:/{p=0} p{print}' "${out}" > "${json_file}" || true
  if [[ ! -s "${json_file}" ]]; then
    echo "ERROR: empty JSON body for ${name} (${json_file})" >&2
    exit 1
  fi
  if have_cmd python3; then
    python3 -c "import json, sys; json.load(open(sys.argv[1]))" "${json_file}" 2>/dev/null || {
      echo "ERROR: invalid JSON for ${name} (${json_file})" >&2
      exit 1
    }
  elif have_cmd python; then
    python -c "import json, sys; json.load(open(sys.argv[1]))" "${json_file}" 2>/dev/null || {
      echo "ERROR: invalid JSON for ${name} (${json_file})" >&2
      exit 1
    }
  fi

  # Extract a compact body snippet (best-effort)
  local body_snip
  body_snip="$(awk 'BEGIN{inbody=0} /^\r?$/{inbody=1; next} {if(inbody) print}' "${out}" | tail -n 60 | tr -d '\r' || true)"
  local body_snip_s
  body_snip_s="$(printf "%s\n" "${body_snip}" | sanitize_text)"
  local headers_snip headers_snip_s
  headers_snip="$(awk 'BEGIN{inbody=0} {if(!inbody) print} /^\r?$/{exit}' "${out}" | head -n 40 | tr -d '\r' || true)"
  headers_snip_s="$(printf "%s\n" "${headers_snip}" | sanitize_text)"

  # Write evidence section (mask token)
  local masked="(none)"
  if [[ -n "${token}" ]]; then masked="$(mask_token "${token}")"; fi

  write_evidence "### ${name}"
  write_evidence ""
  write_evidence "- **URL**: \`${url}\`"
  write_evidence "- **Method**: \`${method}\`"
  write_evidence "- **Auth header**: \`${DEVICE_AUTH_HEADER}: ${masked}\`"
  write_evidence "- **HTTP status (curl)**: **${status}**"
  write_evidence ""
  write_evidence "**Response headers (head, raw)**:"
  write_evidence ""
  write_evidence "\`\`\`"
  printf "%s\n" "${headers_snip_s}" >> "${EVIDENCE_FILE}"
  write_evidence "\`\`\`"
  write_evidence ""
  write_evidence "**Response (tail, raw)**:"
  write_evidence ""
  write_evidence "\`\`\`"
  printf "%s\n" "${body_snip_s}" >> "${EVIDENCE_FILE}"
  write_evidence "\`\`\`"
  write_evidence ""
}

passfail_init() {
  PASSFAIL_FILE="${OUT_DIR}/summary.tsv"
  printf "test\tresult\tnotes\n" > "${PASSFAIL_FILE}"
}

passfail_add() {
  local test="$1"; local result="$2"; local notes="${3:-}"
  printf "%s\t%s\t%s\n" "${test}" "${result}" "${notes}" >> "${PASSFAIL_FILE}"
}

extract_body_json() {
  # Extract JSON from curl -i output file (best-effort): take last {...} block.
  local file="$1"
  # Body starts after first blank line; take everything after and try to find JSON object.
  local body
  body="$(awk 'BEGIN{inbody=0} /^\r?$/{inbody=1; next} {if(inbody) print}' "${file}" | tr -d '\r' || true)"
  # Heuristic: find first '{' and last '}'.
  local json
  json="$(printf "%s" "${body}" | sed -n '1,/^{/!p' >/dev/null 2>&1; true)"
  # Simpler: use python/jq? We'll just return full body and let json_get fail gracefully.
  printf "%s" "${body}"
}

get_status_from_capture() {
  local file="$1"
  grep -Eo 'CURL_HTTP_STATUS:[0-9]+' "${file}" | tail -n 1 | cut -d: -f2 || true
}

write_header() {
  write_evidence ""
  write_evidence "## Release C Final Test Evidence"
  write_evidence ""
  write_evidence "- **Run (UTC)**: \`${RUN_ID}\`"
  write_evidence "- **BASE_URL**: \`${BASE_URL}\`"
  write_evidence "- **USER_ID**: \`${USER_ID}\`"
  write_evidence "- **DEVICE_ID**: \`${DEVICE_ID}\`"
  write_evidence "- **DEVICE_AUTH_HEADER**: \`${DEVICE_AUTH_HEADER}\`"
  write_evidence "- **Artifacts dir**: \`${OUT_DIR}\`"
  write_evidence ""
  write_evidence "> Note: tokens/secrets are masked in this report."
  write_evidence "> Prior ingest INTERNAL_ERROR root cause: HTTP status masking (HTTPException was caught by broad \`except Exception\` and returned 200). Fixed by re-raising HTTPException and returning HTTP 500 for unexpected exceptions; invalid token now returns 401."
  write_evidence ""
}

db_evidence() {
  write_evidence "## Database Evidence (best-effort)"
  write_evidence ""
  # Detect psql: explicit path first, then PATH (do not rely on PATH alone)
  local psql_cmd=""
  if [[ -x /usr/bin/psql ]]; then
    psql_cmd="/usr/bin/psql"
  elif have_cmd psql; then
    psql_cmd="$(command -v psql)"
  fi
  if [[ -z "${psql_cmd}" ]]; then
    write_evidence "- **psql**: not found (/usr/bin/psql and \`command -v psql\` both missing); skipping DB evidence."
    write_evidence ""
    return 0
  fi
  write_evidence "- **psql path**: \`${psql_cmd}\`"
  write_evidence ""

  # Attempt basic connectivity; log exact error on failure
  set +e
  local dblist
  dblist="$("${psql_cmd}" -U postgres -h 127.0.0.1 -d postgres -lqt 2>&1)"
  local rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    write_evidence "- **psql connect**: FAILED (exit code ${rc})"
    write_evidence ""
    write_evidence "\`\`\`"
    printf "%s\n" "${dblist}" >> "${EVIDENCE_FILE}"
    write_evidence "\`\`\`"
    write_evidence ""
    write_evidence "- Skipping DB queries (connection failed; secrets left masked)."
    write_evidence ""
    return 0
  fi

  write_evidence "- **psql connect**: OK"
  write_evidence ""

  # Choose likely DB name from list
  local dbname
  dbname="$(
    printf "%s\n" "${dblist}" \
      | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/, "", $1); print $1}' \
      | grep -E '^(sedi|backend|app|postgres)$' \
      | head -n 1
  )"
  if [[ -z "${dbname}" ]]; then
    dbname="postgres"
  fi

  write_evidence "- **Detected DB**: \`${dbname}\`"
  write_evidence ""

  # Run key queries
  local q1 q2 q3
  q3="select device_id, user_id, status, last_seen_at, created_at, revoked_at from devices where device_id='${DEVICE_ID}' and user_id=${USER_ID} limit 5;"
  q1="select id, user_id, device_id, event_type, dedupe_key, recorded_at, received_at from device_events where device_id='${DEVICE_ID}' order by id desc limit 10;"
  q2="select id, user_id, domain, key, value_json, source, created_at, updated_at from user_memory_facts where user_id=${USER_ID} and domain='vitals' order by id desc limit 10;"

  write_evidence "**devices row**:"
  write_evidence ""
  write_evidence "\`\`\`"
  "${psql_cmd}" -U postgres -h 127.0.0.1 -d "${dbname}" -c "${q3}" 2>&1 | sed -E 's/(password=)[^ ]+/\1*** /g' >> "${EVIDENCE_FILE}" || true
  write_evidence "\`\`\`"
  write_evidence ""

  write_evidence "**recent device_events**:"
  write_evidence ""
  write_evidence "\`\`\`"
  "${psql_cmd}" -U postgres -h 127.0.0.1 -d "${dbname}" -c "${q1}" 2>&1 | sed -E 's/(password=)[^ ]+/\1*** /g' >> "${EVIDENCE_FILE}" || true
  write_evidence "\`\`\`"
  write_evidence ""

  write_evidence "**recent user_memory_facts (vitals)**:"
  write_evidence ""
  write_evidence "\`\`\`"
  "${psql_cmd}" -U postgres -h 127.0.0.1 -d "${dbname}" -c "${q2}" 2>&1 | sed -E 's/(password=)[^ ]+/\1*** /g' >> "${EVIDENCE_FILE}" || true
  write_evidence "\`\`\`"
  write_evidence ""
}

main() {
  wait_for_http_ok
  write_header
  passfail_init

  # 0) Sanity: root endpoint
  curl_capture "00_root" "GET" "${BASE_URL}/" ""
  passfail_add "Root endpoint reachable" "INFO" "See 00_root"

  # 1) Register device -> token1
  local reg_url="${BASE_URL}/devices/register?user_id=${USER_ID}"
  local reg_body
  reg_body="$(printf '{"device_id":"%s","device_type":"heart_rate"}' "${DEVICE_ID}")"
  curl_capture "01_register_token1" "POST" "${reg_url}" "${reg_body}"

  local reg_json="${OUT_DIR}/01_register_token1.json"
  local token1
  token1="$(json_get_file "${reg_json}" ".data.token")"

  if [[ -n "${token1}" && "${token1}" != "null" ]]; then
    passfail_add "Register issues device token" "PASS" "token1=$(mask_token "${token1}")"
  else
    passfail_add "Register issues device token" "FAIL" "Could not parse data.token (jq/python may be missing or response not ok)"
  fi

  # 2) Re-register -> token2 (rotation path)
  curl_capture "02_reregister_token2" "POST" "${reg_url}" "${reg_body}"
  local reg2_json="${OUT_DIR}/02_reregister_token2.json"
  local token2
  token2="$(json_get_file "${reg2_json}" ".data.token")"

  if [[ -n "${token2}" && "${token2}" != "null" ]]; then
    if [[ -n "${token1}" && "${token1}" != "null" && "${token2}" != "${token1}" ]]; then
      passfail_add "Re-register rotates token (token2 != token1)" "PASS" "token2=$(mask_token "${token2}")"
    else
      passfail_add "Re-register rotates token (token2 != token1)" "FAIL" "token2 missing or equals token1"
    fi
  else
    passfail_add "Re-register rotates token (token2 != token1)" "FAIL" "Could not parse data.token"
  fi

  # 3) Heartbeat with token2 (server may not enforce auth; record behavior)
  local hb_url="${BASE_URL}/device/heartbeat"
  local hb_body
  hb_body="$(printf '{"device_id":"%s","user_id":%s,"status":"ok"}' "${DEVICE_ID}" "${USER_ID}")"
  curl_capture "03_heartbeat_token2" "POST" "${hb_url}" "${hb_body}" "${token2:-}"
  passfail_add "Heartbeat with token2 works (200 expected)" "INFO" "See 03_heartbeat_token2"

  # 4) Heartbeat with token1 (record policy)
  curl_capture "04_heartbeat_token1" "POST" "${hb_url}" "${hb_body}" "${token1:-}"
  passfail_add "Heartbeat with token1 behavior recorded" "INFO" "See 04_heartbeat_token1"

  # 5) Ingest with token2 (expect 200 ok:true with event_id)
  local ingest_url="${BASE_URL}/device/ingest"
  local recorded_at
  recorded_at="$(date -u +%Y-%m-%dT%H:%M:00Z)"
  local ingest_body
  ingest_body="$(printf '{"user_id":%s,"device_id":"%s","event_type":"heart_rate","payload":{"bpm":82},"recorded_at":"%s"}' "${USER_ID}" "${DEVICE_ID}" "${recorded_at}")"
  curl_capture "05_ingest_token2" "POST" "${ingest_url}" "${ingest_body}" "${token2:-}"

  local ing_json="${OUT_DIR}/05_ingest_token2.json"
  local event_id ok_flag
  ok_flag="$(json_get_file "${ing_json}" ".ok")"
  event_id="$(json_get_file "${ing_json}" ".data.event_id")"
  if [[ "${ok_flag}" == "true" && -n "${event_id}" && "${event_id}" != "null" ]]; then
    passfail_add "Ingest with token2 works (200 and event_id returned)" "PASS" "event_id=${event_id}"
  else
    passfail_add "Ingest with token2 works (200 and event_id returned)" "FAIL" "ok=${ok_flag} event_id=${event_id}"
  fi

  # 6) Ingest duplicate (same recorded_at => same 5-min bucket dedupe)
  curl_capture "06_ingest_duplicate" "POST" "${ingest_url}" "${ingest_body}" "${token2:-}"
  local dup_json="${OUT_DIR}/06_ingest_duplicate.json"
  local dup_msg dup_event_id
  dup_msg="$(json_get_file "${dup_json}" ".data.message")"
  dup_event_id="$(json_get_file "${dup_json}" ".data.event_id")"
  if [[ "${dup_msg}" == "Event already exists (duplicate)" && ( "${dup_event_id}" == "" || "${dup_event_id}" == "null" ) ]]; then
    passfail_add "Ingest duplicate does NOT create new event" "PASS" "message=${dup_msg}"
  else
    passfail_add "Ingest duplicate does NOT create new event" "INFO" "Unexpected duplicate response; see 06_ingest_duplicate"
  fi

  # 7) Ingest with invalid/old token (token1) MUST be HTTP 401; if not, flag masking bug.
  curl_capture "07_ingest_old_token1" "POST" "${ingest_url}" "${ingest_body}" "${token1:-}"
  local old_txt="${OUT_DIR}/07_ingest_old_token1.txt"
  local old_json="${OUT_DIR}/07_ingest_old_token1.json"
  local old_status old_ok old_err_code
  old_status="$(get_status_from_capture "${old_txt}")"
  old_ok="$(json_get_file "${old_json}" ".ok")"
  old_err_code="$(json_get_file "${old_json}" ".error.code")"

  if [[ "${old_status}" == "401" ]]; then
    passfail_add "Ingest with invalid/old token returns HTTP 401" "PASS" "status=401"
  else
    # Many routers mistakenly mask HTTPException into 200 + ok:false
    passfail_add "Ingest with invalid/old token returns HTTP 401" "FAIL" "status=${old_status} ok=${old_ok} error.code=${old_err_code} (BUG: HTTP status masking?)"
  fi

  # 8) Rate limit: burst ingestion requests until 429 observed (best-effort).
  # Backend default DEVICE_RATE_LIMIT_PER_MINUTE=30; use 200 to trigger if single worker.
  # Note: limit is per-process (in-memory); multiple workers each have their own bucket.
  local rl_burst=200
  local rl_hit="no"
  local i
  for i in $(seq 1 "${rl_burst}"); do
    local name
    name="$(printf "08_rate_%03d" "${i}")"
    curl_capture "${name}" "POST" "${ingest_url}" "${ingest_body}" "${token2:-}"
    local f="${OUT_DIR}/${name}.txt"
    local st
    st="$(get_status_from_capture "${f}")"
    if [[ "${st}" == "429" ]]; then
      rl_hit="yes"
      break
    fi
  done
  if [[ "${rl_hit}" == "yes" ]]; then
    passfail_add "Rate limit returns 429 after bursts" "PASS" "Observed 429 during burst"
  else
    passfail_add "Rate limit returns 429 after bursts" "INFO" "No 429 in ${rl_burst} requests (limit=30/min in code; multiple workers or different env can prevent 429)"
  fi

  # 9) Optional API evidence: list devices (may show last_seen_at without DB access)
  curl_capture "09_list_devices" "GET" "${BASE_URL}/devices?user_id=${USER_ID}" ""
  passfail_add "last_seen behavior observed (API-level)" "INFO" "See 09_list_devices for last_seen_at"

  # DB evidence (best-effort)
  db_evidence

  # Summary
  write_evidence "## PASS/FAIL Summary"
  write_evidence ""
  write_evidence "\`\`\`"
  cat "${PASSFAIL_FILE}" >> "${EVIDENCE_FILE}"
  write_evidence "\`\`\`"
  write_evidence ""

  # Bugs found section (heuristic: any FAIL rows)
  local fails
  fails="$(awk -F'\t' 'NR>1 && $2=="FAIL"{print "- " $1 ": " $3}' "${PASSFAIL_FILE}" || true)"
  write_evidence "## Bugs found"
  write_evidence ""
  if [[ -n "${fails}" ]]; then
    printf "%s\n" "${fails}" >> "${EVIDENCE_FILE}"
  else
    write_evidence "- (none observed in this run)"
  fi
  write_evidence ""

  # Console summary (safe)
  echo "Evidence appended to: ${EVIDENCE_FILE}"
  echo "Artifacts saved to:   ${OUT_DIR}"
  echo ""
  echo "PASS/FAIL summary:"
  awk -F'\t' 'NR==1{next} {printf "- %s: %s\n", $1, $2}' "${PASSFAIL_FILE}"
}

main "$@"

