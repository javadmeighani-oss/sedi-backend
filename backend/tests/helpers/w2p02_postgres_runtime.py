"""W2-P01 GitHub PostgreSQL knowledge memory runtime helper (v503-pattern contract).

No top-level backend.app import, engine creation, or DB connection.
"""
from __future__ import annotations

import importlib
import json
import os
import platform
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlparse

# --- Governed sentinels (frozen) ---
SENTINEL_GITHUB_POSTGRES_TARGET_REFUSED = "SENTINEL_GITHUB_POSTGRES_TARGET_REFUSED"
SENTINEL_GITHUB_POSTGRES_PRODUCTION_IDENTIFIER_REFUSED = (
    "SENTINEL_GITHUB_POSTGRES_PRODUCTION_IDENTIFIER_REFUSED"
)
SENTINEL_GITHUB_POSTGRES_URL_MISMATCH = "SENTINEL_GITHUB_POSTGRES_URL_MISMATCH"
SENTINEL_APPLICATION_IMPORT_BEFORE_TEST_DATABASE_BINDING = (
    "SENTINEL_APPLICATION_IMPORT_BEFORE_TEST_DATABASE_BINDING"
)
SENTINEL_RUNTIME_NODE_MANIFEST_MISMATCH = "SENTINEL_RUNTIME_NODE_MANIFEST_MISMATCH"
SENTINEL_RUNTIME_BOOTSTRAP_FORBIDDEN_IN_COLLECT_ONLY = (
    "SENTINEL_RUNTIME_BOOTSTRAP_FORBIDDEN_IN_COLLECT_ONLY"
)
BLOCKED_DEPENDENCY_RESOLUTION = "BLOCKED_DEPENDENCY_RESOLUTION"
CONTROLLED_FIXTURE_CLEANUP_FAILED = "CONTROLLED_FIXTURE_CLEANUP_FAILED"

EXPECTED_HOST = "127.0.0.1"
EXPECTED_PORT = 5432
EXPECTED_DATABASE = "sedi_w2p02_safety"
EXPECTED_USER = "sedi_w2p02_test"
EXPECTED_PASSWORD = "sedi_w2p02_test_password"
EXPECTED_TEST_URL = (
    f"postgresql+psycopg2://{EXPECTED_USER}:{EXPECTED_PASSWORD}@"
    f"{EXPECTED_HOST}:{EXPECTED_PORT}/{EXPECTED_DATABASE}"
)

PRODUCTION_REFUSE_SUBSTRINGS = (
    "api.sedi-ai.com",
    "sedi-cloudir",
    "sedi-backend",
    "sedi-postgres",
    "production",
    "prod",
    "live",
    "staging",
    "staging-prod",
    "sedi_db",
)

W2P02_EXPECTED_SCHEMA_TABLES: tuple[str, ...] = (
    "knowledge_conflicts",
    "knowledge_safety_reviews",
    "knowledge_units",
    "knowledge_memory_items",
    "knowledge_memory_transitions",
    "knowledge_provenance",
    "governed_source_profiles",
    "knowledge_gaps",
    "i5_raw_evidence",
    "weekly_knowledge_runs",
    "i5_governance_decisions",
)

_W2P02_TEST = "backend/tests/test_section30_i5_w2_p02_conflict_safety.py"

W2P02_RUNTIME_SELECTORS: tuple[str, ...] = (
    f"{_W2P02_TEST}::test_W2P02_T5_01_metadata_contains_safety_tables",
    f"{_W2P02_TEST}::test_W2P02_T5_02_named_checks_present_in_pg_catalog",
    f"{_W2P02_TEST}::test_W2P02_T6_01_create_conflict",
    f"{_W2P02_TEST}::test_W2P02_T6_02_resolve_conflict",
    f"{_W2P02_TEST}::test_W2P02_T6_03_enqueue_safety_review",
    f"{_W2P02_TEST}::test_W2P02_T6_04_freshness_current",
    f"{_W2P02_TEST}::test_W2P02_T6_05_eligibility_eligible_path",
    f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints",
    f"{_W2P02_TEST}::test_W2P02_T8_uq_fk_runtime_negative",
    f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards",
)

