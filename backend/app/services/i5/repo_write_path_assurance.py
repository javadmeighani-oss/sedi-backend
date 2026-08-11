"""Repo-wide I5/knowledge write-path assurance scanner.

SCAN_ROOTS and WRITE_OPERATION_CLASSES are explicit; REPO_WRITE_PATH_COVERAGE=100%
is only valid when those enumerations match the scanner implementation.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Explicit coverage contract (Evidence Assurance Pack)
# ---------------------------------------------------------------------------

SCAN_ROOTS = (
    "backend/app",
    "backend/scripts",
    "backend/jobs",
    "backend/tasks",
    "backend/workers",
    "backend/commands",
)

EXCLUDED_ROOT_GLOBS = (
    "**/__pycache__/**",
    "**/.venv/**",
    "**/venv/**",
    "**/node_modules/**",
)

# Migrations scanned separately and classified MIGRATION_ONLY.
MIGRATION_ROOT = "backend/alembic/versions"

WRITE_OPERATION_CLASSES = (
    "ORM_CONSTRUCTOR",
    "ORM_ADD",
    "ORM_BULK",
    "ORM_MERGE",
    "SA_CORE_INSERT_UPDATE_DELETE",
    "QUERY_UPDATE_DELETE",
    "RAW_SQL_DML",
    "DIRECT_SENSITIVE_ATTR_MUTATION",
)

SENSITIVE_MODEL_NAMES = frozenset(
    {
        "KnowledgeUnit",
        "KnowledgeProvenance",
        "I5RawEvidence",
        "GovernedSourceProfile",
        "GovernedSourceProfileVersion",
        "I5ScientificArtifact",
        "I5ScientificArtifactVersion",
        "I5KnowledgeUnitEvidenceLink",
        "I5KnowledgeClaimDetail",
        "I5ClinicalStudy",
        "I5StudyPopulation",
        "I5StudyOutcome",
        "I5StudyEffectEstimate",
        "I5ClinicalRecommendation",
        "I5ClinicalRecommendationEvidenceLink",
        "I5GovernanceDecision",
        "KnowledgeGap",
        "WeeklyKnowledgeRun",
        "WeeklyKnowledgeRunAttempt",
        "WeeklyRunSourceResult",
        "WeeklyRunGapResult",
        "I5SourceCoverageGap",
        "I5ScientificChangeEvent",
        "I5ConnectorRunEvent",
    }
)

SENSITIVE_TABLE_NAMES = frozenset(
    {
        "knowledge_units",
        "knowledge_provenance",
        "i5_raw_evidence",
        "governed_source_profiles",
        "governed_source_profile_versions",
        "i5_scientific_artifacts",
        "i5_scientific_artifact_versions",
        "i5_knowledge_unit_evidence_links",
        "i5_knowledge_claim_details",
        "i5_clinical_studies",
        "i5_clinical_recommendations",
        "i5_governance_decisions",
        "knowledge_gaps",
        "weekly_knowledge_runs",
        "weekly_knowledge_run_attempts",
        "weekly_run_source_results",
        "weekly_run_gap_results",
        "i5_source_coverage_gaps",
    }
)

SENSITIVE_ATTRS = frozenset(
    {
        "runtime_eligibility",
        "publication_state",
        "provenance_complete",
        "medical_safety_state",
        "version_state",
        "conflict_state",
        "review_state",
    }
)

# Relative path under backend/ → (classification, production_reachability, reason)
PATH_CLASSIFICATION: dict[str, tuple[str, str, str]] = {
    # KNOW-05 / weekly runtime
    "app/services/i5/know05/bounded_ingestion.py": (
        "SPECIALIZED_CANONICAL_WRITER",
        "PRODUCTION_REACHABLE",
        "CT.gov bounded persist via know05 cycle",
    ),
    "app/services/i5/know05/acquisition_boundary.py": (
        "CANONICAL_RUNTIME_WRITER",
        "PRODUCTION_REACHABLE",
        "metadata-only acquisition evidence",
    ),
    "app/services/i5/know05/orchestrator.py": (
        "CANONICAL_RUNTIME_WRITER",
        "PRODUCTION_REACHABLE",
        "know05 weekly ledger",
    ),
    "app/services/i5/know05/coverage_engine.py": (
        "CANONICAL_RUNTIME_WRITER",
        "PRODUCTION_REACHABLE",
        "coverage gap materialization",
    ),
    "app/services/i5/know05/publication.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "publication stage / proven-gate attribute updates",
    ),
    "app/services/i5/weekly_orchestrator.py": (
        "CANONICAL_RUNTIME_WRITER",
        "PRODUCTION_REACHABLE",
        "scheduler weekly ledger",
    ),
    "app/services/i5/governed_weekly_runtime.py": (
        "CANONICAL_RUNTIME_WRITER",
        "PRODUCTION_REACHABLE",
        "RAW→KU→provenance persistence + GSP activation helpers",
    ),
    "app/services/i5/runtime_knowledge_retrieval.py": (
        "CANONICAL_RUNTIME_WRITER",
        "PRODUCTION_REACHABLE",
        "runtime retrieval KnowledgeGap enqueue",
    ),
    "app/services/i5/admin_review_service.py": (
        "ADMIN_MAINTENANCE_WRITER",
        "PRODUCTION_REACHABLE",
        "admin triage / medical_safety updates",
    ),
    "app/services/i5/multisource_activation.py": (
        "ADMIN_MAINTENANCE_WRITER",
        "NON_PRODUCTION_TOOL",
        "manual multisource activation allowlist",
    ),
    # KNOW-01
    "app/services/i5/know01/format_gap_persistence.py": (
        "CANONICAL_RUNTIME_WRITER",
        "PRODUCTION_REACHABLE",
        "UNSUPPORTED_FORMAT durable gap",
    ),
    "app/services/i5/know01/coverage_gaps.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "source coverage gap upsert",
    ),
    "app/services/i5/know01/registry_service.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "ensure_gsp / registry extension upsert",
    ),
    "app/services/i5/know01/authority_assessment.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "authority assessment demotes GSP eligibility",
    ),
    "app/services/i5/know01/book_registry.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "reference book registry",
    ),
    "app/services/i5/know01/seed_registry.py": (
        "BOOTSTRAP_SEED_WRITER",
        "NON_PRODUCTION_TOOL",
        "registry seed",
    ),
    # KNOW-02/03/04
    "app/services/i5/know02/artifacts.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "artifact/version/evidence link upserts",
    ),
    "app/services/i5/know02/taxonomy.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "taxonomy/coverage cell helpers",
    ),
    "app/services/i5/know02/seed_fixtures.py": (
        "BOOTSTRAP_SEED_WRITER",
        "NON_PRODUCTION_TOOL",
        "know02 seed fixtures",
    ),
    "app/services/i5/know03/studies.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "clinical study upserts",
    ),
    "app/services/i5/know03/effects.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "effect estimate writers",
    ),
    "app/services/i5/know03/recommendations.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "recommendation upserts",
    ),
    "app/services/i5/know03/seed_fixtures.py": (
        "BOOTSTRAP_SEED_WRITER",
        "NON_PRODUCTION_TOOL",
        "know03 seed fixtures",
    ),
    "app/services/i5/know04/change_intelligence.py": (
        "CANONICAL_RUNTIME_WRITER",
        "PRODUCTION_REACHABLE",
        "artifact change / supersession events",
    ),
    "app/services/i5/know04/observability.py": (
        "CANONICAL_RUNTIME_WRITER",
        "PRODUCTION_REACHABLE",
        "connector run events",
    ),
    "app/services/i5/know04/seed_profiles.py": (
        "BOOTSTRAP_SEED_WRITER",
        "NON_PRODUCTION_TOOL",
        "connector profile seeds",
    ),
    # governance
    "app/services/governance/kb_b2_source_profile_persistence.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "GSP persistence library",
    ),
    "app/services/governance/kb_b2_legacy_companion_seed.py": (
        "LEGACY_SUPPORTED_WRITER",
        "NON_PRODUCTION_TOOL",
        "legacy companion seed",
    ),
    # routers that may construct (if any) — classify if hit
    "app/routers/i5_admin.py": (
        "ADMIN_MAINTENANCE_WRITER",
        "PRODUCTION_REACHABLE",
        "admin API surface",
    ),
}


class WriterClassification(str, Enum):
    CANONICAL_RUNTIME_WRITER = "CANONICAL_RUNTIME_WRITER"
    CANONICAL_SERVICE_HELPER = "CANONICAL_SERVICE_HELPER"
    SPECIALIZED_CANONICAL_WRITER = "SPECIALIZED_CANONICAL_WRITER"
    BOOTSTRAP_SEED_WRITER = "BOOTSTRAP_SEED_WRITER"
    TEST_ONLY_WRITER = "TEST_ONLY_WRITER"
    MIGRATION_ONLY_WRITER = "MIGRATION_ONLY_WRITER"
    ADMIN_MAINTENANCE_WRITER = "ADMIN_MAINTENANCE_WRITER"
    LEGACY_SUPPORTED_WRITER = "LEGACY_SUPPORTED_WRITER"
    LEGACY_NONCANONICAL_WRITER = "LEGACY_NONCANONICAL_WRITER"
    UNCLASSIFIED_WRITER = "UNCLASSIFIED_WRITER"
    UNAUTHORIZED_WRITER = "UNAUTHORIZED_WRITER"


@dataclass(frozen=True)
class WriterHit:
    path: str
    symbol: str
    lineno: int
    operation: str
    target: str
    classification: str
    production_reachability: str
    reason: str
    allowed: bool


@dataclass
class ScanReport:
    hits: list[WriterHit] = field(default_factory=list)
    scan_roots_used: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)

    @property
    def unclassified(self) -> list[WriterHit]:
        return [h for h in self.hits if h.classification == "UNCLASSIFIED_WRITER"]

    @property
    def unauthorized(self) -> list[WriterHit]:
        return [h for h in self.hits if h.classification == "UNAUTHORIZED_WRITER" or not h.allowed]

    @property
    def unresolved_reachability(self) -> list[WriterHit]:
        return [
            h
            for h in self.hits
            if h.classification not in {"TEST_ONLY_WRITER", "MIGRATION_ONLY_WRITER"}
            and h.production_reachability == "UNRESOLVED"
        ]


def _backend_root() -> Path:
    # .../backend/app/services/i5/repo_write_path_assurance.py → backend/
    return Path(__file__).resolve().parents[3]


def _workspace_root() -> Path:
    return _backend_root().parent


def _iter_py_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts or ".venv" in p.parts or "venv" in p.parts:
            continue
        yield p


def _classify_path(rel_backend: str) -> tuple[str, str, str, bool]:
    """Return classification, reachability, reason, allowed."""
    norm = rel_backend.replace("\\", "/")
    if norm.startswith("tests/") or "/tests/" in norm or norm.startswith("backend/tests/"):
        return "TEST_ONLY_WRITER", "TEST_ONLY", "under backend/tests", True
    if "alembic/versions/" in norm:
        return "MIGRATION_ONLY_WRITER", "MIGRATION_ONLY", "alembic migration DDL/DML", True
    if norm.endswith("repo_write_path_assurance.py") or norm.endswith("write_path_guard.py"):
        return "CANONICAL_SERVICE_HELPER", "NON_PRODUCTION_TOOL", "assurance scanner module", True
    if norm in PATH_CLASSIFICATION:
        c, r, reason = PATH_CLASSIFICATION[norm]
        return c, r, reason, True
    if "seed" in Path(norm).name.lower() or norm.endswith("seed_fixtures.py"):
        return "BOOTSTRAP_SEED_WRITER", "NON_PRODUCTION_TOOL", "seed filename heuristic", True
    return "UNCLASSIFIED_WRITER", "UNRESOLVED", "no allowlist entry", False


_RAW_SQL_RE = re.compile(
    r"(?is)\b(INSERT\s+INTO|UPDATE\s+|DELETE\s+FROM|MERGE\s+)\s*([`\"'\[]?\w+[`\"'\]]?)"
)
_SENSITIVE_TABLE_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(t) for t in sorted(SENSITIVE_TABLE_NAMES, key=len, reverse=True)) + r")\b"
)


class _RepoWriterVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.hits: list[tuple[str, str, int, str]] = []  # op, target, lineno, symbol_hint
        self._func_stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    def _sym(self) -> str:
        return self._func_stack[-1] if self._func_stack else "<module>"

    def visit_Call(self, node: ast.Call) -> None:
        ctor = self._ctor_name(node.func)
        if ctor:
            self.hits.append(("ORM_CONSTRUCTOR", ctor, node.lineno, self._sym()))
        # db.add / session.add
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"add", "add_all"}:
            self.hits.append(("ORM_ADD", node.func.attr, node.lineno, self._sym()))
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "bulk_insert_mappings",
            "bulk_update_mappings",
            "bulk_save_objects",
            "merge",
        }:
            target = self._first_arg_model(node) or node.func.attr
            op = "ORM_MERGE" if node.func.attr == "merge" else "ORM_BULK"
            self.hits.append((op, target, node.lineno, self._sym()))
        # query(...).update / .delete
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"update", "delete"}:
            if self._call_chain_has_query(node.func.value):
                tgt = self._extract_query_model(node.func.value) or "QUERY"
                self.hits.append(("QUERY_UPDATE_DELETE", tgt, node.lineno, self._sym()))
        # insert()/update()/delete() core
        if isinstance(node.func, ast.Name) and node.func.id in {"insert", "update", "delete"}:
            tgt = self._first_arg_model(node) or node.func.id
            if tgt in SENSITIVE_MODEL_NAMES or tgt in {"insert", "update", "delete"}:
                # only keep if sensitive model or we'll filter via raw later
                if tgt in SENSITIVE_MODEL_NAMES:
                    self.hits.append(("SA_CORE_INSERT_UPDATE_DELETE", tgt, node.lineno, self._sym()))
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"insert", "update", "delete"}:
            # sqlalchemy.sql.expression style less common
            pass
        # text("...")
        if isinstance(node.func, ast.Name) and node.func.id == "text" and node.args:
            lit = self._const_str(node.args[0])
            if lit:
                for m in _RAW_SQL_RE.finditer(lit):
                    table = m.group(2).strip("`\"'[]")
                    if table.lower() in SENSITIVE_TABLE_NAMES or _SENSITIVE_TABLE_RE.search(lit):
                        self.hits.append(("RAW_SQL_DML", table.lower(), node.lineno, self._sym()))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for t in node.targets:
            attr = self._attr_name(t)
            if attr in SENSITIVE_ATTRS:
                self.hits.append(("DIRECT_SENSITIVE_ATTR_MUTATION", attr, node.lineno, self._sym()))
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        attr = self._attr_name(node.target)
        if attr in SENSITIVE_ATTRS:
            self.hits.append(("DIRECT_SENSITIVE_ATTR_MUTATION", attr, node.lineno, self._sym()))
        self.generic_visit(node)

    @staticmethod
    def _attr_name(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    @staticmethod
    def _const_str(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    @staticmethod
    def _ctor_name(func: ast.AST) -> Optional[str]:
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "models" and func.attr in SENSITIVE_MODEL_NAMES:
                return func.attr
        if isinstance(func, ast.Name) and func.id in SENSITIVE_MODEL_NAMES:
            return func.id
        return None

    @staticmethod
    def _first_arg_model(node: ast.Call) -> Optional[str]:
        if not node.args:
            return None
        a0 = node.args[0]
        if isinstance(a0, ast.Attribute) and isinstance(a0.value, ast.Name) and a0.value.id == "models":
            return a0.attr
        if isinstance(a0, ast.Name):
            return a0.id
        return None

    @staticmethod
    def _call_chain_has_query(node: ast.AST) -> bool:
        cur: ast.AST | None = node
        while cur is not None:
            if isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute) and cur.func.attr == "query":
                return True
            if isinstance(cur, ast.Attribute):
                cur = cur.value
            elif isinstance(cur, ast.Call):
                cur = cur.func
            else:
                break
        return False

    @staticmethod
    def _extract_query_model(node: ast.AST) -> Optional[str]:
        cur: ast.AST | None = node
        while cur is not None:
            if isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute) and cur.func.attr == "query":
                if cur.args:
                    a0 = cur.args[0]
                    if isinstance(a0, ast.Attribute) and isinstance(a0.value, ast.Name):
                        return a0.attr
                    if isinstance(a0, ast.Name):
                        return a0.id
            if isinstance(cur, ast.Attribute):
                cur = cur.value
            elif isinstance(cur, ast.Call):
                cur = cur.func
            else:
                break
        return None


def _filter_hit(operation: str, target: str) -> bool:
    """Keep only materially sensitive hits."""
    if operation == "ORM_CONSTRUCTOR":
        return target in SENSITIVE_MODEL_NAMES
    if operation == "ORM_ADD":
        # ORM_ADD alone is noisy; keep only when co-located with constructors via same scan —
        # drop bare add to avoid false positives from unrelated models.
        return False
    if operation in {"ORM_BULK", "ORM_MERGE", "SA_CORE_INSERT_UPDATE_DELETE", "QUERY_UPDATE_DELETE"}:
        return target in SENSITIVE_MODEL_NAMES or target.lower() in SENSITIVE_TABLE_NAMES
    if operation == "RAW_SQL_DML":
        return target.lower() in SENSITIVE_TABLE_NAMES
    if operation == "DIRECT_SENSITIVE_ATTR_MUTATION":
        return target in SENSITIVE_ATTRS
    return False


def _eligibility_mutation_unauthorized(target: str, path: str, lineno: int, source: str) -> bool:
    """Flag assigning runtime_eligibility='ELIGIBLE' outside allowlisted activation paths."""
    if target != "runtime_eligibility":
        return False
    # Inspect nearby source line for ELIGIBLE literal assignment
    lines = source.splitlines()
    if lineno - 1 < 0 or lineno - 1 >= len(lines):
        return False
    line = lines[lineno - 1]
    if "ELIGIBLE" not in line:
        return False
    if "NOT_ELIGIBLE" in line:
        return False
    allow_paths = {
        "app/services/i5/governed_weekly_runtime.py",
        "app/services/i5/multisource_activation.py",
    }
    return path.replace("\\", "/") not in allow_paths


def scan_source_text(
    source: str,
    *,
    rel_path: str,
    force_unclassified: bool = False,
) -> list[WriterHit]:
    """Scan a single source string (also used for negative controls)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    visitor = _RepoWriterVisitor()
    visitor.visit(tree)
    # Also textual raw SQL fallback (handles multi-line / non-ast text())
    for i, line in enumerate(source.splitlines(), start=1):
        if _RAW_SQL_RE.search(line) and _SENSITIVE_TABLE_RE.search(line):
            m = _RAW_SQL_RE.search(line)
            table = (m.group(2) if m else "unknown").strip("`\"'[]").lower()
            visitor.hits.append(("RAW_SQL_DML", table, i, "<module>"))

    hits: list[WriterHit] = []
    seen: set[tuple[str, str, int]] = set()
    for op, target, lineno, sym in visitor.hits:
        if not _filter_hit(op, target) and not (
            op == "DIRECT_SENSITIVE_ATTR_MUTATION" and target in SENSITIVE_ATTRS
        ):
            continue
        key = (op, target, lineno)
        if key in seen:
            continue
        seen.add(key)
        if force_unclassified:
            classification, reach, reason, allowed = (
                "UNAUTHORIZED_WRITER",
                "UNRESOLVED",
                "negative-control synthetic",
                False,
            )
        else:
            classification, reach, reason, allowed = _classify_path(rel_path)
            if classification == "UNCLASSIFIED_WRITER":
                classification = "UNAUTHORIZED_WRITER"
                allowed = False
            # Direct ELIGIBLE mutation outside activation allowlist is unauthorized —
            # but never reclassify TEST_ONLY / MIGRATION_ONLY hits.
            if (
                allowed
                and classification
                not in {"TEST_ONLY_WRITER", "MIGRATION_ONLY_WRITER", "BOOTSTRAP_SEED_WRITER"}
                and op == "DIRECT_SENSITIVE_ATTR_MUTATION"
                and _eligibility_mutation_unauthorized(target, rel_path, lineno, source)
            ):
                classification = "UNAUTHORIZED_WRITER"
                allowed = False
                reason = "direct runtime_eligibility=ELIGIBLE outside activation allowlist"
                reach = "UNRESOLVED"
            elif (
                not allowed
                and op == "DIRECT_SENSITIVE_ATTR_MUTATION"
                and rel_path.replace("\\", "/").startswith("tests/")
            ):
                classification, reach, reason, allowed = (
                    "TEST_ONLY_WRITER",
                    "TEST_ONLY",
                    "test fixture eligibility mutation",
                    True,
                )
        hits.append(
            WriterHit(
                path=rel_path,
                symbol=sym,
                lineno=lineno,
                operation=op,
                target=target,
                classification=classification,
                production_reachability=reach,
                reason=reason,
                allowed=allowed,
            )
        )
    return hits


