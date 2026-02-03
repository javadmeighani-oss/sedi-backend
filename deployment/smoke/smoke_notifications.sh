#!/usr/bin/env bash
set -euo pipefail

# Production-safe smoke test for Notifications API (Release B3)
#
# Requirements:
# - No auth assumed; uses current user_id query param behavior
# - No external services (no OpenAI)
#
# Usage:
#   BASE_URL="http://localhost:8000" USER_ID=1 ./deployment/smoke/smoke_notifications.sh

BASE_URL="${BASE_URL:-http://localhost:8000}"
USER_ID="${USER_ID:-1}"
LIMIT="${LIMIT:-5}"

pass() { echo "✅ $1"; }
fail() { echo "❌ $1"; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

need_cmd curl

get_unread() {
  curl -sS -f "${BASE_URL}/notifications/unread?user_id=${USER_ID}&limit=${LIMIT}"
}

parse_first_id() {
  local json="$1"
  if command -v jq >/dev/null 2>&1; then
    echo "$json" | jq -r '.data.notifications[0].id // empty'
  else
    python - <<'PY'
import json, sys
data = json.load(sys.stdin)
try:
  print(data.get("data", {}).get("notifications", [{}])[0].get("id", "") or "")
except Exception:
  print("")
PY
  fi
}

parse_count() {
  local json="$1"
  if command -v jq >/dev/null 2>&1; then
    echo "$json" | jq -r '.data.count // (.data.notifications|length) // 0'
  else
    python - <<'PY'
import json, sys
data = json.load(sys.stdin)
try:
  d = data.get("data", {}) or {}
  if "count" in d and isinstance(d["count"], int):
    print(d["count"])
  else:
    print(len(d.get("notifications", []) or []))
except Exception:
  print(0)
PY
  fi
}

contains_unread_id() {
  local json="$1"
  local id="$2"
  if command -v jq >/dev/null 2>&1; then
    # shellcheck disable=SC2016
    echo "$json" | jq -e --arg id "$id" '.data.notifications[]? | select((.id|tostring)==$id)' >/dev/null 2>&1
  else
    python - <<'PY'
import json, sys, os
data = json.load(sys.stdin)
target = os.environ.get("TARGET_ID", "")
items = (data.get("data", {}) or {}).get("notifications", []) or []
found = any(str(i.get("id")) == str(target) for i in items if isinstance(i, dict))
sys.exit(0 if found else 1)
PY
  fi
}

echo "== Notifications Smoke (B3) =="
echo "BASE_URL=${BASE_URL}"
echo "USER_ID=${USER_ID}"

# 1) unread
unread_1="$(get_unread)" || fail "GET /notifications/unread failed"
ok_1="$(echo "$unread_1" | (command -v jq >/dev/null 2>&1 && jq -r '.ok' || python -c "import json,sys; print(json.load(sys.stdin).get('ok'))"))" || true
[[ "$ok_1" == "True" || "$ok_1" == "true" ]] || fail "Unread response ok != true"
count_1="$(parse_count "$unread_1")"
pass "Unread fetched (count=${count_1})"

first_id="$(parse_first_id "$unread_1")"
[[ -n "$first_id" ]] || fail "No unread notifications to test with (need at least 1 for USER_ID=${USER_ID})"
pass "Found first unread notification id=${first_id}"

# 2) mark-read
mark_read_resp="$(curl -sS -f -X POST "${BASE_URL}/notifications/${first_id}/mark-read?user_id=${USER_ID}")" || fail "POST /notifications/{id}/mark-read failed"
ok_2="$(echo "$mark_read_resp" | (command -v jq >/dev/null 2>&1 && jq -r '.ok' || python -c "import json,sys; print(json.load(sys.stdin).get('ok'))"))" || true
[[ "$ok_2" == "True" || "$ok_2" == "true" ]] || fail "Mark-read response ok != true"
pass "Marked read id=${first_id}"

# 3) feedback
feedback_payload='{"feedback":"neutral","reason":"smoke_test","action":"irrelevant"}'
feedback_resp="$(curl -sS -f -X POST "${BASE_URL}/notifications/${first_id}/feedback?user_id=${USER_ID}" -H "Content-Type: application/json" -d "$feedback_payload")" || fail "POST /notifications/{id}/feedback failed"
ok_3="$(echo "$feedback_resp" | (command -v jq >/dev/null 2>&1 && jq -r '.ok' || python -c "import json,sys; print(json.load(sys.stdin).get('ok'))"))" || true
[[ "$ok_3" == "True" || "$ok_3" == "true" ]] || fail "Feedback response ok != true"
pass "Feedback accepted id=${first_id}"

# 4) unread again, verify decreased or id not present
unread_2="$(get_unread)" || fail "GET /notifications/unread (second) failed"
count_2="$(parse_count "$unread_2")"

id_still_present="false"
if command -v jq >/dev/null 2>&1; then
  if echo "$unread_2" | jq -e --arg id "$first_id" '.data.notifications[]? | select((.id|tostring)==$id)' >/dev/null 2>&1; then
    id_still_present="true"
  fi
else
  TARGET_ID="$first_id" contains_unread_id "$unread_2" "$first_id" && id_still_present="true" || true
fi

if [[ "$count_2" -lt "$count_1" ]]; then
  pass "Unread count decreased (${count_1} -> ${count_2})"
elif [[ "$id_still_present" == "false" ]]; then
  pass "Marked notification no longer present in unread list"
else
  fail "Unread did not decrease and id still present (count ${count_1} -> ${count_2}, id=${first_id})"
fi

pass "Notifications smoke test completed successfully"
