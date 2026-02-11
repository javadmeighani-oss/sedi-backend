# Production Notifications Rollout Checklist (Stage 16.6.3)

Operational guide for deploying and validating push notifications on Hetzner (systemd `sedi-backend.service`).

---

## 1. Required Env Vars (~1000 users)

Set these in the service environment. **Never commit secrets.**

| Variable | Recommended Value | Description |
|----------|-------------------|-------------|
| `FCM_PROJECT_ID` | (from Firebase) | Firebase project ID |
| `FCM_SERVICE_ACCOUNT_JSON` | `/var/www/sedi/backend/secrets/fcm-service-account.json` | Path to service account JSON (preferred over inline) |
| `FCM_DISABLED` | `false` | Must be `false` for production FCM |
| `ADMIN_TOKEN` | (strong random string) | Required for admin endpoints |
| `DELIVER_BATCH_SIZE` | `200` | Max pending per deliver run |
| `FCM_TIMEOUT_SECONDS` | `5` | Per-request FCM timeout |
| `FCM_MAX_RETRIES` | `2` | In-process retries on failure |
| `FCM_BACKOFF_SECONDS` | `10` | Backoff between retries |
| `ENGAGEMENT_MAX_PER_DAY` | `3` | Max engagement nudges per user per day |
| `ENGAGEMENT_MIN_HOURS` | `3` | Min hours between engagement nudges |

---

## 2. systemd Environment Configuration

### Option A: Drop-in override (recommended)

Create drop-in directory and override file:

```bash
sudo mkdir -p /etc/systemd/system/sedi-backend.service.d
sudo nano /etc/systemd/system/sedi-backend.service.d/override.conf
```

Add (replace values; do not commit this file):

```ini
[Service]
# FCM push notifications
Environment="FCM_PROJECT_ID=your-project-id"
Environment="FCM_SERVICE_ACCOUNT_JSON=/var/www/sedi/backend/secrets/fcm-service-account.json"
Environment="FCM_DISABLED=false"
Environment="ADMIN_TOKEN=your-admin-token"
Environment="DELIVER_BATCH_SIZE=200"
Environment="FCM_TIMEOUT_SECONDS=5"
Environment="FCM_MAX_RETRIES=2"
Environment="FCM_BACKOFF_SECONDS=10"
Environment="ENGAGEMENT_MAX_PER_DAY=3"
Environment="ENGAGEMENT_MIN_HOURS=3"
```

### Option B: EnvironmentFile

If using a separate env file (ensure it is not in git):

```ini
[Service]
EnvironmentFile=/var/www/sedi/backend/.env
# Or a dedicated secrets file:
# EnvironmentFile=/var/www/sedi/backend/secrets/notifications.env
```

### Apply and restart

```bash
sudo systemctl daemon-reload
sudo systemctl restart sedi-backend.service
sudo systemctl status sedi-backend.service
```

### View logs

```bash
sudo journalctl -u sedi-backend.service -n 200 --no-pager
sudo journalctl -u sedi-backend.service -f
```

---

## 3. Sanity Checks (curl)

### 3.1 Root health

```bash
curl -s http://localhost:8000/
```

### 3.2 Notification admin health

```bash
curl -s -X GET "http://localhost:8000/notifications/admin/health" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN"
```

Expected: `{"ok": true, "data": {"notifications_pending_count": N, "notifications_failed_last_1h": N, "last_deliver_pending_run_at": "..."}}`

### 3.3 List push devices (user 1)

```bash
curl -s -X GET "http://localhost:8000/notifications/admin/push_devices?user_id=1" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN"
```

### 3.4 Enqueue + deliver test push

```bash
curl -s -X POST "http://localhost:8000/notifications/admin/test_push?deliver=true" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN" \
  -d '{"user_id": 1, "channel": "engagement", "title": "Prod Test", "body": "Verify push delivery"}'
```

Expected: `{"ok": true, "data": {"notification_id": N, "delivered": true, "sent_count": 1}}`

---

## 4. Verify on Android

1. **Token registration**: Open app, complete onboarding. Confirm `push_devices` has a row (see 3.3).
2. **Receive push**: Run 3.4 and confirm device receives notification.
3. **Action buttons**: Tap LIKE/DISLIKE/OPEN_CHAT; verify feedback stored:
   ```sql
   SELECT * FROM notification_feedback ORDER BY created_at DESC LIMIT 5;
   ```

---

## 5. Rollback Plan

If issues occur, apply one or more:

| Action | Command / Change |
|--------|------------------|
| Disable FCM | `Environment="FCM_DISABLED=true"` (logs only, no real sends) |
| Reduce load | `Environment="DELIVER_BATCH_SIZE=50"` |
| Disable engagement | `Environment="ENGAGEMENT_MAX_PER_DAY=0"` |

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart sedi-backend.service
```

---

## 6. Monitoring

### Grep [NOTIF] logs

```bash
sudo journalctl -u sedi-backend.service -n 500 --no-pager | grep '\[NOTIF\]'
```

### Watch failed_last_1h trends

```bash
# Run every 5 min
while true; do
  curl -s -H "X-Admin-Token: $ADMIN_TOKEN" \
    http://localhost:8000/notifications/admin/health | jq '.data.notifications_failed_last_1h'
  sleep 300
done
```

---

## 7. Scheduler Cadence

| Job | Recommended Cadence | Notes |
|-----|---------------------|-------|
| Morning brief | Daily, per-user timezone | Scheduler runs hourly; triggers per user at local morning |
| Engagement nudge | Every 3–6 hours | Respects `ENGAGEMENT_MIN_HOURS` and `ENGAGEMENT_MAX_PER_DAY` |
| Deliver pending | Every 5–10 minutes | Runs `deliver_pending` to flush outbox |
| Health alert | On-demand | Triggered by vitals/decision engine |

Tune `DELIVER_BATCH_SIZE` and cron frequency based on `backend/docs/NOTIFICATIONS_DB_INDEX_SANITY.md`.

---

## 8. Sanity Script

Run the helper script (see `backend/scripts/prod_notifications_sanity.sh`). On the server, source env first if checking FCM vars:

```bash
# On server (source env for FCM var checks):
source /var/www/sedi/backend/.env 2>/dev/null || true
ADMIN_TOKEN=your_token BASE_URL=http://localhost:8000 USER_ID=1 bash backend/scripts/prod_notifications_sanity.sh

# Or from another host (health/curl checks only; FCM vars will show unset):
ADMIN_TOKEN=your_token BASE_URL=http://91.107.168.130:8000 USER_ID=1 bash backend/scripts/prod_notifications_sanity.sh
```

---

## Related Docs

- `backend/docs/PROD_NOTIFICATIONS_EXECUTION_RUNBOOK.md` — Copy-paste production runbook (sanity script, validation sequence, rollback)
- `backend/docs/RELEASE_STAGE16_6_NOTIFICATIONS_V1.md` — Feature overview
- `backend/docs/NOTIFICATIONS_E2E_CHECKLIST.md` — E2E verification
- `backend/docs/NOTIFICATIONS_DB_INDEX_SANITY.md` — Index inventory and ops cadence
- `backend/scripts/notifications_mock_load.py` — Mock load script (FCM_DISABLED=true)
- `backend/deployment/README.md` — Deployment overview
