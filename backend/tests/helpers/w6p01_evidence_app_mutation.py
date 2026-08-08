"""I5-IMPL-W6-P01 — scope-aware `backend/app/**` mutation sentinel (pure, no GH/CI deps).

Extracted from the `i5-w6p02-offline-e2e` CI evidence-pack step so the allowlist
logic can be unit tested without a GitHub Actions runner. The prior sentinel
failed the gate on ANY `backend/app/**` change since `GATE_START_SHA`; W6-P01
authorizes a small, explicit set of application paths (the controlled live
acquisition surface) while every other `backend/app/**` path remains blocked
(fail-closed — never skipped, never an unconditional PASS).
"""
from __future__ import annotations

from typing import Iterable, List, Sequence

APP_ROOT_PREFIX = "backend/app/"


def _extract_path(name_status_line: str) -> str:
    """Return the (new) path from one `git diff --name-status` line, or ''.

    Handles plain `STATUS\\tpath` lines and rename/copy lines
    (`R100\\told_path\\tnew_path`) by taking the last tab-separated field.
    """
    line = name_status_line.rstrip("\r\n")
    if not line.strip():
        return ""
    parts = line.split("\t")
    if len(parts) < 2:
        return ""
    return parts[-1].strip()


def _is_allowed(path: str, allowlist_prefixes: Sequence[str]) -> bool:
    for raw in allowlist_prefixes:
        prefix = (raw or "").strip()
        if not prefix:
            continue
        if prefix.endswith("/**"):
            root = prefix[: -len("/**")]
            if path == root or path.startswith(root + "/"):
                return True
        elif prefix.endswith("/"):
            if path.startswith(prefix):
                return True
        elif path == prefix:
            return True
    return False


def unexpected_app_mutations(
    name_status_lines: Iterable[str],
    allowlist_prefixes: Sequence[str],
) -> List[str]:
    """Return `backend/app/**` paths from a `git diff --name-status` listing that
    are NOT covered by `allowlist_prefixes`.

    Paths outside `backend/app/` are ignored — this sentinel only governs the
    application source tree; `alembic/` migrations and `backend/tests/**` are
    intentionally unrestricted by this specific gate.

    `allowlist_prefixes` entries may be:
      - an exact file path (e.g. ``backend/app/services/i5/metrics.py``)
      - a directory wildcard ending in ``/**`` (e.g. ``backend/app/services/i5/adapters/**``)
      - a bare directory prefix ending in ``/``
    """
    unexpected: List[str] = []
    for line in name_status_lines:
        path = _extract_path(line)
        if not path or not path.startswith(APP_ROOT_PREFIX):
            continue
        if _is_allowed(path, allowlist_prefixes):
            continue
        unexpected.append(path)
    return unexpected