W2P02_EXPECTED_RUNTIME_NODE_IDS: frozenset[str] = frozenset(
    (
        f"{_W2P02_TEST}::test_W2P02_T5_01_metadata_contains_safety_tables",
        f"{_W2P02_TEST}::test_W2P02_T5_02_named_checks_present_in_pg_catalog",
        f"{_W2P02_TEST}::test_W2P02_T6_01_create_conflict",
        f"{_W2P02_TEST}::test_W2P02_T6_02_resolve_conflict",
        f"{_W2P02_TEST}::test_W2P02_T6_03_enqueue_safety_review",
        f"{_W2P02_TEST}::test_W2P02_T6_04_freshness_current",
        f"{_W2P02_TEST}::test_W2P02_T6_05_eligibility_eligible_path",
        f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints[W2P02-T7-ck_kc_conflict_state_vocab]",
        f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints[W2P02-T7-ck_kc_idempotency_key_format]",
        f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints[W2P02-T7-ck_kc_units_ordered]",
        f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints[W2P02-T7-ck_kc_units_ordered_equal]",
        f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints[W2P02-T7-ck_ksr_queue_status_vocab]",
        f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints[W2P02-T7-ck_ksr_medical_safety_state_vocab]",
        f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints[W2P02-T7-ck_ksr_idempotency_key_format]",
        f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints[W2P02-T7-ck_kc_conflict_state_vocab_update]",
        f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints[W2P02-T7-ck_ksr_queue_status_vocab_update]",
        f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints[W2P02-T7-ck_ksr_medical_safety_state_vocab_update]",
        f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints[W2P02-T7-ck_kc_idempotency_key_format_update]",
        f"{_W2P02_TEST}::test_W2P02_T7_negative_check_constraints[W2P02-T7-ck_ksr_idempotency_key_format_update]",
        f"{_W2P02_TEST}::test_W2P02_T8_uq_fk_runtime_negative[W2P02-T8-uq_kc_idempotency_key]",
        f"{_W2P02_TEST}::test_W2P02_T8_uq_fk_runtime_negative[W2P02-T8-uq_kc_unit_pair]",
        f"{_W2P02_TEST}::test_W2P02_T8_uq_fk_runtime_negative[W2P02-T8-uq_kc_conflict_key]",
        f"{_W2P02_TEST}::test_W2P02_T8_uq_fk_runtime_negative[W2P02-T8-fk_kc_ku_a]",
        f"{_W2P02_TEST}::test_W2P02_T8_uq_fk_runtime_negative[W2P02-T8-fk_kc_ku_b]",
        f"{_W2P02_TEST}::test_W2P02_T8_uq_fk_runtime_negative[W2P02-T8-uq_ksr_queue_item_id]",
        f"{_W2P02_TEST}::test_W2P02_T8_uq_fk_runtime_negative[W2P02-T8-uq_ksr_idempotency_key]",
        f"{_W2P02_TEST}::test_W2P02_T8_uq_fk_runtime_negative[W2P02-T8-fk_ksr_knowledge_unit_id]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-freshness_unknown]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-freshness_stale]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-freshness_expired_valid_until]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-freshness_expired_policy]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-conflict_blocks_eligibility]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-blocked_safety]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-retraction_revoked]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-illegal_conflict_transition]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-illegal_medical_safety_transition]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-high_risk_human]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-idempotent_conflict]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-matrix_eligible]",
        f"{_W2P02_TEST}::test_W2P02_T9_fail_closed_matrix_and_guards[W2P02-T9-matrix_withdrawn]",
    )
)

EXPECTED_RUNTIME_NODE_COUNT = 40

EXPECTED_SELECTOR_COUNT = 10

