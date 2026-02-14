# Stage 25 Step 1 – Phone OTP Auth Runbook

## Env vars

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Production | **Canonical** secret for JWT signing (access tokens). Must be **≥ 32 bytes**, recommended **64 bytes** random (e.g. `openssl rand -base64 48`). If missing when `DEBUG=false` or `ENV=prod`, the app fails at startup. Backward-compat: `JWT_SECRET` is read when `SECRET_KEY` is not set. **Rotating SECRET_KEY invalidates all existing access tokens** (expected; users must re-auth or use refresh token where applicable). |
| `OTP_SECRET` | Optional | Used only for OTP HMAC hashing (server-side). If missing, `SECRET_KEY` is used. Changing it invalidates active OTP codes only (max 5 minutes), not refresh tokens. |
| `SMS_DISABLED` | Optional | Set to `true` / `1` / `yes` to skip sending SMS and log OTP with `[OTP_DEV]` (dev mode). Preserved in Step 2.2. |
| `SMS_PROVIDER` | Optional | `kavenegar` (default) or `dummy`. Provider-agnostic gateway (Step 2.2). |
| `KAVENEGAR_API_KEY` | When SMS_PROVIDER=kavenegar | API key from Kavenegar panel. |
| `KAVENEGAR_SENDER` | Optional | Sender line (e.g. short number). If empty, Kavenegar default is used. |
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

```bash
curl -s -X POST http://127.0.0.1:8000/auth/request_otp \
  -H "Content-Type: application/json" \
  -d '{"phone": "+989121234567"}'
```

Expected: `{"ok": true, "data": {"ok": true, "next": "verify_otp"}}`.  
With `SMS_DISABLED=true`, the 6-digit code is logged (e.g. `[OTP_DEV] phone=... code=...`).  
Optional: `Accept-Language: fa` or `en` / `ar` for OTP message language (default fa).

### 2. Verify OTP and get tokens

```bash
curl -s -X POST http://127.0.0.1:8000/auth/verify_otp \
  -H "Content-Type: application/json" \
  -d '{"phone": "+989121234567", "code": "123456"}'
```

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
| POST | `/auth/request_otp` | Body: `{ "phone": "+..." }`. Rate-limited (e.g. 3 per 10 min). |
| POST | `/auth/verify_otp` | Body: `{ "phone": "+...", "code": "123456" }`. Returns tokens. |
| GET | `/auth/me` | Header: `Authorization: Bearer <access_token>`. |
| POST | `/auth/refresh` | Header: `Authorization: Bearer <refresh_token>`. |
| POST | `/auth/logout` | Header: `Authorization: Bearer <refresh_token>`. Revokes that token. |

## Security notes

- **SECRET_KEY**: Must be ≥ 32 bytes; 64 bytes random recommended. Rotation invalidates existing access tokens (users re-auth or refresh).
- OTP and refresh tokens are stored hashed (HMAC-SHA256).
- OTP: max 5 verify attempts per code; expiry e.g. 5 min; rate limit 3 requests per 10 min per phone.
- Access token: JWT, default 60 min.
- Refresh token: opaque, stored in DB, default 30 days; revocable via `/auth/logout`.

---

## Step 2.2 – Real SMS (Kavenegar)

- When `SMS_DISABLED=false` and `SMS_PROVIDER=kavenegar`, OTP is sent via Kavenegar REST API. On send failure the API returns **503** with detail `SMS delivery unavailable` (request still succeeds from rate-limit/DB perspective; client can retry).
- OTP text: EN `Sedi verification code: {code}`, FA `کد تایید صدی: {code}`, AR `رمز التحقق من صدي: {code}` (from `Accept-Language`).

### Troubleshooting

- **No SMS received:** Check `KAVENEGAR_API_KEY` and Kavenegar panel (balance, sender, logs). Ensure phone is E.164 (e.g. +989121234567).
- **503 on request_otp:** Provider returned error or timeout. Check backend logs for `SMS send failed provider=... error=...`.

### Journalctl (backend logs)

```bash
# SMS/OTP related
journalctl -u sedi-backend.service -g "OTP_DEV|SMS send failed|SMS delivery" --no-pager -n 100

# Last 50 lines
journalctl -u sedi-backend.service -n 50 --no-pager
```

---

## Running tests (Step 2.2)

```bash
cd backend
pytest tests/test_auth_otp_v1.py -v
pytest tests/test_sms_gateway_kavenegar_dummy.py -v
```
