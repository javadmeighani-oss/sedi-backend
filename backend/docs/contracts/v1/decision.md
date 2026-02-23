# V1 Contract: Decision

**Base path:** `/decision`  
**Envelope:** This endpoint does **not** use `ApiResponse`. It returns `{ "ok": true, "decision": { ... } }` (no `data`/`error` wrapper).

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /decision/evaluate | Evaluate event → decision (none / notify / store_only) |

---

## Headers

| Header | Required | Notes |
|--------|----------|------|
| Content-Type | Yes | application/json |

---

## POST /decision/evaluate

**Request body:** `{ "event": { ... } }` — event is a JSON object. No fixed schema; rules read fields they expect (see Notes).

**Success (200):**
```json
{
  "ok": true,
  "decision": {
    "decision": "notify",
    "reason": "HR_HIGH_REST",
    "severity": "medium",
    "source_event_id": null,
    "meta": { "bpm": 140, "context": "rest" }
  }
}
```

**Decision object fields (V1):**

| Field | Type | Notes |
|-------|------|-------|
| decision | string | Outcome: `none` \| `notify` \| `store_only` |
| reason | string | Rule identifier or `"no_rule_matched"` |
| severity | string | Optional. e.g. `low`, `medium`, `high` |
| source_event_id | number \| null | Optional. Set when rule has event id. |
| meta | object | Optional. Rule-specific key-value data. |

**Naming (V1):** What older docs may call "outcome" is **decision** in the API. What may be called "metadata" is **meta**. The field **action** is **not** returned by this endpoint in V1.

**Error (4xx/5xx):** Standard FastAPI (e.g. validation error). No envelope; body format is FastAPI default.

---

## Example: HR_HIGH_REST (working in V1)

The only rule wired to this endpoint in V1 is **HR_HIGH_REST**. It expects the event to have **top-level** `event_type`, `bpm`, and `context` (not nested under `payload`).

**Request:**
```json
{
  "event": {
    "user_id": 1,
    "device_id": "Sedi001",
    "event_type": "heart_rate",
    "bpm": 140,
    "context": "rest",
    "recorded_at": "2025-02-22T12:00:00Z"
  }
}
```

**Response (200):** `decision.decision` = `"notify"`, `decision.reason` = `"HR_HIGH_REST"`.

**Note:** Events that send heart rate only inside `payload` (e.g. `payload: { "bpm": 140 }`) are **not** matched by this endpoint in V1; the rule reads top-level `bpm` and `context`. High-severity rules for blood_pressure, glucose, and temperature are part of the **ingest pipeline** (`/device/ingest`), not POST `/decision/evaluate`.

---

## Notes

- **Scope (V1):** POST `/decision/evaluate` uses `decide_from_event()` with `default_rules()` only. Callers should not expect `notify` for blood_pressure, glucose, or temperature from this endpoint; those rules run in the ingest path.
- **Idempotency:** Evaluate is stateless; same event yields same decision. Dedupe/rate limiting is applied at ingest layer, not here.
- **Usage:** Typically called internally or by tests; device events are processed via `/device/ingest`, which may call the decision engine internally.
