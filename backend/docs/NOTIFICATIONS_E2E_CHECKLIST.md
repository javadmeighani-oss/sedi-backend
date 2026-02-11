# Notifications E2E Verification Checklist (Stage 16.6.1)

End-to-end verification for push notifications.

## Required Env Vars

| Variable | Required | Description |
|----------|----------|-------------|
| `FCM_PROJECT_ID` | For production FCM | Firebase project ID |
| `FCM_SERVICE_ACCOUNT_JSON` | For production FCM | Path or inline JSON for service account |
| `FCM_DISABLED` | No | Set to `true` to use mock (no-op send) |
| `ADMIN_TOKEN` | Recommended for admin endpoints | When set, `X-Admin-Token` header required for admin routes |

### Stage 16.6.2 Operational (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `DELIVER_BATCH_SIZE` | 200 | Max pending per deliver run |
| `FCM_TIMEOUT_SECONDS` | 5 | Per-request FCM timeout |
| `FCM_MAX_RETRIES` | 2 | In-process retries on failure |
| `FCM_BACKOFF_SECONDS` | 10 | Backoff between retries |
| `ENGAGEMENT_MAX_PER_DAY` | 3 | Max engagement nudges per user per day |
| `ENGAGEMENT_MIN_HOURS` | 3 | Min hours between engagement nudges |

## Verify Token Registration from the App

1. Login in the Flutter app (complete onboarding).
2. App calls `POST /notifications/push/register` with `user_id`, `fcm_token`, `platform: android`.
3. Use the admin endpoint to confirm:

```bash
curl -s -X GET "http://localhost:8000/notifications/admin/push_devices?user_id=1" \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

Expected: `{"ok": true, "data": {"devices": [...], "count": N}}` with masked tokens (e.g. `abc123...xyz9`).

## Curl Commands

### 1. List push devices (admin)

```bash
curl -s -X GET "${BASE_URL}/notifications/admin/push_devices?user_id=1" \
  -H "X-Admin-Token: ${ADMIN_TOKEN}"
```

### 2. Enqueue test push (admin)

```bash
curl -s -X POST "${BASE_URL}/notifications/admin/test_push" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: ${ADMIN_TOKEN}" \
  -d '{"user_id": 1, "channel": "engagement", "title": "E2E Test", "body": "Verify push"}'
```

Response: `{"ok": true, "data": {"notification_id": N, "channel": "engagement", "delivered": false}}`

### 3. Enqueue + deliver in one call

```bash
curl -s -X POST "${BASE_URL}/notifications/admin/test_push?deliver=true" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: ${ADMIN_TOKEN}" \
  -d '{"user_id": 1, "channel": "morning"}'
```

### 4. Run deliver_pending (admin)

```bash
curl -s -X POST "${BASE_URL}/notifications/deliver_pending?limit=100" \
  -H "X-Admin-Token: ${ADMIN_TOKEN}"
```

### 5. Submit feedback (user; no admin token)

```bash
curl -s -X POST "${BASE_URL}/notifications/${NOTIFICATION_ID}/feedback" \
  -H "Content-Type: application/json" \
  -d '{"action": "like", "client_ts": "2025-02-11T12:00:00Z"}'
```

### 6. Notification health (admin)

```bash
curl -s -X GET "${BASE_URL}/notifications/admin/health" \
  -H "X-Admin-Token: ${ADMIN_TOKEN}"
```

Returns: `notifications_pending_count`, `notifications_failed_last_1h`, `last_deliver_pending_run_at`.

### 7. Validate feedback rows

Query DB:

```sql
SELECT id, notification_id, user_id, action, created_at
FROM notification_feedback
WHERE notification_id = :id
ORDER BY created_at DESC;
```

## Expected Logs and DB Checks

### (1) Token registration exists

- `push_devices` table: row with `user_id`, `is_active=true`, `fcm_token` (unique).
- Logs: no token leakage; admin endpoint returns masked token only.

### (2) Notification created with proper fields

- `notifications` table: `channel`, `priority`, `title`, `body`, `language`, `actions_json`, `dedupe_key`, `scheduled_for`, `status=queued`, `deeplink_url`.

### (3) deliver_pending sends via FCM (or mock)

- When `FCM_DISABLED=true`: logs show `[FCM]` mock success; `status=sent`, `is_sent=true`.
- When FCM configured: `provider=fcm`, `provider_message_id` set on success.

### (4) Action feedback hits backend

- `notification_feedback` table: row with `notification_id`, `user_id`, `action` (like/dislike/open_chat/dismissed).

## Smoke Script

```bash
cd backend
BASE_URL=http://localhost:8000 ADMIN_TOKEN=your_token USER_ID=1 python scripts/notifications_e2e_smoke.py
```

See `backend/scripts/notifications_e2e_smoke.py` for details.
