# Ops Verification Checklist

Quick SQL and API checks for notification delivery, push tokens, and OTP/SMS health.

## 1. Failed notifications (last_error)

```sql
SELECT id, user_id, type, status, provider, last_error, created_at
FROM public.notifications
WHERE status = 'failed'
   OR last_error IS NOT NULL AND last_error != ''
ORDER BY created_at DESC
LIMIT 20;
```

```sql
SELECT status, COUNT(*) FROM public.notifications GROUP BY status;
```

## 2. Active push tokens per user

```sql
SELECT id, user_id, platform, LEFT(fcm_token, 8) || '...' AS token_prefix, is_active, last_seen_at
FROM public.push_devices
WHERE user_id = :user_id  -- replace with actual user_id
  AND is_active = true;
```

```sql
SELECT user_id, COUNT(*) AS active_tokens
FROM public.push_devices
WHERE is_active = true
GROUP BY user_id;
```

## 3. Recent OTP send attempts

OTP attempts are stored in `otp_codes`. There is no separate `last_send_error` column; failures are logged. To inspect recent OTP activity:

```sql
SELECT id, phone, sent_count, attempts, created_at
FROM public.otp_codes
ORDER BY created_at DESC
LIMIT 20;
```

**Note:** When SMS send fails (e.g. missing `MEDIANA_API_KEY`), the API returns an error to the client instead of `dev_code`. Check application logs for `[OTP] SMS send failed` entries.

## 4. Environment variables (manual check)

- **SMS:** `MEDIANA_API_KEY`, `MEDIANA_OTP_PATTERN_CODE`, `SMS_PROVIDER` (default: mediana), `SMS_DISABLED`
- **FCM:** `FCM_PROJECT_ID`, `FCM_SERVICE_ACCOUNT_JSON`, `FCM_DISABLED`

## 5. OTP request paths

| Path | Notes |
|------|------|
| POST /auth/request_otp | Canonical |
| POST /auth/otp/request | Alias (REST-style) |
| POST /auth/verify_otp | Canonical |
| POST /auth/otp/verify | Alias |

## 6. Device disconnect notification duplicates

After the fix (IntegrityError handling + advisory lock), duplicates should be rare. To verify:

```sql
SELECT dedupe_key, COUNT(*) AS cnt
FROM public.notifications
WHERE type = 'device_disconnected'
  AND dedupe_key IS NOT NULL
GROUP BY dedupe_key
HAVING COUNT(*) > 1;
```

Expected: 0 rows.