_IMPORT_GUARD_COMPLETE = False
_ENGINE_REGISTRY: list[Any] = []


@dataclass
class W2P02GitHubPostgresEvidence:
    mode: str = ""
    run_id: str = ""
    workflow_sha: str = ""
    commit_sha: str = ""
    runner_os: str = ""
    python_version: str = ""
    postgres_image: str = "postgres:15"
    database_name: str = ""
    target_host: str = ""
    target_port: int = 0
    test_url_redacted: str = ""
    url_equality_pass: bool = False
    production_refusal_pass: bool = False
    import_guard_pass: bool = False
    dependency_versions: dict[str, str] = field(default_factory=dict)
    schema_tables: list[str] = field(default_factory=list)
    selector_count: int = 0
    collected_node_ids: list[str] = field(default_factory=list)
    manifest_equality_pass: bool = False
    diagnostic_events: list[dict[str, Any]] = field(default_factory=list)
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    failure_markers: list[str] = field(default_factory=list)
    cleanup_result: str = ""
    cleanup_events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class W2P02PluginState:
    collect_only_mode: bool = False
    runtime_mode: bool = False
    manifest_pass: bool = False
    runtime_bootstrapped: bool = False
    active_node_id: Optional[str] = None
    evidence: W2P02GitHubPostgresEvidence = field(default_factory=W2P02GitHubPostgresEvidence)
    engine: Any = None
    handle_error_registered: bool = False
    diagnostic_dedupe: set[tuple[str, Optional[str], Optional[str]]] = field(default_factory=set)
    _handle_error_callable: Optional[Callable[..., None]] = None


class W2P02HarnessError(RuntimeError):
    """Controlled harness failure with governed marker."""


def detect_collect_only_mode(config: Any) -> bool:
    return bool(getattr(config.option, "collectonly", False))


def detect_runtime_mode(config: Any) -> bool:
    return not detect_collect_only_mode(config)


def assert_no_db_bootstrap_in_collect_only(collect_only_mode: bool) -> None:
    if collect_only_mode:
        raise W2P02HarnessError(SENTINEL_RUNTIME_BOOTSTRAP_FORBIDDEN_IN_COLLECT_ONLY)


def scrub_inherited_database_env() -> None:
    for key in (
        "SEDI_W2P02_PG_ADMIN_URL",
        "SEDI_W2P02_PG_TEST_URL",
        "SEDI_W2P02_PG_OWNERSHIP_MARKER",
    ):
        os.environ.pop(key, None)


def _redact_url(url: str) -> str:
    if not url:
        return url
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        user = parsed.username or ""
        db = (parsed.path or "").lstrip("/")
        return f"{parsed.scheme}://{user}:***@{host}{port}/{db}"
    except Exception:
        return "<redacted>"


def refuse_production_shared_targets(test_url: str) -> None:
    lower = test_url.lower()
    for token in PRODUCTION_REFUSE_SUBSTRINGS:
        if token in lower:
            raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_PRODUCTION_IDENTIFIER_REFUSED)
    parsed = urlparse(test_url)
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "::1"}:
        raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_TARGET_REFUSED)
    if host != EXPECTED_HOST:
        raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_TARGET_REFUSED)
    if parsed.port not in (None, EXPECTED_PORT):
        raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_TARGET_REFUSED)


def parse_and_validate_github_test_url(test_url: str) -> dict[str, Any]:
    refuse_production_shared_targets(test_url)
    parsed = urlparse(test_url)
    database = (parsed.path or "").lstrip("/")
    if database != EXPECTED_DATABASE:
        raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_TARGET_REFUSED)
    if (parsed.username or "") != EXPECTED_USER:
        raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_TARGET_REFUSED)
    return {
        "host": parsed.hostname,
        "port": parsed.port or EXPECTED_PORT,
        "database": database,
        "user": parsed.username,
        "redacted_url": _redact_url(test_url),
    }


