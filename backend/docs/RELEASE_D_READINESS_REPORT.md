# Release D Readiness Report

**Scope:** Backend codebase analysis only. No code was modified.

---

## Q1) DB and ORM

**Direct answer:** PostgreSQL is used (default URL); SQLAlchemy is the ORM. Alembic is **not** present; migrations are hand-written SQL in `deployment/migrations/` and applied manually (no `alembic.ini`, no `alembic upgrade` in CI/startup).

**Evidence:**
- **DB URL / engine:** `backend/app/database.py`
  - `DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://sedi_user:sedi_password@localhost:5432/sedi_db")`
  - `engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)`
  - `SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)`
  - `get_db()` yields a session and closes it
- **ORM:** SQLAlchemy; `Base = declarative_base()`; models in `app/models.py` (User, Notification, DeviceEvent, Device, UserMemoryFact, etc.)
- **Requirements:** `backend/requirements.txt` includes `sqlalchemy`, `psycopg2-binary` (no alembic)
- **Migrations:** `backend/deployment/migrations/` contains SQL files (e.g. `001_add_dedupe_key_to_notifications.sql`, `002_add_device_events.sql`, … `005_harden_devices_defaults.sql`); `README.md` describes manual apply via `psql -d sedi_db -f <file>`
- **Alembic:** No `alembic.ini` or `alembic/` in backend; `HOW_TO_FIX_SCHEMA.md` mentions `alembic revision` / `alembic upgrade head` as a possible approach but it is not set up in this repo

**Notes/Risks:**
- Schema changes require manual SQL and manual apply on server; no versioned migration history or rollback story.
- Default `DATABASE_URL` is a local Postgres; production must set `DATABASE_URL` in env.

---

## Q2) Notification “sending” behavior

**Direct answer:** Notifications are **only stored in the DB** (created via `DecisionEngine` → `NotificationBuilder.persist()`). There is **no push/email/SMS delivery**; `is_sent` exists on the model but is always set to `False` and no worker sends them. Scheduling uses **APScheduler** in-process (sync job execution); no Celery/RQ/separate worker.

**Evidence:**
- **Creation path:** `app/services/notification_engine.py` — `DecisionEngine`, `NotificationBuilder.persist()`; notifications inserted with `is_sent=False` (e.g. lines 300, 360)
- **Model:** `app/models.py` — `Notification` has `is_sent = Column(Boolean, default=False, nullable=False)`; no FCM/push/email fields
- **Router:** `app/routers/notifications.py` — GET/list, unread, mark_read, feedback; comments (lines 371–386) describe a **future** scheduler flow: query `is_sent=False`, “Send them (via push notification, SMS, etc.)”, mark sent — **not implemented**
- **Scheduler:** `app/core/scheduler.py` — `BackgroundScheduler` (APScheduler); jobs `run_inactivity_notifications()`, morning check, etc. call `DecisionEngine` to **create** notifications (persist to DB only)
- **Requirements:** `apscheduler` present; no `celery`, `rq`, or push/email SDKs

**Notes/Risks:**
- Clients (e.g. app) must poll `/notifications` or `/notifications/unread`; no server-initiated push.
- “Sending” in Release D would require a new component (worker or cron) that reads unsent rows and calls a delivery channel (FCM, etc.) and sets `is_sent=True`.

---

## Q3) Device event schema

**Direct answer:** Canonical schema is **Pydantic request + vital-registry validation**; persistence is **SQLAlchemy `DeviceEvent`** in table `device_events`. Required: `user_id`, `event_type`, non-empty `payload`; `device_id` and `recorded_at` optional. Per-type payload rules (e.g. `bpm` for heart_rate) are enforced in the vital registry.

