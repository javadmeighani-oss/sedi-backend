# Smoke Test: Notification Engine Import

## Quick Import Test

Test that the notification_engine module can be imported without conflicts:

```bash
cd backend
python -c "from app.services import notification_engine; print('✅ Import successful')"
```

## Expected Output

```
✅ Import successful
```

## What This Tests

This smoke test verifies that:
1. The `app/services/notification_engine.py` module can be imported
2. There is no import ambiguity between the module and package
3. The module correctly imports from `notification_runtime` package

## Troubleshooting

If you see an import error:
- Check that `app/services/notification_runtime/` exists
- Verify `app/services/notification_engine.py` imports from `notification_runtime`
- Ensure no `app/services/notification_engine/` folder exists (it should be renamed to `notification_runtime/`)

---

# Release B2: Notification API Examples

## List Unread Notifications

```bash
# Get unread notifications for user
curl -X GET "http://localhost:8000/notifications/unread?user_id=1&limit=20"

# With type filter
curl -X GET "http://localhost:8000/notifications/unread?user_id=1&type=morning_brief&limit=20"
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "notifications": [
      {
        "id": 1,
        "user_id": 1,
        "type": "morning_brief",
        "title": "صبح بخیر",
        "body": "صبح بخیر عزیزم...",
        "priority": "normal",
        "is_read": false,
        "is_sent": false,
        "scheduled_for": null,
        "created_at": "2026-02-02T10:00:00"
      }
    ],
    "count": 1
  }
}
```

## Mark Notification as Read

```bash
curl -X POST "http://localhost:8000/notifications/1/mark-read?user_id=1"
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "ok": true,
    "notification_id": 1,
    "is_read": true
  }
}
```

## Submit Feedback

```bash
# Standardized feedback (Release B2)
curl -X POST "http://localhost:8000/notifications/1/feedback?user_id=1" \
  -H "Content-Type: application/json" \
  -d '{
    "feedback": "positive",
    "reason": "Helpful notification",
    "action": null
  }'

# Negative feedback with action
curl -X POST "http://localhost:8000/notifications/1/feedback?user_id=1" \
  -H "Content-Type: application/json" \
  -d '{
    "feedback": "negative",
    "reason": "Too early",
    "action": "too_early"
  }'
```

**Response:**
```json
{
  "ok": true,
  "data": {
    "notification_id": 1,
    "feedback": "positive",
    "message": "Feedback recorded successfully"
  }
}
```

## Notes

- All endpoints require `user_id` as a query parameter
- `mark-read` and `feedback` endpoints validate ownership (notification must belong to the user)
- Feedback is stored in UserMemoryFact for morning_brief notifications
- Rate limits are enforced via dedupe_key (logged when suppressed)

---

# Release C1: Device Ingestion Examples

## Ingest Heart Rate Event

```bash
# Set device token (must match DEVICE_INGEST_TOKEN env var)
export DEVICE_TOKEN="your-secret-token"

# Ingest heart rate event
curl -X POST "http://localhost:8000/device/ingest" \
  -H "Content-Type: application/json" \
  -H "X-DEVICE-TOKEN: $DEVICE_TOKEN" \
  -d '{
    "user_id": 1,
    "device_id": "Sedi001",
    "event_type": "heart_rate",
    "payload": {
      "bpm": 82,
      "quality": "good"
    },
    "recorded_at": "2026-02-02T10:30:00Z"
  }'
```

**Response (Success):**
```json
{
  "ok": true,
  "data": {
    "event_id": 123,
    "dedupe_key": "heart_rate:1:2026-02-02T10:30"
  }
}
```

**Response (Duplicate):**
```json
{
  "ok": true,
  "data": {
    "event_id": null,
    "dedupe_key": "heart_rate:1:2026-02-02T10:30",
    "message": "Event already exists (duplicate)"
  }
}
```

**Response (Invalid Token):**
```json
{
  "detail": "Invalid device token"
}
```

## Verify Device Events in Database

```sql
-- Check device_events table
SELECT id, user_id, device_id, event_type, payload_json, recorded_at, received_at, dedupe_key
FROM device_events
ORDER BY received_at DESC
LIMIT 10;

-- Verify scale indexes exist (Release C1.1)
-- Expected:
-- - ix_device_events_user_time (user_id, received_at DESC)
-- - ix_device_events_user_dedupe (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'device_events'
  AND indexname IN ('ix_device_events_user_time', 'ix_device_events_user_dedupe')
ORDER BY indexname;

-- Check memory facts created from device events
SELECT id, user_id, domain, key, value_json, source, last_seen_at
FROM user_memory_facts
WHERE source = 'device' AND domain = 'vitals'
ORDER BY last_seen_at DESC
LIMIT 10;

-- Verify no duplicates by dedupe_key
SELECT event_type, dedupe_key, COUNT(*) as count
FROM device_events
WHERE received_at > NOW() - INTERVAL '24 hours'
GROUP BY event_type, dedupe_key
HAVING COUNT(*) > 1;
```

