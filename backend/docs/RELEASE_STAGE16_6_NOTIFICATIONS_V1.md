# Release Stage 16.6 – Push Notifications v1

Production-grade push notifications via Firebase Cloud Messaging (FCM) for Android.

## Features

- **Morning Brief**: Scheduled by user timezone (UserMemoryFact key `timezone`; default Asia/Tehran)
- **Engagement Nudge**: Sent if user inactive for 3+ hours; max 3/day per user
- **Health Care Alert**: Entrypoint `enqueue_health_alert()` for vitals/rules/decision engine (wiring only; no vitals rules in this release)
- **Notification actions**: LIKE, DISLIKE, OPEN_CHAT (backend accepts feedback via `/notifications/{id}/feedback`)
- **Multi-language**: Uses existing `resolve_effective_language` and templates (en, fa, ar)
- **Idempotency**: `dedupe_key` and `ttl_seconds` supported
- **Scale readiness**: Indexes, batching, timeouts, safe retries for up to 1000 users

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FCM_PROJECT_ID` | Yes (for production) | Firebase project ID |
| `FCM_SERVICE_ACCOUNT_JSON` | Yes (for production) | Path to service account JSON file, or inline JSON string |
| `FCM_DISABLED` | No | Set to `true`/`1`/`yes` to use dev mock (no-op send; returns success) |
| `ADMIN_TOKEN` | No | If set, admin endpoints require `X-Admin-Token` header |
| `DELIVER_BATCH_SIZE` | No | Max pending notifications per deliver run (default 200). Stage 16.6.2 |
| `FCM_TIMEOUT_SECONDS` | No | Per-request FCM timeout (default 5). Stage 16.6.2 |
| `FCM_MAX_RETRIES` | No | In-process retries per notification on failure (default 2). Stage 16.6.2 |
| `FCM_BACKOFF_SECONDS` | No | Backoff between retries (default 10). Stage 16.6.2 |
| `ENGAGEMENT_MAX_PER_DAY` | No | Max engagement nudges per user per day (default 3). Stage 16.6.2 |
| `ENGAGEMENT_MIN_HOURS` | No | Min hours between engagement nudges (default 3). Stage 16.6.2 |
| `NOTIF_AI_ENHANCE` | No | Enable AI tone enhancement (default false). Stage 16.6.4 |

## API Endpoints

- `POST /notifications/push/register` – Register/upsert FCM token (body: `platform`, `fcm_token`, `device_id?`, `app_version?`, `user_id`)
- `POST /notifications/push/unregister` – Deactivate token (query: `fcm_token`, `user_id`)
- `POST /notifications/{id}/feedback` – Submit action feedback (`action`: like | dislike | open_chat | dismissed)
- `POST /notifications/deliver_pending` – Admin: run delivery outbox (optional `X-Admin-Token` if `ADMIN_TOKEN` set)
- `GET /notifications/admin/health` – Admin: lightweight health (pending_count, failed_last_1h, last_deliver_pending_run_at). Stage 16.6.2

## Data Model

- **push_devices**: `user_id`, `platform`, `fcm_token` (unique), `device_id`, `is_active`, `last_seen_at`
- **notification_feedback**: `notification_id`, `user_id`, `action`, `meta_json`
- **notifications** (additive): `channel`, `priority`, `language`, `actions_json`, `deeplink_url`, `provider`, `provider_message_id`, `status`, `last_error`, `ttl_seconds`

## Migrations

Apply `backend/deployment/migrations/006_stage16_6_push_notifications.sql` (idempotent).

## Dev Mode

Set `FCM_DISABLED=true` to use mock FCM; all sends succeed without calling Firebase.

## Quiet Hours (Stage 16.6.4)

UserMemoryFact key `quiet_hours` (domain=preferences):

```json
{ "start": "22:00", "end": "08:00", "enabled": true }
```

- morning, engagement: suppressed during quiet hours
- health_alert: suppressed only if priority != "critical"
- Timezone: UserMemoryFact key `timezone` (e.g. `{"tz": "Asia/Tehran"}`)

## Example Notifications (fa/en/ar)

**Morning (en):** "Good morning dear 🌅 Try to get more rest tonight. Have a wonderful day."
**Engagement (fa):** "سلام عزیزم، همه چی خوبه؟ 🌿"
**Health alert (en, critical):** "An unusual reading was detected. Open Sedi to review. If urgent, seek professional care."

## Chat Commands (Stage 16.6.5)

Users can set notification preferences via chat text commands. Stored in UserMemoryFact (domain=preferences).

**Set timezone:**
- en: `set timezone Asia/Tehran` / `timezone: Asia/Tehran`
- fa: `تایم زون: Asia/Tehran` / `تایم‌زون: Asia/Tehran`
- ar: `المنطقة الزمنية: Asia/Tehran`

**Set quiet hours:**
- en: `quiet hours 22:00-08:00` / `do not disturb 22:00-08:00`
- fa: `ساعات سکوت 22:00-08:00` / `مزاحم نشو 22:00-08:00`
- ar: `ساعات الهدوء 22:00-08:00`

**Disable quiet hours:**
- en: `disable quiet hours` / `quiet hours off`
- fa: `خاموش کردن ساعات سکوت` / `ساعات سکوت خاموش`
- ar: `إيقاف ساعات الهدوء`

## Release Freeze & Go/No-Go

See `NOTIFICATIONS_V1_FREEZE_GO_NO_GO.md` for the authoritative release freeze checklist, device/server test scenarios, acceptance thresholds, and rollback plan.

## Health Alert Hook

```python
from backend.app.services.notification_engine import enqueue_health_alert

enqueue_health_alert(db, user_id=1, alert_code="high_heart_rate", alert_reason="HR > 100", priority="high")
```

Call from decision engine or vitals rules when conditions are met. No full vitals evaluation is implemented here.