**Evidence:**
- **Request schema:** `app/schemas/device.py` — `DeviceIngestRequest`: `user_id` (int), `device_id` (Optional[str]), `event_type` Literal["heart_rate","blood_pressure","glucose","temperature"], `payload` (Dict, must not be empty), `recorded_at` (Optional[datetime])
- **Validation:** `app/services/vitals/vital_registry.py` — `validate_event(event_type, payload)` raises `VitalValidationError`; per type: heart_rate → `bpm` (int), optional `quality`; blood_pressure → `sys`, `dia` (int), optional `pulse`; glucose → `mg_dl` or `mmol_l`; temperature → `c` or `f`
- **Persistence:** `app/models.py` — `DeviceEvent`: `user_id`, `device_id`, `event_type`, `payload_json` (Text), `recorded_at`, `received_at`, `dedupe_key`, `embedding_id`
- **Ingest flow:** `app/routers/device.py` → `ingest_event()` in `app/services/device_ingestion.py`; `validate_event()` then insert; dedupe by `dedupe_key` (from `app/services/vitals/dedupe.py` / `vital_registry.build_dedupe_key`)

**Notes/Risks:**
- `payload` is stored as JSON string; type-specific required fields are enforced only at ingest via the registry, not by the DB schema.

---

## Q4) Memory creation status

**Direct answer:** Memory **is** created and persisted from device events. Path: **ingest_event** → **map_to_memory_facts** (vital_registry) → **MemoryRepository.upsert_fact** (UserMemoryFact). **MemoryContext** is built from **UserMemoryFact** (lifestyle domain) and used in notification flows (morning brief, connection_ping, lifestyle evaluation); it is **not** built from raw device events directly.

**Evidence:**
- **Event → memory:** `app/services/device_ingestion.py` (lines 145–167): after creating `DeviceEvent`, calls `map_to_memory_facts(...)` then `repo.upsert_fact(...)` for each update; source `"device"`
- **Mapping:** `app/services/vitals/vital_registry.py` — `map_to_memory_facts()` returns `List[MemoryUpdate]` (domain, key, value, confidence, source); e.g. heart_rate → lifestyle facts
- **Repository:** `app/services/memory/memory_repository.py` — `MemoryRepository.upsert_fact()`; persists to `UserMemoryFact` (table `user_memory_facts`); contract in `memory_contract.py`
- **MemoryContext:** `app/services/memory/memory_context.py` — `build_memory_context(db, user_id)` reads `UserMemoryFact` by domain `"lifestyle"` and fills `MemoryContext` (sleep_duration_hours, hydration_ml, activity_level, etc.)
- **Usage:** `app/services/notification_engine.py` — e.g. `create_morning_brief`, `create_connection_ping`, `evaluate_lifestyle_context` call `build_memory_context(self.db, user_id)` and pass it to fallback/notification builders; `app/core/scheduler.py` uses `build_memory_context` in scheduled jobs; `app/routers/lifestyle.py` exposes GET that returns `build_memory_context(db, user_id).to_dict()`

**Notes/Risks:**
- Memory is **fact-based** (key/value per domain); there is no free-form “memory narrative” or vector/RAG persistence for device events in this path.
- `embedding_id` on `UserMemoryFact` and `DeviceEvent` is RAG-ready but not populated in the current flow.

---

## Q5) AI usage surface

**Direct answer:** AI is used for **notification copy** (optional, env-gated) and for **chat/onboarding** (GPT). Notification AI is **optional** and **feature-flagged** via `NOTIF_AI_ENHANCE`; on AI failure the notification path **falls back to non-AI payload** (unchanged). Chat depends on `OPENAI_API_KEY`; errors are caught and surfaced to the client.

**Evidence:**
- **Notification copy:** `app/services/notification_runtime/ai_enhancer.py` — `NOTIF_AI_ENHANCE = os.getenv("NOTIF_AI_ENHANCE", "false").lower() in ("true", "1", "yes")`; `enhance_with_ai(payload)` calls `app.core.ai_text_engine.generate_notification_text()`; on `ImportError` or any `Exception` returns payload unchanged and logs
- **AI text engine:** `app/core/ai_text_engine.py` — `OpenAI(api_key=os.getenv("OPENAI_API_KEY"))`; `generate_notification_text(language, notification_type, user_name, ...)`; raises if `OPENAI_API_KEY` not set at import
- **Chat/GPT:** `app/core/conversation/prompts.py` — `OpenAI`, `OPENAI_API_KEY`; `app/routers/interact.py` catches errors and checks for "openai" in error string/type for user-facing messages
- **Other:** `app/routers/health.py`, `app/routers/ai_core.py` use `generate_notification_text` for specific endpoints

