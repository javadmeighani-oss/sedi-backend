#!/usr/bin/env bash
# Run from repo root (parent of backend/). Ensures only backend/tests is collected:
# - quarantines root test_*.py, tests/, backend/backend into _quarantine_tests
# - removes __pycache__, .pyc, .pytest_cache
# Usage: ./scripts/pytest_clean_collect.sh [--sync] [--run]
#   --sync  git fetch + reset --hard origin/main first
#   --run   run pytest -q after cleanup (default: only collect-only)

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [[ "$*" == *--sync* ]]; then
  echo "[pytest_clean_collect] Syncing to origin/main..."
  git fetch origin
  git reset --hard origin/main
  git log -1 --oneline
fi

echo "[pytest_clean_collect] Quarantine duplicates..."
mkdir -p _quarantine_tests
shopt -s nullglob 2>/dev/null || true
for f in test_*.py; do
  [[ -f "$f" ]] && mv -v "$f" _quarantine_tests/ || true
done
[[ -d tests ]] && mv -v tests _quarantine_tests/tests_root || true
[[ -d backend/backend ]] && mv -v backend/backend _quarantine_tests/backend_backend || true

echo "[pytest_clean_collect] Clean Python caches..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
rm -rf .pytest_cache 2>/dev/null || true

echo "[pytest_clean_collect] Collection check (first 30 lines)..."
python -m pytest --collect-only -q 2>&1 | head -n 30

if [[ "$*" == *--run* ]]; then
  echo "[pytest_clean_collect] Running pytest -q..."
  python -m pytest -q
fi
