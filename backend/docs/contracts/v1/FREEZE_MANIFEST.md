# Sedi Backend V1 API Contract Freeze Manifest

**Date:** 2026-02-22  
**Git tag:** `v1.0-api-freeze`  
**Commit:** 6313482

---

## What is frozen

- **ApiResponse envelope** for auth, notifications, device (non-ingest), knowledge, and decision endpoints as documented in `backend/docs/contracts/v1/*.md` (auth.md, interact.md, notifications.md, device.md, knowledge.md, decision.md).
- **`POST /device/ingest`** returns **raw `DeviceIngestResponse`** by design (not the shared ApiResponse envelope). OpenAPI documents `DeviceIngestResponse` for 200.

---

## Source of truth

| Item | Path |
|------|------|
| Contract docs | `backend/docs/contracts/v1/` |
| Contract tests | `backend/tests/contracts/` |

---

## Validation commands

```bash
# Contract tests only
PYTHONPATH=/var/www/sedi/backend python -m pytest backend/tests/contracts/ -q

# Full backend test suite
PYTHONPATH=/var/www/sedi/backend python -m pytest backend/tests -q
```

**Optional:** Inspect OpenAPI for schema consistency:

- Schemas `ApiError` and `ApiResponse` (or `APIResponse`) present in `openapi.json` / `app.openapi()`.
- `POST /device/ingest` 200 response references `DeviceIngestResponse`.

---

## Notes

- **Interact** endpoints return `InteractionResponse` directly (no envelope).
- **Decision** endpoint returns `{ "ok": true, "decision": {...} }` (no ApiResponse envelope).
- Any future change to V1 contracts must update both docs and contract tests. **Breaking changes** require a new version directory (e.g. `v1.1` or `v2`); do not alter the frozen `v1` contract in place.
