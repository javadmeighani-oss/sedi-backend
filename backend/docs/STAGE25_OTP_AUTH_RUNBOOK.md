# Stage 25 Step 1 – Phone OTP Auth Runbook

## Env vars

| Variable | Required | Description |
|----------|----------|-------------|
| `JWT_SECRET` | Production | Secret for signing access JWTs. Default: `sedi_secret_key_2025`. |
| `SMS_DISABLED` | Optional | Set to `true` / `1` / `yes` to skip sending SMS and log OTP with `[OTP_DEV]` (dev mode). |
| `BASE_URL` | Optional | Base URL for internal SMS gateway call (e.g. `http://127.0.0.1:8000`). Used when SMS is enabled. |
| `DATABASE_URL` | Yes | PostgreSQL connection string (existing). |

## Migrations

```bash
cd backend
alembic upgrade head
```

This applies `002_phone_otp` (adds `users.phone`, `otp_codes`, `refresh_tokens`).

## Curl examples

Base URL assumed: `http://127.0.0.1:8000`. Use `BASE_URL` or your host in production.

### 1. Request OTP

```bash
curl -s -X POST http://127.0.0.1:8000/auth/request_otp \
  -H "Content-Type: application/json" \
  -d '{"phone": "+989121234567"}'
```

Expected: `{"ok": true, "data": {"ok": true, "next": "verify_otp"}}`.  
With `SMS_DISABLED=true`, the 6-digit code is logged (e.g. `[OTP_DEV] phone=... code_message=...`).

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

- OTP and refresh tokens are stored hashed (bcrypt).
- OTP: max 5 verify attempts per code; expiry e.g. 5 min; rate limit 3 requests per 10 min per phone.
- Access token: JWT, default 60 min.
- Refresh token: opaque, stored in DB, default 30 days; revocable via `/auth/logout`.
