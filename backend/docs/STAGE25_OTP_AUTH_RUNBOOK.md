# Stage 25 Step 1 – Phone OTP Auth Runbook

**Stage 25 OTP is the only supported auth.** The legacy JWT refresh/login router (`auth_login`) is disabled and must not be re-included. **Passkey endpoints** (`/auth/set-passkey`, `/auth/verify-passkey`) are **disabled in production (V1)** when `ENV=prod` or `DEBUG=false` (return 404); they are for dev/internal only.

## Env vars

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Production | **Canonical** secret for JWT signing (access tokens). Must be **≥ 32 bytes**, recommended **64 bytes** random (e.g. `openssl rand -base64 48`). If missing when `DEBUG=false` or `ENV=prod`, the app fails at startup. Backward-compat: `JWT_SECRET` is read when `SECRET_KEY` is not set. **Rotating SECRET_KEY invalidates all existing access tokens** (expected; users must re-auth or use refresh token where applicable). |
| `OTP_SECRET` | Optional | Used only for OTP HMAC hashing (server-side). If missing, `SECRET_KEY` is used. Changing it invalidates active OTP codes only (max 5 minutes), not refresh tokens. |
| `SMS_DISABLED` | Optional | Set to `true` / `1` / `yes` to skip sending SMS (dev mode). Returns `dev_code` in API response. |
| `SMS_PROVIDER` | Optional | `mediana` (default) or `dummy`. |
| `MEDIANA_API_KEY` | When SMS_PROVIDER=mediana | API key from Mediana panel (`X-API-KEY`). Server env only. |
| `MEDIANA_OTP_PATTERN_CODE` | When SMS_PROVIDER=mediana | Approved OTP pattern code from Mediana panel. |
| `DATABASE_URL` | Yes | PostgreSQL connection string (existing). If it contains `%xx` URL-encoding (e.g. in the password), Alembic env disables configparser interpolation so no `ValueError` is raised. |

## Migrations

```bash
cd backend
alembic upgrade head
```

This applies `002_phone_otp` (adds `users.phone`, `otp_codes`, `refresh_tokens`).

If `DATABASE_URL` contains `%xx` URL-encoding (e.g. in the password), Alembic env disables configparser interpolation to avoid `ValueError`.

## Curl examples

Base URL assumed: `http://127.0.0.1:8000`. Use `BASE_URL` or your host in production.

### 1. Request OTP

Canonical path: `/auth/request_otp`. Alias (REST-style): `/auth/otp/request`.

```bash
curl -s -X POST http://127.0.0.1:8000/auth/request_otp \
  -H "Content-Type: application/json" \
  -d '{"phone": "+989121234567"}'
```

Expected: `{"ok": true, "data": {"ok": true, "next": "verify_otp"}}` or with `dev_code` for testing: `{"ok": true, "data": {"ok": true, "next": "verify_otp", "dev_code": "123456"}}`.  
When SMS is not sent (`SMS_DISABLED=true`), `dev_code` is returned so the app can display it (e.g. SnackBar) for testing without real SMS. When SMS is enabled and Mediana fails, the API returns `OTP_REQUEST_FAILED` (no `dev_code`).  
Optional: `Accept-Language: fa` or `en` / `ar` for OTP message language (default fa).

### 2. Verify OTP and get tokens

```bash
curl -s -X POST http://127.0.0.1:8000/auth/verify_otp \
  -H "Content-Type: application/json" \
  -d '{"phone": "+989121234567", "code": "123456"}'
```

Optional headers for audit (stored on refresh token row): `X-Device-Info`, `X-Client-IP`.

Expected: `{"ok": true, "data": {"access_token": "...", "refresh_token": "...", "token_type": "bearer", "expires_in": 3600}}`.

### 3. GET /auth/me (requires access token)

```bash
ACCESS_TOKEN="<paste access_token from step 2>"
curl -s http://127.0.0.1:8000/auth/me \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Expected: `{"ok": true, "data": {"user_id": 1, "phone": "+989121234567", "display_name": null, "language": "en"}}`.

### 4. Refresh access token (optional)

```bash
REFRESH_TOKEN="<paste refresh_token from step 2>"
curl -s -X POST http://127.0.0.1:8000/auth/refresh \
  -H "Authorization: Bearer $REFRESH_TOKEN"
