# V1 Contract: Auth

**Base path:** `/auth`  
**Envelope:** Success and error responses use `ApiResponse` (`ok`, `data`, `error`). Errors use `ApiError` (`code`, `message`, `details?`).

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /auth/request_otp | Request OTP for phone (SMS or dev log) |
| POST | /auth/otp/request | Alias for request_otp (REST-style) |
| POST | /auth/verify_otp | Verify OTP; create user if missing; return tokens |
| POST | /auth/otp/verify | Alias for verify_otp (REST-style) |
| GET | /auth/me | Current user info (requires Bearer) |
| POST | /auth/refresh | Exchange refresh token for new access + refresh |
| POST | /auth/logout | Revoke refresh token (Bearer = refresh token) |
| POST | /auth/set-passkey | Set passkey for user (may be disabled in prod) |
| POST | /auth/verify-passkey | Verify passkey (may be disabled in prod) |

---

## Headers

| Header | Required | Notes |
|--------|----------|------|
| Content-Type | Yes (POST) | application/json |
| Authorization | For /me, /refresh, /logout | Bearer &lt;access_token&gt; or Bearer &lt;refresh_token&gt; for /refresh, /logout |
| Accept-Language | Optional | OTP message language |
| X-Device-Info | Optional | Audit |
| X-Client-IP | Optional | Audit |

---

## 1. POST /auth/request_otp

**Request body:**
```json
{
  "phone": "+989123456789"
}
```

**Success (200):**
```json
{
  "ok": true,
  "data": {
    "ok": true,
    "next": "verify_otp"
  },
  "error": null
}
```

**Error (200 with envelope):**
```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "OTP_REQUEST_FAILED",
    "message": "Rate limit exceeded",
    "details": null
  }
}
```

---

## 2. POST /auth/verify_otp

**Request body:**
```json
{
  "phone": "+989123456789",
  "code": "123456"
}
```

**Success (200):**
```json
{
  "ok": true,
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 3600
  },
  "error": null
}
```

**Error (200):**
```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "OTP_INVALID",
    "message": "Invalid or expired code",
    "details": null
  }
}
```
Codes: `OTP_INVALID`, `OTP_EXPIRED`, `TOO_MANY_ATTEMPTS`.

---

## 3. GET /auth/me

**Headers:** `Authorization: Bearer <access_token>`

**Success (200):**
```json
{
  "ok": true,
  "data": {
    "user_id": 1,
    "phone": "+989123456789",
    "display_name": "User",
    "language": "en"
  },
  "error": null
}
```

**Error (401):** FastAPI raises HTTPException; body may be non-envelope. Contract: client should treat 401 as unauthorized.

---

## 4. POST /auth/refresh

**Headers:** `Authorization: Bearer <refresh_token>`

**Success (200):**
```json
{
  "ok": true,
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 3600
  },
  "error": null
}
```

**Error (401):** Invalid or expired refresh token.

---

## 5. POST /auth/logout

**Headers:** `Authorization: Bearer <refresh_token>`

**Success (200):**
```json
{
  "ok": true,
  "data": { "revoked": true },
  "error": null
}
```

---

## 6. POST /auth/set-passkey, POST /auth/verify-passkey

**Query params:** `user_id`, `passkey` (or body depending on implementation).

**Success (200):** `{"ok": true, "data": {"user_id": 1, "passkey_set": true}, "error": null}` or `{"verified": true}`.

**Error (200):** `{"ok": false, "error": {"code": "USER_NOT_FOUND", "message": "User not found."}}`.  
Codes: `USER_NOT_FOUND`, `INVALID_KEY`, `LOCKED`.  
Note: In prod/V1 these endpoints may return 404 (disabled).

---

## Notes

- All success responses use `ok: true`, `data` set, `error: null`.
- All business errors (OTP, passkey) use 200 + envelope with `ok: false` and `error: { code, message }`.
- HTTP 401 is used for missing/invalid Bearer token (no envelope required).
