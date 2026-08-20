"""I7-CI-GUARD-01 — fail-closed Alembic deny scan (no ripgrep dependency)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.scripts.ci_alembic_stage17_deny_guard import main, scan_alembic_versions

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"


def test_ci_alembic_deny_guard_passes_on_repo_versions():
    violations = scan_alembic_versions(VERSIONS)
    assert violations == [], violations
    assert main(["--versions-dir", str(VERSIONS)]) == 0


def test_ci_alembic_deny_guard_fail_closed_on_forbidden_content(tmp_path: Path):
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "061_scis01_pgvector_kce_foundation.py").write_text(
        "CREATE EXTENSION IF NOT EXISTS vector;\n# rag_embeddings NONCANONICAL\n",
        encoding="utf-8",
    )
    (versions / "999_bad_rag.py").write_text(
        "op.execute('CREATE TABLE rag_embeddings (id int)')\n",
        encoding="utf-8",
    )
    (versions / "998_bad_ivf.py").write_text(
        "USING ivfflat (embedding vector_cosine_ops)\n",
        encoding="utf-8",
    )
    (versions / "997_bad_vector.py").write_text(
        "CREATE EXTENSION vector;\n",
        encoding="utf-8",
    )
    violations = scan_alembic_versions(versions)
    assert any("FORBIDDEN_RAG_EMBEDDINGS_TABLE" in v for v in violations)
    assert any("FORBIDDEN_IVFFLAT" in v for v in violations)
    assert any("FORBIDDEN_VECTOR_OUTSIDE_SCIS01" in v for v in violations)
    assert main(["--versions-dir", str(versions)]) == 1


def test_ci_alembic_deny_guard_fail_closed_on_missing_dir(tmp_path: Path):
    missing = tmp_path / "nope"
    violations = scan_alembic_versions(missing)
    assert violations and violations[0].startswith("MISSING_VERSIONS_DIR")
    assert main(["--versions-dir", str(missing)]) == 1
