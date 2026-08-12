"""Repo-wide I5/knowledge write-path assurance scanner.

Sensitive model/table universe is derived from SQLAlchemy models (and explicit
exclusions), not from two hand-maintained unrelated lists. ORM_ADD uses bounded
local inference. REPO_WRITE_PATH_COVERAGE=100% is only valid when SCAN_ROOTS,
WRITE_OPERATION_CLASSES, and the derived universe match the implementation.
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
    "backend/ops",
)

EXCLUDED_ROOT_GLOBS = (
    "**/__pycache__/**",
    "**/.venv/**",
    "**/venv/**",
    "**/node_modules/**",
)

MIGRATION_ROOT = "backend/alembic/versions"
MIGRATION_RECONCILE_PREFIXES = tuple(f"{i:03d}_" for i in range(51, 66))

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

# Tablename → exclusion reason (must be empty set for unexplained gaps).
EXPLICIT_TABLE_EXCLUSIONS: dict[str, str] = {}

# Schema-only tables (migration-defined, no mapped model) that remain sensitive.
EXPLICIT_SCHEMA_ONLY_SENSITIVE_TABLES: frozenset[str] = frozenset()

# Category assignment for evidence pack (model class name → category).
_MODEL_CATEGORY_HINTS: dict[str, str] = {
    "KnowledgeUnit": "I5_CORE_KNOWLEDGE",
    "KnowledgeProvenance": "I5_CORE_KNOWLEDGE",
    "I5KnowledgeUnitEvidenceLink": "I5_CORE_KNOWLEDGE",
    "I5KnowledgeClaimDetail": "I5_CORE_KNOWLEDGE",
    "I5KnowledgeUnitConcept": "I5_CORE_KNOWLEDGE",
    "I5KnowledgeUnitDimension": "I5_CORE_KNOWLEDGE",
    "KnowledgeGap": "I5_CORE_KNOWLEDGE",
    "I5GovernanceDecision": "I5_CONFLICT_SAFETY",
    "KnowledgeConflict": "I5_CONFLICT_SAFETY",
    "SafetyReviewQueueItem": "I5_CONFLICT_SAFETY",
    "KnowledgeMemoryItem": "LEGACY_KNOWLEDGE_RUNTIME",
    "KnowledgeMemoryTransition": "LEGACY_KNOWLEDGE_RUNTIME",
    "KnowledgeSource": "RAG_KNOWLEDGE_STORAGE",
    "KnowledgeDocument": "RAG_KNOWLEDGE_STORAGE",
    "KnowledgeChunk": "RAG_KNOWLEDGE_STORAGE",
    "KnowledgeChunkEmbedding": "RAG_KNOWLEDGE_STORAGE",
    "KnowledgeIngestionRun": "RAG_KNOWLEDGE_STORAGE",
    "GovernedSourceProfile": "I5_SOURCE_GOVERNANCE",
    "GovernedSourceProfileVersion": "I5_SOURCE_GOVERNANCE",
    "I5SourceRegistryExtension": "I5_SOURCE_GOVERNANCE",
    "I5SourceRegistryRole": "I5_SOURCE_GOVERNANCE",
    "I5SourceP0Tag": "I5_SOURCE_GOVERNANCE",
    "I5ReferenceBook": "I5_SOURCE_GOVERNANCE",
    "I5ReferenceBookEdition": "I5_SOURCE_GOVERNANCE",
    "I5RawEvidence": "I5_ACQUISITION",
    "I5SourceCoverageGap": "I5_ACQUISITION",
    "I5SourceIngestionAudit": "I5_ACQUISITION",
    "I5ConnectorProfile": "I5_ACQUISITION",
    "I5ConnectorCursor": "I5_ACQUISITION",
    "I5ConnectorRunEvent": "I5_ACQUISITION",
    "I5ScientificArtifact": "I5_ARTIFACT_VERSIONING",
    "I5ScientificArtifactVersion": "I5_ARTIFACT_VERSIONING",
    "I5ArtifactVersionContentDriftEvent": "I5_ARTIFACT_VERSIONING",
    "I5KnowledgeDimension": "I5_TAXONOMY",
    "I5ClinicalConcept": "I5_TAXONOMY",
    "I5ClinicalConceptLabel": "I5_TAXONOMY",
    "I5ClinicalConceptMapping": "I5_TAXONOMY",
    "I5SediPriorityOverlay": "I5_TAXONOMY",
    "I5TerminologyRelease": "I5_TAXONOMY",
    "I5TerminologyImportContract": "I5_TAXONOMY",
    "I5TerminologyMappingConflictEvent": "I5_TAXONOMY",
    "I5TerminologyImportRun": "I5_TAXONOMY",
    "I5KnowledgeCoverageCell": "I5_TAXONOMY",
    "I5ClinicalStudy": "I5_STUDY_EVIDENCE",
    "I5StudyArtifactLink": "I5_STUDY_EVIDENCE",
    "I5StudyConditionLink": "I5_STUDY_EVIDENCE",
    "I5StudyPopulation": "I5_STUDY_EVIDENCE",
    "I5StudyPopulationCriterion": "I5_STUDY_EVIDENCE",
    "I5Intervention": "I5_STUDY_EVIDENCE",
    "I5InterventionMapping": "I5_STUDY_EVIDENCE",
    "I5StudyIntervention": "I5_STUDY_EVIDENCE",
    "I5ClinicalOutcome": "I5_STUDY_EVIDENCE",
    "I5StudyOutcome": "I5_STUDY_EVIDENCE",
    "I5StudyEffectEstimate": "I5_STUDY_EVIDENCE",
    "I5ClinicalRecommendation": "I5_RECOMMENDATION",
    "I5ClinicalRecommendationConditionLink": "I5_RECOMMENDATION",
    "I5ClinicalRecommendationEvidenceLink": "I5_RECOMMENDATION",
    "WeeklyKnowledgeRun": "I5_WEEKLY_LEDGER",
    "WeeklyKnowledgeRunAttempt": "I5_WEEKLY_LEDGER",
    "WeeklyRunSourceResult": "I5_WEEKLY_LEDGER",
    "WeeklyRunGapResult": "I5_WEEKLY_LEDGER",
    "I5ScientificChangeEvent": "I5_CHANGE_INTELLIGENCE",
}


def _is_i5_persistence_tablename(name: str) -> bool:
    return (
        name.startswith("i5_")
        or name.startswith("knowledge_")
        or name.startswith("governed_")
        or name.startswith("weekly_")
    )


@dataclass(frozen=True)
class ModelTableEntry:
    model: str
    tablename: str
    category: str
    sensitive: bool
    exclusion_reason: str = ""


@dataclass
class PersistenceUniverse:
    entries: list[ModelTableEntry] = field(default_factory=list)
    sensitive_model_names: frozenset[str] = frozenset()
    sensitive_table_names: frozenset[str] = frozenset()
    model_to_table: dict[str, str] = field(default_factory=dict)
    table_to_model: dict[str, str] = field(default_factory=dict)
    explicit_exclusions: dict[str, str] = field(default_factory=dict)
    schema_only_tables: frozenset[str] = frozenset()
    unexplained_model_exclusions: list[str] = field(default_factory=list)
    unexplained_table_exclusions: list[str] = field(default_factory=list)


def reconstruct_persistence_universe() -> PersistenceUniverse:
    """Derive sensitive model/table sets from SQLAlchemy authority."""
    from backend.app import models as models_mod

    entries: list[ModelTableEntry] = []
    model_to_table: dict[str, str] = {}
    table_to_model: dict[str, str] = {}
    sensitive_models: set[str] = set()
    sensitive_tables: set[str] = set()

    for name in dir(models_mod):
        obj = getattr(models_mod, name)
        if not isinstance(obj, type):
            continue
        tn = getattr(obj, "__tablename__", None)
        if not isinstance(tn, str) or not _is_i5_persistence_tablename(tn):
            continue
        cat = _MODEL_CATEGORY_HINTS.get(name)
        if cat is None:
            if tn.startswith("i5_"):
                cat = "I5_CORE_KNOWLEDGE"
            elif tn.startswith("knowledge_"):
                cat = "LEGACY_KNOWLEDGE_RUNTIME"
            elif tn.startswith("governed_"):
                cat = "I5_SOURCE_GOVERNANCE"
            else:
                cat = "I5_WEEKLY_LEDGER"
        reason = EXPLICIT_TABLE_EXCLUSIONS.get(tn, "")
        sensitive = tn not in EXPLICIT_TABLE_EXCLUSIONS
        entries.append(
            ModelTableEntry(
                model=name,
                tablename=tn,
                category=cat,
                sensitive=sensitive,
                exclusion_reason=reason,
            )
        )
        model_to_table[name] = tn
        table_to_model[tn] = name
        if sensitive:
            sensitive_models.add(name)
            sensitive_tables.add(tn)

    sensitive_tables |= set(EXPLICIT_SCHEMA_ONLY_SENSITIVE_TABLES)

    unexplained_models = [
        e.model
        for e in entries
        if not e.sensitive and not e.exclusion_reason
    ]
    unexplained_tables = [
        tn for tn, reason in EXPLICIT_TABLE_EXCLUSIONS.items() if not reason
    ]

    return PersistenceUniverse(
        entries=sorted(entries, key=lambda e: e.model),
        sensitive_model_names=frozenset(sensitive_models),
        sensitive_table_names=frozenset(sensitive_tables),
        model_to_table=model_to_table,
        table_to_model=table_to_model,
        explicit_exclusions=dict(EXPLICIT_TABLE_EXCLUSIONS),
        schema_only_tables=EXPLICIT_SCHEMA_ONLY_SENSITIVE_TABLES,
        unexplained_model_exclusions=unexplained_models,
        unexplained_table_exclusions=unexplained_tables,
    )


_UNIVERSE = reconstruct_persistence_universe()
SENSITIVE_MODEL_NAMES: frozenset[str] = _UNIVERSE.sensitive_model_names
SENSITIVE_TABLE_NAMES: frozenset[str] = _UNIVERSE.sensitive_table_names
SENSITIVE_MODEL_TO_TABLE: dict[str, str] = dict(_UNIVERSE.model_to_table)

SENSITIVE_ATTRS = frozenset(
    {
        "runtime_eligibility",
        "publication_state",
        "provenance_complete",
        "medical_safety_state",
        "version_state",
        "conflict_state",
        "review_state",
        "freshness_state",
        "rights_mode",
        "activation_state",
        "queue_status",
        "superseded_by_version_id",
        "evidence_linked",
        "conflict_clear",
        "governance_approved",
    }
)

# Relative path under backend/ → (classification, production_reachability, reason)
PATH_CLASSIFICATION: dict[str, tuple[str, str, str]] = {
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
    "app/routers/i5_admin.py": (
        "ADMIN_MAINTENANCE_WRITER",
        "PRODUCTION_REACHABLE",
        "admin API surface",
    ),
    "ops/db03/apply_roles_sedi_v1.py": (
        "ADMIN_MAINTENANCE_WRITER",
        "NON_PRODUCTION_TOOL",
        "DB03 role grant maintenance script (no I5 knowledge DML)",
    ),
    # Legacy Gate-3 / SCIS RAG knowledge storage (in universe; classified, not silent)
    "app/services/gate3/kb_embedding_service.py": (
        "LEGACY_SUPPORTED_WRITER",
        "PRODUCTION_REACHABLE",
        "Gate-3 KnowledgeChunkEmbedding writer",
    ),
    "app/services/gate3/knowledge_base_service.py": (
        "LEGACY_SUPPORTED_WRITER",
        "PRODUCTION_REACHABLE",
        "Gate-3 KnowledgeSource/Document writer",
    ),
    "app/services/gate3/knowledge_update_service.py": (
        "LEGACY_SUPPORTED_WRITER",
        "PRODUCTION_REACHABLE",
        "Gate-3 ingestion/document/chunk writer",
    ),
    "app/services/scis/indexing.py": (
        "LEGACY_SUPPORTED_WRITER",
        "PRODUCTION_REACHABLE",
        "SCIS RAG indexing writer for knowledge_* tables",
    ),
    "app/services/i5/adapters/live_transport.py": (
        "LEGACY_SUPPORTED_WRITER",
        "NON_PRODUCTION_TOOL",
        "live transport may touch KnowledgeSource identity helpers",
    ),
    "app/services/i5/iran_directory_import.py": (
        "LEGACY_SUPPORTED_WRITER",
        "PRODUCTION_REACHABLE",
        "Iran directory upsert via dynamic getattr (Iran* models; not I5 knowledge tables)",
    ),
    "app/services/i5/iran_directory_normalization.py": (
        "LEGACY_SUPPORTED_WRITER",
        "NON_PRODUCTION_TOOL",
        "Iran directory normalization helpers",
    ),
    "app/services/i5/know03/terminology.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "terminology import contract upserts",
    ),
    "app/services/i5/know04/terminology.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "terminology import run ledger",
    ),
    "app/services/i5/know04/terminology_remap.py": (
        "CANONICAL_SERVICE_HELPER",
        "PRODUCTION_REACHABLE",
        "terminology mapping conflict events",
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
    absent_roots: list[str] = field(default_factory=list)

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

    @property
    def unresolved_orm_add(self) -> list[WriterHit]:
        # Unresolved adds on explicitly allowlisted paths are manually classified
        # (cannot infer dynamic getattr targets); only unallowlisted unresolved count.
        return [
            h
            for h in self.hits
            if h.operation == "ORM_ADD"
            and h.target == "ORM_ADD_UNRESOLVED_TARGET"
            and not h.allowed
        ]


def _backend_root() -> Path:
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


def _path_is_i5_knowledge_surface(norm: str) -> bool:
    n = norm.replace("\\", "/")
    return (
        "/services/i5/" in f"/{n}"
        or n.startswith("app/services/i5/")
        or "/services/governance/" in f"/{n}"
        or n.startswith("app/services/governance/")
        or "know0" in n
        or n.endswith("repo_write_path_assurance.py")
        or n.endswith("write_path_guard.py")
    )


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
    # No unsafe seed filename auto-allow: seed writers must be explicitly classified.
    return "UNCLASSIFIED_WRITER", "UNRESOLVED", "no allowlist entry", False


def stale_path_classification_entries() -> list[str]:
    backend = _backend_root()
    stale: list[str] = []
    for rel in PATH_CLASSIFICATION:
        if not (backend / rel).exists():
            stale.append(rel)
    return stale


def _rebuild_table_regex(tables: frozenset[str]) -> re.Pattern[str]:
    if not tables:
        return re.compile(r"(?!x)x")
    return re.compile(
        r"(?i)\b(" + "|".join(re.escape(t) for t in sorted(tables, key=len, reverse=True)) + r")\b"
    )


_RAW_SQL_RE = re.compile(
    r"(?is)\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE)\s+([`\"'\[]?\w+[`\"'\]]?)"
)
_SENSITIVE_TABLE_RE = _rebuild_table_regex(SENSITIVE_TABLE_NAMES)


def refresh_sensitive_regexes() -> None:
    """Refresh module regex after universe rebuild (tests may call)."""
    global _SENSITIVE_TABLE_RE, SENSITIVE_MODEL_NAMES, SENSITIVE_TABLE_NAMES, _UNIVERSE
    _UNIVERSE = reconstruct_persistence_universe()
    SENSITIVE_MODEL_NAMES = _UNIVERSE.sensitive_model_names
    SENSITIVE_TABLE_NAMES = _UNIVERSE.sensitive_table_names
    _SENSITIVE_TABLE_RE = _rebuild_table_regex(SENSITIVE_TABLE_NAMES)


def _ann_to_model(node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    if isinstance(node, ast.Name) and node.id in SENSITIVE_MODEL_NAMES:
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "models" and node.attr in SENSITIVE_MODEL_NAMES:
            return node.attr
    if isinstance(node, ast.Subscript):  # Optional[X] / list[X]
        return _ann_to_model(node.slice) or _ann_to_model(getattr(node, "value", None))
    if isinstance(node, ast.BinOp):  # X | None
        return _ann_to_model(node.left) or _ann_to_model(node.right)
    if isinstance(node, ast.Tuple):
        for elt in node.elts:
            m = _ann_to_model(elt)
            if m:
                return m
    return None


class _RepoWriterVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.hits: list[tuple[str, str, int, str]] = []
        self._func_stack: list[str] = []
        self._local_types: dict[str, Optional[str]] = {}
        self._fn_return_types: dict[str, Optional[str]] = {}
        self._param_types: dict[str, Optional[str]] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_fn(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_fn(node)

    def _visit_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        ret = _ann_to_model(node.returns)
        self._fn_return_types[node.name] = ret
        saved_locals = dict(self._local_types)
        saved_params = dict(self._param_types)
        self._param_types = {}
        for arg in list(node.args.args) + list(node.args.kwonlyargs):
            t = _ann_to_model(arg.annotation)
            if t:
                self._param_types[arg.arg] = t
                self._local_types[arg.arg] = t
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()
        self._local_types = saved_locals
        self._param_types = saved_params

    def _sym(self) -> str:
        return self._func_stack[-1] if self._func_stack else "<module>"

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            t = _ann_to_model(node.annotation)
            if t:
                self._local_types[node.target.id] = t
            elif node.value is not None:
                inferred = self._infer_expr_type(node.value)
                if inferred:
                    self._local_types[node.target.id] = inferred
        attr = self._attr_name(node.target)
        if attr in SENSITIVE_ATTRS:
            self.hits.append(("DIRECT_SENSITIVE_ATTR_MUTATION", attr, node.lineno, self._sym()))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        inferred = self._infer_expr_type(node.value)
        for t in node.targets:
            if isinstance(t, ast.Name) and inferred:
                self._local_types[t.id] = inferred
            if isinstance(t, ast.Tuple) and isinstance(node.value, (ast.Tuple, ast.List)):
                for elt_t, elt_v in zip(t.elts, node.value.elts):
                    if isinstance(elt_t, ast.Name):
                        iv = self._infer_expr_type(elt_v)
                        if iv:
                            self._local_types[elt_t.id] = iv
            attr = self._attr_name(t)
            if attr in SENSITIVE_ATTRS:
                self.hits.append(("DIRECT_SENSITIVE_ATTR_MUTATION", attr, node.lineno, self._sym()))
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        attr = self._attr_name(node.target)
        if attr in SENSITIVE_ATTRS:
            self.hits.append(("DIRECT_SENSITIVE_ATTR_MUTATION", attr, node.lineno, self._sym()))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        ctor = self._ctor_name(node.func)
        if ctor:
            self.hits.append(("ORM_CONSTRUCTOR", ctor, node.lineno, self._sym()))

        if isinstance(node.func, ast.Attribute) and node.func.attr in {"add", "add_all"}:
            if self._looks_like_session_receiver(node.func.value):
                if node.func.attr == "add":
                    target = self._resolve_add_target(node.args[0] if node.args else None)
                    self.hits.append(("ORM_ADD", target, node.lineno, self._sym()))
                else:
                    for tgt in self._resolve_add_all_targets(node.args[0] if node.args else None):
                        self.hits.append(("ORM_ADD", tgt, node.lineno, self._sym()))

        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "bulk_insert_mappings",
            "bulk_update_mappings",
            "bulk_save_objects",
            "merge",
        }:
            target = self._first_arg_model(node) or node.func.attr
            op = "ORM_MERGE" if node.func.attr == "merge" else "ORM_BULK"
            self.hits.append((op, target, node.lineno, self._sym()))

        if isinstance(node.func, ast.Attribute) and node.func.attr in {"update", "delete"}:
            if self._call_chain_has_query(node.func.value):
                tgt = self._extract_query_model(node.func.value) or "QUERY"
                self.hits.append(("QUERY_UPDATE_DELETE", tgt, node.lineno, self._sym()))

        if isinstance(node.func, ast.Name) and node.func.id in {"insert", "update", "delete"}:
            tgt = self._first_arg_model(node) or node.func.id
            if tgt in SENSITIVE_MODEL_NAMES:
                self.hits.append(("SA_CORE_INSERT_UPDATE_DELETE", tgt, node.lineno, self._sym()))

        # model.__table__.insert() / table.insert()
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"insert", "update", "delete"}:
            tgt = self._table_attr_model(node.func.value)
            if tgt and tgt in SENSITIVE_MODEL_NAMES:
                self.hits.append(("SA_CORE_INSERT_UPDATE_DELETE", tgt, node.lineno, self._sym()))

        if isinstance(node.func, ast.Name) and node.func.id == "text" and node.args:
            lit = self._const_str(node.args[0])
            if lit:
                self._emit_raw_sql_from_text(lit, node.lineno)

        self.generic_visit(node)

    def _emit_raw_sql_from_text(self, lit: str, lineno: int) -> None:
        for m in _RAW_SQL_RE.finditer(lit):
            table = m.group(2).strip("`\"'[]").lower()
            if table in SENSITIVE_TABLE_NAMES or _SENSITIVE_TABLE_RE.search(lit):
                self.hits.append(("RAW_SQL_DML", table, lineno, self._sym()))

    def _resolve_add_target(self, arg: Optional[ast.AST]) -> str:
        if arg is None:
            return "ORM_ADD_UNRESOLVED_TARGET"
        inferred = self._infer_expr_type(arg)
        if inferred and inferred in SENSITIVE_MODEL_NAMES:
            return inferred
        if inferred and inferred not in SENSITIVE_MODEL_NAMES:
            return f"NON_SENSITIVE:{inferred}"
        return "ORM_ADD_UNRESOLVED_TARGET"

    def _resolve_add_all_targets(self, arg: Optional[ast.AST]) -> list[str]:
        if arg is None:
            return ["ORM_ADD_UNRESOLVED_TARGET"]
        if isinstance(arg, (ast.List, ast.Tuple)):
            out: list[str] = []
            for elt in arg.elts:
                out.append(self._resolve_add_target(elt))
            return out or ["ORM_ADD_UNRESOLVED_TARGET"]
        return [self._resolve_add_target(arg)]

    @staticmethod
    def _looks_like_session_receiver(node: ast.AST) -> bool:
        """True for db/session-like receivers; False for set/list .add false positives."""
        session_names = {
            "db",
            "session",
            "sess",
            "sa_session",
            "db_session",
            "connection",
            "conn",
        }
        if isinstance(node, ast.Name):
            return node.id in session_names or node.id.endswith("_db") or node.id.endswith("_session")
        if isinstance(node, ast.Attribute):
            return node.attr in session_names or node.attr.endswith("_db") or node.attr.endswith("_session")
        return False

    def _infer_expr_type(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Call):
            ctor = self._ctor_name(node.func)
            if ctor:
                return ctor
            # factory call by name
            if isinstance(node.func, ast.Name):
                if node.func.id in self._fn_return_types and self._fn_return_types[node.func.id]:
                    return self._fn_return_types[node.func.id]
            if isinstance(node.func, ast.Attribute):
                # models.X(...) already handled by ctor; other attrs unknown
                pass
        if isinstance(node, ast.Name):
            if node.id in self._local_types:
                return self._local_types[node.id]
            if node.id in self._param_types:
                return self._param_types[node.id]
            if node.id in SENSITIVE_MODEL_NAMES:
                return node.id
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "models" and node.attr in SENSITIVE_MODEL_NAMES:
                return node.attr
        return None

    @staticmethod
    def _attr_name(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    @staticmethod
    def _const_str(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):  # f-string — skip
            return None
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
    def _table_attr_model(node: ast.AST) -> Optional[str]:
        # models.KnowledgeUnit.__table__ or KnowledgeUnit.__table__
        if isinstance(node, ast.Attribute) and node.attr == "__table__":
            if isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name):
                if node.value.value.id == "models" and node.value.attr in SENSITIVE_MODEL_NAMES:
                    return node.value.attr
            if isinstance(node.value, ast.Name) and node.value.id in SENSITIVE_MODEL_NAMES:
                return node.value.id
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


def _filter_hit(operation: str, target: str, *, rel_path: str) -> bool:
    if operation == "ORM_CONSTRUCTOR":
        return target in SENSITIVE_MODEL_NAMES
    if operation == "ORM_ADD":
        if target.startswith("NON_SENSITIVE:"):
            return False
        if target in SENSITIVE_MODEL_NAMES:
            return True
        if target == "ORM_ADD_UNRESOLVED_TARGET":
            # Only inventory unresolved adds on I5/knowledge surfaces.
            return _path_is_i5_knowledge_surface(rel_path)
        return False
    if operation in {"ORM_BULK", "ORM_MERGE", "SA_CORE_INSERT_UPDATE_DELETE", "QUERY_UPDATE_DELETE"}:
        return target in SENSITIVE_MODEL_NAMES or target.lower() in SENSITIVE_TABLE_NAMES
    if operation == "RAW_SQL_DML":
        return target.lower() in SENSITIVE_TABLE_NAMES
    if operation == "DIRECT_SENSITIVE_ATTR_MUTATION":
        return target in SENSITIVE_ATTRS
    return False


def _eligibility_mutation_unauthorized(target: str, path: str, lineno: int, source: str) -> bool:
    if target != "runtime_eligibility":
        return False
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


def _scan_raw_sql_whole_source(source: str, visitor: _RepoWriterVisitor) -> None:
    """Multiline-robust raw SQL detection across the whole file text."""
    for m in _RAW_SQL_RE.finditer(source):
        table = m.group(2).strip("`\"'[]").lower()
        if table not in SENSITIVE_TABLE_NAMES and not _SENSITIVE_TABLE_RE.search(m.group(0)):
            # Also accept when table appears after UPDATE with newlines
            window = source[m.start() : m.start() + 200]
            tm = _SENSITIVE_TABLE_RE.search(window)
            if not tm:
                continue
            table = tm.group(1).lower()
        lineno = source[: m.start()].count("\n") + 1
        visitor.hits.append(("RAW_SQL_DML", table, lineno, "<module>"))


def scan_source_text(
    source: str,
    *,
    rel_path: str,
    force_unclassified: bool = False,
) -> list[WriterHit]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    visitor = _RepoWriterVisitor()
    # First pass: collect function return annotations before body walk completeness —
    # visitor already records returns when entering each function.
    visitor.visit(tree)
    _scan_raw_sql_whole_source(source, visitor)

    hits: list[WriterHit] = []
    seen: set[tuple[str, str, int]] = set()
    for op, target, lineno, sym in visitor.hits:
        if not _filter_hit(op, target, rel_path=rel_path):
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
            # Unresolved ORM_ADD on allowlisted I5 path: retain hit for inventory but keep allowed.
            if (
                op == "ORM_ADD"
                and target == "ORM_ADD_UNRESOLVED_TARGET"
                and not allowed
                and classification
                not in {"TEST_ONLY_WRITER", "MIGRATION_ONLY_WRITER", "BOOTSTRAP_SEED_WRITER"}
            ):
                classification = "UNAUTHORIZED_WRITER"
                reason = "unresolved ORM_ADD target on I5 surface"
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


def discover_unscanned_db_writing_roots() -> list[str]:
    """Find backend package dirs with sensitive I5 writes outside SCAN_ROOTS."""
    ws = _workspace_root()
    backend = ws / "backend"
    configured = {r.replace("backend/", "").split("/")[0] for r in SCAN_ROOTS}
    configured |= {"tests", "alembic"}
    suspects: list[str] = []
    sensitive_tokens = tuple(SENSITIVE_MODEL_NAMES) + tuple(SENSITIVE_TABLE_NAMES)
    write_markers = ("session.add", "db.add", "add_all(", "bulk_insert", "bulk_update", ".execute(")
    for child in backend.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if name in configured or name.startswith(".") or name in {"__pycache__", "venv", ".venv"}:
            continue
        hit = False
        for p in child.rglob("*.py"):
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not any(m in txt for m in write_markers):
                continue
            if any(tok in txt for tok in sensitive_tokens):
                hit = True
                break
        if hit:
            suspects.append(f"backend/{name}")
    return suspects


def extract_migration_i5_tables() -> set[str]:
    """Static extraction of I5 table names from migrations 051–065.

    Supports both ``op.create_table('…')`` and raw SQL ``CREATE TABLE …``
    inside ``op.execute`` strings used by KNOW02/03/04 migrations.
    """
    ws = _workspace_root()
    root = ws / MIGRATION_ROOT
    tables: set[str] = set()
    if not root.exists():
        return tables
    create_op_re = re.compile(
        r"""create_table\(\s*['\"]([a-z0-9_]+)['\"]""",
        re.IGNORECASE,
    )
    create_sql_re = re.compile(
        r"""CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z0-9_]+)""",
        re.IGNORECASE,
    )
    for p in root.glob("*.py"):
        if not re.match(r"0(5[1-9]|6[0-5])_", p.name):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for rx in (create_op_re, create_sql_re):
            for m in rx.finditer(text):
                tn = m.group(1).lower()
                if _is_i5_persistence_tablename(tn):
                    tables.add(tn)
    return tables


def reconcile_migration_i5_tables(
    universe: PersistenceUniverse | None = None,
) -> dict[str, str]:
    """Map each migration I5 table to FOUND_IN_MODEL / SCHEMA_ONLY / EXCLUDED / UNEXPLAINED."""
    universe = universe or reconstruct_persistence_universe()
    model_tables = {e.tablename for e in universe.entries}
    result: dict[str, str] = {}
    for tn in sorted(extract_migration_i5_tables()):
        if tn in EXPLICIT_TABLE_EXCLUSIONS:
            result[tn] = f"EXCLUDED:{EXPLICIT_TABLE_EXCLUSIONS[tn]}"
        elif tn in model_tables:
            result[tn] = "FOUND_IN_CURRENT_MODEL_UNIVERSE"
        elif tn in EXPLICIT_SCHEMA_ONLY_SENSITIVE_TABLES:
            result[tn] = "SCHEMA_ONLY_CURRENT_TABLE"
        else:
            # Migration created it; if not in models and not excluded → unexplained
            result[tn] = "UNEXPLAINED"
    return result


def scan_repository(*, include_migrations: bool = True, include_tests: bool = True) -> ScanReport:
    refresh_sensitive_regexes()
    ws = _workspace_root()
    report = ScanReport(
        scan_roots_used=[],
        exclusions=list(EXCLUDED_ROOT_GLOBS)
        + [
            "documentation",
            "generated caches",
            "alembic versions classified MIGRATION_ONLY (scanned)",
        ],
    )
    roots: list[Path] = []
    for rel in SCAN_ROOTS:
        p = ws / rel
        if p.exists():
            roots.append(p)
            report.scan_roots_used.append(rel)
        else:
            report.absent_roots.append(rel)
            report.scan_roots_used.append(f"{rel} (absent)")

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
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            report.hits.extend(scan_source_text(text, rel_path=rel))
    return report


def inventory_summary(report: ScanReport | None = None) -> dict[str, int]:
    report = report or scan_repository()
    by_op = {}
    for h in report.hits:
        by_op[h.operation] = by_op.get(h.operation, 0) + 1
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
        "ORM_CONSTRUCTOR_HITS": by_op.get("ORM_CONSTRUCTOR", 0),
        "ORM_ADD_HITS": by_op.get("ORM_ADD", 0),
        "ORM_BULK_HITS": by_op.get("ORM_BULK", 0),
        "ORM_MERGE_HITS": by_op.get("ORM_MERGE", 0),
        "SA_CORE_DML_HITS": by_op.get("SA_CORE_INSERT_UPDATE_DELETE", 0),
        "QUERY_UPDATE_DELETE_HITS": by_op.get("QUERY_UPDATE_DELETE", 0),
        "RAW_SQL_DML_HITS": by_op.get("RAW_SQL_DML", 0),
        "DIRECT_SENSITIVE_ATTR_MUTATION_HITS": by_op.get("DIRECT_SENSITIVE_ATTR_MUTATION", 0),
        "UNRESOLVED_ORM_ADD_TARGET_COUNT": len(report.unresolved_orm_add),
        "RAW_SQL_SENSITIVE_WRITE_COUNT": len(raw),
        "RAW_SQL_UNCLASSIFIED_COUNT": sum(1 for h in raw if not h.allowed),
        "BULK_SENSITIVE_WRITE_COUNT": len(bulk),
        "MERGE_SENSITIVE_WRITE_COUNT": len(merge),
        "QUERY_UPDATE_SENSITIVE_WRITE_COUNT": len(qu),
        "UNCLASSIFIED_BULK_OR_MERGE_COUNT": sum(1 for h in bulk + merge + qu if not h.allowed),
        "DIRECT_MUTATION_HITS": len(mut),
        "UNAUTHORIZED_DIRECT_ELIGIBILITY_MUTATION_COUNT": len(elig_unauth),
        "STALE_PATH_CLASSIFICATION_COUNT": len(stale_path_classification_entries()),
        "UNSCANNED_DB_WRITING_RUNTIME_ROOT_COUNT": len(discover_unscanned_db_writing_roots()),
    }


