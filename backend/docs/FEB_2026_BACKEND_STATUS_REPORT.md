# Sedi Backend Freeze Status Report — February 2026

**Scope:** Architecture, Releases C/D, notifications, device ingestion, test infra, migrations, CI.  
**Baseline:** Repository contents as of report generation. No speculation.

---

## A) Current Backend Architecture

### Folder Map & Responsibilities

| Path | Responsibility |
|------|----------------|
| `backend/app/main.py` | FastAPI app, CORS, router registration, scheduler start |
| `backend/app/routers/` | HTTP endpoints: auth, auth_otp, interact, health, lifestyle, notifications, ai_core, conditions, device, devices, decision, memory, user_knowledge, knowledge, knowledge_admin, system |
| `backend/app/core/` | `scheduler` (APScheduler jobs), `security`, `device_auth`, `conversation` (brain, prompts, memory) |
| `backend/app/services/` | `notification_engine`, `device_ingestion`, `vitals` (rule_alerts, vital_registry, dedupe), `memory`, `notifications` (delivery_service, send_guard_v1, adaptive_policy_v1), `notification_runtime` (renderer, i18n_resolver, quiet_hours, templates_v1, user_context_adapter), `medical`, `rag`, `local_rag` |
| `backend/app/decision_engine/` | Rules evaluation, health alerts, notification creation |
| `backend/app/models.py` | SQLAlchemy models (User, Notification, Device, DeviceEvent, etc.) |
| `backend/app/schemas/` | Pydantic request/response schemas |
| `backend/app/database.py` | Engine, SessionLocal, get_db, DATABASE_URL from env |
| `backend/alembic/` | Versioned migrations (001_baseline_v1 → 007) |
| `backend/tests/` | conftest, test_db_config, acceptance (Release D), unit tests |
| `backend/docs/` | Runbooks, TEST_DB_AUTH_FIX, PROD_NOTIFICATIONS_*, MIGRATIONS |

### Key Routers

