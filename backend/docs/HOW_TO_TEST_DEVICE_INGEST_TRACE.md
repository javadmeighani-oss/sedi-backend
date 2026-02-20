# How to test device ingest trace_id and diagnostic response

## 1. Ingest with custom trace ID (header echoed in response)

```bash
curl -s -X POST "http://localhost:8000/device/ingest" \
  -H "Content-Type: application/json" \
  -H "X-DEVICE-TOKEN: YOUR_DEVICE_INGEST_TOKEN" \
  -H "X-TRACE-ID: test-trace-001" \
  -d '{"user_id": 1, "event_type": "heart_rate", "payload": {"bpm": 85}}'
```

**Expected:** `200` response; `data.trace_id` equals `"test-trace-001"`; `data` includes `device_event_dedupe_hit`, `decision_outcome`, `actions_created`, `skipped_reason`, `trace_id`.

**Log grep:**
```bash
# All ingest logs for this request should include the same trace id
grep "trace=test-trace-001" <your_log_file>
# Or in stdout:
# [DEVICE_INGEST] CREATED ... trace=test-trace-001
# [DEVICE_INGEST] decision outcome=... trace=test-trace-001
# [D2_GUARD] ... trace=test-trace-001   (if guard evaluated)
# [NOTIF] enqueue ... trace=test-trace-001   (if notification created)
```

## 2. Ingest without X-TRACE-ID (server generates trace_id)

```bash
curl -s -X POST "http://localhost:8000/device/ingest" \
  -H "Content-Type: application/json" \
  -H "X-DEVICE-TOKEN: YOUR_DEVICE_INGEST_TOKEN" \
  -d '{"user_id": 1, "event_type": "heart_rate", "payload": {"bpm": 90}}'
```

**Expected:** `200` response; `data.trace_id` is a non-empty string (uuid4 hex). Same diagnostic fields as above.

**Log grep:**
```bash
# Each request gets a unique trace id in logs
grep "\[DEVICE_INGEST\]" <your_log_file> | tail -5
# Lines should end with trace=<hex string>
```

---

**Note:** Replace `YOUR_DEVICE_INGEST_TOKEN` with the value of `DEVICE_INGEST_TOKEN` in your env (or a registered device token if using DB/hybrid auth). Replace `user_id: 1` with a valid user id in your DB.