def bind_github_database_environment(test_url: str) -> None:
    parsed = parse_and_validate_github_test_url(test_url)
    os.environ["DATABASE_URL"] = test_url
    os.environ["TEST_DATABASE_URL"] = test_url
    os.environ["APP_ENV"] = "test_isolated"
    os.environ["ENVIRONMENT"] = "test_isolated"
    os.environ["ENV"] = "test_isolated"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ.setdefault("OPENAI_API_KEY", "w2p02-test-placeholder-not-used")
    _ = parsed


def verify_bound_environment(expected_db_name: str, expected_host: str) -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    test_url = os.environ.get("TEST_DATABASE_URL", "")
    if not db_url or not test_url:
        raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_URL_MISMATCH)
    if db_url != test_url:
        raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_URL_MISMATCH)
    parsed = parse_and_validate_github_test_url(db_url)
    if parsed["database"] != expected_db_name or parsed["host"] != expected_host:
        raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_URL_MISMATCH)
    for key, expected in (
        ("APP_ENV", "test_isolated"),
        ("ENVIRONMENT", "test_isolated"),
        ("ENV", "test_isolated"),
    ):
        if os.environ.get(key) != expected:
            raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_URL_MISMATCH)


def assert_import_guard_completed() -> None:
    if not _IMPORT_GUARD_COMPLETE:
        raise W2P02HarnessError(SENTINEL_APPLICATION_IMPORT_BEFORE_TEST_DATABASE_BINDING)


def mark_import_guard_complete() -> None:
    global _IMPORT_GUARD_COMPLETE
    verify_bound_environment(EXPECTED_DATABASE, EXPECTED_HOST)
    _IMPORT_GUARD_COMPLETE = True


def import_database_module_after_binding():
    assert_import_guard_completed()
    return importlib.import_module("backend.app.database")


def import_models_after_binding():
    assert_import_guard_completed()
    return importlib.import_module("backend.app.models")


def _normalize_node_id(node_id: str) -> str:
    return node_id.replace("\\", "/")


def verify_runtime_selector_manifest(
    collected_node_ids: Iterable[str],
    expected_ids: Optional[frozenset[str]] = None,
) -> list[str]:
    expected = expected_ids or W2P02_EXPECTED_RUNTIME_NODE_IDS
    collected = sorted({_normalize_node_id(node_id) for node_id in collected_node_ids})
    if len(collected) != EXPECTED_RUNTIME_NODE_COUNT:
        raise W2P02HarnessError(SENTINEL_RUNTIME_NODE_MANIFEST_MISMATCH)
    missing = sorted(expected - set(collected))
    extra = sorted(set(collected) - expected)
    if missing or extra:
        raise W2P02HarnessError(SENTINEL_RUNTIME_NODE_MANIFEST_MISMATCH)
    return collected


def refuse_schema_start_after_manifest_mismatch(manifest_pass: bool) -> None:
    if not manifest_pass:
        raise W2P02HarnessError(SENTINEL_RUNTIME_NODE_MANIFEST_MISMATCH)


def create_test_engine():
    assert_import_guard_completed()
    from sqlalchemy import create_engine

    engine = create_engine(os.environ["TEST_DATABASE_URL"], future=True)
    _ENGINE_REGISTRY.append(engine)
    return engine


def create_all_schema(engine) -> list[str]:
    database_mod = import_database_module_after_binding()
    import_models_after_binding()
    database_mod.Base.metadata.create_all(bind=engine)
    return sorted(database_mod.Base.metadata.tables.keys())


def verify_w2p02_schema_tables(engine, expected_tables: tuple[str, ...]) -> None:
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(engine)
    present = set(inspector.get_table_names())
    missing = [t for t in expected_tables if t not in present]
    if missing:
        raise W2P02HarnessError(
            f"CONTROLLED_SCHEMA_SETUP_FAILED missing tables: {','.join(missing)}"
        )


def create_db_session(connection):
    from sqlalchemy.orm import Session

    return Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )


def build_outer_transaction_db_fixture(connection):
    return create_db_session(connection)


def recover_session_after_integrity_error(session):
    """Reserved for unexpected non-nested failures only."""
    try:
        session.rollback()
    except Exception:
        pass
    try:
        session.expire_all()
    except Exception:
        pass
    return session


def extract_integrity_diagnostics(exc: BaseException) -> dict[str, Any]:
    orig = getattr(exc, "orig", exc)
    diag = getattr(orig, "diag", None)
    return {
        "sqlstate": getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None),
        "constraint_name": getattr(diag, "constraint_name", None) if diag else None,
        "table_name": getattr(diag, "table_name", None) if diag else None,
        "column_name": getattr(diag, "column_name", None) if diag else None,
    }


def extract_handle_error_diagnostics(exception_context: Any) -> dict[str, Any]:
    exc = getattr(exception_context, "original_exception", None) or getattr(
        exception_context, "sqlalchemy_exception", None
    )
    if exc is None:
        return {}
    return extract_integrity_diagnostics(exc)


def set_active_node_id(state: W2P02PluginState, node_id: str) -> None:
    state.active_node_id = node_id


def clear_active_node_id(state: W2P02PluginState) -> None:
    state.active_node_id = None


def correlate_diagnostic_to_node(
    state: W2P02PluginState, node_id: str, diag: dict[str, Any]
) -> dict[str, Any]:
    payload = {
        "node_id": node_id,
        **diag,
    }
    key = (node_id, payload.get("sqlstate"), payload.get("constraint_name"))
    if key in state.diagnostic_dedupe:
        return payload
    state.diagnostic_dedupe.add(key)
    state.evidence.diagnostic_events.append(payload)
    return payload


def record_correlated_diagnostic(state: W2P02PluginState, diag: dict[str, Any]) -> None:
    node_id = state.active_node_id
    if not node_id:
        return
    correlate_diagnostic_to_node(state, node_id, diag)


def _make_handle_error_listener(state: W2P02PluginState):
    def _listener(exception_context):
        if not state.runtime_mode or state.collect_only_mode:
            return
        diag = extract_handle_error_diagnostics(exception_context)
        if diag:
            record_correlated_diagnostic(state, diag)

    return _listener


def register_handle_error_listener(engine, state: W2P02PluginState) -> None:
    assert_no_db_bootstrap_in_collect_only(state.collect_only_mode)
    if state.handle_error_registered:
        return
    from sqlalchemy import event

    listener = _make_handle_error_listener(state)
    event.listen(engine, "handle_error", listener)
    state._handle_error_callable = listener
    state.handle_error_registered = True


def remove_handle_error_listener(engine, state: W2P02PluginState) -> None:
    if not state.handle_error_registered or state._handle_error_callable is None:
        return
    from sqlalchemy import event

    try:
        event.remove(engine, "handle_error", state._handle_error_callable)
    except Exception:
        pass
    state.handle_error_registered = False
    state._handle_error_callable = None


def capture_dependency_versions() -> dict[str, str]:
    import sqlalchemy

    versions: dict[str, str] = {
        "python": sys.version.split()[0],
        "sqlalchemy": getattr(sqlalchemy, "__version__", "unknown"),
    }
    try:
        import psycopg2

        versions["psycopg2"] = getattr(psycopg2, "__version__", "unknown")
    except ImportError:
        try:
            import psycopg2_binary  # type: ignore

            versions["psycopg2-binary"] = getattr(psycopg2_binary, "__version__", "unknown")
        except ImportError:
            versions["psycopg2"] = "not_installed"
    try:
        import pytest as _pytest

        versions["pytest"] = getattr(_pytest, "__version__", "unknown")
    except ImportError:
        versions["pytest"] = "not_installed"
    return versions