```

Returns new `access_token` and `refresh_token`.

### 5. Logout (revoke refresh token)

```bash
curl -s -X POST http://127.0.0.1:8000/auth/logout \
  -H "Authorization: Bearer $REFRESH_TOKEN"
```

Expected: `{"ok": true, "data": {"revoked": true}}`.

## Endpoints summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | **Monitoring (Freeze B1):** 200 JSON with `ok`, `version`, `env` (prod/dev), `db` (ok/error), `timestamp`. No secrets. Use for production health checks. |
| POST | `/auth/request_otp` | Body: `{ "phone": "+..." }`. Rate-limited (e.g. 5 per 10 min). |
| POST | `/auth/otp/request` | Alias for request_otp. |
| POST | `/auth/verify_otp` | Body: `{ "phone": "+...", "code": "123456" }`. Returns tokens. |
| POST | `/auth/otp/verify` | Alias for verify_otp. |
| GET | `/auth/me` | Header: `Authorization: Bearer <access_token>`. |
| POST | `/auth/refresh` | Header: `Authorization: Bearer <refresh_token>`. |
| POST | `/auth/logout` | Header: `Authorization: Bearer <refresh_token>`. Revokes that token. |

## Security notes

- **SECRET_KEY**: Must be ≥ 32 bytes; 64 bytes random recommended. Rotation invalidates existing access tokens (users re-auth or refresh).
- OTP and refresh tokens are stored hashed (HMAC-SHA256).
- OTP: max 5 verify attempts per code; expiry e.g. 5 min; rate limit 3 requests per 10 min per phone.
- Access token: JWT, default 60 min.
- Refresh token: opaque, stored in DB, default 30 days; revocable via `/auth/logout`.

### Refresh session policy (V1)

- **(a) Multiple sessions:** Multiple active refresh sessions per user are allowed (multi-device). We do **not** revoke all previous refresh tokens on login.
- **(b) Rotation:** Each refresh is revoked immediately on use. Calling `POST /auth/refresh` with a valid token returns new tokens and invalidates the one sent.
- **(c) Logout:** `POST /auth/logout` revokes only the presented refresh token (Bearer). Other sessions remain valid.
- **(d) Future options (not in V1):** Device-aware revoke or revoke-all-on-login may be added later; not enabled for V1 field test.

Optional audit: `POST /auth/verify_otp` accepts `X-Device-Info` and `X-Client-IP` headers; when present, they are stored on the new refresh token row for auditability.

---

## Step 2.2 – Real SMS (Mediana)

برای ارسال واقعی SMS به کاربران:

1. **حساب مدیانا**: ثبت‌نام در پنل Mediana و دریافت API key
2. **پترن OTP**: کد پترن تأییدشده را از پنل بگیرید (`MEDIANA_OTP_PATTERN_CODE`)
3. **سرور production** (`/etc/sedi/sedi-backend.env`):
   - `SMS_DISABLED=false`
   - `SMS_PROVIDER=mediana`
   - `MEDIANA_API_KEY=<from panel>`
   - `MEDIANA_OTP_PATTERN_CODE=<pattern code>`
4. بعد از تغییر env، کانتینر `sedi-backend` را recreate کنید.

- OTP via `POST https://api.mediana.ir/sms/v1/send/otp` with `patternCode`, `recipient` (`09…`), `otpCode` (6-digit backend code).
- Legacy `SMS_PROVIDER=kavenegar` is **not supported**.

### Troubleshooting

- **No SMS received:** Check `MEDIANA_API_KEY`, pattern code, and Mediana panel (balance, logs). Phone is normalized to `09xxxxxxxxx`. For local testing without SMS, set `SMS_DISABLED=true` — `dev_code` is returned in the API response.
- **OTP_REQUEST_FAILED:** SMS enabled but provider misconfigured or Mediana error. Check logs for `[OTP] SMS send failed`.

### Journalctl (backend logs)

```bash
# SMS/OTP related
journalctl -u sedi-backend.service -g "DEV OTP|SMS send failed" --no-pager -n 100

# Last 50 lines
journalctl -u sedi-backend.service -n 50 --no-pager
```

---

## Running tests (Step 2.2)

```bash
cd backend
pytest tests/test_auth_otp_v1.py -v
pytest tests/test_sms_gateway_mediana.py tests/test_sms_gateway_dummy.py tests/test_sms_gateway_basic.py -v
```
