# V1 Contract: Decision

**Base path:** `/decision`  
**Envelope:** This endpoint does **not** use `ApiResponse`. It returns `{ "ok": true, "decision": { ... } }` (no `data`/`error` wrapper).

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /decision/evaluate | Evaluate device event → decision (none / notify / store_only) |

---

## Headers

| Header | Required | Notes |
|--------|----------|------|
| Content-Type | Yes | application/json |

---

## POST /decision/evaluate

**Request body:**
```json
{
  "event": {
    "user_id": 1,
    "device_id": "Sedi001",
    "event_type": "heart_rate",
    "payload": { "bpm": 140 },
    "recorded_at": "2025-02-22T12:00:00Z"
  }
}
```

**Success (200):**
```json
{
  "ok": true,
  "decision": {
    "outcome": "notify",
    "action": "CreateHealthAlertAction",
    "reason": "HIGH_HR",
    "metadata": {}
  }
}
```

**Outcome values:** `none` | `notify` | `store_only` (or equivalent per implementation).

**Error (4xx/5xx):** Standard FastAPI (e.g. validation error). No envelope; body format is FastAPI default.

---

## Notes

- **Idempotency:** Evaluate is stateless; same event yields same decision. Dedupe/rate limiting is applied at ingest layer, not here.
- **Usage:** Typically called internally or by tests; device events are processed via `/device/ingest`, which may call the decision engine internally.
