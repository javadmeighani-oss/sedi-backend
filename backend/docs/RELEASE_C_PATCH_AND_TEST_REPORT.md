# Release C — Patch Ingest (preserve HTTPException) + Test Report

**Server layout (WorkingDirectory:** `/var/www/sedi/backend`**):**

| Item | Server path |
|------|-------------|
| Ingest route file | `app/routers/device.py` |
| Test script | `backend/scripts/release_c_final_tests.sh` |
| Evidence file | `backend/docs/release_c_test_evidence.md` |
| Server helper script | `backend/scripts/server_patch_ingest_and_run_release_c.sh` |
| Report template | `backend/docs/RELEASE_C_PATCH_AND_TEST_REPORT.md` |

---

## Exact diff / snippet (app/routers/device.py)

**File (on server):** `app/routers/device.py`  
**Function:** `ingest_device_event` (endpoint `@router.post("/ingest")`)

Required exception block:

```python
    except VitalValidationError as e:
        # Schema-driven validation errors -> 422
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    except DeviceRateLimitExceeded as e:
        # Return 429 (do not write to DB)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))

    except HTTPException as e:
        # Preserve correct HTTP status codes (e.g., 401/429/422). Do not swallow auth/validation exceptions.
        logger.debug("[DEVICE_INGEST] Re-raising HTTPException status_code=%s", e.status_code)
        raise

    except Exception as e:
        logger.exception("Failed to ingest event")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "code": "INTERNAL_ERROR", "message": "Failed to ingest event"},
        )
```

- `except HTTPException` must be immediately before `except Exception`.
- One generic exception handler only; unexpected errors return HTTP 500 via `JSONResponse`, not 200.

---

## How to run on the server

1. SSH: `ssh root@91.107.168.130`
2. Run (from service WorkingDirectory):
   ```bash
   cd /var/www/sedi/backend && bash ./backend/scripts/server_patch_ingest_and_run_release_c.sh
   ```
3. Full output is written to `/tmp/release_c_patch_report_<timestamp>.txt`.
4. Script exits with non-zero if either critical check fails:
   - "Ingest with token2 works (200 and event_id returned)" → FAIL, or
   - "Ingest with invalid/old token returns HTTP 401" → FAIL

**Server commands used inside the script:**

- Backup: `cp app/routers/device.py /tmp/device.py.bak.<ts>`
- Compile: `/var/www/sedi/backend/.venv/bin/python -m py_compile app/routers/device.py`
- Restart: `sudo systemctl restart sedi-backend.service`
- Tests: `bash ./backend/scripts/release_c_final_tests.sh`
- Evidence tail: `tail -n 120 backend/docs/release_c_test_evidence.md`
- Artifacts: `ls -1dt /tmp/sedi_release_c/* | head -1` and `ls -la "$LATEST"`

---

## Report sections (fill after run)

### B1) py_compile output

```
(paste here)
```

### B2) systemctl status (top 30 lines)

```
(paste here)
```

### B3) release_c_final_tests.sh output (including PASS/FAIL summary)

```
(paste here)
```

### C1) Latest artifact dir path + listing

```
LATEST_ARTIFACT_DIR=...
(paste ls -la output)
```

### C2) Tail of backend/docs/release_c_test_evidence.md (last 120 lines)

```
(paste here)
```

### C3) If any FAIL: journalctl (ingest/auth-related lines highlighted)

```
(paste if FAIL; highlight lines mentioning DEVICE_INGEST, 401, Invalid device token, HTTPException)
```

---

## Final conclusion

- **Release C PASS** if:
  - “Ingest with token2 works (200 and event_id returned)” → **PASS**
  - “Ingest with invalid/old token returns HTTP 401” → **PASS**
- **Release C NOT READY** if either of the above is **FAIL** — list exactly which checks failed.

---

*After running the script on the server, paste the script output into this report and set the final conclusion.*