# ---------------------------------------------------------------------------
# Negative-control detectors
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


def detect_negative_raw_sql_study_population() -> bool:
    src = (
        "from sqlalchemy import text\n"
        "def evil(db):\n"
        "    db.execute(text(\"UPDATE i5_study_populations SET age_min=0\"))\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_sql_pop.py", force_unclassified=True)
    return any(h.operation == "RAW_SQL_DML" and "study_population" in h.target for h in hits)


def detect_negative_raw_sql_study_effect() -> bool:
    src = (
        "from sqlalchemy import text\n"
        "def evil(db):\n"
        "    db.execute(text(\"UPDATE i5_study_effect_estimates SET effect_value=1\"))\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_sql_eff.py", force_unclassified=True)
    return any(h.operation == "RAW_SQL_DML" and "effect" in h.target for h in hits)


def detect_negative_raw_sql_recommendation_evidence() -> bool:
    src = (
        "from sqlalchemy import text\n"
        "def evil(db):\n"
        "    db.execute(text(\"UPDATE i5_clinical_recommendation_evidence_links SET support_direction='X'\"))\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_sql_rec.py", force_unclassified=True)
    return any(h.operation == "RAW_SQL_DML" and "recommendation_evidence" in h.target for h in hits)


def detect_negative_raw_sql_multiline() -> bool:
    src = (
        "from sqlalchemy import text\n"
        "def evil(db):\n"
        "    db.execute(text(\"\"\"\n"
        "UPDATE\n"
        "    i5_study_effect_estimates\n"
        "SET effect_value=1\n"
        "\"\"\"))\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_sql_ml.py", force_unclassified=True)
    return any(h.operation == "RAW_SQL_DML" for h in hits)


