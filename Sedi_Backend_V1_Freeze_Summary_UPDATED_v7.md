# Sedi Platform -- Backend V1 Freeze Summary

Generated at: 2026-02-22T06:56:18.215673 UTC

------------------------------------------------------------------------

## 1️⃣ Server & Runtime Status

-   Service: `sedi-backend.service` (systemd)
-   Working Directory: `/var/www/sedi/backend`
-   Runtime: `uvicorn` inside `.venv`
-   Environment File: `/etc/sedi/sedi-backend.env`
-   Scheduler: APScheduler active at startup
-   Admin authentication: `ADMIN_TOKEN` enabled
-   FCM mode: `FCM_DISABLED=true` (Mock / db_only mode)

------------------------------------------------------------------------

## 2️⃣ Notification System Status (Backend)

### Architecture

-   Outbox pattern via `notifications` table
-   `DeliveryService.deliver_pending()` processes queued items
-   Runtime lock prevents overlap (scheduler + HTTP)
-   Pluggable adapters:
    -   `FCMAdapter`
    -   `LoggingOnlyAdapter` (db_only mode)

### Provider Persistence Fix (Resolved)

Problem: - `provider` field was NULL in DB for sent notifications.

Fix Applied: - `provider` always set from `adapter.channel` in success
path. - `db.flush()` added before `commit()`. - `db.refresh()` commented
(optional).

Validation: - Test via `/notifications/admin/test_push?deliver=true` -
Confirmed: - `status = sent` - `is_sent = true` - `provider = db_only`

Status: ✅ FIXED & VERIFIED

------------------------------------------------------------------------

## 3️⃣ Required Backend Freeze Areas Before Frontend Redesign

### A) API Contract Freeze

-   Finalize payload & response structures for:
    -   `/auth/*`
    -   `/interact/*`
    -   `/notifications/*`
    -   `/device/*`
    -   `/knowledge/*`
-   Provide example curl contracts
-   Define API versioning strategy

------------------------------------------------------------------------

### B) Notification Stability

-   Add regression test for provider persistence
-   Finalize state machine: `queued → sent/failed`
-   Lock feedback & unread behavior
-   Prepare operational runbook

------------------------------------------------------------------------

### C) Device & Ingestion

-   Finalize ingest contract (payload & dedupe rules)
-   Ensure idempotency
-   Define error codes clearly

------------------------------------------------------------------------

### D) Knowledge Capture & Onboarding

-   Freeze fatigue policy
-   Freeze next_question contract
-   Lock answer/apply state transitions
-   Finalize text/language behavior

------------------------------------------------------------------------

### E) Decision Engine

-   Define which outputs reach frontend
-   Add acceptance tests for key scenarios:
    -   Heart rate
    -   Blood pressure
    -   Glucose
    -   Temperature

------------------------------------------------------------------------

### F) Operational Readiness

-   Standardized logs (auth, notifications, ingest, KC)
-   Health endpoints
-   Server runbook documentation

------------------------------------------------------------------------

## 4️⃣ Recommended Execution Order

1.  API Contract Freeze
2.  Notification Freeze + Tests
3.  Device/Ingestion Contract
4.  Knowledge Capture Freeze
5.  Decision Engine Acceptance Tests
6.  Start Frontend Redesign

------------------------------------------------------------------------

## Current Position Summary

Backend core architecture is stable. Notification system persistence
issue resolved. System operational in mock push mode. Ready for
structured freeze process before frontend redesign.
------------------------------------------------------------------------

## 5️⃣ API Contract Freeze — Completed (V1)

**Status:** ✅ DONE (Docs + OpenAPI + Contract Tests)

### What was implemented
- Added **V1 envelope schemas** for documented OpenAPI consistency:
  - `backend/app/schemas/api_envelope.py` → `ApiResponse` + `ApiError`
  - Exported as `ApiResponseV1`, `ApiError` from `backend/app/schemas/__init__.py`
- Updated router `response_model` to formalize the V1 envelope in OpenAPI (runtime payload unchanged):
  - `backend/app/routers/auth_otp.py`
  - `backend/app/routers/auth.py`
  - `backend/app/routers/notifications.py`
  - `backend/app/routers/device.py` (non-ingest endpoints)
  - `backend/app/routers/knowledge.py`
- Added **V1 contract docs** (curl + request/response examples):
  - `backend/docs/contracts/v1/auth.md`
  - `backend/docs/contracts/v1/interact.md`
  - `backend/docs/contracts/v1/notifications.md`
  - `backend/docs/contracts/v1/device.md`
  - `backend/docs/contracts/v1/knowledge.md`
  - `backend/docs/contracts/v1/decision.md`
  - `backend/docs/contracts/v1/README.md`

