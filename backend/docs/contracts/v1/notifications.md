# V1 Contract: Notifications

**Base path:** `/notifications`  
**Envelope:** All listed endpoints use `ApiResponse` (`ok`, `data`, `error`). Errors use `ApiError` (`code`, `message`, `details?`).

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /notifications | List notifications (paginated) |
| GET | /notifications/ | Alias for list |
| GET | /notifications/unread | Unread count / list |
| POST | /notifications/{id}/mark-read | Mark as read |
| POST | /notifications/{id}/read | Alias mark-read |
| POST | /notifications/push/register | Register FCM token |
| POST | /notifications/push/unregister | Unregister FCM token |
| POST | /notifications/{id}/feedback | Submit feedback (seen, interact, dismiss, like, dislike) |
| POST | /notifications/deliver_pending | Run delivery job (admin or internal) |
| GET | /notifications/admin/push_devices | Admin: list push devices for user |
| POST | /notifications/admin/test_push | Admin: enqueue test push; optional deliver=true |
| POST | /notifications/admin/notif/send_now | Admin: send now (channel: morning, engagement, health_alert) |
| Others | /notifications/admin/* | templates, feedback_stats, adaptive_state, health, observability, companion_ping |

---

## Headers

| Header | Required | Notes |
|--------|----------|------|
| Content-Type | Yes (POST) | application/json |
| Authorization | For user-scoped list/unread/feedback | Bearer &lt;access_token&gt; |
| X-Admin-Token | For admin/* | Required if ADMIN_TOKEN env is set |

---

## 1. GET /notifications

**Query params:** Optional limit, offset, user_id (or from token).

**Success (200):**
```json
{
  "ok": true,
  "data": {
    "items": [
      {
        "id": 1,
        "user_id": 1,
        "type": "health_alert",
        "title": "High heart rate",
        "body": "Your heart rate was elevated.",
        "is_read": false,
        "is_sent": true,
        "created_at": "2025-02-22T12:00:00",
        "channel": "health_alert",
        "priority": "high"
      }
    ],
    "total": 1
  },
  "error": null
}
```

**Error (200):**
```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Valid token required",
    "details": null
  }
}
```

---

## 2. GET /notifications/unread

**Success (200):** `ApiResponse` with `data` containing unread count and/or list (shape as per implementation).

---

## 3. POST /notifications/{notification_id}/mark-read

**Success (200):**
```json
{
  "ok": true,
  "data": { "read": true },
  "error": null
}
```

---

## 4. POST /notifications/push/register

**Request body (example):**
```json
{
  "user_id": 1,
  "fcm_token": "long-fcm-token-string",
  "platform": "android",
  "device_id": "optional-device-id"
}
```

**Success (200):** `ApiResponse` with `data` indicating registration result.

**Error (200):** Invalid token or user: `{"ok": false, "error": {"code": "USER_NOT_FOUND", "message": "..."}}`.

---

## 5. POST /notifications/{notification_id}/feedback

**Request body (V1 contract):**
```json
{
  "reaction": "seen",
  "timestamp": "2025-02-22T12:00:00Z",
  "action_id": "open_chat",
  "feedback_text": null
}
```
Reaction: `seen` | `interact` | `dismiss` | `like` | `dislike`.

**Success (200):** `ApiResponse` with `ok: true`, `data` with feedback result, `error: null`.

---

## 6. POST /notifications/admin/test_push

**Headers:** `X-Admin-Token: $ADMIN_TOKEN` (if ADMIN_TOKEN set).

**Query params:** `deliver` (optional bool): if true, run deliver_pending after enqueue.

**Request body:**
```json
{
  "user_id": 1,
  "title": "Test",
  "body": "Hello",
  "channel": "engagement",
  "priority": "normal",
  "ttl_seconds": 3600
}
```

**Success (200):**
```json
{
  "ok": true,
  "data": {
    "notification_id": 42,
    "channel": "engagement",
    "delivered": true,
    "sent_count": 1
  },
  "error": null
}
```

**Error (200):**
```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "USER_NOT_FOUND",
    "message": "User not found.",
    "details": null
  }
}
```

**Error (401):** Missing or invalid X-Admin-Token when ADMIN_TOKEN is set.

---

## 7. POST /notifications/deliver_pending

Runs the delivery job. Admin or internal use. Returns `ApiResponse` with `data` containing `sent_count` or similar.

---

## Notes

- **Dedupe:** Notifications use `dedupe_key` for idempotency; admin test_push uses a unique key per request.
- **Admin:** When `ADMIN_TOKEN` is set, all `/notifications/admin/*` require header `X-Admin-Token`.
- All success responses: `ok: true`, `data` set, `error: null`. Business errors: 200 + `ok: false` + `error`.
