# Sedi Gate 5.2 Closure — Raw Heart/ECG Store-Only Ingestion

**Date:** 2026-07-03

---

## 1. Closure verdict

**Gate 5.2 is production-deployed and stable.**

Gate 5.2 delivered store-only raw heart/ECG signal batch ingestion with append-only storage, Gadget Hub and sensor ownership validation, and idempotent dedupe — isolated from clinical interpretation, ML, notifications, and existing vital ingest paths. Production is healthy at closure with no rollback.

---

## 2. Final production state

| Item | Value |
|------|-------|
| **Main commit** | `bdd5c8baaa06f467b8f8b56997ea2aa33c2fc2f2` |
| **Main message** | `feat(gate5b): add raw signal batch ingestion` |
| **PR** | [#15 — Gate 5.2: Raw signal batch ingestion](https://github.com/javadmeighani-oss/sedi-backend/pull/15) |
| **Production image** | `ghcr.io/javadmeighani-oss/sedi-backend:bdd5c8baaa06f467b8f8b56997ea2aa33c2fc2f2` |
| **Previous production image** | `ghcr.io/javadmeighani-oss/sedi-backend:59b588534c5d5d5f9d9e546d2c46848f9ddc9fc0` |
| **Pre-deploy readonly run** | `28671822245` — **success** |
| **Deploy workflow run** | `28674585960` — **success** |
| **Migration workflow run** | `28674659247` — **success** |
| **Post-deploy readonly run** | `28674705732` — **success** |
| **`/health`** | HTTP **200** — `db: ok` |
| **`/healthz`** | HTTP **200** — `db_ok: true` |
| **Alembic head** | `041_gate5b_raw_signal_batches` (head) |
| **Rollback** | **None** |
| **Pre-deploy backup** | `sedi_db_predeploy_20260703_204521.sql.gz` |
| **Frontend** | **Unchanged** — no frontend deploy |
| **Env files** | **Unchanged** — no env edits |
| **Workflows** | **Unchanged** — no workflow edits |

**Previous production state (pre–Gate 5.2 deploy):**

| Item | Value |
|------|-------|
| **Pre-deploy image** | `ghcr.io/javadmeighani-oss/sedi-backend:59b588534c5d5d5f9d9e546d2c46848f9ddc9fc0` |
| **Pre-deploy Alembic** | `040_gate5a_hub_sensor_status` (head) |

---

## 3. What Gate 5.2 delivered

Gate 5.2 ([PR #15](https://github.com/javadmeighani-oss/sedi-backend/pull/15)) adds raw heart/ECG store-only ingestion on top of Gate 5.1 Gadget Hub and sensor registry foundations.

### Delivered capabilities

- **Raw Heart/ECG store-only ingestion foundation** — append-only batches; no interpretation.
- **New `raw_signal_batches` table** — PostgreSQL JSONB sample storage for v1.
- **`RawSignalBatch` model** — isolated from `DeviceEvent`, notifications, care, and memory models.
- **`POST /device/signals/raw`** — Gadget Hub ingest via `X-DEVICE-TOKEN`.
- **Gadget Hub ownership validation** — only `device_type=gadget_hub` may submit.
- **Registered sensor ownership validation** — sensor must belong to hub and not be revoked.
- **Signal/sensor compatibility validation**:
  - `ecg` → sensor must be `ecg`
  - `heart_rate_raw` → sensor may be `ecg` or `heart_rate`
  - `unknown` → any registered sensor
- **Idempotent `client_batch_id` dedupe** — replay returns `dedupe_hit=true` (HTTP 200).
- **Object-storage boundary columns** — `storage_backend`, `object_storage_key` (unused in v1).
- **OpenAPI snapshot update** — contract reflects new endpoint and schemas.
- **Gate 5.2 tests** — `test_gate5b_raw_signal_ingestion.py` (20 tests); CI green on PR and main.

### Key files (Gate 5.2 — PR #15)

| Area | Files |
|------|-------|
| Migration | `backend/alembic/versions/041_gate5b_raw_signal_batches.py` |
| Models | `backend/app/models.py` (`RawSignalBatch`) |
| Schemas | `backend/app/schemas/device.py` |
| API | `backend/app/routers/device.py` |
| Service | `backend/app/services/gate5/raw_signal_ingestion.py` |
| Tests | `backend/tests/test_gate5b_raw_signal_ingestion.py` |
| Contract | `backend/tests/contracts/snapshots/openapi_v1_snapshot.json` |

---

## 4. Migration

**Revision:** `041_gate5b_raw_signal_batches`

| Property | Detail |
|----------|--------|
| **Type** | Additive migration |
| **New table** | `raw_signal_batches` |
| **Foreign keys** | `users.id`, `devices.id`, `device_sensors.id` |
| **Constraints** | Unique `dedupe_key` |
| **Indexes** | `(user_id, received_at)`, `(hub_device_id, sensor_key, started_at)`, `(client_batch_id, hub_device_id)` |
| **Data impact** | No destructive data operation; no production data migration |

**Upgrade path:** `040_gate5a_hub_sensor_status` → `041_gate5b_raw_signal_batches`

Migration run `28674659247` completed successfully immediately after deploy.

---

## 5. Safety boundaries

Gate 5.2 does **not**:

- Interpret ECG
- Detect arrhythmia
- Run ML
- Run preprocessing
- Diagnose
- Create health alerts
- Create care recommendations
- Create notifications
- Write to `device_events`
- Write to `user_memory_facts`
- Use OpenAI or LLMs for vital interpretation
- Expose a raw signal read API
- Touch frontend
- Change env files

Gate 5.2 is storage and ingest infrastructure only — raw numeric samples persisted with operational metadata, no clinical side effects.

---

## 6. Validation evidence

### PR and CI

| Check | Result |
|-------|--------|
| [PR #15](https://github.com/javadmeighani-oss/sedi-backend/pull/15) merged (squash) | **Yes** |
| PR CI — Backend V1 freeze tests | **Success** |
| PR CI — Gate 4-B DB QA | **Success** |
| Main post-merge — Build Sedi Backend Image (`28671610207`) | **Success** |
| Main post-merge — Backend V1 freeze tests (`28671610154`) | **Success** |

### Production deploy and validation

| Check | Run / result |
|-------|----------------|
| Pre-deploy production baseline | `28671822245` — **success** |
| Deploy Sedi Backend from GHCR | `28674585960` — **success** |
| Pre-deploy DB backup | `sedi_db_predeploy_20260703_204521.sql.gz` — **created** |
| Gate 4-B Production Migration (`alembic upgrade head`) | `28674659247` — **success** |
| Post-deploy readonly validation | `28674705732` — **success** |
| Public `/health` | **200 OK** |
| Public `/healthz` | **200 OK** |
| Running image confirmed | `ghcr.io/javadmeighani-oss/sedi-backend:bdd5c8baaa06f467b8f8b56997ea2aa33c2fc2f2` |
| Alembic after migration | `041_gate5b_raw_signal_batches` (head) |
| Post-deploy logs (30m grep) | **Clean** — no Traceback / ERROR / Exception |
| Rollback | **None** |

---

## 7. API smoke result

| Check | Result |
|-------|--------|
| `POST /device/signals/raw` without `X-DEVICE-TOKEN` | **422** — `Field required` for header |
| `GET /devices/hub-status` without JWT | **401** — `Missing or invalid authorization header` |
| Unauthenticated rejection before raw signal write | **Yes** — 422 is acceptable; request blocked before any sync logic runs |
| Production data written during smoke | **No** |
| Authenticated hub-status / raw-signal ingest smoke | **Deferred** — no safe QA JWT or device token available at closure |

---

## 8. Known non-blocking follow-ups

These items do **not** block Gate 5.2 closure or production stability:

1. **Run authenticated hub-status smoke** with QA JWT when available.
2. **Run authenticated raw-signal ingest smoke** with safe QA hub/device token when available.
3. **Optional future cleanup:** align missing `X-DEVICE-TOKEN` response from **422** to **401** if desired for API consistency.
4. **Define retention policy** for `raw_signal_batches` — not implemented in Gate 5.2.
5. **Consider recursive forbidden clinical-key scan** inside `metadata` / `quality_metadata` (top-level only in Gate 5.2).
6. **Plan object-storage offload** for larger future raw signal volumes when PostgreSQL JSONB limits are approached.

---

## 9. Gate 5.3 handoff

**Gate 5.3 may start after this closure doc is merged.**

Recommended Gate 5.3 scope: **Raw Signal Preprocessing / Feature Extraction Foundation**:

- Read internal `raw_signal_batches`
- Compute non-diagnostic technical features
- Signal quality metrics
- Sample/window metadata
- No diagnosis
- No arrhythmia detection
- No ML risk scoring
- No notifications
- No care recommendations

Gate 5.2 remains the stable store-only foundation; Gate 5.3 adds technical preprocessing only.

---

## Revision history

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-07-03 | Gate 5.2 closure — PR #15 deployed and migrated to production |
