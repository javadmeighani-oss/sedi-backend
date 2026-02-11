# Production Notifications Execution Runbook

Copy-paste commands for validating push notifications on the Hetzner server.

---

## 1. Preconditions

| Item | Value |
|------|-------|
| `ADMIN_TOKEN` | Set (strong random string) |
| `FCM_PROJECT_ID` | From Firebase Console |
| `FCM_SERVICE_ACCOUNT_JSON` | Path to JSON file (e.g. `/etc/sedi/fcm_service_account.json`) |
| `FCM_DISABLED` | `false` (must be false for real sends) |
| Service name | `sedi-backend.service` |
| Base URL (local) | `http://127.0.0.1:8000` |
| Base URL (public) | `http://<server-ip>:8000` |

---

## 2. systemd Env Setup (Drop-in Override)

Create drop-in directory and override file:

```bash
sudo mkdir -p /etc/systemd/system/sedi-backend.service.d
sudo nano /etc/systemd/system/sedi-backend.service.d/override.conf
```

Example contents (replace `...` with real values; do NOT commit):

```ini
[Service]
Environment=FCM_PROJECT_ID=...
Environment=FCM_SERVICE_ACCOUNT_JSON=/etc/sedi/fcm_service_account.json
Environment=FCM_DISABLED=false
Environment=ADMIN_TOKEN=...
Environment=DELIVER_BATCH_SIZE=200
Environment=FCM_TIMEOUT_SECONDS=5
Environment=FCM_MAX_RETRIES=2
Environment=FCM_BACKOFF_SECONDS=10
Environment=ENGAGEMENT_MAX_PER_DAY=3
Environment=ENGAGEMENT_MIN_HOURS=3
```

---

## 3. Restart + Verify Env Loaded

```bash
sudo systemctl daemon-reload
sudo systemctl restart sedi-backend.service
sudo systemctl status sedi-backend.service --no-pager | head
```

Confirm env on running PID (keys only; no values):

```bash
PID=$(systemctl show sedi-backend.service -p MainPID --value)
sudo cat /proc/$PID/environ 2>/dev/null | tr '\0' '\n' | cut -d= -f1 | sort
```

Expected keys include: `FCM_PROJECT_ID`, `FCM_SERVICE_ACCOUNT_JSON`, `FCM_DISABLED`, `ADMIN_TOKEN`, etc.

---

## 4. Run Sanity Script on Server

```bash
ADMIN_TOKEN=... BASE_URL=http://127.0.0.1:8000 USER_ID=<your_user_id> bash backend/scripts/prod_notifications_sanity.sh
```

**Expected output (summary):**
- `[OK] FCM_PROJECT_ID is set`
- `[OK] FCM_SERVICE_ACCOUNT_JSON is set` (and path readable)
- `[OK] FCM_DISABLED is not true`
- `[OK] GET /`
- `[OK] GET /notifications/admin/health`
- `[OK] GET /notifications/admin/push_devices` with `Devices: N`
- `[OK] POST /notifications/admin/test_push?deliver=true` with `notification_id=... sent_count=N`
- `All checks passed.`

If no token registered for user: `sent_count=0` is acceptable; `admin health ok` and `pending_count` still confirm subsystem is up.

---

## 5. Real Device Validation Sequence (Exact Order)

### 5.1 Install APK

Download APK from GitHub Actions (or build) and install on Android device.

### 5.2 Login

Complete onboarding / verification in app so the user has a `user_id`.

### 5.3 Confirm Token Registered (server)

```bash
curl -s -H "X-Admin-Token: YOUR_ADMIN_TOKEN" \
  "http://127.0.0.1:8000/notifications/admin/push_devices?user_id=<id>"
```

**Expected:** `{"ok": true, "data": {"devices": [...], "count": 1}}` (or count > 0).

### 5.4 Trigger Test Push (server)

```bash
curl -s -X POST -H "X-Admin-Token: YOUR_ADMIN_TOKEN" -H "Content-Type: application/json" \
  "http://127.0.0.1:8000/notifications/admin/test_push?deliver=true" \
  -d '{"user_id": <id>, "channel": "engagement", "priority": "high"}'
```

**Expected:** `{"ok": true, "data": {"notification_id": N, "channel": "engagement", "delivered": true, "sent_count": 1}}`

### 5.5 Verify on Phone

- Notification appears within seconds.
- Tap notification → Chat opens; `open_chat` feedback stored.
- Tap Like/Dislike → feedback stored.

---

## 6. Verify Feedback Stored (Server-Side)

### Option A: Grep backend logs

```bash
sudo journalctl -u sedi-backend.service -n 500 --no-pager | grep -E "feedback|POST.*notifications/[0-9]*/feedback"
```

### Option B: Query DB (if DB access available)

```sql
SELECT id, notification_id, action, created_at
FROM notification_feedback
ORDER BY created_at DESC
LIMIT 10;
```

---

## 7. Logs to Watch

```bash
sudo journalctl -u sedi-backend.service -f | grep -E '\[NOTIF\]|\[E2E\]'
```

**Good examples:**
- `[E2E] admin push_devices user_id=1 count=1`
- `[E2E] admin test_push user_id=1 channel=engagement notification_id=42 deliver=True sent=1`
- `[NOTIF] deliver_pending ...`

**Bad examples:**
- `FCM_DISABLED is true` when expecting real sends
- `401` / `Admin token required` → `ADMIN_TOKEN` missing or wrong
- `USER_NOT_FOUND` → invalid `user_id`
- `sent_count=0` with no push devices → token not registered (login/register step)

---

## 8. Rollback

### 8.1 Disable FCM and Engagement

Edit override:

```ini
[Service]
Environment=FCM_DISABLED=true
Environment=ENGAGEMENT_MAX_PER_DAY=0
```

### 8.2 Restart

```bash
sudo systemctl daemon-reload
sudo systemctl restart sedi-backend.service
```

### 8.3 Confirm

```bash
curl -s -H "X-Admin-Token: YOUR_ADMIN_TOKEN" http://127.0.0.1:8000/notifications/admin/health
```

And:

```bash
sudo journalctl -u sedi-backend.service -n 50 --no-pager | grep FCM_DISABLED
```

---

## 9. Commands from Laptop (Remote Checks)

Replace `<server-ip>` with your Hetzner IP:

```bash
# Root health
curl -s "http://<server-ip>:8000/"

# Admin health
curl -s -H "X-Admin-Token: YOUR_ADMIN_TOKEN" \
  "http://<server-ip>:8000/notifications/admin/health"

# Sanity script (remote; FCM env vars will not be checked)
ADMIN_TOKEN=... BASE_URL=http://<server-ip>:8000 USER_ID=1 bash backend/scripts/prod_notifications_sanity.sh
```

---

## Related Docs

- `backend/docs/PROD_NOTIFICATIONS_ROLLOUT_CHECKLIST.md` — Full rollout checklist
- `backend/docs/RELEASE_STAGE16_6_NOTIFICATIONS_V1.md` — Feature overview
- `backend/docs/NOTIFICATIONS_E2E_CHECKLIST.md` — E2E verification