def verify_sqlalchemy_version_minimum() -> None:
    import sqlalchemy

    version = getattr(sqlalchemy, "__version__", "0")
    major_text = version.split(".", 1)[0]
    try:
        major = int(major_text)
    except ValueError:
        major = 0
    if major < 2:
        raise W2P02HarnessError(BLOCKED_DEPENDENCY_RESOLUTION)


def record_dependency_versions(pip_freeze_subset: dict[str, str]) -> dict[str, str]:
    versions = capture_dependency_versions()
    versions.update(pip_freeze_subset)
    return versions


def resolve_runner_temp_dir(repo_root: Optional[Path] = None) -> Path:
    repo_root = (repo_root or _find_repo_root()).resolve()
    target = (Path(tempfile.gettempdir()) / "sedi_w2p02_postgres_runtime_evidence").resolve()
    target.mkdir(parents=True, exist_ok=True)
    if _path_is_inside(target, repo_root):
        raise W2P02HarnessError("FAIL_UNAUTHORIZED_REPOSITORY_MUTATION evidence path in repo")
    return target


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists() or (parent / "backend").is_dir() and (parent / "docs").is_dir():
            return parent
    return here.parents[3]


def _path_is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def assert_evidence_path_outside_repository(path: Path, repo_root: Optional[Path] = None) -> None:
    repo_root = repo_root or _find_repo_root()
    if _path_is_inside(path.resolve(), repo_root.resolve()):
        raise W2P02HarnessError("FAIL_UNAUTHORIZED_REPOSITORY_MUTATION")


