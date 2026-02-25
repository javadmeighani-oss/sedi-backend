"""
Utility for OpenAPI snapshot used by V1 contract freeze tests.

Regenerate snapshot (Linux/macOS):
PYTHONPATH=. python -m backend.tests.contracts._openapi_snapshot_util --write
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.app.main import app

KEEP_TOP_LEVEL_KEYS = ("openapi", "info", "paths", "components")
SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "openapi_v1_snapshot.json"


def canonical_openapi_string() -> str:
    """Return canonicalized OpenAPI JSON with only stable contract sections."""
    schema = app.openapi()
    reduced = {key: schema[key] for key in KEEP_TOP_LEVEL_KEYS if key in schema}
    normalized = _normalize_json(reduced)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _normalize_json(value: Any) -> Any:
    """
    Normalize nested JSON to reduce cross-environment ordering noise.

    OpenAPI generators can emit some arrays (e.g. anyOf) in different orders
    between Python/library versions. Sorting list items by canonical JSON keeps
    snapshots stable while preserving the same schema semantics.
    """
    if isinstance(value, dict):
        return {key: _normalize_json(item) for key, item in value.items()}

    if isinstance(value, list):
        normalized_items = [_normalize_json(item) for item in value]
        return sorted(
            normalized_items,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
        )

    return value


def write_snapshot(path: Path = SNAPSHOT_PATH) -> Path:
    """Write canonical OpenAPI snapshot to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_openapi_string(), encoding="utf-8")
    return path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate canonical OpenAPI snapshot for V1 contracts.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write snapshot file to backend/tests/contracts/snapshots/openapi_v1_snapshot.json",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    content = canonical_openapi_string()
    if args.write:
        written_path = write_snapshot()
        print(f"Wrote snapshot: {written_path}")
    else:
        print(content)


if __name__ == "__main__":
    main()
