# V1 Contract: Device

**Base path:** `/device`  
**Envelope:** All endpoints except `/ingest` use `ApiResponse` (`ok`, `data`, `error`). `/ingest` uses `DeviceIngestResponse` (same shape: `ok`, `data`, `error` with error as object `{ code, message }`).

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /device/pending-commands | Get pending voice commands for gadget (user_id query) |
| POST | /device/heartbeat | Device heartbeat (device_id, user_id, battery, status, etc.) |
| POST | /device/acknowledge | Acknowledge command execution (sound_id, status) |
| POST | /device/ingest | Ingest device event (vitals); requires X-DEVICE-TOKEN |

---

## Headers

| Header | Required | Notes |
|--------|----------|------|
| Content-Type | Yes (POST) | application/json |
| X-DEVICE-TOKEN | For /ingest | Per-device or legacy token (DEVICE_AUTH_MODE) |
| X-TRACE-ID | Optional | Request tracing for ingest |

---

## 1. GET /device/pending-commands

**Query params:** `user_id` (required).

**Success (200):**
```json
{
  "ok": true,
  "data": {
    "commands": [
      {
        "sound_id": "alert_default",
        "text": "هشدار سلامت",
        "volume": 90,
        "repeat": 2,
        "language": "fa",
        "priority": 3
      }
    ]
  },
  "error": null
}
```

**Empty:** `{"ok": true, "data": {"commands": []}, "error": null}`.

---

## 2. POST /device/heartbeat

**Request body:**
```json
{
  "device_id": "Sedi001",
  "user_id": 1,
  "battery": 92,
  "temperature": 41.3,
  "status": "active"
}
```

**Success (200):**
```json
{
  "ok": true,
  "data": {
    "message": "Heartbeat received successfully."
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
    "code": "INVALID_PAYLOAD",
    "message": "Missing required fields: user_id and device_id are required."
  }
}
```
Codes: `INVALID_PAYLOAD`, `USER_NOT_FOUND`, `DEVICE_NOT_FOUND`.

---

## 3. POST /device/acknowledge

**Request body:**
```json
{
  "user_id": 1,
  "sound_id": "alert_temp",
  "status": "played"
}
```

**Success (200):**
```json
{
  "ok": true,
  "data": { "acknowledged": true },
  "error": null
}
```

**Error (200):** `{"ok": false, "error": {"code": "USER_NOT_FOUND", "message": "User not found."}}`.

---

## 4. POST /device/ingest

**Headers:** `X-DEVICE-TOKEN: <token>` (required). Optional: `X-TRACE-ID`.

**Request body:**
```json
{
  "user_id": 1,
  "device_id": "Sedi001",
  "event_type": "heart_rate",
  "payload": {
    "bpm": 82,
    "quality": "good"
  },
  "recorded_at": "2026-02-02T10:30:00Z"
}
```

**Event types:** `heart_rate` | `blood_pressure` | `glucose` | `temperature`.

**Success (200) – new event:**
```json
{
  "ok": true,
  "data": {
    "event_id": 123,
    "dedupe_key": "heart_rate:1:2026-02-02T10:30",
    "device_event_dedupe_hit": false,
    "decision_outcome": "actions_executed",
    "actions_created": 1,
    "skipped_reason": null,
    "trace_id": "a1b2c3d4e5f6"
  },
  "error": null
}
```

**Success (200) – duplicate:**
```json
{
  "ok": true,
  "data": {
    "event_id": null,
    "dedupe_key": "heart_rate:1:2026-02-02T10:30",
    "message": "Event already exists (duplicate)",
    "device_event_dedupe_hit": true
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
    "message": "User not found"
  }
}
```
Codes: `USER_NOT_FOUND`, `INVALID_PAYLOAD`, `VALIDATION_ERROR`.

**Error (422):** Validation (e.g. vital schema). Body is FastAPI validation format, not envelope.

**Error (429):** Rate limit. Body may be non-envelope.

**Error (500):** `{"ok": false, "code": "INTERNAL_ERROR", "message": "Failed to ingest event"}` (ingest may return this shape).

---

## Notes

- **Dedupe:** Ingest uses internal dedupe (e.g. event_type + user_id + time window). Duplicate returns 200 with `event_id: null` and message.
- **Auth:** Ingest supports DEVICE_AUTH_MODE: legacy_only, db_only, hybrid. X-DEVICE-TOKEN is always required.
- Pending-commands marks returned alerts as read when fetched.