def scan_repository(*, include_migrations: bool = True, include_tests: bool = True) -> ScanReport:
    backend = _backend_root()
    report = ScanReport(
        scan_roots_used=list(SCAN_ROOTS),
        exclusions=[
            "**/__pycache__/**",
            "**/.venv/**",
            "venv",
            "documentation",
            "generated caches",
            "alembic versions classified MIGRATION_ONLY (scanned separately)"
            if include_migrations
            else "alembic versions excluded",
        ],
    )
    roots: list[Path] = []
    for rel in SCAN_ROOTS:
        roots.append(backend / rel.replace("backend/", "", 1) if rel.startswith("backend/") else backend / rel)
    # normalize: SCAN_ROOTS are relative to workspace, backend is backend/
    ws = _workspace_root()
    roots = []
    for rel in SCAN_ROOTS:
        p = ws / rel
        roots.append(p)
        report.scan_roots_used.append(rel if p.exists() else f"{rel} (absent)")

    if include_tests:
        roots.append(ws / "backend/tests")
        report.scan_roots_used.append("backend/tests")
    if include_migrations:
        roots.append(ws / MIGRATION_ROOT)
        report.scan_roots_used.append(MIGRATION_ROOT)

    for root in roots:
        if not root.exists():
            continue
        for path in _iter_py_files(root):
            try:
                rel = path.relative_to(ws / "backend").as_posix()
            except ValueError:
                rel = path.as_posix()
            # Skip assurance modules' string examples? still scan; classify as helper
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            report.hits.extend(scan_source_text(text, rel_path=rel))
    return report


