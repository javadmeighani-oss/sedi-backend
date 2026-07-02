# Gate 4-C Closure — Notification to Chat Context Restoration

## 1. Final status

Gate 4-C backend production is complete and stable.

| Item | Value |
|------|-------|
| Gate 4-C1 feature | Merged and deployed ([PR #5](https://github.com/javadmeighani-oss/sedi-backend/pull/5)) |
| Gate 4-C1 safety hotfix | Merged and deployed ([PR #6](https://github.com/javadmeighani-oss/sedi-backend/pull/6)) |
| Gate 4-C2 dedup | Merged and deployed ([PR #7](https://github.com/javadmeighani-oss/sedi-backend/pull/7)) |
| Production image | `ghcr.io/javadmeighani-oss/sedi-backend:7d5472e7e8cf6f6ad66f5ea95707fcec9b83e9de` |
| Alembic current/head | `039_gate4b_notification_context_fields` |
| Migration required for Gate 4-C | **No** |
| Frontend | **Unchanged** |

Gate 4-C is **closed**.

---

## 2. Gate 4-C1 implementation summary

Gate 4-C1 wires notification-to-chat continuity on the backend.

### `/interact/chat` extensions

- Accepts optional `source_notification_id` (plus optional `conversation_id`, `thread_id`, `interaction_source`).
- Backend verifies notification ownership before processing.
- **Missing notification** → **404**
- **Foreign notification** (belongs to another user) → **403**
- **No JWT** → **401** (unchanged)
- Normal chat without `source_notification_id` is unchanged.

### Safe internal context restoration

- `build_safe_chat_context()` builds an internal-only dict from the notification row.
- `ConversationBrain.process_message()` receives optional `notification_context` and injects a `[NOTIFICATION_CONTEXT]` system block.
- Response may include continuity fields: `continued_from_notification`, `source_notification_id`, `conversation_id`.
- **No raw `context_json`** is returned to the client.

### InteractionEvent linkage

- When `source_notification_id` is present, a `chat_message` `InteractionEvent` is created with minimal metadata (`message_length` only — no full user message).

### Key files

- `backend/app/routers/interact.py`
- `backend/app/services/gate4/notification_chat_context.py`
- `backend/app/services/gate4/interaction_event_service.py`
- `backend/app/schemas/chat.py`
- `backend/tests/test_gate4c_interaction_events.py`
- `backend/tests/test_gate4c_notification_chat_context.py`

---

## 3. Gate 4-C1 safety hotfix

A post-merge safety review identified that `notification.body` could leak dosage-bearing text into GPT context (e.g. medication reminders).

The hotfix ([PR #6](https://github.com/javadmeighani-oss/sedi-backend/pull/6), main commit `44f5513`) removed body injection entirely.

### What is excluded

- Raw `notification.body`
- Dosage-bearing reminder text (e.g. `500mg`, medication names from body)
- `notification_summary` field in context builder

### What remains in safe context

- `category`
- `template_key`
- `risk_level`
- `source_type` / `source_id`
- Sanitized `context_hints` (allowlisted keys only)
- Safe `notification_title` only (truncated)

OpenAPI contract was unchanged by the hotfix; only internal context composition changed.

---

## 4. Gate 4-C2 dedup policy

Gate 4-C2 ([PR #7](https://github.com/javadmeighani-oss/sedi-backend/pull/7)) adds backend-side idempotent dedup for notification-linked `chat_message` `InteractionEvent` rows.

### Hybrid dedup (Option E)

| Condition | Dedup key |
|-----------|-----------|
| `conversation_id` present (non-empty after strip) | `user_id` + `source_notification_id` + `event_type=chat_message` + `conversation_id` |
| `conversation_id` absent or empty | `user_id` + `source_notification_id` + `event_type=chat_message` + `conversation_id IS NULL` |

### Behavior on deduped requests

- Chat processing **still runs** (GPT, memory, response).
- Notification ownership verification **still runs**.
- Safe notification context **still builds** and passes to `ConversationBrain`.
- `continued_from_notification=True` **still returned** when `source_notification_id` is set.
- Only the duplicate `InteractionEvent` **insert is skipped**; existing row is returned.

### Infrastructure

- **No migration** required.
- **No unique index** required for V1 — `SELECT … LIMIT 1` before insert uses existing indexes on `user_id`, `source_notification_id`, and `conversation_id`.

### Key files

- `backend/app/services/gate4/interaction_event_service.py` — `find_existing_notification_chat_message_event()`, idempotent `create_chat_message_event()`
- `backend/tests/test_gate4c_interaction_events.py` — dedup integration tests

---

## 5. Production deploys and runs

### Gate 4-C1 (feature + safety hotfix image)

| Item | Value |
|------|-------|
| C1 main commit | `61ca29c` |
| Safety hotfix main commit | `44f5513bc72c296324cfafaef33b784afc1e9623` |
| Production image deployed | `ghcr.io/javadmeighani-oss/sedi-backend:44f5513bc72c296324cfafaef33b784afc1e9623` |
| Deploy workflow run | [28613071323](https://github.com/javadmeighani-oss/sedi-backend/actions/runs/28613071323) |
| Post-deploy readonly run | [28613167491](https://github.com/javadmeighani-oss/sedi-backend/actions/runs/28613167491) |

Previous production image before C1 deploy: `882e0ddf45b0bb8371f762c3b19f5fe7bfad4370` (Gate 4-B).

### Gate 4-C2 (dedup)

| Item | Value |
|------|-------|
| Main commit | `7d5472e7e8cf6f6ad66f5ea95707fcec9b83e9de` |
| Production image deployed | `ghcr.io/javadmeighani-oss/sedi-backend:7d5472e7e8cf6f6ad66f5ea95707fcec9b83e9de` |
| Deploy workflow run | [28615261478](https://github.com/javadmeighani-oss/sedi-backend/actions/runs/28615261478) |
| Post-deploy readonly run | [28615403946](https://github.com/javadmeighani-oss/sedi-backend/actions/runs/28615403946) |

Previous production image before C2 deploy: `44f5513bc72c296324cfafaef33b784afc1e9623` (Gate 4-C1).

Neither deploy ran Alembic. Pre-deploy DB backups were created by the standard deploy workflow.

---

## 6. CI summary

| Gate | Backend V1 freeze tests | Gate 4-B DB QA | Notes |
|------|-------------------------|----------------|-------|
| Gate 4-C1 (PR #5) | Pass | Pass | OpenAPI snapshot updated for optional chat fields |
| Safety hotfix (PR #6) | Pass | Pass | No API contract change |
| Gate 4-C2 (PR #7) | Pass ([28614922272](https://github.com/javadmeighani-oss/sedi-backend/actions/runs/28614922272)) | Pass ([28614487832](https://github.com/javadmeighani-oss/sedi-backend/actions/runs/28614487832)) | Dedup integration tests ran in DB QA |

- **No migration files** were added for Gate 4-C.
- Post-merge `main` builds succeeded for C2: image build [28614922117](https://github.com/javadmeighani-oss/sedi-backend/actions/runs/28614922117).

---

## 7. Production checks

Checks performed after Gate 4-C2 deploy (final production state).

### Health

- Public `/health` — **200**, `db: ok`
- Public `/healthz` — **200**, `db_ok: true`
- Local health checks (127.0.0.1) — passed during deploy and post-deploy readonly check

### Security smoke

- `POST /notifications/deliver_pending` without admin token — **401** (`Admin token required`)
- `GET /notifications` without JWT — **401**

### Alembic

- Current and head remained **`039_gate4b_notification_context_fields`**
- No migration was run during Gate 4-C deploys

### Post-deploy logs (30-minute window, filtered)

- No `Traceback`
- No `ERROR`
- No `Exception`
- No scheduler loop/spam
- No Gate 4-C errors

Readonly check: [28615403946](https://github.com/javadmeighani-oss/sedi-backend/actions/runs/28615403946).

---

## 8. Known validation gap

A safe JWT test user was **not available** during production deploy, so the following behavior checks were **not run in production**:

- Normal `/interact/chat` with JWT and no `source_notification_id`
- Missing `source_notification_id` (invalid id) returns 404
- Foreign notification returns 403
- Valid notification first chat creates one `chat_message` event
- Duplicate same notification + same `conversation_id` does not create a second event

**This is not a production blocker** because CI integration tests and unauthenticated security smoke passed. These checks should be completed later with a staging or QA test account (synthetic user, no real PII).

---

## 9. Mobile handoff

Mobile clients should:

1. Open chat from a deeplink carrying `source_notification_id` (from push payload or notification inbox).
2. Send `source_notification_id` on the **first** notification-originated chat turn.
3. Send `conversation_id` when available (enables per-session dedup and future V2 thread grouping).
4. Avoid logging real health content or user messages.
5. Rely on backend idempotency — repeating `source_notification_id` on subsequent turns will not create duplicate timeline events (Gate 4-C2).

Reference: `backend/docs/gate4/GATE4E2_MOBILE_CONTRACT_HANDOFF.md`

**Backend is ready.** Mobile wiring of `source_notification_id` is a follow-up, not a Gate 4-C blocker.

---

## 10. Remaining Gate 4 path

**Gate 4-C is closed.**

The next backend gate should be **Gate 4-D**.

Gate 4-D should focus on:

- Feedback intelligence
- Notification preference behavior
- Quiet hours / sleep-aware policy
- Follow-up and timing policy
- Reducing irrelevant notifications
- Using `interaction_events` to decide whether the user is active in conversation

Gate 4-D should **not** include:

- Frontend redesign
- iOS/APNs implementation
- Wearable/device integration
- Gate 5 device work

---

## Document history

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-07-02 | Gate 4-C closure — C1, safety hotfix, C2 dedup production complete |
