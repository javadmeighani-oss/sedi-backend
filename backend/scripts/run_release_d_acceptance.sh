#!/usr/bin/env bash
# Run Release D acceptance tests safely on the server using sedi_test_db (never production).
# Run from backend root: ./scripts/run_release_d_acceptance.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BACKEND_ROOT"

# ----- Safety: refuse if current DATABASE_URL points to production -----
if [[ -n "${DATABASE_URL:-}" ]]; then
  if echo "$DATABASE_URL" | grep -qE '/sedi_db(\?|$)'; then
    echo "ERROR: DATABASE_URL points to production DB (sedi_db). Refusing to run."
    exit 1
  fi
fi

# ----- A) Ensure venv is active -----
if [[ -z "${VIRTUAL_ENV:-}" ]] && [[ -f .venv/bin/activate ]]; then
  echo "Activating .venv..."
  set +u
  source .venv/bin/activate
  set -u
fi

# ----- B) Verify python exists -----
python --version

# ----- C) Ensure pytest exists -----
if ! python -m pytest --version &>/dev/null; then
  echo "ERROR: pytest not found. Install with: pip install pytest"
  exit 1
fi

# ----- D) Ensure Postgres test DB exists -----
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='sedi_test_db'" | grep -q 1; then
  echo "Test DB sedi_test_db already exists."
else
  echo "Creating test DB sedi_test_db..."
  sudo -u postgres psql -c "CREATE DATABASE sedi_test_db;"
fi
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE sedi_test_db TO sedi_user;" 2>/dev/null || true

# ----- E) Run compile + tests with DATABASE_URL override only for these commands -----
export DATABASE_URL="postgresql://sedi_user:sedi123%21%40%23@localhost:5432/sedi_test_db"
python -m py_compile tests/acceptance/test_release_d.py
python -m pytest -q tests/acceptance/test_release_d.py -v --tb=short

# ----- F) Success -----
echo "Release D acceptance tests completed successfully."