def write_runner_temp_evidence(path: Path, payload: dict[str, Any]) -> None:
    assert_evidence_path_outside_repository(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def capture_redacted_evidence(evidence: W2P02GitHubPostgresEvidence) -> dict[str, Any]:
    return {
        "mode": evidence.mode,
        "run_id": evidence.run_id,
        "workflow_sha": evidence.workflow_sha,
        "commit_sha": evidence.commit_sha,
        "runner_os": evidence.runner_os or platform.platform(),
        "python_version": evidence.python_version or sys.version.split()[0],
        "postgres_image": evidence.postgres_image,
        "database_name": evidence.database_name,
        "target_host": evidence.target_host,
        "target_port": evidence.target_port,
        "test_url_redacted": evidence.test_url_redacted,
        "url_equality_pass": evidence.url_equality_pass,
        "production_refusal_pass": evidence.production_refusal_pass,
        "import_guard_pass": evidence.import_guard_pass,
        "dependency_versions": dict(evidence.dependency_versions),
        "schema_tables": list(evidence.schema_tables),
        "selector_count": evidence.selector_count,
        "collected_node_ids": list(evidence.collected_node_ids),
        "manifest_equality_pass": evidence.manifest_equality_pass,
        "diagnostic_events": list(evidence.diagnostic_events),
        "pass_count": evidence.pass_count,
        "fail_count": evidence.fail_count,
        "skip_count": evidence.skip_count,
        "failure_markers": list(evidence.failure_markers),
        "cleanup_result": evidence.cleanup_result,
        "cleanup_events": list(evidence.cleanup_events),
    }


def record_fixture_cleanup_error(
    state: W2P02PluginState,
    *,
    cleanup_operation: str,
    exc: BaseException,
) -> dict[str, Any]:
    """Record a redacted fixture cleanup failure without secret-bearing payloads."""
    entry = {
        "cleanup_operation": cleanup_operation,
        "exception_type": type(exc).__name__,
        "marker": CONTROLLED_FIXTURE_CLEANUP_FAILED,
        "active_node_id": state.active_node_id,
    }
    state.evidence.cleanup_events.append(entry)
    state.evidence.failure_markers.append(CONTROLLED_FIXTURE_CLEANUP_FAILED)
    state.evidence.cleanup_result = CONTROLLED_FIXTURE_CLEANUP_FAILED
    return entry


def independent_db_resource_cleanup(
    state: W2P02PluginState,
    *,
    session: Any,
    outer_transaction: Any,
    connection: Any,
) -> list[dict[str, Any]]:
    """Attempt session.close, active outer rollback, and connection.close independently."""
    cleanup_errors: list[dict[str, Any]] = []
    if session is not None:
        try:
            session.close()
        except Exception as exc:
            cleanup_errors.append(
                record_fixture_cleanup_error(state, cleanup_operation="session.close", exc=exc)
            )
    if outer_transaction is not None:
        try:
            if getattr(outer_transaction, "is_active", False):
                outer_transaction.rollback()
        except Exception as exc:
            cleanup_errors.append(
                record_fixture_cleanup_error(
                    state, cleanup_operation="outer_transaction.rollback", exc=exc
                )
            )
    if connection is not None:
        try:
            connection.close()
        except Exception as exc:
            cleanup_errors.append(
                record_fixture_cleanup_error(state, cleanup_operation="connection.close", exc=exc)
            )
    return cleanup_errors


def dispose_all_engines() -> None:
    while _ENGINE_REGISTRY:
        engine = _ENGINE_REGISTRY.pop()
        try:
            engine.dispose()
        except Exception:
            pass


def initialize_evidence_context(state: W2P02PluginState, *, mode: str) -> None:
    ev = state.evidence
    ev.mode = mode
    ev.runner_os = platform.platform()
    ev.python_version = sys.version.split()[0]
    ev.run_id = os.environ.get("GITHUB_RUN_ID", "")
    ev.workflow_sha = os.environ.get("GITHUB_SHA", "")
    ev.commit_sha = os.environ.get("GITHUB_SHA", "")


def configure_environment_from_urls(state: W2P02PluginState) -> str:
    """Bind DATABASE_URL and TEST_DATABASE_URL fail-closed; never manufacture URLs."""
    scrub_inherited_database_env()
    raw_db = os.environ.get("DATABASE_URL")
    raw_test = os.environ.get("TEST_DATABASE_URL")
    if raw_db is None or raw_test is None:
        raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_URL_MISMATCH)
    db_url = raw_db.strip()
    test_url = raw_test.strip()
    if not db_url or not test_url:
        raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_URL_MISMATCH)
    if db_url != test_url:
        raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_URL_MISMATCH)
    parse_and_validate_github_test_url(test_url)
    if test_url != EXPECTED_TEST_URL:
        raise W2P02HarnessError(SENTINEL_GITHUB_POSTGRES_URL_MISMATCH)
    # Reassign only after both supplied URLs were present, non-empty, equal, and target-valid.
    bind_github_database_environment(test_url)
    verify_bound_environment(EXPECTED_DATABASE, EXPECTED_HOST)
    parsed = parse_and_validate_github_test_url(test_url)
    state.evidence.database_name = parsed["database"]
    state.evidence.target_host = parsed["host"] or ""
    state.evidence.target_port = int(parsed["port"] or EXPECTED_PORT)
    state.evidence.test_url_redacted = parsed["redacted_url"]
    state.evidence.url_equality_pass = True
    state.evidence.production_refusal_pass = True
    state.evidence.selector_count = len(W2P02_RUNTIME_SELECTORS)
    return test_url


def runtime_bootstrap_after_manifest(state: W2P02PluginState) -> None:
    refuse_schema_start_after_manifest_mismatch(state.manifest_pass)
    assert_no_db_bootstrap_in_collect_only(state.collect_only_mode)
    if state.runtime_bootstrapped:
        return
    verify_sqlalchemy_version_minimum()
    state.evidence.dependency_versions = capture_dependency_versions()
    mark_import_guard_complete()
    state.evidence.import_guard_pass = True
    engine = create_test_engine()
    state.engine = engine
    register_handle_error_listener(engine, state)
    tables = create_all_schema(engine)
    verify_w2p02_schema_tables(engine, W2P02_EXPECTED_SCHEMA_TABLES)
    state.evidence.schema_tables = [t for t in tables if t in W2P02_EXPECTED_SCHEMA_TABLES]
    state.runtime_bootstrapped = True
