# Sedi Backend V1 — Operational Runbook

**Stack:** Ubuntu + systemd (`sedi-backend.service`), Uvicorn → FastAPI `backend.app.main`, Postgres, Alembic. APScheduler runs jobs (deliver_pending, morning, engagement, device_disconnected, medication_reminders).

---

## 1. Quick status checks

**Service status**
```bash
sudo systemctl status sedi-backend.service
```
- Check `Active: active (running)` and **MainPID** (e.g. `Main PID: 12345`).

**Main process and runtime env (mask secrets)**
```bash
PID=$(systemctl show sedi-backend.service -p MainPID --value)
# If MainPID is 0, service is not running
[ "$PID" = "0" ] && echo "Service not running" || \
  sudo tr '\0' '\n' < "/proc/$PID/environ" | grep -E '^[A-Z_]' | sed 's/DATABASE_URL=.*/DATABASE_URL=***MASKED***/'
```
- Use this to confirm env (ENV, APP_ENV, etc.) without printing `DATABASE_URL` or other secrets.

---

## 2. Start / stop / restart

**Restart**
```bash
sudo systemctl restart sedi-backend.service
```

**Verify after restart**
- Listening on port 8000:
  ```bash
  sudo ss -tlnp | grep 8000
  # or: curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health
  ```
- Health OK:
  ```bash
  curl -s http://127.0.0.1:8000/health | head -5
  ```

**Stop / start**
```bash
sudo systemctl stop sedi-backend.service
sudo systemctl start sedi-backend.service
```

---

## 3. Database checks

**Alembic current revision (use app env, do not hardcode URL)**  
Export `DATABASE_URL` from the running process if needed, then:
```bash
cd /var/www/sedi/backend   # or your app root
export DATABASE_URL="$(sudo tr '\0' '\n' < /proc/$(systemctl show sedi-backend.service -p MainPID --value)/environ 2>/dev/null | grep '^DATABASE_URL=' | cut -d= -f2-)"
# If you must type it: never paste into docs or logs; use a masked echo for verification only:
# echo "DATABASE_URL is set: $( [ -n "$DATABASE_URL" ] && echo yes || echo no )"
alembic current
alembic heads
```
- **Expected head:** `010_add_notification_guard_state` (or later if new migrations added).
- Mismatch: see §7 Common issues.

**Optional: psql connectivity**
```bash
# Only if DATABASE_URL is exported in your shell (e.g. from /proc/... as above)
psql "$DATABASE_URL" -c "SELECT 1"
```

---

## 4. Health checks (exact curl commands)

**GET /health** (lightweight; no ApiResponse wrapper)
```bash
curl -i http://127.0.0.1:8000/health
```
- **Semantics:** 200 JSON with `ok`, `version`, `env` (prod/dev), `db` (ok/error), `timestamp`. No secrets. Use for monitoring.
- **Guarantee:** App is up and DB connectivity was checked (SELECT 1).

**GET /healthz** (ApiResponse style; 503 if DB fails)
```bash
curl -i http://127.0.0.1:8000/healthz
```
- **Semantics:** 200 with `ok`, `data.db_ok`, `data.server_time`, `data.version`, `error`. Returns **503** if DB check fails.
- **Guarantee:** Suitable for load balancer / k8s readiness; failing DB → 503.

---

## 5. Scheduler & notifications checks

**Confirm deliver_pending is running (logs)**
- Scheduler logs with tag `[Sedi Scheduler]`; delivery service uses `[NOTIF]`.
- Recent deliver_pending runs:
  ```bash
  sudo journalctl -u sedi-backend.service --since "30 min ago" --no-pager | grep -E '\[Sedi Scheduler\] deliver_pending|\[NOTIF\] deliver_pending'
  ```
- Expected pattern: `[Sedi Scheduler] deliver_pending job start` and `deliver_pending job end duration_ms=... sent_count=...`, or `[NOTIF] deliver_pending start batch_size=... pending_count=...` and `deliver_pending end duration_ms=... sent_count=...`.

**Interpret pending_count=0**
- In `[NOTIF] deliver_pending start batch_size=... pending_count=N`, `pending_count` is the number of queued notifications in that batch.
- `pending_count=0` means no pending notifications in the batch (outbox empty or already processed). Not an error.

**Admin delivery health (optional)**  
If `ADMIN_TOKEN` and `X-Admin-Token` are configured:
```bash
curl -s -H "X-Admin-Token: YOUR_ADMIN_TOKEN" http://127.0.0.1:8000/notifications/admin/health
```
- Contains `pending_count`, `last_deliver_pending_run_at`, etc. **Never log or paste the token.**

---

## 6. Log inspection recipes

**Last 30 minutes**
```bash
sudo journalctl -u sedi-backend.service --since "30 min ago" --no-pager
```

**Last N lines**
```bash
sudo journalctl -u sedi-backend.service -n 200 --no-pager
```

**Follow live**
```bash
sudo journalctl -u sedi-backend.service -f
```

**Errors / exceptions**
```bash
sudo journalctl -u sedi-backend.service --since "1 hour ago" --no-pager | grep -iE 'error|exception|traceback|failed'
```

**Scheduler and delivery only**
```bash
sudo journalctl -u sedi-backend.service --since "1 hour ago" --no-pager | grep -E '\[Sedi Scheduler\]|\[NOTIF\]'
```

---

## 7. Common issues + fixes

**DB auth errors in CLI (alembic, psql)**  
- Cause: `DATABASE_URL` not set in your shell; app gets it from systemd/env.  
- Fix: Source from the running process (see §3) or from a secure env file; **never** paste URLs into docs or logs.

**Migration mismatch (alembic current ≠ heads)**  
- Symptoms: App or migrations fail with "can't locate revision", schema errors.  
- Fix: Ensure same codebase and DB; run `alembic upgrade head` from app root with correct `DATABASE_URL`. Backup DB before upgrading.

**Service restart loops**  
- Check logs: `sudo journalctl -u sedi-backend.service -n 100 --no-pager`.  
- Common: missing or wrong `DATABASE_URL`, port 8000 in use, import/runtime error at startup. Fix env or code and restart.

---

## 8. Safety notes

- **Never** print or log `DATABASE_URL`, `ADMIN_TOKEN`, API keys, or any secret. Use masking (e.g. `sed 's/DATABASE_URL=.*/DATABASE_URL=***MASKED***/'`) when showing env.
- Prefer reading env from `/proc/$PID/environ` for the running process instead of storing secrets in extra files.
- Before running destructive DB commands, confirm DB and take backups.

---

## Daily checklist

- [ ] `systemctl status sedi-backend.service` → active (running).
- [ ] `curl -s http://127.0.0.1:8000/health` → `"ok": true`, `"db": "ok"`.
- [ ] Recent logs: no repeated errors; `[Sedi Scheduler]` / `[NOTIF]` deliver_pending runs present if expected.

---

## Before release checklist

- [ ] `alembic current` matches expected head (e.g. `010_add_notification_guard_state`).
- [ ] `curl -i http://127.0.0.1:8000/health` and `curl -i http://127.0.0.1:8000/healthz` return 200 (503 on healthz only if DB down).
- [ ] No unhandled exceptions in last 30 min of logs.
- [ ] Scheduler started: logs show `[Sedi Scheduler] Background scheduler started successfully`.
- [ ] Env and secrets: verified without printing secrets (masked commands only).