def inventory_summary(report: ScanReport | None = None) -> dict[str, int]:
    report = report or scan_repository()
    raw = [h for h in report.hits if h.operation == "RAW_SQL_DML"]
    bulk = [h for h in report.hits if h.operation == "ORM_BULK"]
    merge = [h for h in report.hits if h.operation == "ORM_MERGE"]
    qu = [h for h in report.hits if h.operation == "QUERY_UPDATE_DELETE"]
    mut = [h for h in report.hits if h.operation == "DIRECT_SENSITIVE_ATTR_MUTATION"]
    elig_unauth = [
        h
        for h in report.hits
        if h.operation == "DIRECT_SENSITIVE_ATTR_MUTATION"
        and h.target == "runtime_eligibility"
        and not h.allowed
    ]
    return {
        "TOTAL_SENSITIVE_WRITER_HITS": len(report.hits),
        "CLASSIFIED_WRITER_HITS": len(report.hits) - len(report.unclassified),
        "UNCLASSIFIED_WRITER_COUNT": len(report.unclassified),
        "UNAUTHORIZED_WRITER_COUNT": len(report.unauthorized),
        "UNRESOLVED_PRODUCTION_REACHABILITY_COUNT": len(report.unresolved_reachability),
        "RAW_SQL_SENSITIVE_WRITE_COUNT": len(raw),
        "RAW_SQL_UNCLASSIFIED_COUNT": sum(1 for h in raw if not h.allowed),
        "BULK_SENSITIVE_WRITE_COUNT": len(bulk),
        "MERGE_SENSITIVE_WRITE_COUNT": len(merge),
        "QUERY_UPDATE_SENSITIVE_WRITE_COUNT": len(qu),
        "UNCLASSIFIED_BULK_OR_MERGE_COUNT": sum(
            1 for h in bulk + merge + qu if not h.allowed
        ),
        "DIRECT_MUTATION_HITS": len(mut),
        "UNAUTHORIZED_DIRECT_ELIGIBILITY_MUTATION_COUNT": len(elig_unauth),
    }


