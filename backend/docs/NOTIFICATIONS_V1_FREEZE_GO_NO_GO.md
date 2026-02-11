# Notifications v1 Release Freeze + Go/No-Go (Stage 16.6.8)

Production-grade checklist for 100–1000 user rollout.

---

## 1. Scope

Stage 16.6 Notifications v1 capabilities:

| Capability | Description |
|------------|-------------|
| morning | Scheduled morning brief per user timezone |
| engagement | Engagement nudge (inactive 3+ h; max 3/day) |
| health_alert | Health care alerts via `enqueue_health_alert()` |
| Action buttons | LIKE, DISLIKE, OPEN_CHAT (feedback stored) |
| quiet_hours + timezone | Via chat commands; UserMemoryFact |
| Admin tools | `/admin/health`, `/admin/test_push`, `/admin/push_devices` |
| CI artifact | Android APK from GitHub Actions (`sedi-android-apk-<sha>`) |

---

## 2. Pre-Freeze Verification (Server)

### 2.1 Confirm env vars set

| Variable | Required | Notes |
|----------|----------|-------|
| `FCM_PROJECT_ID` | Yes (prod) | Firebase project ID |
| `FCM_SERVICE_ACCOUNT_JSON` | Yes (prod) | Path to service account JSON |
| `ADMIN_TOKEN` | Yes (admin endpoints) | Do not print in logs |
| `FCM_DISABLED` | No | `false` for prod; `true` for mock |
| `DELIVER_BATCH_SIZE` | No | Default 200 |
| `ENGAGEMENT_MAX_PER_DAY` | No | Default 3 |
| `ENGAGEMENT_MIN_HOURS` | No | Default 3 |

### 2.2 GET /notifications/admin/health

```bash
curl -s -X GET "http://localhost:8000/notifications/admin/health" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN"
```

**Expected:** `{"ok": true, "data": {"notifications_pending_count": N, "notifications_failed_last_1h": N, "last_deliver_pending_run_at": "..."}}`

### 2.3 Run prod_notifications_sanity.sh

```bash
# On server (source env for FCM var checks):
source /var/www/sedi/backend/.env 2>/dev/null || true
ADMIN_TOKEN=YOUR_ADMIN_TOKEN BASE_URL=http://localhost:8000 USER_ID=1 bash backend/scripts/prod_notifications_sanity.sh
```

**Expected:** All checks pass; test push enqueued and delivered if FCM enabled.

### 2.4 Run notifications_e2e_smoke.py

```bash
cd backend
ADMIN_TOKEN=YOUR_ADMIN_TOKEN BASE_URL=http://localhost:8000 USER_ID=1 python scripts/notifications_e2e_smoke.py
```

**Expected:** GET push_devices, POST test_push, POST deliver_pending, POST feedback all return 200; `ok: true` in responses.

### 2.5 Expected values

| Metric | Expectation |
|--------|-------------|
| pending_count | Stable (or decreasing after deliver runs) |
| failed_last_1h | Near zero |
| last_deliver_pending_run_at | Updates when deliver_pending runs |

---

## 3. Android Device Verification (Real Phone)

### S1: Token registration after login

| | |
|---|------|
| **Setup** | Fresh install or reinstall APK; complete onboarding; log in. |
| **Steps** | Open app, complete onboarding, reach ChatPage. |
| **Expected** | Backend receives FCM token; `push_devices` has a row for user. |

**Verify:** `curl -s -H "X-Admin-Token: YOUR_ADMIN_TOKEN" "http://localhost:8000/notifications/admin/push_devices?user_id=1" | jq .`

---

### S2: Receive test_push (app backgrounded)

| | |
|---|------|
| **Setup** | App logged in; app moved to background. |
| **Steps** | Run: `curl -s -X POST "http://localhost:8000/notifications/admin/test_push?deliver=true" -H "Content-Type: application/json" -H "X-Admin-Token: YOUR_ADMIN_TOKEN" -d '{"user_id": 1, "channel": "engagement", "title": "Test", "body": "Verify push"}'` |
| **Expected** | System notification appears in tray. |

---

### S3: Tap notification → open_chat feedback

| | |
|---|------|
| **Setup** | Notification visible (from S2). |
| **Steps** | Tap notification body (not action button). |
| **Expected** | App opens to ChatPage; `open_chat` feedback stored. |

**Verify feedback row:**
```bash
# Via API (if feedback endpoint exposes list): N/A
# Via DB:
psql -d sedi_db -c "SELECT id, notification_id, user_id, action, created_at FROM notification_feedback ORDER BY created_at DESC LIMIT 5;"
```

---

### S4: LIKE / DISLIKE → feedback + dismiss

| | |
|---|------|
| **Setup** | Notification visible. |
| **Steps** | Tap LIKE or DISLIKE action button. |
| **Expected** | Feedback stored (like/dislike); notification dismissed. |