### Contract tests added
- `backend/tests/contracts/test_v1_openapi_contracts.py`
  - Validates presence of V1 paths and envelope schemas
  - Validates `POST /device/ingest` uses **raw `DeviceIngestResponse`** for 200
- `backend/tests/contracts/test_v1_example_payloads.py`
  - Validates example payloads from docs against Pydantic models
  - Includes `DeviceIngestResponse` success + error examples

### Important V1 note (by design)
- Most V1 endpoints use **ApiResponse** envelope (`ok/data/error`).
- `POST /device/ingest` returns **raw `DeviceIngestResponse`** (still has `ok/data/error`, but is not the shared `ApiResponse` schema in OpenAPI).

### Validation on server
- Contract suite:
  - `PYTHONPATH=/var/www/sedi/backend python -m pytest backend/tests/contracts/ -q`
  - Result: **26 passed** ✅
- Full suite:
  - `PYTHONPATH=/var/www/sedi/backend python -m pytest backend/tests -q`
  - Result: **315 passed, 2 skipped** ✅

------------------------------------------------------------------------

## 6️⃣ Freeze Test Fixes Applied (Pre-Freeze Stabilization)

**Goal:** bring test suite to green without changing runtime behavior.

### A) Push register token validation (tests/docs alignment)
- Backend rejects placeholder/short FCM tokens; tests were using short tokens → 422.
- Tests updated to use a realistic token (≥80 chars, no placeholder words).
- Docs updated accordingly in `contracts/v1/notifications.md`.

### B) Decision engine EventDto backward compatibility (tests)
- `EventDto.received_at` is required in runtime ingest path, but unit tests omitted it.
- Made `received_at` default to `datetime.utcnow()` via `Field(default_factory=...)` for test backward-compatibility.

### C) Health alert code consistency
- `CreateHealthAlertAction.alert_code` was empty in some high-rule actions.
- Set `alert_code=<rule_id>` for all high severity rules (`heart_rate_high`, `heart_rate_low`, `blood_pressure_high`, `glucose_high`, `glucose_low`, `temperature_high`).
- Adjusted decision engine test expectation to `alert_code == "heart_rate_high"` and `priority == "high"`.

------------------------------------------------------------------------

## 7️⃣ Versioning / Traceability

- **Git tag:** `v1.0-api-freeze`
- **Commit (tag target):** `6313482` (docs(backend): finalize /device/ingest V1 contract - device.md, README note, contract tests)
- **Freeze manifest:** `backend/docs/contracts/v1/FREEZE_MANIFEST.md`
  - Declares scope + validation commands + rules for future breaking changes.

Last updated: 2026-02-22T11:33:15Z

------------------------------------------------------------------------

## 8️⃣ Notification Freeze — Provider/Failure Safety + Server Sanity + Data Cleanup (V1)

**Status:** ✅ DONE (Regression tests + server verification + DB consistency)

### What changed (code)
1) **New regression tests** to prevent `provider` from staying empty and to harden failure handling:
- `backend/tests/acceptance/test_notifications_provider_persistence.py`
  - `test_logging_only_adapter_sets_provider_db_only_and_sent`
  - `test_success_path_sets_provider_from_adapter_channel`
  - `test_failure_path_persists_provider_and_sets_status_failed`

2) **DeliveryService failure hardening** (minimal, no structural refactor):
- File: `backend/app/services/notifications/delivery_service.py`
  - Cache `nid` / `uid` **once per notification** before retry loop (safe logging).
  - **Do not `db.rollback()`** on `adapter.send()` exceptions (adapter errors are not DB errors; rollback was expiring/detaching ORM instances and breaking retries + tests).
  - Ensure failure-finalization persists `provider` (uses `adapter.channel` fallback).

### Server verification (Hetzner)
**A) Acceptance tests (server)**
- `python -m pytest -q backend/tests/acceptance/test_notifications_provider_persistence.py`
- Result: **3 passed** ✅

**B) Endpoints involved**
- `POST /notifications/admin/test_push` (requires JSON body)
- `POST /notifications/deliver_pending?limit=...` (**requires X-Admin-Token**)

**C) End-to-end sanity (FCM_DISABLED=true → db_only)**
1) Create queued notification:
- `POST /notifications/admin/test_push` body: `{"user_id":1,"channel":"engagement"}`
- Example created: `notification_id=25`

2) Deliver:
- `POST /notifications/deliver_pending?limit=10` with `X-Admin-Token`
- Result: `sent_count=1`

3) DB verify (notifications row id=25):
- `status='sent'`, `provider='db_only'`, `sent_at IS NOT NULL` ✅