## Notes

- Requires `X-DEVICE-TOKEN` header matching `DEVICE_INGEST_TOKEN` environment variable
- Events are deduplicated using **5-minute time buckets**:
  - Dedupe key format: `{event_type}:{user_id}:{YYYY-MM-DDTHH}:{bucket_min:02d}`
  - Minutes are rounded **down** to nearest 5-minute bucket (0, 5, 10, 15, ..., 55)
  - Examples:
    - `06:44` and `06:40` → same bucket `06:40`
    - `06:45` → different bucket `06:45`
    - `06:49` → same bucket as `06:45` (`06:45`)
  - Uses `recorded_at` from device if present, else `received_at` (server timestamp)
- Heart rate events are automatically mapped to `vitals.heart_rate_bpm` memory fact
- Health alerts are triggered rule-based (no AI) when heart rate is outside safe range (60-100 bpm by default)
- Alerts respect existing notification dedupe/rate-limit policies

## Verify 5-Minute Dedupe Buckets

```sql
-- Check dedupe keys and their time buckets
SELECT 
    id,
    user_id,
    event_type,
    recorded_at,
    received_at,
    dedupe_key,
    EXTRACT(MINUTE FROM recorded_at) as recorded_minute,
    EXTRACT(MINUTE FROM received_at) as received_minute
FROM device_events
WHERE user_id = 1
ORDER BY received_at DESC
LIMIT 20;

-- Verify events in same 5-minute bucket share same dedupe_key
SELECT 
    dedupe_key,
    COUNT(*) as event_count,
    MIN(recorded_at) as first_recorded,
    MAX(recorded_at) as last_recorded,
    ARRAY_AGG(id ORDER BY received_at) as event_ids
FROM device_events
WHERE user_id = 1 
  AND event_type = 'heart_rate'
  AND received_at > NOW() - INTERVAL '1 hour'
GROUP BY dedupe_key
HAVING COUNT(*) > 1
ORDER BY first_recorded DESC;

-- Expected: Events within same 5-minute window should have same dedupe_key
-- Example: Events at 06:40, 06:41, 06:44 should all have dedupe_key ending in "06:40"
```

---

# Release C2: Device Identity v1 (Per-device tokens)

## Register Device (returns token once)

```bash
curl -X POST "http://localhost:8000/devices/register?user_id=1" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"Sedi001","device_type":"heart_rate"}'
```

**Response (token shown once):**
```json
{
  "ok": true,
  "data": {
    "device_id": "Sedi001",
    "token": "...."
  }
}
```

## Ingest using per-device token (DB auth)

```bash
export DEVICE_TOKEN="(token from register)"

curl -X POST "http://localhost:8000/device/ingest" \
  -H "Content-Type: application/json" \
  -H "X-DEVICE-TOKEN: $DEVICE_TOKEN" \
  -d '{
    "user_id": 1,
    "device_id": "Sedi001",
    "event_type": "heart_rate",
    "payload": { "bpm": 82 }
  }'
```

## Revoke device

```bash
curl -X POST "http://localhost:8000/devices/Sedi001/revoke?user_id=1"
```

## Rotate token (returns new token once)

```bash
curl -X POST "http://localhost:8000/devices/Sedi001/rotate-token?user_id=1"
```

## List devices

```bash
curl -X GET "http://localhost:8000/devices?user_id=1"
```

## DB verification (devices)

```sql
SELECT device_id, device_type, status, last_seen_at, created_at, revoked_at
FROM devices
ORDER BY id DESC
LIMIT 20;
```

## Auth Modes

- `DEVICE_AUTH_MODE=hybrid` (default): try DB per-device token first, fallback to legacy `DEVICE_INGEST_TOKEN` if set
- `DEVICE_AUTH_MODE=db_only`: only DB per-device token (requires `device_id` in ingest request)
- `DEVICE_AUTH_MODE=legacy_only`: only shared token `DEVICE_INGEST_TOKEN` (C1 behavior)

# Release B3: DB Verification (Production)

## Verify no legacy notification types exist

```sql
SELECT DISTINCT type
FROM notifications
ORDER BY type;
```

## Verify `dedupe_key` is non-null for recent rows

```sql
SELECT
  COUNT(*) FILTER (WHERE dedupe_key IS NULL) AS nulls,
  COUNT(*) AS total
FROM notifications
WHERE created_at > NOW() - INTERVAL '6 hours';
```

## Detect duplicates by `dedupe_key` (last 24h)

```sql
SELECT type, dedupe_key, COUNT(*)
FROM notifications
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY type, dedupe_key
HAVING COUNT(*) > 1;
```