def detect_negative_raw_sql_case_variation() -> bool:
    src = (
        "from sqlalchemy import text\n"
        "def evil(db):\n"
        "    db.execute(text(\"update I5_Study_Populations set age_min=1\"))\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_sql_case.py", force_unclassified=True)
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


def detect_negative_core_table_insert() -> bool:
    src = (
        "from backend.app import models\n"
        "def evil(session):\n"
        "    session.execute(models.KnowledgeUnit.__table__.insert().values(canonical_unit_id='x'))\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_table_ins.py", force_unclassified=True)
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


def detect_negative_secondary_sensitive_mutation() -> bool:
    src = (
        "def evil(ku):\n"
        "    ku.publication_state = 'PUBLISHED'\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_mut2.py", force_unclassified=True)
    return any(
        h.operation == "DIRECT_SENSITIVE_ATTR_MUTATION" and h.target == "publication_state"
        for h in hits
    )


def detect_negative_orm_add_indirect() -> bool:
    src = (
        "from backend.app import models\n"
        "def build_sensitive_ku() -> models.KnowledgeUnit:\n"
        "    return models.KnowledgeUnit(canonical_unit_id='x')\n"
        "def evil(db):\n"
        "    obj = build_sensitive_ku()\n"
        "    db.add(obj)\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_add_ind.py", force_unclassified=True)
    return any(h.operation == "ORM_ADD" and h.target == "KnowledgeUnit" for h in hits)


def detect_negative_orm_add_all_indirect() -> bool:
    src = (
        "from backend.app import models\n"
        "def build_ku() -> models.KnowledgeUnit:\n"
        "    return models.KnowledgeUnit(canonical_unit_id='x')\n"
        "def build_provenance() -> models.KnowledgeProvenance:\n"
        "    return models.KnowledgeProvenance(knowledge_unit_id=1)\n"
        "def evil_many(db):\n"
        "    ku = build_ku()\n"
        "    prov = build_provenance()\n"
        "    db.add_all([ku, prov])\n"
    )
    hits = scan_source_text(src, rel_path="app/services/i5/evil_add_all.py", force_unclassified=True)
    targets = {h.target for h in hits if h.operation == "ORM_ADD"}
    return "KnowledgeUnit" in targets and "KnowledgeProvenance" in targets