### DB cleanup (one-time)
Goal: remove legacy rows where `status in ('sent','failed')` but `provider` was empty (pre-fix data).

- Backfill sent rows (legacy engagement):
  - ids: `22, 23` → `provider='db_only'`
- Backfill failed rows (legacy user_id=2):
  - ids: `1,3,5,7,9,15,21` → `provider='fcm'`

**QC result:**
- `sent_missing_provider = 0`
- `failed_missing_provider = 0`

### Push devices note (explains NO_TOKENS)
- Table schema uses `fcm_token` (not `token`).
- On this server snapshot, user_id=1 had 2 push_devices but both:
  - `is_active = false`
  - placeholder/short `fcm_token` values (len 25–30)
- Therefore admin `send_now` returned `NO_TOKENS` and did **not** create a notifications row (expected).

------------------------------------------------------------------------

## 9️⃣ Release C (Device Platform) — db_only Operational Freeze + Deploy Local Mode (V1)

**Status:** ✅ DONE (Server runtime verified + end-to-end ingest verified + freeze tag created)

### What was verified on server (Hetzner / systemd)
- Confirmed environment source:
  - `EnvironmentFile=/etc/sedi/sedi-backend.env` (systemd unit + override)
- Prior runtime states (historical):
  - `legacy_only` → then `hybrid`
- Final enforced production mode:
  - `/etc/sedi/sedi-backend.env`: `DEVICE_AUTH_MODE=db_only` ✅
  - `/proc/<PID>/environ`: `DEVICE_AUTH_MODE=db_only` ✅

### Why DB token could not be retrieved from DB
- `devices` table stores only a hash:
  - column: `token_hash` (no plaintext token stored)
- Therefore testing requires issuing a token via `/devices/register`.

### End-to-end verification (db_only)
1) **Register token (query param required)**
- `POST /devices/register?user_id=1`
- Body: `{"device_id":"Sedi001","device_type":"heart_rate"}`
- Response includes `data.token` (example token issued): `rrYvQub3iN8qyNWtr3ZA6jD7knz0yUXdMuh3TnYqkqc`

2) **Ingest with DB token (must succeed)**
- `POST /device/ingest`
- Header: `X-DEVICE-TOKEN: <db_token>`
- Result: `ok=true` (example: `event_id=24`, `device_event_dedupe_hit=false`, `decision_outcome="no_rule"`)

3) **Legacy/invalid token must fail**
- Header: `X-DEVICE-TOKEN: this_is_not_a_valid_db_token`
- Result: `detail="Invalid device token"` ✅

### Deployment tooling changes (repo, Cursor-applied)
Goal: enforce production `db_only` and allow running deploy on the target server without SSH/scp prompts.

1) Enforce `DEVICE_AUTH_MODE=db_only` at deploy time (without overwriting other secrets)
- Files:
  - `backend/deployment/deploy.sh`
  - `deployment/deploy.sh`
- Behavior:
  - Ensures `/etc/sedi` exists
  - Replaces/creates/appends **only** `DEVICE_AUTH_MODE=db_only` in `/etc/sedi/sedi-backend.env`
  - Logs: `[DEPLOY] Enforced DEVICE_AUTH_MODE=db_only`

2) Make deploy scripts safe to run **on the target server** (local mode)
- Added `DEPLOY_LOCAL=1` option (and auto-detect `ON_TARGET_SERVER`)
- Local mode:
  - No `ssh-copy-id`, no `scp`, no `ssh`
  - Uses `sudo cp deployment/sedi-backend.service /etc/systemd/system/sedi-backend.service`
  - Runs daemon-reload/enable/restart locally
  - Prints local tips (`sudo journalctl ...`, `sudo systemctl restart ...`)

3) SSH-key step guard (for laptop/CI vs server)
- Skips `ssh-copy-id` when:
  - `DEPLOY_SKIP_SSH=1` OR `ON_TARGET_SERVER=1`

### Server execution used for finalization
- `DEPLOY_LOCAL=1 DEPLOY_SKIP_SSH=1 bash backend/deployment/deploy.sh`
- Service restarted successfully (new PID observed).

### Freeze marker
- **Git tag:** `release-c-device-freeze` ✅
- Tag pushed to origin successfully.

Last updated: 2026-02-22T14:55:00Z



------------------------------------------------------------------------

## 10️⃣ Release D3 / Stage 4 — Knowledge Capture (KC) Freeze Validation + Server Policy Pinning (V1)

**Status:** ✅ DONE (Server policy pinned + smoke flow verified + acceptance tests green)

### A) Server KC policy pinned (systemd env)

