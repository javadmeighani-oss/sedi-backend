# POST /device/ingest — Device → Decision → Guard Flow Map

Structured map of the exact flow. No code or behavior changes.

---

## 1. Endpoint

| Item | Value |
|------|--------|
| **Path** | `POST /device/ingest` |
| **File** | `backend/app/routers/device.py` |
| **Router prefix** | `/device` (mounted in `backend/app/main.py`: `app.include_router(device.router, prefix="/device", ...)`) |
| **Function** | `ingest_device_event` |
| **Request schema** | `DeviceIngestRequest` (`backend/app/schemas/device.py`: `user_id`, `device_id?`, `event_type`, `payload`, `recorded_at?`) |
| **Response schema** | `DeviceIngestResponse` (`backend/app/schemas/device.py`: `ok`, `data?`, `error?`) |
| **Auth** | `Depends(get_device_token)` → `authorize_device_or_legacy` (`backend/app/core/device_auth.py`) |

---

## 2. Call chain

| Step | File | Function |
|------|------|----------|
| 1. Router | `backend/app/routers/device.py` | `ingest_device_event` |
| 2. Service | `backend/app/services/device_ingestion.py` | `ingest_event` |
| 3. Validation/normalize | `backend/app/services/vitals/vital_registry.py` | `validate_event` |
| 4. Decision entrypoint | `backend/app/decision_engine/service.py` | `evaluate_event` → `evaluate_high_rules` |
| 5. Rules | `backend/app/decision_engine/rules.py` | `evaluate_high_rules` |
| 6. Action execution | `backend/app/services/device_ingestion.py` | `_execute_d1_actions` (guard → dedupe check → persist → record guard) |

---

## 3. Dedupe

| Purpose | File | Function | Format |
|---------|------|----------|--------|
| **Device event dedupe_key** | `backend/app/services/vitals/dedupe.py` | `build_dedupe_key` (called via `vital_registry.build_dedupe_key`) | `{event_type}:{user_id}:{YYYY-MM-DDTHH:MM}` (5‑min bucket) |
| **Where computed** | `backend/app/services/device_ingestion.py` | `ingest_event` (after `validate_event`, before DB lookup) | Uses `vital_registry.build_dedupe_key(user_id, event_type, recorded_at, received_at)` |
| **Device event insert** | `backend/app/services/device_ingestion.py` | `ingest_event` | `db.add(DeviceEvent(..., dedupe_key=dedupe_key)); db.commit(); db.refresh(event)` |
| **Notification alert dedupe_key** | `backend/app/services/device_ingestion.py` | `_execute_d1_actions` | `alert:{event_type}:{user_id}:{minute_bucket}:{rule_id}` (bucket via `minute_bucket(event_dto.recorded_at)` → `YYYYMMDDHHMM`) |

---

## 4. Decision rules

| Item | Location |
|------|----------|
| **Entrypoint** | `backend/app/decision_engine/service.py`: `evaluate_event(event: EventDto)` → `evaluate_high_rules(event)` |
| **Rule implementation** | `backend/app/decision_engine/rules.py`: `evaluate_high_rules` (single function, no registry dispatch) |
| **Rule modules (logical)** | Same file; one branch per event_type. Rule IDs: |
| | `heart_rate` → `heart_rate_high` (bpm ≥ 130), `heart_rate_low` (bpm ≤ 42) |
| | `blood_pressure` → `blood_pressure_high` (sys ≥ 160 or dia ≥ 110) |
| | `glucose` → `glucose_high` (≥ 240), `glucose_low` (≤ 60) |
| | `temperature` → `temperature_high` (≥ 39.0 °C) |
| **Action type** | `CreateHealthAlertAction` (`backend/app/decision_engine/models.py`); executed in `_execute_d1_actions`. |

---

## 5. Guard

| Item | Value |
|------|--------|
| **File** | `backend/app/services/notifications/behavior_guard_d2.py` |
| **Function** | `evaluate_health_alert_guard` (allow/block); `record_health_alert_sent` (update cooldown after send) |
| **Inputs** | `db`, `user_id`, `channel` (e.g. `"health_alert"`), `rule_id`, `severity`, `event_type`, `now_utc` |
| **Behavior** | Quiet hours: block if `in_quiet` and `severity != "high"`; high overrides quiet hours. Cooldown: block if `cooldown_until > now`. |
| **Quiet hours / timezone** | `backend/app/services/notification_runtime/quiet_hours.py`: `is_within_quiet_hours(db, user_id, channel, priority)`. Reads `UserMemoryFact`: `preferences` / `quiet_hours` (JSON: `start`, `end`, `enabled`) and `preferences` / `timezone` (JSON: `tz`). Default tz `Asia/Tehran`. |
| **Cooldown state** | Table `notification_guard_state`: `user_id`, `channel`, `rule_id`, `last_sent_at`, `cooldown_until`, `updated_at`. Read/updated with `FOR UPDATE` in guard and `record_health_alert_sent`. Env: `HEALTH_ALERT_COOLDOWN_SECONDS` (default 900). |

---

## 6. Notification persistence

| Step | File | Function |
|------|------|----------|
| **Builder + persist** | `backend/app/services/notification_engine.py` | `persist_health_alert_d1` → builds `NotificationPayload` → `NotificationBuilder(db).persist(payload, check_dedupe=False)` |
| **Persist implementation** | `backend/app/services/notification_engine.py` | `NotificationBuilder.persist` (creates `Notification` row, sets `dedupe_key=payload.dedupe_key`, `db.add` + `db.commit`) |
| **Where notifications.dedupe_key is set** | Caller passes it: `_execute_d1_actions` builds `dedupe_key = f"alert:{event_type}:{user_id}:{bucket}:{rule_id}"` and passes to `persist_health_alert_d1(..., dedupe_key=dedupe_key)`. `NotificationBuilder.persist` assigns `payload.dedupe_key` to `Notification.dedupe_key` (line ~526). |

---

## 7. DB tables touched

| Table | Operation |
|-------|-----------|
| `users` | Read (user existence, auth when using DB device) |
| `devices` | Read (optional; when `authorize_device_or_legacy` uses DB auth) |
| `device_events` | Read (dedupe by dedupe_key), Insert (new event) |
| `user_memory_facts` | Read (quiet_hours, timezone in `is_within_quiet_hours`); Upsert (memory mapping in `ingest_event` via `MemoryRepository.upsert_fact`) |
| `notifications` | Read (alert dedupe in `_execute_d1_actions`); Insert (via `NotificationBuilder.persist` in `persist_health_alert_d1`) |
| `notification_guard_state` | Read with `FOR UPDATE` (guard); Insert or Update (in `record_health_alert_sent`) |

---

## 8. Logs currently emitted

| Tag / prefix | File(s) | When |
|--------------|---------|------|
| `[DEVICE_INGEST]` | `device_ingestion.py` | DUPLICATE (existing dedupe_key), CREATED (event_id), Mapped to memory, Failed to map to memory, Failed to evaluate/execute, Failed to execute action |
| `[D2_GUARD]` | `behavior_guard_d2.py` | One line per guard decision: `user_id`, `channel`, `rule_id`, `severity`, `allow`, `reason`, `cooldown_until`, `in_quiet` |
| `[NOTIF]` | `notification_engine.py` | On enqueue: `channel`, `user_id`, `dedupe` (in `NotificationBuilder.persist`) |
| `[Notification]` | `notification_engine.py` | Rate limit/dedupe suppressed (not used for D1 health_alert path; D1 uses `check_dedupe=False`) |

---

*Report generated from codebase trace. No refactors or behavior changes.*