**Notes/Risks:**
- If `OPENAI_API_KEY` is missing, `ai_text_engine` import can raise; notification path is protected by try/except and returns unenhanced payload.
- No other feature flags found for AI (e.g. chat is always-on when key is present).

---

## Q6) E2E “final acceptance” scenario candidates

**Direct answer:**

| Scenario | Implemented | Missing / notes |
|----------|-------------|------------------|
| **A) Abnormal heart rate** | Yes (rule-based). Ingest → `rule_alerts.maybe_create_alert` → `DecisionEngine.create_health_alert` → notification stored (e.g. high_heart_rate / low_heart_rate). | No actual delivery (push/SMS); no end-to-end test that asserts notification row + content. |
| **B) Device disconnected** | Partially. No explicit “device disconnected” event type. `connection_ping` is for **chat inactivity** (scheduler), not device last-seen. Device has `last_seen_at` (heartbeat) but no job that creates a “device disconnected” notification from it. | Need: scheduled job or rule that compares `last_seen_at` to now and creates a notification when device is absent X minutes. |
| **C) Medication reminder loop** | Partially. `create_medication_reminder()` and `create_condition_reminder()` exist in `DecisionEngine`; scheduler has morning/inactivity checks. No automated loop that “every 8h create medication reminder” from a user’s medication list. | Need: scheduled job that loads user medications and calls `create_medication_reminder` on a schedule; and/or API that triggers reminder creation. |

**Evidence:**
- **A) Abnormal HR:** `app/services/vitals/rule_alerts.py` — `_hr_alert()` (bpm &lt; 40/50 or &gt; 160/120) → `engine.create_health_alert(...)`; `app/services/device_ingestion.py` calls `maybe_create_alert()` after persisting event
- **B) Device:** `app/models.py` — `Device.last_seen_at`; `app/routers/device.py` heartbeat updates it; `app/core/scheduler.py` — no query on Device or last_seen_at for “disconnected”
- **C) Medication:** `app/services/notification_engine.py` — `create_medication_reminder(medication_name, user_id, ...)`, `create_condition_reminder(...)`; `TimingRules.get_reminder_interval("medication")` → 8h; no scheduler job that iterates medications and creates reminders
- **Decision engine (Release D):** `app/decision_engine/rules.py` — `evaluate_rules()`, `default_rules()` with HR_HIGH_REST; not wired into ingest pipeline (ingest uses `rule_alerts` + `DecisionEngine` directly)

**Recommendation for single “final acceptance” scenario:**  
**A) Abnormal heart rate** — End-to-end path exists: ingest event → validate → persist event → map to memory → rule alert → health_alert notification in DB. Gaps are only: (1) no delivery step, (2) no formal E2E test that asserts notification created with expected body/priority. So the best candidate is **abnormal heart rate** with an E2E test that: ingest HR outside range → query notifications (or dedicated endpoint) → assert one health_alert with correct alert_code/body.

---

## Next steps (top 5 to start Release D confidently)

1. **Notification delivery** — Implement a small “send” path: e.g. query notifications with `is_sent=False` (and optional `scheduled_for <= now`), call a delivery channel (e.g. FCM), then set `is_sent=True`. Without this, Release D “notifications” remain DB-only.
2. **Alembic (or equivalent)** — Introduce versioned migrations (e.g. Alembic) and run `upgrade` in deploy/CI so schema changes are repeatable and rollbackable; reduce reliance on hand-run SQL.
3. **E2E test: abnormal heart rate** — Add one E2E test: ingest heart_rate payload outside safe range → assert one new `health_alert` notification row (and optionally body/priority) so the event → decision → notification path is regression-safe.
4. **Device disconnected** — Add a scheduled job (or extend scheduler) that checks `Device.last_seen_at` (and optionally heartbeat endpoint) and creates a “device disconnected” notification when absent beyond a threshold; define event type or notification type and dedupe.
5. **Medication reminder loop** — Add a scheduled job (or API) that, from stored user medications and interval (e.g. 8h), calls `create_medication_reminder` at the right times so medication reminders are created automatically, not only when explicitly triggered by an endpoint.