Goal: make KC behavior deterministic for V1 and align with frontend redesign assumptions.

Changes applied on server:
- File: `/etc/sedi/sedi-backend.env`
- Added:
  - `APP_TIMEZONE=Europe/Berlin`
  - `KC_DAILY_CAP=3`
  - `KC_COOLDOWN_MINUTES=480`
  - `KC_BURST_GUARD_MINUTES=10`
  - `KC_MAX_CONSECUTIVE_REJECTS=2`
  - `KC_REJECT_COOLDOWN_MINUTES=1440`

Verification:
- Restarted `sedi-backend.service`, confirmed env present in `/proc/<PID>/environ`:
  - `APP_TIMEZONE=Europe/Berlin`
  - `KC_*` variables present

### B) KC OpenAPI sanity

- Verified `/openapi.json` served correctly (HTTP 200) and extracted KC routes:
  - `/knowledge/extract_from_message`
  - `/knowledge/next_question`
  - `/knowledge/apply_answer`
  - `/knowledge/admin/*` (candidates + facts)

### C) KC smoke flow (profile + confirm_candidate)

1) **next_question (profile)**
- `GET /knowledge/next_question?user_id=1` returned:
  - `question_id=kc_q_birth_year_v1`
  - `field_key=birth_year`
  - `policy.daily_cap=3` and `next_eligible_at` consistent with `KC_BURST_GUARD_MINUTES=10`

2) **apply_answer (profile) — regression discovered and verified fixed in repo**
- Initial call used JSON with `answer:"1990"` (no `value`) and resulted in:
  - `applied=profile` response but `birth_year` remained NULL in `user_profile_core`
- Root cause:
  - Router `/knowledge/apply_answer` used `payload.value` for profile/fact and only used `payload.answer` for `confirm_candidate`
- Fix behavior (confirmed in current HEAD):
  - When `value` is missing/blank, router falls back to `answer` for profile/fact as well.
- Post-fix DB validation:
  - `user_profile_core.birth_year` set to `1990` for `user_id=1`

3) **confirm_candidate**
- Created candidate via admin endpoint and confirmed with:
  - `POST /knowledge/apply_answer` with `question_type=confirm_candidate`, `answer="بله"`
- DB validation:
  - `kc_fact_candidates.id=<candidate_id>` status became `accepted`
  - `kc_user_facts.id=<fact_id>` inserted with `fact_type=sex`, `value_json="مرد"`, `verified_by=user`

### D) Acceptance tests added/validated (KC Freeze guardrails)

Purpose: prevent regressions in confirm flow and profile answer/value handling.

- `backend/tests/acceptance/test_kc_confirm_flow.py`
  - Added:
    - `test_apply_answer_with_answer_no_rejects_candidate` (answer="نه" → rejected)
    - `test_apply_answer_with_answer_later_skips_candidate` (answer="بعدا" → skipped, candidate stays pending)
- `backend/tests/acceptance/test_kc_apply_answer_profile_answer_fallback.py` (new)
  - Regression: profile apply_answer must accept `answer` when `value` missing
  - Validates DB: `user_profile_core.birth_year == 1990`

Server run:
- `PYTHONPATH=/var/www/sedi/backend .venv/bin/python -m pytest -q \
  backend/tests/acceptance/test_kc_confirm_flow.py \
  backend/tests/acceptance/test_kc_apply_answer_profile_answer_fallback.py`
- Result: **7 passed** ✅

Notes:
- The code fix + tests were already present in repo HEAD (no additional git diff after validation).
- Pydantic deprecation warnings exist (Config class); not a V1 blocker.

Last updated: 2026-02-22 (Server session)
------------------------------------------------------------------------

## 11️⃣ Decision Engine — Contract Alignment + Backward Compatibility (V1)

**Status:** ✅ DONE (Code + Docs + Acceptance tests green)

### What changed (code)
- File: `backend/app/routers/decision.py`
- Added `_normalize_event_for_rules(event)`:
  - Creates a shallow copy of `event` (does not mutate request body).
  - If `payload` is a dict, lifts `payload.bpm` → top-level `bpm` and `payload.context` → top-level `context` **only if** those keys are missing at top-level.
  - Safe for missing/non-dict payload.
- `POST /decision/evaluate` now calls:
  - `decide_from_event(_normalize_event_for_rules(req.event))`

### Behavior (V1)
- Backward compatible: existing callers using top-level `bpm/context` unchanged.
- Now supports contract-style events that put `bpm/context` under `payload`:
  - HR_HIGH_REST can match both shapes.
- Response envelope/fields unchanged: returns `{"ok": true, "decision": {...}}` (no ApiResponse wrapper).

