# Production Env & Rollback Runbook (Freeze B3)

**Purpose:** Environment variables for the backend are set via a systemd drop-in (`override.conf`). This runbook is the single authoritative reference for production env keys and rollback toggles. To verify which keys are effective, inspect the running process env (keys only, values masked).

---

## 1. Authoritative env table

| Key | Required | Description |
|-----|----------|-------------|
| **DATABASE_URL** | Yes | PostgreSQL connection URL. **NEVER log it.** Mask in logs as `postgresql://***@***/dbname` or similar (show scheme + host hint only). |
| **SECRET_KEY** | Yes | ≥ 32 bytes; used for JWT signing and HMAC (OTP/refresh when OTP_SECRET/REFRESH_SECRET not set). Rotating invalidates access tokens. |
| **ADMIN_TOKEN** | Optional (recommended) | Protects admin endpoints (e.g. notifications/admin). Set a strong random value in prod. |
| **ENV** | Recommended | `prod` or `dev`. When `prod`, passkey endpoints return 404. |
| **DEBUG** | Recommended | `false` in production. When `false` (or ENV=prod), passkey endpoints disabled. |
| **OTP_SECRET** | Optional | Overrides OTP HMAC secret; default SECRET_KEY. |
| **REFRESH_SECRET** | Optional | Overrides refresh-token HMAC secret; default SECRET_KEY. |
| **SMS_DISABLED** | Optional | `true` / `false`. When `true`, OTP is logged only (no SMS sent). Use for dev; in prod set `false` and use real gateway. |
| **FCM_DISABLED** | Optional | `true` / `false`. When `true`, push delivery is disabled (logs only). |
| **DEVICE_AUTH_MODE** | Optional | `hybrid` / `db_only` / `legacy_only`. |
| **DEVICE_INGEST_TOKEN** | Optional (legacy) | Legacy device ingest auth. |
| **ENGAGEMENT_MAX_PER_DAY** | Optional | Cap engagement notifications per user per day (e.g. `3`). Use `0` to disable. |
| **QUIET_HOURS_START** / **QUIET_HOURS_END** | Optional | If used by notification logic (e.g. HH:MM). |

**Note:** Passkey endpoints (`/auth/set-passkey`, `/auth/verify-passkey`) are disabled when `ENV=prod` or `DEBUG=false`.

---

## 2. Rollback toggles (copy-paste safe)

Add or update in `/etc/systemd/system/sedi-backend.service.d/override.conf`, then `sudo systemctl daemon-reload` and `sudo systemctl restart sedi-backend.service`.

| Goal | Env line |
|------|----------|
| Disable push | `Environment="FCM_DISABLED=true"` |
| Disable engagement spam | `Environment="ENGAGEMENT_MAX_PER_DAY=0"` |
| Disable SMS gateway (dev only) | `Environment="SMS_DISABLED=true"` — **In prod, prefer fixing gateway; use only for emergency.** |
| Safe-mode notifications | If deliver job reads FCM_DISABLED/ENGAGEMENT_MAX_PER_DAY, the toggles above reduce send load. |

---

## 3. View current effective env (keys only, masked)

- **Drop-in path:** `/etc/systemd/system/sedi-backend.service.d/override.conf`
- **Active process env:** Keys (and masked presence of secrets) from the running process:

```bash
PID=$(systemctl show sedi-backend.service -p MainPID --value)
if [ -n "$PID" ] && [ "$PID" != "0" ]; then
  echo "=== Env keys (no values) ==="
  tr '\0' '\n' < /proc/$PID/environ | cut -d= -f1 | sort
  echo "=== DATABASE_URL present (masked) ==="
  tr '\0' '\n' < /proc/$PID/environ | grep -q '^DATABASE_URL=' && echo "DATABASE_URL=***" || echo "DATABASE_URL not set"
  echo "=== SECRET_KEY present (masked) ==="
  tr '\0' '\n' < /proc/$PID/environ | grep -q '^SECRET_KEY=' && echo "SECRET_KEY=***" || echo "SECRET_KEY not set"
else
  echo "Service not running or MainPID not found"
fi
```

---

## 4. Change env (systemd drop-in), reload, restart

1. **Edit override:**
   ```bash
   sudo mkdir -p /etc/systemd/system/sedi-backend.service.d
   sudo nano /etc/systemd/system/sedi-backend.service.d/override.conf
   ```
   Add or change lines like:
   ```ini
   [Service]
   Environment="ENV=prod"
   Environment="DEBUG=false"
   Environment="SECRET_KEY=your-64-byte-secret-here"
   Environment="DATABASE_URL=postgresql://user:pass@host:5432/dbname"
   ```

2. **Reload and restart:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart sedi-backend.service
   ```

3. **Verify:**
   - Service: `sudo systemctl status sedi-backend.service --no-pager`
   - Health: `curl -s http://localhost:8000/health | head -5`
   - Env keys (masked): run the script in section 3 above.

---

*No secrets in this doc. Keep override.conf and any EnvironmentFile restricted (e.g. mode 600) and out of version control.*
