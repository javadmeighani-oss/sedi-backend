#!/usr/bin/env bash
# Reset public schema and run Alembic upgrade head.
# Requires CONFIRM_RESET=YES so it does not run accidentally.
# Usage: CONFIRM_RESET=YES ./reset_db_and_migrate.sh
# Run from repo root or from backend/ (script detects backend dir).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$BACKEND_DIR/.." && pwd)"

if [ -z "${DATABASE_URL}" ]; then
  echo "Error: DATABASE_URL is not set. Export it or source your .env." >&2
  exit 1
fi

if [ "${CONFIRM_RESET}" != "YES" ]; then
  echo "Error: CONFIRM_RESET=YES is required to run this script (prevents accidental reset)." >&2
  echo "Usage: CONFIRM_RESET=YES ./scripts/reset_db_and_migrate.sh" >&2
  exit 1
fi

# psql expects postgresql:// URI; SQLAlchemy may use postgresql+psycopg2://
PSQL_URL="${DATABASE_URL//+psycopg2/}"

echo "Dropping and recreating schema public..."
psql "$PSQL_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

echo "Running Alembic upgrade head..."
cd "$BACKEND_DIR"
alembic -c alembic.ini upgrade head

echo "Done. Start the app and verify e.g. curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/openapi.json"