### Tests
- Acceptance suite:
  - `backend/tests/acceptance/test_decision_evaluate_v1.py`
  - Added: `test_evaluate_heart_rate_high_payload_bpm_context`
- Server run:
  - `PYTHONPATH=/var/www/sedi/backend python -m pytest backend/tests/acceptance/test_decision_evaluate_v1.py -q` → **10 passed** ✅
  - `PYTHONPATH=/var/www/sedi/backend python -m pytest backend/tests/acceptance/ -q` → **33 passed** ✅

### Docs
- Updated contract: `backend/docs/contracts/v1/decision.md`
  - Reflects actual response fields (`decision`, `meta`, `severity`, etc.) + clarified scope.
  - Note: payload-style HR is now supported in V1 due to normalization.

Last updated: 2026-02-23

------------------------------------------------------------------------

## 12️⃣ Ops Runbook — Added (V1)

**Status:** ✅ DONE (Docs-only)

- New file: `backend/docs/ops/runbook_v1.md`
- Includes:
  - Quick status: `systemctl status`, `MainPID`, read env from `/proc/$PID/environ` with secret masking.
  - Start/stop/restart + confirm port 8000 + health checks.
  - DB checks: `alembic current/heads` using runtime `DATABASE_URL`.
  - `/health` vs `/healthz` meaning and expected behavior.
  - Scheduler/notifications log interpretation (`deliver_pending`).
  - Log commands + common issues + security notes.
  - Daily checklist + pre-release checklist.

Last updated: 2026-02-23

------------------------------------------------------------------------

## 13️⃣ Notifications Preferences API (V1)

**Status:** ✅ DONE (Migration + API + Docs + Acceptance tests green)

### Migration
- New Alembic revision: `011_add_notification_prefs`
  - Revises: `010_add_notification_guard_state`
  - Table: `notification_prefs`
  - Columns:
    - `user_id` (PK, FK → `users.id` ON DELETE CASCADE)
    - `companion_enabled`
    - `health_alert_enabled`
    - `reminder_medication_enabled`
    - `reminder_appointment_enabled`
    - `reminder_system_enabled`
    - `quiet_hours_enabled`
    - `quiet_start` (HH:MM)
    - `quiet_end` (HH:MM)
    - `engagement_level` (0/1/2)
    - `updated_at`

### Files
- New:
  - `backend/app/schemas/notification_prefs.py`
  - `backend/app/services/notifications/prefs_service.py`
  - `backend/tests/acceptance/test_notifications_prefs_v1.py`
  - `backend/docs/contracts/v1/notifications_prefs.md`
  - `backend/alembic/versions/011_add_notification_prefs.py`
- Modified:
  - `backend/app/models.py` (added `NotificationPrefs`)
  - `backend/app/routers/notifications.py` (added endpoints)

### Endpoints
- `GET /notifications/prefs?user_id=<id>`
  - Returns prefs or defaults (no row ⇒ defaults).
- `PUT /notifications/prefs?user_id=<id>`
  - Partial upsert; returns current prefs.

**Envelope:** `ApiResponse` → `{"ok": true, "data": <NotificationPrefsRead>, "error": null}`  
User not found ⇒ `ok: false`, `error.code = "USER_NOT_FOUND"`.

### Defaults (no row)
- All channels enabled
- quiet hours disabled (`start/end = null`)
- `engagement_level = 1`

### Validation
- `quiet_hours.start/end` must be `HH:MM`
- If `quiet_hours.enabled == true` → both required
- `engagement_level ∈ {0,1,2}`

### Server verification
- Migration:
  - Before: `alembic current` = `010_add_notification_guard_state`
  - After: `alembic upgrade head` → `011_add_notification_prefs (head)` ✅
- Service:
  - `sudo systemctl restart sedi-backend.service`
  - `curl -i http://127.0.0.1:8000/healthz` → 200, `db_ok: true` ✅
- Tests:
  - `PYTHONPATH=/var/www/sedi/backend python -m pytest backend/tests/acceptance/test_notifications_prefs_v1.py -q` → **4 passed** ✅
  - Full acceptance suite after migration: **37 passed** ✅

Last updated: 2026-02-23


------------------------------------------------------------------------

## 14️⃣ Stage 6 (Feb 25, 2026) — Operational Baseline + Ops Endpoint + DB Backup + Runtime Verification (V1)

**Status:** ✅ DONE (server verified end-to-end)

This section captures all changes and verifications performed after the last update, with a focus on V1 operational readiness and scenario-driven acceptance validation.

### A) Runtime verification on server (Hetzner / systemd)

