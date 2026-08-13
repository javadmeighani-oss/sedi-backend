"""AST write-path regression guard for sensitive I5 knowledge models.

Discovers production writers under backend/app/services/i5 and diffs against
an allowlist. Negative control: unauthorized writer patterns must be detected.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Models whose construction via models.<Name>(...) in services must be allowlisted.
SENSITIVE_MODEL_NAMES = frozenset(
    {
        "KnowledgeUnit",
        "KnowledgeProvenance",
        "I5RawEvidence",
        "I5ScientificArtifact",
        "I5ScientificArtifactVersion",
        "I5KnowledgeUnitEvidenceLink",
        "WeeklyRunSourceResult",
        "I5KnowledgeClaimDetail",
        "I5ClinicalStudy",
        "I5ClinicalRecommendation",
    }
)

# Relative posix paths under backend/app/services/i5 allowed to construct these models.
ALLOWED_WRITER_FILES = frozenset(
    {
        "know05/bounded_ingestion.py",
        "know05/catalog12_bounded_ingest.py",
        "know05/acquisition_boundary.py",
        "know05/orchestrator.py",
        "know05/coverage_engine.py",
        "know05/publication.py",
        "know01/format_gap_persistence.py",
        "know01/coverage_gaps.py",
        "know01/registry_service.py",
        "know01/book_registry.py",
        "know02/artifacts.py",
        "know02/taxonomy.py",
        "know02/seed_fixtures.py",
        "know03/studies.py",
        "know03/effects.py",
        "know03/recommendations.py",
        "know03/seed_fixtures.py",
        "know04/change_intelligence.py",
        "know04/observability.py",
        "know04/seed_profiles.py",
        "governed_weekly_runtime.py",
        "weekly_orchestrator.py",
        # SCIS indexing is downstream of KU; path is under services/scis not i5 —
        # listed only if scanned. Keep i5-only scan.
    }
)


@dataclass(frozen=True)
class WriterHit:
    rel_path: str
    model_name: str
    lineno: int
    allowed: bool


def _services_i5_root() -> Path:
    # .../backend/app/services/i5/write_path_guard.py → i5 package root
    return Path(__file__).resolve().parents[1]


def _iter_py_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        if p.name.startswith("_") and p.name != "__init__.py":
            continue
        if "__pycache__" in p.parts:
            continue
        yield p


class _ModelCtorVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.hits: list[tuple[str, int]] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = self._ctor_name(node.func)
        if name in SENSITIVE_MODEL_NAMES:
            self.hits.append((name, node.lineno))
        self.generic_visit(node)

    @staticmethod
    def _ctor_name(func: ast.AST) -> str | None:
        # models.KnowledgeUnit(...)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in {"models"} and func.attr in SENSITIVE_MODEL_NAMES:
                return func.attr
        # KnowledgeUnit(...) direct import
        if isinstance(func, ast.Name) and func.id in SENSITIVE_MODEL_NAMES:
            return func.id
        return None


def scan_i5_writers(*, root: Path | None = None) -> list[WriterHit]:
    base = root or _services_i5_root()
    out: list[WriterHit] = []
    for path in _iter_py_files(base):
        rel = path.relative_to(base).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        visitor = _ModelCtorVisitor()
        visitor.visit(tree)
        allowed = rel in ALLOWED_WRITER_FILES
        for model_name, lineno in visitor.hits:
            out.append(
                WriterHit(
                    rel_path=rel,
                    model_name=model_name,
                    lineno=lineno,
                    allowed=allowed,
                )
            )
    return out


def unauthorized_writer_hits(hits: list[WriterHit] | None = None) -> list[WriterHit]:
    hits = hits if hits is not None else scan_i5_writers()
    return [h for h in hits if not h.allowed]


def detect_unauthorized_writer_in_source(source: str, *, pretend_rel_path: str) -> list[WriterHit]:
    """Negative-control helper: parse arbitrary source as if under pretend_rel_path."""
    tree = ast.parse(source)
    visitor = _ModelCtorVisitor()
    visitor.visit(tree)
    allowed = pretend_rel_path in ALLOWED_WRITER_FILES
    return [
        WriterHit(
            rel_path=pretend_rel_path,
            model_name=name,
            lineno=lineno,
            allowed=allowed,
        )
        for name, lineno in visitor.hits
        if not allowed
    ]
