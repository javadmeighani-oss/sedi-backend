"""CI fail-closed Alembic deny guard (I7-CI-GUARD-01).

Scans backend/alembic/versions with Python only — never uses `rg`.
Missing external tools must not false-pass.

Forbidden:
  - create table ... rag_embeddings
  - USING ivfflat
  - CREATE EXTENSION ... vector outside 061_scis01_pgvector_kce_foundation.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCIS_ALLOWED = "061_scis01_pgvector_kce_foundation.py"
RAG_TABLE_RE = re.compile(r"(?i)create\s+table\s+.*rag_embeddings")
IVFFLAT_RE = re.compile(r"(?i)USING\s+ivfflat")
VECTOR_EXT_RE = re.compile(r"(?i)create\s+extension\s+.*vector")


def scan_alembic_versions(versions_dir: Path) -> list[str]:
    if not versions_dir.is_dir():
        return [f"MISSING_VERSIONS_DIR:{versions_dir}"]
    paths = sorted(versions_dir.glob("*.py"))
    if not paths:
        return [f"EMPTY_VERSIONS_DIR:{versions_dir}"]
    violations: list[str] = []
    for path in paths:
        body = path.read_text(encoding="utf-8")
        if RAG_TABLE_RE.search(body):
            violations.append(f"FORBIDDEN_RAG_EMBEDDINGS_TABLE:{path.name}")
        if IVFFLAT_RE.search(body):
            violations.append(f"FORBIDDEN_IVFFLAT:{path.name}")
        if VECTOR_EXT_RE.search(body) and path.name != SCIS_ALLOWED:
            violations.append(f"FORBIDDEN_VECTOR_OUTSIDE_SCIS01:{path.name}")
        if path.name == SCIS_ALLOWED:
            if not VECTOR_EXT_RE.search(body):
                violations.append(f"SCIS01_MISSING_VECTOR_EXTENSION:{path.name}")
            if "rag_embeddings" in body.lower() and "noncanonical" not in body.lower():
                violations.append(f"SCIS01_RAG_EMBEDDINGS_NOT_MARKED_NONCANONICAL:{path.name}")
    scis = versions_dir / SCIS_ALLOWED
    if not scis.is_file():
        violations.append(f"MISSING_SCIS01_ALLOWLIST_FILE:{SCIS_ALLOWED}")
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed Alembic Stage17/IVFFlat deny guard")
    parser.add_argument(
        "--versions-dir",
        default="backend/alembic/versions",
        help="Path to alembic versions directory",
    )
    args = parser.parse_args(argv)
    versions = Path(args.versions_dir)
    violations = scan_alembic_versions(versions)
    if violations:
        print("STAGE17_ALEMBIC_DENY=FAIL")
        for v in violations:
            print(v)
        return 1
    print("STAGE17_ALEMBIC_DENY=PASS")
    print("MISSING_TOOL_FALSE_PASS=ELIMINATED")
    print(f"SCANNED_DIR={versions.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