**Verify:** Same DB query as S3.

---

### S5: Quiet hours ON → suppressed (except critical health)

| | |
|---|------|
| **Setup** | User has `quiet_hours` enabled (e.g. 22:00–08:00) and `timezone` set. Current time within quiet hours. |
| **Steps** | Trigger morning or engagement (or health normal/high). |
| **Expected** | morning, engagement: no push. Health normal/high: no push. Health critical: push allowed. |

**Setup via chat:** Send `quiet hours 22:00-08:00` and `timezone: Asia/Tehran`. Test during quiet window.

---

### S6: Timezone change impacts morning scheduling

| | |
|---|------|
| **Setup** | User sets timezone via chat: `timezone: Asia/Tehran`. |
| **Steps** | Wait for next morning job (scheduler run at local morning). |
| **Expected** | Morning brief scheduled/triggered at user's local morning (not server time). |

---

### S7: App killed → still receives push; actions work

| | |
|---|------|
| **Setup** | Force-kill app (swipe away). |
| **Steps** | Send test_push with deliver=true. Wait for FCM to deliver. Tap notification. |
| **Expected** | Notification appears; tap opens app; actions (LIKE/DISLIKE/OPEN_CHAT) work. |

---

## 4. Load Sanity (1000 Users Readiness)

### 4.1 Mock load (FCM_DISABLED=true)

```bash
# Set FCM_DISABLED=true on backend; restart.
# Run load script:
ADMIN_TOKEN=YOUR_ADMIN_TOKEN BASE_URL=http://localhost:8000 \
  USER_ID_START=1 USER_COUNT=200 PUSH_PER_USER=2 CONCURRENCY=10 \
  python backend/scripts/notifications_mock_load.py
```

**Acceptance thresholds (mock mode):**

| Metric | Threshold |
|--------|-----------|
| delivered / requested | ≥ 99% |
| avg latency | < 500 ms (for 200 users) |

### 4.2 Production sanity

| Setting | Recommendation |
|---------|----------------|
| deliver_pending batch size | 200 (or 500 for 1000 users) |
| deliver_pending cadence | Every 5–10 minutes |
| engagement limits | ENGAGEMENT_MAX_PER_DAY=3, ENGAGEMENT_MIN_HOURS=3 |

---

## 5. Go/No-Go Criteria

### GO if:

- S1–S5 pass on at least 3 devices
- `failed_last_1h` < 1% of sent in last 24h (or practical threshold, e.g. < 10 failures)
- No token leakage in logs (no raw FCM tokens printed)
- Rollback tested (FCM_DISABLED=true applied and verified)

### NO-GO if:

- open_chat feedback missing in > 5% of tap cases
- Repeated/spam engagement notifications beyond limits
- Health alerts firing without data basis or with unsafe/diagnostic text

---

## 6. Rollback Plan (Copy-Paste)

```bash
# 1. Set env (edit systemd override or .env)
# FCM_DISABLED=true
# ENGAGEMENT_MAX_PER_DAY=0
# DELIVER_BATCH_SIZE=50

sudo nano /etc/systemd/system/sedi-backend.service.d/override.conf
# Add/update:
# Environment="FCM_DISABLED=true"
# Environment="ENGAGEMENT_MAX_PER_DAY=0"
# Environment="DELIVER_BATCH_SIZE=50"

# 2. Restart
sudo systemctl daemon-reload
sudo systemctl restart sedi-backend.service

# 3. Confirm health
curl -s -H "X-Admin-Token: YOUR_ADMIN_TOKEN" http://localhost:8000/notifications/admin/health
```

---

## 7. Ownership & Cadence

| Who | Monitors |
|-----|----------|
| Ops | `failed_last_1h`, `pending_count`, deliver runs |
| Ops | Log grep for [NOTIF] errors |

**Log grep commands:**

```bash
sudo journalctl -u sedi-backend.service -n 500 --no-pager | grep '\[NOTIF\]'
sudo journalctl -u sedi-backend.service -f | grep '\[NOTIF\]'
```

**DB cadence (per NOTIFICATIONS_DB_INDEX_SANITY.md):**

- Weekly: `VACUUM ANALYZE notifications` if table large
- Post-rollout: `EXPLAIN ANALYZE` on delivery query; ensure index usage
- Scale-up: If DELIVER_BATCH_SIZE > 500, verify index usage and DB connections

---

## Related Docs

- `RELEASE_STAGE16_6_NOTIFICATIONS_V1.md` — Feature overview
- `PROD_NOTIFICATIONS_ROLLOUT_CHECKLIST.md` — Rollout, env vars, sanity
- `NOTIFICATIONS_DB_INDEX_SANITY.md` — Index inventory and ops cadence
- `frontend/docs/CI_ANDROID_BUILD_AND_INSTALL.md` — APK download and install
