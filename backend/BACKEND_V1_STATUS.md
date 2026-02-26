# Sedi Backend V1 — Status Report

## 1) Test Suite Status (Server)
- Last run: `python -m pytest -q`
- Result: **354 passed, 2 skipped**
- Warnings: **0**
- Runtime: ~24–25s

### Skipped tests
1) `backend/tests/test_alembic_env_interpolation.py`
   - Reason: `alembic.env_utils._disable_interpolation` not available in this environment
2) `backend/tests/test_local_rag_provider.py`
   - Reason: Vector provider requires `pgvector`

## 2) Language Policy (V1)
### OTP language resolution
- `resolve_lang` parses `Accept-Language`
- V1 default: `en`
- Supported: `en`, `fa`, `ar`
- Unknown/unsupported language -> default `en` (V1)

### Chat language behavior
- Deterministic chat commands (handled before GPT) respect request language policy:
  - Prefer `Accept-Language` (primary), then user preference
- Fix applied: avoid NameError by ensuring `request` is defined/passed when calling language resolver in `/interact/chat`

## 3) Interaction Router (interact)
Mounted with prefix: `/interact`

Key endpoints:
- `POST /interact/introduce`
- `POST /interact/chat`
- `POST /interact/onboarding`
- `GET  /interact/greeting`
- `GET  /interact/history`

Note:
- Earlier test failures were due to calling non-existent routes (e.g. `/interact/register`, `/onboarding` without prefix).

## 4) Notification Runtime (Stage 16.6.x)
Folder: `backend/app/services/notification_runtime/`

Key modules:
- `i18n_resolver.py`
  - Resolves `template.texts` multilingual blocks using:
    `user_language exact/prefix -> default -> fa -> en -> first`
- `renderer.py`
  - Deterministic rendering for channels:
    `morning`, `engagement`, `health_alert`, `companion`
  - Supports multi-language `template.texts` via `resolve_text_by_user_language`
  - Produces: `{title, body, actions_json}`
- `templates_v1.py`
  - Template definitions (including Health Alert)
- `fallback_generator.py`
  - Safe fallback text generation (FA/EN/AR)

## 5) Notification Engine (legacy + runtime integration)
File: `backend/app/services/notification_engine.py`
- Contains language variants for titles/body (e.g. “Health Alert” / “هشدار سلامت”)
- Works alongside runtime renderer for deterministic outputs.

## 6) Pydantic V2 Deprecation Cleanup
- `routers/notifications.py` updated from `.dict()` to `.model_dump()`
- Result: warning-free test run

## 7) Pitfalls & Resolutions (Important)
- Route mismatch caused 404 in tests:
  - Fix: use `/interact/onboarding` and `/interact/chat`
- Tests accidentally touching production-like DB settings via onboarding:
  - Fix: tests must use conftest-provided `client` and `db` fixtures
- Chat NameError (`request is not defined`):
  - Fix: ensure request object is available when calling `resolve_request_lang(...)`

## 8) Ready-for-Frontend Checklist
- Test suite green ✅
- Language policy stabilized ✅
- Notification rendering deterministic + i18n-ready ✅
- No warnings ✅