# ---------------------------------------------------------------------------
# Negative-control detectors (prove scanner capability)
# ---------------------------------------------------------------------------

def detect_negative_direct_constructor() -> bool:
    src = (
        "from backend.app import models\n"
        "def evil(db):\n"
        "    db.add(models.KnowledgeUnit(canonical_unit_id='x'))\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_bypass.py", force_unclassified=True)
    return any(h.operation == "ORM_CONSTRUCTOR" and h.target == "KnowledgeUnit" for h in hits)


def detect_negative_raw_sql() -> bool:
    src = (
        "from sqlalchemy import text\n"
        "def evil(db):\n"
        "    db.execute(text(\"UPDATE knowledge_units SET runtime_eligibility='ELIGIBLE'\"))\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_sql.py", force_unclassified=True)
    return any(h.operation == "RAW_SQL_DML" for h in hits)


def detect_negative_core_update() -> bool:
    src = (
        "from sqlalchemy import update\n"
        "from backend.app import models\n"
        "def evil(session):\n"
        "    session.execute(update(models.KnowledgeUnit).values(runtime_eligibility='ELIGIBLE'))\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_core.py", force_unclassified=True)
    return any(
        h.operation == "SA_CORE_INSERT_UPDATE_DELETE" and h.target == "KnowledgeUnit" for h in hits
    )


def detect_negative_bulk_write() -> bool:
    src = (
        "from backend.app import models\n"
        "def evil(session):\n"
        "    session.bulk_insert_mappings(models.KnowledgeUnit, [{'canonical_unit_id': 'x'}])\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_bulk.py", force_unclassified=True)
    return any(h.operation == "ORM_BULK" and h.target == "KnowledgeUnit" for h in hits)


def detect_negative_query_update() -> bool:
    src = (
        "from backend.app import models\n"
        "def evil(db):\n"
        "    db.query(models.KnowledgeUnit).update({'runtime_eligibility': 'ELIGIBLE'})\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_q.py", force_unclassified=True)
    return any(h.operation == "QUERY_UPDATE_DELETE" and h.target == "KnowledgeUnit" for h in hits)


def detect_negative_eligibility_mutation() -> bool:
    src = (
        "def evil(ku):\n"
        "    ku.runtime_eligibility = 'ELIGIBLE'\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_mut.py", force_unclassified=True)
    return any(
        h.operation == "DIRECT_SENSITIVE_ATTR_MUTATION" and h.target == "runtime_eligibility"
        for h in hits
    )
