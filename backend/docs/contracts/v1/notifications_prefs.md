# V1 Contract: Notification Preferences

**Base path:** `/notifications`  
**Envelope:** ApiResponse — `{ "ok": true, "data": <NotificationPrefsRead>, "error": null }` on success.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /notifications/prefs | Get notification preferences for a user |
| PUT | /notifications/prefs | Create or update preferences (partial update) |

---

## Query parameters

| Parameter | Required | Notes |
|-----------|----------|-------|
| user_id | Yes | User ID (GET and PUT) |

---

## GET /notifications/prefs

**Success (200):**
```json
{
  "ok": true,
  "data": {
    "user_id": 1,
    "channels": {
      "companion": true,
      "health_alert": true,
      "reminder_medication": true,
      "reminder_appointment": true,
      "reminder_system": true
    },
    "quiet_hours": {
      "enabled": false,
      "start": null,
      "end": null
    },
    "engagement_level": 1
  },
  "error": null
}
```

**Defaults (when no row exists):** All channels enabled, `quiet_hours.enabled` false, `quiet_hours.start`/`end` null, `engagement_level` 1. Fail-open: no row returns defaults, not an error.

**Error (200 with ok false):** e.g. `USER_NOT_FOUND` when user_id does not exist.

---

## PUT /notifications/prefs

**Request body (partial update):**
```json
{
  "channels": {
    "companion": false,
    "health_alert": true,
    "reminder_medication": true,
    "reminder_appointment": true,
    "reminder_system": false
  },
  "quiet_hours": {
    "enabled": true,
    "start": "22:00",
    "end": "07:00"
  },
  "engagement_level": 2
}
```

All top-level keys are optional. Omitted keys leave existing (or default) values unchanged.

**Validation:**
- `quiet_hours.start` and `quiet_hours.end`: when provided, must match `HH:MM` (`^\d{2}:\d{2}$`).
- If `quiet_hours.enabled` is true, both `start` and `end` are required in the request.
- `engagement_level`: 0 (low), 1 (normal), 2 (high).

**Success (200):** Same envelope as GET; `data` is the current prefs after the update.

**Error (422):** Validation error (e.g. invalid HH:MM or missing start/end when enabled).  
**Error (200 with ok false):** e.g. `USER_NOT_FOUND`.

---

## Semantics

- **Defaults:** No DB row ⇒ GET returns default values (all channels on, quiet hours off, engagement 1).
- **Partial update:** PUT only updates fields present in the body; others keep current or default.
- **Idempotency:** PUT with same body returns same data; GET after PUT returns persisted values.
