#!/bin/bash
# prod_notifications_sanity.sh (Stage 16.6.3)
# Safe server-side sanity checks for push notifications. Does NOT print secrets.
# Usage: ADMIN_TOKEN=... BASE_URL=... USER_ID=... bash backend/scripts/prod_notifications_sanity.sh

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
USER_ID="${USER_ID:-1}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"

# Strip trailing slash
BASE_URL="${BASE_URL%/}"

echo "=== Prod Notifications Sanity ==="
echo "BASE_URL=$BASE_URL USER_ID=$USER_ID"
echo ""

# 1) Check required env vars (existence only; do not print values)
check_env() {
  local name="$1"
  local val="${!name}"
  if [ -z "$val" ]; then
    echo "[FAIL] Env var $name is not set"
    return 1
  fi
  echo "[OK] $name is set"
  return 0
}

ERRORS=0
check_env FCM_PROJECT_ID || ERRORS=$((ERRORS+1))
check_env FCM_SERVICE_ACCOUNT_JSON || ERRORS=$((ERRORS+1))
if [ -n "$FCM_SERVICE_ACCOUNT_JSON" ] && [ -f "$FCM_SERVICE_ACCOUNT_JSON" ]; then
  echo "[OK] FCM_SERVICE_ACCOUNT_JSON path exists and is readable"
else
  echo "[WARN] FCM_SERVICE_ACCOUNT_JSON path may not exist or be readable"
fi
if [ "${FCM_DISABLED:-false}" = "true" ] || [ "${FCM_DISABLED:-false}" = "1" ]; then
  echo "[WARN] FCM_DISABLED is true - FCM sends are mocked"
else
  echo "[OK] FCM_DISABLED is not true"
fi
if [ -z "$ADMIN_TOKEN" ]; then
  echo "[WARN] ADMIN_TOKEN not set - admin endpoints may return 401"
fi
echo ""

# 2) Root health
echo "--- Root health ---"
if curl -sf "${BASE_URL}/" > /dev/null; then
  echo "[OK] GET /"
else
  echo "[FAIL] GET /"
  ERRORS=$((ERRORS+1))
fi
echo ""

# 3) Admin health
echo "--- Notifications admin health ---"
if [ -z "$ADMIN_TOKEN" ]; then
  echo "[SKIP] ADMIN_TOKEN not set"
else
  RESP=$(curl -sf -X GET "${BASE_URL}/notifications/admin/health" \
    -H "X-Admin-Token: ${ADMIN_TOKEN}" 2>/dev/null || echo '{"ok":false}')
  if echo "$RESP" | grep -q '"ok":true'; then
    echo "[OK] GET /notifications/admin/health"
    echo "$RESP" | grep -o '"notifications_pending_count":[0-9]*' || true
    echo "$RESP" | grep -o '"notifications_failed_last_1h":[0-9]*' || true
    echo "$RESP" | grep -o '"last_deliver_pending_run_at":"[^"]*"' || true
  else
    echo "[FAIL] GET /notifications/admin/health"
    echo "$RESP" | head -c 200
    echo ""
    ERRORS=$((ERRORS+1))
  fi
fi
echo ""

# 4) Push devices
echo "--- Push devices for user $USER_ID ---"
if [ -z "$ADMIN_TOKEN" ]; then
  echo "[SKIP] ADMIN_TOKEN not set"
else
  RESP=$(curl -sf -X GET "${BASE_URL}/notifications/admin/push_devices?user_id=${USER_ID}" \
    -H "X-Admin-Token: ${ADMIN_TOKEN}" 2>/dev/null || echo '{"ok":false}')
  if echo "$RESP" | grep -q '"ok":true'; then
    echo "[OK] GET /notifications/admin/push_devices"
    COUNT=$(echo "$RESP" | grep -o '"count":[0-9]*' | grep -o '[0-9]*')
    echo "  Devices: $COUNT"
  else
    echo "[FAIL] GET /notifications/admin/push_devices"
    ERRORS=$((ERRORS+1))
  fi
fi
echo ""

# 5) Test push
echo "--- Test push (enqueue + deliver) ---"
if [ -z "$ADMIN_TOKEN" ]; then
  echo "[SKIP] ADMIN_TOKEN not set"
else
  RESP=$(curl -sf -X POST "${BASE_URL}/notifications/admin/test_push?deliver=true" \
    -H "Content-Type: application/json" \
    -H "X-Admin-Token: ${ADMIN_TOKEN}" \
    -d "{\"user_id\": ${USER_ID}, \"channel\": \"engagement\", \"title\": \"Sanity Test\", \"body\": \"Prod sanity check\"}" 2>/dev/null || echo '{"ok":false}')
  if echo "$RESP" | grep -q '"ok":true'; then
    echo "[OK] POST /notifications/admin/test_push?deliver=true"
    NOTIF_ID=$(echo "$RESP" | grep -o '"notification_id":[0-9]*' | grep -o '[0-9]*')
    SENT=$(echo "$RESP" | grep -o '"sent_count":[0-9]*' | grep -o '[0-9]*')
    echo "  notification_id=$NOTIF_ID sent_count=$SENT"
  else
    echo "[FAIL] POST /notifications/admin/test_push"
    echo "$RESP" | head -c 300
    echo ""
    ERRORS=$((ERRORS+1))
  fi
fi
echo ""

# Summary
echo "=== Summary ==="
if [ "$ERRORS" -eq 0 ]; then
  echo "All checks passed."
else
  echo "Errors: $ERRORS"
  exit 1
fi