**Python runtime note**
- Server does not provide `python` binary by default; use venv python:
  - `./.venv/bin/python` (Python 3.10.12)

**Contracts suite (server)**
- `PYTHONPATH=/var/www/sedi/backend ./.venv/bin/python -m pytest backend/tests/contracts/ -q`
- Result observed on server: **27 passed** ✅ (warnings only)

**Full tests (server)**
- `PYTHONPATH=/var/www/sedi/backend ./.venv/bin/python -m pytest -q`
- Result observed on server: **339 passed, 2 skipped** ✅ (warnings only)

### B) Timezone pinning update (V1 operational change)

- Server env updated:
  - `/etc/sedi/sedi-backend.env`: `APP_TIMEZONE=Asia/Dubai`
- Verified via `/proc/<PID>/environ`:
  - `APP_TIMEZONE=Asia/Dubai`
  - `DEVICE_AUTH_MODE=db_only`

> Note: This supersedes earlier server state where `APP_TIMEZONE=Europe/Berlin` was present.

### C) A3 Acceptance tests — Auth & Devices E2E scenarios added

Two new scenario-driven acceptance tests were added (A3) to cover the most important end-to-end flows.

**Files**
- `backend/tests/acceptance/test_auth_e2e_v1.py`
- `backend/tests/acceptance/test_devices_e2e_v1.py`

**Auth E2E flow covered**
- `POST /auth/request_otp`
- `POST /auth/verify_otp`
- `GET /auth/me`
- `POST /auth/refresh`
- `POST /auth/logout`
- Asserts refresh invalidation after logout (`/auth/refresh` returns 401).

**Devices E2E flow covered (db_only mode)**
- `GET /devices`
- `POST /devices/register`
- `POST /devices/{device_id}/rotate-token`
- `POST /devices/{device_id}/revoke`
- `POST /device/ingest`
- Asserts token rotation works and old token fails; revoke disables ingestion.

**Server verification**
- `PYTHONPATH=/var/www/sedi/backend ./.venv/bin/python -m pytest backend/tests/acceptance/test_auth_e2e_v1.py -q` → **1 passed** ✅
- `PYTHONPATH=/var/www/sedi/backend ./.venv/bin/python -m pytest backend/tests/acceptance/test_devices_e2e_v1.py -q` → **1 passed** ✅

### D) New minimal ops endpoint: GET /ops/status (admin-protected)

**Goal**
Provide a safe, minimal operational endpoint for V1 monitoring without changing public API contracts.

**Code changes**
- New file: `backend/app/routers/ops.py`
- Registered in: `backend/app/main.py` via `app.include_router(ops.router)`
- New test: `backend/tests/test_ops_status_endpoint.py`

**Security**
- Requires header: `X-ADMIN-TOKEN`
- Compares strictly with env `ADMIN_TOKEN`
- If `ADMIN_TOKEN` unset/empty → `403` with `detail="admin_disabled"`
- If token missing/wrong → `403` with `detail="forbidden"`
- Response intentionally excludes secrets.

**Response (V1)**
- Envelope: `{"ok": true, "data": {...}, "error": null}`
- Includes:
  - `service.now_utc`
  - `db.latency_ms` (select 1)
  - `counts` (schema-safe fallbacks)
  - `runtime`: `DEVICE_AUTH_MODE`, `FCM_DISABLED`, `APP_TIMEZONE`

**Server verification**
- Test:
  - `PYTHONPATH=/var/www/sedi/backend ./.venv/bin/python -m pytest backend/tests/test_ops_status_endpoint.py -q`
  - Result: **3 passed** ✅
- Runtime curl:
  - `curl -sS -H "X-ADMIN-TOKEN: <ADMIN_TOKEN>" http://127.0.0.1:8000/ops/status | python3 -m json.tool`
  - Example observed: `db.latency_ms≈34ms`, `notifications_pending=0`, `FCM_DISABLED=true`, `APP_TIMEZONE=Asia/Dubai`.

### E) Health endpoints sanity

- `GET /healthz` → 200 ✅
- `GET /health` → 200 ✅
- `GET /status` → 404 (not implemented) ✅

### F) DB backup & restore sanity (V1 operational requirement)

**Backup directory**
- Created: `/var/backups/sedi` with permissions `700`

**Backup command (custom format)**
- `pg_dump -Fc ... -f /var/backups/sedi/sedi_db_<timestamp>.dump`

**Sanity check**
- `pg_restore --list <dump> | head`
- Verified metadata:
  - Dumped from Postgres 14.20
  - TOC entries present (e.g. `alembic_version`, `device_events`, `devices`, ...)

