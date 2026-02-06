#!/usr/bin/env bash
# Server script: run from /var/www/sedi/backend (service WorkingDirectory).
# Paths: app/routers/device.py, backend/scripts/release_c_final_tests.sh, backend/docs/release_c_test_evidence.md
# Usage: cd /var/www/sedi/backend && bash ./backend/scripts/server_patch_ingest_and_run_release_c.sh

set -euo pipefail

WORK_DIR="/var/www/sedi/backend"
REPORT_FILE="/tmp/release_c_patch_report_$(date +%s).txt"

# Tee all output to report file (and stdout)
exec > >(tee "$REPORT_FILE") 2>&1

echo "=== Working directory: $WORK_DIR ==="
cd "$WORK_DIR"

# ---- Part A: Backup, verify/patch ingest, ensure import ----
echo ""
echo "========== Part A) Backup and patch app/routers/device.py =========="

# A1) Backup
cp app/routers/device.py "/tmp/device.py.bak.$(date +%s)"
echo "A1) Backup created: /tmp/device.py.bak.<ts>"

# A2) Ensure JSONResponse import
if ! grep -q "from fastapi.responses import JSONResponse" app/routers/device.py; then
  sed -i '/^from fastapi import /a from fastapi.responses import JSONResponse' app/routers/device.py
  echo "A2) Added from fastapi.responses import JSONResponse"
else
  echo "A2) from fastapi.responses import JSONResponse already present"
fi

# A3) Patch exception block by markers (no function name). Idempotent: skip if HTTPException already before Exception.
python3 << 'PYEOF'
path = "app/routers/device.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Locate the unique block by markers: VitalValidationError then DeviceRateLimitExceeded then Exception (within a window)
WINDOW = 3500
start = content.find("except VitalValidationError as e:")
if start == -1:
    start = content.find("except VitalValidationError ")
if start == -1:
    print("A3) ERROR: except VitalValidationError not found")
    exit(1)

window = content[start : start + WINDOW]
# Must see DeviceRateLimitExceeded and Exception in order in this window
if "except DeviceRateLimitExceeded" not in window or "except Exception as e:" not in window:
    print("A3) ERROR: exception chain (VitalValidationError -> DeviceRateLimitExceeded -> Exception) not found in window")
    exit(1)

# Idempotent: if HTTPException already present before Exception in this block, skip
idx_http = window.find("except HTTPException")
idx_generic = window.find("except Exception as e:")
if idx_http >= 0 and idx_generic >= 0 and idx_http < idx_generic and "raise" in window[idx_http:idx_generic]:
    print("A3) SKIP: already patched")
    exit(0)

# Find line-based span (preserve indentation; block is inside try)
lines = content.splitlines(keepends=True)
start_i = None
for i, line in enumerate(lines):
    if "except VitalValidationError" in line:
        start_i = i
        break
if start_i is None:
    print("A3) ERROR: could not find except VitalValidationError block")
    exit(1)

# End at last "        )" in this exception chain (before next def or @router)
end_i = None
for j in range(start_i, len(lines)):
    if lines[j].strip().startswith("def ") or (
        lines[j].strip().startswith("@") and "router" in lines[j]
    ):
        break
    if lines[j].rstrip() == "        )":
        end_i = j
if end_i is None:
    print("A3) ERROR: could not find end of exception block")
    exit(1)

new_block = """    except VitalValidationError as e:
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
"""

new_content = "".join(lines[:start_i]) + new_block + "\n" + "".join(lines[end_i + 1 :])
with open(path, "w", encoding="utf-8") as f:
    f.write(new_content)
print("A3) Patched exception block (HTTPException before Exception)")
PYEOF

echo "A3) Verify order:"
grep -n "except HTTPException\|except Exception as e:" app/routers/device.py || true

# ---- Part B: Compile, restart, run tests ----
echo ""
echo "========== Part B) Verify, restart, run tests =========="

# B1) py_compile (full path to venv python)
PYTHON="/var/www/sedi/backend/.venv/bin/python"
echo "B1) py_compile app/routers/device.py:"
if [ -x "$PYTHON" ]; then
  "$PYTHON" -m py_compile app/routers/device.py && echo "  OK" || { echo "  FAIL"; exit 1; }
else
  python3 -m py_compile app/routers/device.py && echo "  OK" || { echo "  FAIL"; exit 1; }
fi

# B2) Restart service, status
echo ""
echo "B2) systemctl restart + status (first 30 lines):"
sudo systemctl restart sedi-backend.service
sudo systemctl status sedi-backend.service --no-pager | head -n 30

# B3) Run Release C tests (server path: backend/scripts/release_c_final_tests.sh)
echo ""
echo "B3) Release C final tests (bash ./backend/scripts/release_c_final_tests.sh):"
bash ./backend/scripts/release_c_final_tests.sh || true

# ---- Part C: Evidence ----
echo ""
echo "========== Part C) Evidence =========="

echo "C1) Latest artifact dir under /tmp/sedi_release_c:"
ls -1dt /tmp/sedi_release_c/* 2>/dev/null | head -n 3 || echo "  (none)"
LATEST="$(ls -1dt /tmp/sedi_release_c/* 2>/dev/null | head -n 1)"
echo "LATEST_ARTIFACT_DIR=$LATEST"
[ -n "$LATEST" ] && ls -la "$LATEST" || true

echo ""
echo "C2) Tail (last 120 lines) of backend/docs/release_c_test_evidence.md:"
if [ -f backend/docs/release_c_test_evidence.md ]; then
  tail -n 120 backend/docs/release_c_test_evidence.md
else
  echo "  (file not found)"
fi

echo ""
echo "C3) If any FAIL in PASS/FAIL summary, journalctl:"
HAS_FAIL=0
if [ -n "$LATEST" ] && [ -f "${LATEST}/summary.tsv" ]; then
  if awk -F'\t' 'NR>1 && $2=="FAIL"' "${LATEST}/summary.tsv" | read -r _; then
    HAS_FAIL=1
  fi
fi
if [ "$HAS_FAIL" = 1 ]; then
  sudo journalctl -u sedi-backend.service -n 200 --no-pager
else
  echo "  (No FAIL in summary; skipping journalctl)"
fi

echo ""
echo "========== Report written to: $REPORT_FILE =========="

# Exit non-zero if either critical ingest check failed
EXIT_CODE=0
if [ -n "$LATEST" ] && [ -f "${LATEST}/summary.tsv" ]; then
  while IFS=$'\t' read -r test_name result _; do
    [ "$result" != "FAIL" ] && continue
    case "$test_name" in
      "Ingest with token2 works (200 and event_id returned)")
        echo "RELEASE C: FAIL - Ingest with token2 works -> FAIL"
        EXIT_CODE=1
        ;;
      "Ingest with invalid/old token returns HTTP 401")
        echo "RELEASE C: FAIL - Ingest with invalid/old token returns HTTP 401 -> FAIL"
        EXIT_CODE=1
        ;;
    esac
  done < <(awk -F'\t' 'NR>1' "${LATEST}/summary.tsv")
fi
exit "$EXIT_CODE"
