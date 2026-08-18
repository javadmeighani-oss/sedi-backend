"""Canonical Javad-editable trusted-source control manifest (I5-S49).

Runtime crawler activation derives ONLY from governed active entries in
``backend/config/i5/multisource_activation_allowlist_v1.yaml``.
PostgreSQL GSP/registry tables remain runtime audit state.
``seed_registry.py`` is bootstrap-only and MUST NOT be runtime activation authority.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

PACKAGE_ID = "I5-TRUSTED-SOURCE-MANIFEST-V2"
MANIFEST_RELATIVE = Path("backend/config/i5/multisource_activation_allowlist_v1.yaml")
MANIFEST_AUTHORITY = "CANONICAL_TRUSTED_SOURCE_CONTROL"
SEED_REGISTRY_BOOTSTRAP_ONLY = True
PYTHON_SEED_RUNTIME_AUTHORITY = False

_ALLOWED_RIGHTS = frozenset({"OGL", "PUBLIC_DOMAIN", "APPROVED", "ACCEPTABLE"})
_ALLOWED_EVIDENCE = frozenset({"LOW", "MODERATE", "HIGH"})


class TrustedSourceManifestError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        message = code if not detail else f"{code}:{detail}"
        super().__init__(message)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


@lru_cache(maxsize=1)
def load_trusted_source_manifest() -> dict[str, Any]:
    path = _repo_root() / MANIFEST_RELATIVE
    if not path.is_file():
        raise TrustedSourceManifestError("TRUSTED_SOURCE_MANIFEST_MISSING", str(path))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("sources"):
        raise TrustedSourceManifestError("TRUSTED_SOURCE_MANIFEST_INVALID")
    authority = str(data.get("manifest_authority") or "").strip()
    if authority and authority != MANIFEST_AUTHORITY:
        raise TrustedSourceManifestError("TRUSTED_SOURCE_MANIFEST_AUTHORITY_MISMATCH", authority)
    return data


def _activation_yes(value: Any) -> bool:
    if value is True:
        return True
    return str(value or "").strip().upper() in {"YES", "TRUE", "1"}


def _low_risk_flag(value: Any) -> bool:
    return str(value or "NO").strip().upper() in {"YES", "TRUE", "1"}


def manifest_rows() -> list[dict[str, Any]]:
    return list(load_trusted_source_manifest().get("sources") or [])


def active_manifest_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in manifest_rows():
        if not _activation_yes(row.get("activation")):
            continue
        key = str(row.get("source_key") or "").strip()
        url = str(row.get("exact_url") or "").strip()
        if not key or not url:
            raise TrustedSourceManifestError("MANIFEST_ROW_INCOMPLETE", key or "missing_key")
        rights = str(row.get("rights_terms_state") or "UNKNOWN").upper()
        if rights not in _ALLOWED_RIGHTS:
            raise TrustedSourceManifestError("MANIFEST_RIGHTS_FAIL_CLOSED", f"{key}:{rights}")
        low_risk = row.get("governed_low_risk_eligibility", "NO")
        if _low_risk_flag(low_risk):
            strength = str(row.get("eligibility_evidence_strength") or "LOW").upper()
            if strength not in _ALLOWED_EVIDENCE:
                raise TrustedSourceManifestError("MANIFEST_EVIDENCE_STRENGTH_INVALID", f"{key}:{strength}")
        rows.append(row)
    if len(rows) < 2:
        raise TrustedSourceManifestError("MANIFEST_TOO_SMALL", str(len(rows)))
    families = {str(r.get("publisher_family") or r.get("allowed_domain")) for r in rows}
    if len(families) < 4:
        raise TrustedSourceManifestError("MANIFEST_PUBLISHER_DIVERSITY_BELOW_FLOOR", str(sorted(families)))
    return rows


def active_source_keys() -> frozenset[str]:
    return frozenset(str(r["source_key"]) for r in active_manifest_rows())


def manifest_row_for_key(source_key: str) -> Optional[dict[str, Any]]:
    for row in manifest_rows():
        if str(row.get("source_key")) == source_key:
            return row
    return None


def governed_low_risk_eligible(source_key: str) -> bool:
    row = manifest_row_for_key(source_key)
    if row is None or not _activation_yes(row.get("activation")):
        return False
    return _low_risk_flag(row.get("governed_low_risk_eligibility"))


def manifest_attribution(source_key: str) -> dict[str, str]:
    row = manifest_row_for_key(source_key) or {}
    publisher = str(row.get("publisher") or "Official source")
    rights = str(row.get("rights_terms_state") or "UNKNOWN").upper()
    license_label = "OGL-v3.0" if rights == "OGL" else "PUBLIC_DOMAIN" if rights == "PUBLIC_DOMAIN" else rights
    notes = str(row.get("license_notes") or "")
    required = f"Information from {publisher}"
    if notes:
        required = f"{required}. {notes[:200]}"
    return {
        "required_text": required,
        "license": license_label,
        "publisher": publisher,
    }


def assert_runtime_activation_key_allowed(source_key: str) -> None:
    """Fail-closed: runtime fetch activation must be manifest-governed."""
    if source_key not in active_source_keys():
        raise TrustedSourceManifestError("RUNTIME_ACTIVATION_NOT_IN_MANIFEST", source_key)


def validate_manifest_contract() -> dict[str, Any]:
    rows = active_manifest_rows()
    low_risk = [str(r["source_key"]) for r in rows if governed_low_risk_eligible(str(r["source_key"]))]
    return {
        "manifest_authority": MANIFEST_AUTHORITY,
        "manifest_path": str(MANIFEST_RELATIVE),
        "active_count": len(rows),
        "low_risk_count": len(low_risk),
        "low_risk_keys": low_risk,
        "seed_registry_bootstrap_only": SEED_REGISTRY_BOOTSTRAP_ONLY,
        "python_seed_runtime_authority": PYTHON_SEED_RUNTIME_AUTHORITY,
    }