**Result**
- Backup file produced successfully and verified readable by pg_restore ✅

### G) Operations Runbook (repo) — consolidated V1 daily ops

**New repo file**
- `OPERATIONS_RUNBOOK_V1.md` (root of repo)

**Content**
- Daily checklist (health checks + ops/status)
- 5-minute incident flow
- Safe restart + env verify via `/proc`
- DB backup + sanity check + retention suggestion
- Minimal monitoring options (cron/timer instructions only)
- Minimal data/feedback queries + fallbacks
- Links to:
  - `HOW_TO_CHECK_LOGS.md`
  - `BACKEND_RESTART_INSTRUCTIONS.md`
  - `README_DEPLOYMENT.md`

**Note**
- No secrets hardcoded; placeholders used (e.g. `<ADMIN_TOKEN>`).

**Server presence verified**
- `OPERATIONS_RUNBOOK_V1.md` present on server after `git pull --ff-only` ✅

### H) Commit traceability

- Ops endpoint commit (server observed):
  - `feat(ops): add admin-protected /ops/status endpoint`
- Runbook commit advanced origin/main:
  - `origin/main` moved from `a78f526` → `917ae21` (server fetch output)

------------------------------------------------------------------------


------------------------------------------------------------------------

## 15️⃣ Stage 7 (Feb 25, 2026) — CI Workflow Reality Check + Server Reconnect Playbook (V1)

**Status:** ✅ VERIFIED (server commands executed + local CI-style DB validated)

This section records what was *actually present and verified on the server* during the Feb 25 session, including the admin-protected ops endpoint behavior, runtime env confirmation, and a reality-check on the CI workflow file.

### A) Ops endpoint access: why `/ops/status` was `forbidden` at first

Observed:
- `GET /ops/status` without token → `{"detail":"forbidden"}`
- `GET /ops/status` with `X-ADMIN-TOKEN: $ADMIN_TOKEN` → still `forbidden`

Root cause (shell/env, not backend):
- `$ADMIN_TOKEN` was empty in the shell session:
  - `echo "ADMIN_TOKEN=[$ADMIN_TOKEN]"` → `ADMIN_TOKEN=[]`

Fix / correct way (server-safe):
- Read the token from the systemd env file and pass it explicitly:
  - `TOKEN="$(sudo awk -F= '/^ADMIN_TOKEN=/{print $2}' /etc/sedi/sedi-backend.env | tail -n 1 | tr -d '\r')"`
  - `curl -sS -H "X-ADMIN-TOKEN: $TOKEN" http://127.0.0.1:8000/ops/status | python3 -m json.tool`

Result:
- `ok=true`, with runtime snapshot including:
  - `DEVICE_AUTH_MODE=db_only`
  - `FCM_DISABLED=true`
  - `APP_TIMEZONE=Asia/Dubai`

### B) Runtime env confirmed from running PID

Service status (systemd):
- `sudo systemctl status sedi-backend.service --no-pager -l`
- Scheduler started successfully (`APScheduler` logs present)
- Service listening on `0.0.0.0:8000`

Runtime env (from `/proc/<PID>/environ`, abbreviated):
- `DATABASE_URL=postgresql://sedi_user:...@localhost:5432/sedi_db`
- `DEVICE_AUTH_MODE=db_only`
- `DEVICE_INGEST_TOKEN=<present>`
- `ADMIN_TOKEN=<present>`
- `FCM_DISABLED=true`
- `APP_TIMEZONE=Asia/Dubai`
- `OPENAI_API_KEY=<present>`

### C) CI-style database + migrations + targeted test runs (server)

Goal:
- Reproduce the GitHub Actions "ephemeral Postgres + migrate + subset tests" flow on the server using a dedicated DB.

1) Create fresh DB  
> Note: `DROP DATABASE` cannot run inside a transaction when issued via `-c` with multiple statements.

Commands used:
- Interactive SQL block:
  - `sudo -u postgres psql <<'SQL'`
  - `DROP DATABASE IF EXISTS sedi_ci_test;`
  - `CREATE DATABASE sedi_ci_test OWNER sedi_user;`
  - `SQL`

2) Run migrations on the CI DB
- `DATABASE_URL="postgresql+psycopg2://sedi_user:SediDbPass_2026@localhost:5432/sedi_ci_test" python -m alembic -c backend/alembic.ini upgrade head`

Observed:
- Upgraded through `011_add_notification_prefs (head)`.

3) Run contract tests against CI DB
- `TEST_DATABASE_URL="postgresql+psycopg2://sedi_user:SediDbPass_2026@localhost:5432/sedi_ci_test" python -m pytest -q backend/tests/contracts/ --tb=long`
- Result observed: **27 passed** ✅

