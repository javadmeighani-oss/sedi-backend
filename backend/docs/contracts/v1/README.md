# V1 Contract Pack

API contract freeze for V1: shared envelope, contract docs, and automated contract tests.

## Files Added

| Path | Description |
|------|-------------|
| `backend/app/schemas/api_envelope.py` | `ApiError` (code, message, details?) and `ApiResponse` (ok, data, error); helpers `ok_response`, `err_response` |
| `backend/docs/contracts/v1/auth.md` | Auth: request_otp, verify_otp, me, refresh, logout, passkey; headers; request/response examples |
| `backend/docs/contracts/v1/interact.md` | Interact: introduce, chat; no envelope; InteractionResponse examples |
| `backend/docs/contracts/v1/notifications.md` | Notifications: list, unread, feedback, push/register, admin/test_push, deliver_pending; envelope examples |
| `backend/docs/contracts/v1/device.md` | Device: pending-commands, heartbeat, acknowledge, ingest; headers; request/response examples |
| `backend/docs/contracts/v1/knowledge.md` | Knowledge: next_question, extract_from_message, apply_answer; admin endpoints; envelope examples |
| `backend/docs/contracts/v1/decision.md` | Decision: POST /evaluate; request/response (ok, decision) |
| `backend/tests/contracts/__init__.py` | Package marker |
| `backend/tests/contracts/test_v1_openapi_contracts.py` | OpenAPI: target paths exist, 200 documented, envelope schema present |
| `backend/tests/contracts/test_v1_example_payloads.py` | Example JSON from contract docs validate against Pydantic / required keys |

## Files Modified

| Path | Change |
|------|--------|
| `backend/app/schemas/__init__.py` | Export `ApiResponseV1`, `ApiError` from `api_envelope` |
| `backend/app/routers/auth_otp.py` | `response_model=ApiResponseV1` for request_otp, verify_otp, me, refresh, logout |
| `backend/app/routers/auth.py` | `response_model=ApiResponseV1` for set-passkey, verify-passkey |
| `backend/app/routers/notifications.py` | `response_model=ApiResponseV1` for all endpoints that used APIResponse |
| `backend/app/routers/device.py` | `response_model=ApiResponseV1` for pending-commands, heartbeat, acknowledge (ingest keeps DeviceIngestResponse) |
| `backend/app/routers/knowledge.py` | `response_model=ApiResponseV1` for next_question, extract_from_message, apply_answer |

## Running Tests

From repo root (so `backend` is importable and conftest can load):

```bash
# All tests (requires DB URL and deps, e.g. psycopg2)
pytest backend/tests/ -q

# Contract tests only (still loads app + conftest; needs same env)
pytest backend/tests/contracts/ -v
```

No server; no external network. CI should run `pytest -q` in the same environment as other backend tests (DATABASE_URL set or skipped per test_db_config).

## OpenAPI

OpenAPI schema now includes `ApiResponse` and `ApiError` from `api_envelope` for all endpoints that use `response_model=ApiResponseV1`. Runtime response shape is unchanged (ok, data, error; error has code, message, optional details).

## Notes

- Decision endpoint (`POST /decision/evaluate`) is **not** wrapped in ApiResponse; it returns `{ "ok": true, "decision": {...} }` as documented in decision.md.
- Interact endpoints return `InteractionResponse` directly (no envelope).
- Device `/ingest` uses `DeviceIngestResponse` (same envelope shape; error as object).
