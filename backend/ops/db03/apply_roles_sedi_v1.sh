#!/usr/bin/env bash
# Thin wrapper: fail-closed role apply via Python applicator.
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python "${SCRIPT_DIR}/apply_roles_sedi_v1.py"