4) Run mandatory acceptance subset (all green)
- `python -m pytest -q backend/tests/acceptance/test_release_d.py --tb=long` → **3 passed** ✅
- `python -m pytest -q backend/tests/acceptance/test_decision_engine_scenarios_v1.py --tb=long` → **6 passed** ✅
- `python -m pytest -q backend/tests/acceptance/test_kc_apply_answer_profile_answer_fallback.py --tb=long` → **1 passed** ✅

5) Optional acceptance tests (safe-skip behavior)
- `test_device_ingestion_c1.py` was **absent** → SKIP message printed ✅
- Notification prefs acceptance test was present and green:
  - `python -m pytest -q backend/tests/acceptance/test_notifications_prefs_v1.py --tb=long` → **4 passed** ✅

### D) CI Freeze Definition (Source of Truth)

Source of truth file:
- Path: `.github/workflows/ci-backend-tests.yml`
- Verified location: repo root `/var/www/sedi/backend`

Current CI freeze definition:
- **Mandatory**
  - `backend/tests/contracts/`
  - `backend/tests/acceptance/test_release_d.py`
  - `backend/tests/acceptance/test_decision_engine_scenarios_v1.py`
  - `backend/tests/acceptance/test_kc_apply_answer_profile_answer_fallback.py`
- **Optional (only if present)**
  - `backend/tests/acceptance/test_device_ingestion_c1.py`
  - `backend/tests/acceptance/test_notification_prefs_v1.py` OR `backend/tests/acceptance/test_notifications_prefs_v1.py`

Important clarifications:
- Current CI **does NOT run E2E tests** (no `test_auth_e2e_v1.py` / `test_devices_e2e_v1.py` in this workflow).
- CI migrations run against an ephemeral Postgres service (`postgres:15`) via `TEST_DATABASE_URL`; `DATABASE_URL` is set only for the migration step.

### E) Server reconnect quick commands (copy/paste)

Use these after reconnecting to avoid re-discovering runtime state:

1) Service + PID
- `sudo systemctl status sedi-backend.service --no-pager -l`

2) Confirm runtime env (no secrets printed beyond keys)
- `PID="$(systemctl show -p MainPID --value sedi-backend.service)" && echo "PID=$PID" && sudo tr '\0' '\n' < /proc/$PID/environ | egrep '^(DATABASE_URL|DEVICE_AUTH_MODE|DEVICE_INGEST_TOKEN|ADMIN_TOKEN|FCM_DISABLED|APP_TIMEZONE|OPENAI_API_KEY|LANG)=' || true`

3) Ops status (admin)
- `TOKEN="$(sudo awk -F= '/^ADMIN_TOKEN=/{print $2}' /etc/sedi/sedi-backend.env | tail -n 1 | tr -d '\r')" && curl -sS -H "X-ADMIN-TOKEN: $TOKEN" http://127.0.0.1:8000/ops/status | python3 -m json.tool`

4) CI-style DB recreate + migrate (optional)
- `sudo -u postgres psql <<'SQL'`
- `DROP DATABASE IF EXISTS sedi_ci_test;`
- `CREATE DATABASE sedi_ci_test OWNER sedi_user;`
- `SQL`
- `cd /var/www/sedi/backend && source .venv/bin/activate && export PYTHONPATH=/var/www/sedi/backend && DATABASE_URL="postgresql+psycopg2://sedi_user:SediDbPass_2026@localhost:5432/sedi_ci_test" python -m alembic -c backend/alembic.ini upgrade head`

5) Run the same mandatory subset locally (optional)
- `TEST_DATABASE_URL="postgresql+psycopg2://sedi_user:SediDbPass_2026@localhost:5432/sedi_ci_test" python -m pytest -q backend/tests/contracts/ --tb=long`
- `TEST_DATABASE_URL="postgresql+psycopg2://sedi_user:SediDbPass_2026@localhost:5432/sedi_ci_test" python -m pytest -q backend/tests/acceptance/test_release_d.py --tb=long`
- `TEST_DATABASE_URL="postgresql+psycopg2://sedi_user:SediDbPass_2026@localhost:5432/sedi_ci_test" python -m pytest -q backend/tests/acceptance/test_decision_engine_scenarios_v1.py --tb=long`
- `TEST_DATABASE_URL="postgresql+psycopg2://sedi_user:SediDbPass_2026@localhost:5432/sedi_ci_test" python -m pytest -q backend/tests/acceptance/test_kc_apply_answer_profile_answer_fallback.py --tb=long`

Last updated: 2026-02-25T15:57:38Z

------------------------------------------------------------------------
