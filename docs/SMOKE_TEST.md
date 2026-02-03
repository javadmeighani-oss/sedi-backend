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