| Router | Prefix | Main endpoints |
|--------|--------|----------------|
| system | / | GET / (root health) |
| device | /device | POST /ingest, POST /heartbeat, GET /pending-commands |
| notifications | /notifications | GET /, /unread, POST /{id}/feedback, /admin/* |
| interact | /interact | Chat, onboarding |
| decision | (root) | Decision-related |
| memory | /memory | Memory CRUD |
| user_knowledge | /user | Profile baseline, facts |

---

## B) Release C Checklist Status

| Item | Status | Key Location |
|------|--------|--------------|
| Device ingest endpoint | ✅ | `backend/app/routers/device.py` @router.post("/ingest") |
| VitalValidationError → 422 | ✅ | Lines 255–257 |
| DeviceRateLimitExceeded → 429 | ✅ | Lines 259–261 |
| HTTPException re-raised (auth/validation) | ✅ | Lines 264–266 |
| Generic Exception → 500 JSONResponse | ✅ | Lines 268–273 |
| Auth modes (legacy_only, db_only, hybrid) | ✅ | `backend/app/core/device_auth.py` |
| X-DEVICE-TOKEN header | ✅ | `get_device_token` Depends |

**Run script:** `backend/scripts/server_patch_ingest_and_run_release_c.sh`  
**Report template:** `backend/docs/RELEASE_C_PATCH_AND_TEST_REPORT.md`

---

## C) Release D Checklist Status

| Item | Status | Key Rule/Guard |
|------|--------|----------------|
| Abnormal heart rate → health_alert | ✅ | `rule_alerts.maybe_create_alert` → `DecisionEngine.create_health_alert` |
| Device disconnected → notification | ✅ | `run_device_disconnected_check` (scheduler), `DEVICE_DISCONNECTED_THRESHOLD_MIN` |
| Medication reminder → notification | ✅ | `run_medication_reminders` (scheduler), `create_medication_reminder` (8h dedupe) |
| ENV/APP_ENV != production | ✅ | `test_release_d.py` module-level guard |
| Test DB not production-like | ✅ | `_is_production_db_url` blocks sedi_db, prod, production |
| Scheduler uses test DB in tests | ✅ | `patch_scheduler_db` fixture monkeypatches `get_db` |
| DEVICE_AUTH_MODE=legacy_only in CI | ✅ | `.github/workflows/ci-backend-tests.yml` env |

**Acceptance tests:** `backend/tests/acceptance/test_release_d.py`  
- `test_release_d_abnormal_hr_creates_health_alert`  
- `test_release_d_device_disconnected_creates_notification`  
- `test_release_d_medication_reminder_creates_notification`

---

## D) Notification System Capabilities

| Capability | Implementation | Location |
|------------|----------------|----------|
| i18n | Multi-language templates (en, fa, ar); prefix fallback | `notification_runtime/i18n_resolver.py`, `language_resolver.py` |
| Renderer | Channel-based rendering, template.texts, personalization | `notification_runtime/renderer.py` |
| Context | User context (name, goals, lifestyle, language) | `notification_runtime/user_context_adapter.py` |
| Dedup | dedupe_key, send_guard_v1 `_dedupe_exists` | `send_guard_v1.py`, `notification_engine.py` |
| Caps | Companion cap, adaptive policy (paused_until) | `adaptive_policy_v1.py`, `send_guard_v1.py` |
| Quiet hours | UserMemoryFact "quiet_hours" + timezone; morning/engagement suppress | `notification_runtime/quiet_hours.py` |
| Logging | `[NOTIF]` prefix | delivery_service, notification_engine |
| Feedback | POST /{id}/feedback, NotificationFeedback, morning_brief adjustment | `routers/notifications.py` |
| Delivery | FCM adapter or LoggingOnlyAdapter; run_deliver_pending job | `notifications/delivery_service.py`, `core/scheduler.py` |

---

## E) Database & Migrations

| Item | Status | Notes |
|------|--------|-------|
| Alembic | In use | `backend/alembic/`, `alembic.ini` |
| Baseline | 001_baseline_v1_schema | Users first (no FK), then FK-dependent tables |
| Revision chain | 001 → 002 → 003 → 004 → 005 → 006 → 007 | 002 phone OTP, 003 meds condition_id, 004–007 KC/behavior |
| TEST_DATABASE_URL | Alembic env.py prefers over DATABASE_URL | `alembic/env.py` line 23 |
| Production | DATABASE_URL from env; manual `alembic upgrade head` | `backend/docs/MIGRATIONS.md` |
| Legacy SQL | `deployment/migrations/` still exists | Used for pgvector (008) and other standalone SQL |

**Production safety:** Migrations run manually; `reset_db_and_migrate.sh` requires `CONFIRM_RESET=YES`.

---

## F) Test Infrastructure

| Component | Strategy | Location |
|-----------|----------|----------|
| DB URL | Single source: `get_test_database_url()` | `backend/tests/test_db_config.py` |
| Engine | Session-scoped, created once | `conftest.py` _TEST_ENGINE |
| Schema | `Base.metadata.create_all` at session start, `drop_all` at end | `_create_drop_all` fixture |
| Isolation | Per-test transaction + rollback | `db` fixture: `connection.begin()` → `transaction.rollback()` |
| API client | `client` fixture overrides `get_db` with test `db` | Same transaction as test |
| Scheduler | Disabled when `PYTEST_CURRENT_TEST` set | `main.py` _should_start_scheduler |
| Acceptance DB | `patch_scheduler_db` provides same session to scheduler | `test_release_d.py` |

**Canonical test DB name:** `sedi_test` (CI and fallback).

---

## G) Blocking Issues & Next Steps

### 1. DB Auth (Resolved)

- **Issue:** Peer auth failure when using Unix socket (`host=/var/run/postgresql`).
- **Fix:** Tests use TCP (127.0.0.1:5432) via `TEST_DATABASE_URL` or fallback; never `DATABASE_URL`.
- **Doc:** `backend/docs/TEST_DB_AUTH_FIX.md`
- **Next step:** Ensure `sedi_test_user` (or CI `sedi_user`) exists and pg_hba has `host ... md5` for TCP.

### 2. FCM Real Device

- **Issue:** End-to-end push requires FCM creds and registered device token.
- **Env:** `FCM_PROJECT_ID`, `FCM_SERVICE_ACCOUNT_JSON`, `FCM_DISABLED=false`, `ADMIN_TOKEN`.
- **Next steps:**
  1. Configure FCM per `backend/docs/PROD_NOTIFICATIONS_ROLLOUT_CHECKLIST.md`
  2. Run sanity script: `ADMIN_TOKEN=... bash backend/scripts/prod_notifications_sanity.sh`
  3. Register device via app; confirm row in `push_devices`
  4. Use `POST /notifications/admin/test_push?deliver=true` to verify delivery

---

## H) Freeze Criteria Checklist

| Criterion | Status |
|-----------|--------|
| Release C device ingest (422/429/500/HTTPException) | ✅ Implemented |
| Release D acceptance tests (HR, device disconnected, medication) | ✅ In CI |
| CI backend tests green | ⬜ Run `pytest backend/tests/` (requires Postgres) |
| Test DB auth via TCP (no peer) | ✅ test_db_config + TEST_DB_AUTH_FIX |
| Canonical test DB name `sedi_test` | ✅ CI + fallback |
| Alembic migrations apply cleanly | ⬜ Verify `alembic upgrade head` on target DB |
| Notification delivery (FCM or db_only) | ✅ Implemented; FCM needs prod config |
| Scheduler jobs registered | ✅ morning, inactivity, engagement, deliver_pending, device_disconnected, medication_reminders |
| No production DB in tests | ✅ TEST_DATABASE_URL only; DATABASE_URL never used |
| Docs: TEST_DB_AUTH_FIX, runbooks | ✅ Present |

---

## Files of Record (Top 15)

| Path | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app, routers, scheduler start |
| `backend/app/database.py` | Engine, SessionLocal, get_db, DATABASE_URL |
| `backend/app/models.py` | SQLAlchemy models |
| `backend/app/routers/device.py` | Device ingest, heartbeat, pending-commands |
| `backend/app/routers/notifications.py` | List, feedback, admin endpoints |
| `backend/app/services/notification_engine.py` | DecisionEngine, NotificationBuilder, template rendering |
| `backend/app/services/device_ingestion.py` | Ingest flow, validation, memory mapping |
| `backend/app/services/notifications/delivery_service.py` | FCM/LoggingOnly adapter, deliver_pending |
| `backend/app/services/notifications/send_guard_v1.py` | Send guard (pause, quiet hours, dedup, cap) |
| `backend/app/core/scheduler.py` | APScheduler jobs (morning, inactivity, engagement, deliver, device_disconnected, medication) |
| `backend/app/core/device_auth.py` | Device token auth (legacy/db/hybrid) |
| `backend/tests/conftest.py` | Test engine, db fixture, client fixture, transaction rollback |
| `backend/tests/test_db_config.py` | Single source for TEST_DATABASE_URL |
| `backend/alembic/versions/001_baseline_v1_schema.py` | Baseline schema |
| `.github/workflows/ci-backend-tests.yml` | Release D acceptance CI |

---

## Inconsistencies & Risks

### 1. Test DB User Difference (Documented)

- **CI:** Uses `sedi_user` / `sedi_pass` (Postgres service env).
- **Fallback:** Uses `sedi_test_user` / `StrongTestPass123`.
- **DB name:** Unified to `sedi_test` everywhere.
- **Risk:** Low. CI sets `TEST_DATABASE_URL`; local uses fallback. Both use TCP.
- **Recommendation:** Document in TEST_DB_AUTH_FIX or TESTING.md that CI and local may use different users; DB name `sedi_test` is canonical.

### 2. RELEASE_D_READINESS_REPORT Outdated

- States "Alembic is **not** present"; repo now has Alembic.
- **Recommendation:** Update or archive that report.

### 3. Dual Migration Paths

- Alembic in `backend/alembic/versions/` and legacy SQL in `deployment/migrations/`.
- **Recommendation:** Prefer Alembic for schema; use deployment/migrations only for standalone SQL (e.g. pgvector) until migrated into Alembic.

---

## Related Docs

- `backend/docs/TEST_DB_AUTH_FIX.md` — Test DB auth fix
- `backend/docs/TESTING.md` — How to run Release D acceptance
- `backend/docs/PROD_NOTIFICATIONS_ROLLOUT_CHECKLIST.md` — FCM rollout
- `backend/docs/PROD_NOTIFICATIONS_EXECUTION_RUNBOOK.md` — Copy-paste runbook
- `backend/docs/MIGRATIONS.md` — Alembic usage
- `backend/docs/RELEASE_C_PATCH_AND_TEST_REPORT.md` — Release C report template
