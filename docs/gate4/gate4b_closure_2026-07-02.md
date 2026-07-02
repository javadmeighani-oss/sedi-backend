# Gate 4-B Closure — Notification Context Foundation

## 1. Final status

Gate 4-B backend production is complete and stable.

| Item | Value |
|------|-------|
| PR | [#2](https://github.com/javadmeighani-oss/sedi-backend/pull/2) merged |
| Main commit | `882e0ddf45b0bb8371f762c3b19f5fe7bfad4370` |
| Production image | `ghcr.io/javadmeighani-oss/sedi-backend:882e0ddf45b0bb8371f762c3b19f5fe7bfad4370` |
| Alembic current/head | `039_gate4b_notification_context_fields` |
| Deploy workflow run | `28607275765` |
| Migration workflow run | `28607650926` |
| Post-deploy readonly check run | `28608465711` |
| Test Server SSH run | `28608066075` |

## 2. What Gate 4-B added

Gate 4-B established the **notification traceability foundation** on the backend.

### `notifications` context fields

Six nullable columns on `notifications`:

- `category`
- `source_type`
- `source_id`
- `context_json`
- `risk_level`
- `template_key`

### Supporting schema and behavior

- **`interaction_events` prerequisite table** — timeline table introduced in migration 037; required for downstream interaction traceability.
- **Safe context sanitization / allowlist approach** — notification context is mapped and persisted through controlled mappers (`notification_context`, `notification_contract`, `push_payload`) rather than accepting arbitrary payloads.
- **Additive schema only** — no destructive column drops or rewrites; existing notification rows remain valid with nullable new fields.
- **No frontend change** — Gate 4-B scope was backend schema, services, API serialization, and tests only.

## 3. Migration path applied

Production Alembic path:

```
036_gate3g_kb_fetch_review
  → 037_gate4c_interaction_events
  → 038_gate4d3_notification_prefs_daily_time
  → 039_gate4b_notification_context_fields
```

Notes:

- Migration completed successfully via workflow run `28607650926`.
- Production DB reached revision `039`.
- Rollback was not required.

## 4. Production checks

### Health

- Public `/health` — **200**, `db: ok`
- Public `/healthz` — **200**, `db_ok: true`
- Local health checks (127.0.0.1) — passed during post-deploy readonly check

### Security smoke

- `POST /notifications/deliver_pending` without admin token — **401** (`Admin token required`)
- `GET /notifications` without JWT — **401**

### Post-deploy logs (30-minute window, filtered)

- No `Traceback`
- No `ERROR`
- No `Exception`
- No notification spam loop
- No scheduler loop

## 5. Count-only production snapshot

Snapshot taken during post-deploy readonly check (`28608465711`):

| Table | Count |
|-------|------:|
| `notifications` | 7 |
| `interaction_events` | 0 |
| `push_devices` | 0 |

Row contents were not inspected or recorded.

## 6. Operational notes

- The **deploy workflow does not run Alembic automatically** — image swap and container recreate only.
- Migration was executed **separately** through a temporary/manual production migration workflow (`gate4b-prod-migrate.yml`, run `28607650926`).
- A **pre-deploy backup** was created before the deploy:
  - `sedi_db_predeploy_20260702_202608.sql.gz`
  - Non-zero size, approximately 19K
- The feature branch `feature/gate4b/notification-context` was **not deleted**.

## 7. Remaining cleanup decision

The following items need a later decision:

- `gate4b-prod-migrate.yml`
- Gate 4-B post-deploy readonly check workflow ([PR #3](https://github.com/javadmeighani-oss/sedi-backend/pull/3))

Options (not decided in this note):

- **Keep** as manual operational tools for future Gate 4 production steps
- **Disable/remove** after broader Gate 4 closure

## 8. Gate 4-C entry point

The next Gate 4 backend step should be:

**Gate 4-C: notification → chat context restoration**

**Goal:** When a user taps a notification action such as "صحبت کنیم", the app opens chat and the backend restores the notification context so the conversation continues from that exact interaction.

Gate 4-C should **not** include:

- Frontend redesign
- iOS/APNs implementation
- `user_event` scheduler
- Medication logic expansion
- Delivery policy tuning
- Gate 4-D feedback intelligence
