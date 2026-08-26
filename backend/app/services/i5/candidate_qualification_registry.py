"""Candidate qualification registry loader (not runtime activation authority)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REGISTRY_RELATIVE = Path("backend/config/i5/candidate_qualification_registry_v1.yaml")
ALLOWED_STATUSES = frozenset({"QUALIFIED", "REJECTED", "NEEDS_REVIEW"})


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "backend" / "config" / "i5").is_dir():
            return parent
    return Path.cwd()


@lru_cache(maxsize=1)
def load_candidate_qualification_registry() -> dict[str, Any]:
    path = _repo_root() / REGISTRY_RELATIVE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("activation_policy") != "QUALIFIED_DOES_NOT_AUTO_ACTIVATE":
        raise ValueError("BAD_CANDIDATE_REGISTRY_POLICY")
    return data


def candidate_rows() -> list[dict[str, Any]]:
    return list(load_candidate_qualification_registry().get("candidates") or [])


def qualification_counts() -> dict[str, int]:
    rows = candidate_rows()
    counts = {s: 0 for s in ALLOWED_STATUSES}
    for row in rows:
        status = str(row.get("qualification_status") or "").strip().upper()
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"INVALID_QUALIFICATION_STATUS:{status}")
        counts[status] += 1
    return counts


def assert_no_auto_activation_except(*, allowed_active_keys: set[str]) -> None:
    """Registry rows must remain activation=NO; runtime allowlist is separate."""
    for row in candidate_rows():
        act = str(row.get("activation") or "NO").strip().upper()
        if act in {"YES", "TRUE", "1"}:
            raise AssertionError(f"REGISTRY_ROW_ACTIVE:{row.get('candidate_id')}")
        cid = str(row.get("candidate_id") or "")
        # Even gate-authorized NIOSH stays activation=NO in registry.
        if cid and cid not in allowed_active_keys and act == "YES":
            raise AssertionError(f"UNAUTHORIZED_REGISTRY_ACTIVATION:{cid}")


__all__ = [
    "REGISTRY_RELATIVE",
    "ALLOWED_STATUSES",
    "load_candidate_qualification_registry",
    "candidate_rows",
    "qualification_counts",
    "assert_no_auto_activation_except",
]
