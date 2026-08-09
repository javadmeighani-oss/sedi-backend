"""Load authoritative I5 coverage manifest (§194 bootstrap YAML)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PACKAGE_ID = "I5-COVERAGE-MANIFEST-V1"
MANIFEST_RELATIVE = Path("backend/config/i5/coverage_manifest_v1.yaml")
EXPECTED_ENTITY_COUNT = 19
REQUIRED_ALIASES = {"D18": "ALS", "D19": "MS"}


class CoverageManifestError(ValueError):
    pass


def _repo_root() -> Path:
    # backend/app/services/i5/this_file -> repo root
    return Path(__file__).resolve().parents[4]


def manifest_path() -> Path:
    return _repo_root() / MANIFEST_RELATIVE


@lru_cache(maxsize=1)
def load_coverage_manifest() -> dict[str, Any]:
    path = manifest_path()
    if not path.is_file():
        raise CoverageManifestError(f"MANIFEST_MISSING:{path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CoverageManifestError("MANIFEST_NOT_OBJECT")
    entities = data.get("entities") or []
    if len(entities) != EXPECTED_ENTITY_COUNT:
        raise CoverageManifestError(f"ENTITY_COUNT_MISMATCH:{len(entities)}")
    ids = [str(e.get("id")) for e in entities]
    if len(set(ids)) != EXPECTED_ENTITY_COUNT:
        raise CoverageManifestError("DUPLICATE_ENTITY_IDS")
    for entity_id, alias in REQUIRED_ALIASES.items():
        row = next((e for e in entities if str(e.get("id")) == entity_id), None)
        if row is None or str(row.get("alias", "")).upper() != alias:
            raise CoverageManifestError(f"REQUIRED_ALIAS_MISSING:{entity_id}:{alias}")
    mapping = data.get("source_mapping") or {}
    missing = [eid for eid in ids if eid not in mapping or not mapping[eid]]
    if missing:
        raise CoverageManifestError(f"SOURCE_MAPPING_INCOMPLETE:{','.join(missing)}")
    return data


def entity_ids() -> list[str]:
    return [str(e["id"]) for e in load_coverage_manifest()["entities"]]


def source_mapped_count() -> tuple[int, int]:
    data = load_coverage_manifest()
    mapped = sum(1 for eid, srcs in (data.get("source_mapping") or {}).items() if srcs)
    return mapped, EXPECTED_ENTITY_COUNT


def publisher_families_from_allowlist(allowlist: dict[str, Any]) -> set[str]:
    families = set()
    for row in allowlist.get("sources") or []:
        if str(row.get("activation", "")).upper() == "YES":
            families.add(str(row.get("publisher_family") or row.get("allowed_domain") or ""))
    return {f for f in families if f}


__all__ = [
    "PACKAGE_ID",
    "EXPECTED_ENTITY_COUNT",
    "CoverageManifestError",
    "load_coverage_manifest",
    "entity_ids",
    "source_mapped_count",
    "publisher_families_from_allowlist",
    "manifest_path",
]
