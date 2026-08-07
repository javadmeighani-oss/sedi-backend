"""W4-P02 GitHub PostgreSQL grounded synthesis runtime helper.

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
EXPECTED_DATABASE = "sedi_w4p02_synthesis"
EXPECTED_USER = "sedi_w4p02_test"
EXPECTED_PASSWORD = "sedi_w4p02_test_password"
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

W4P02_EXPECTED_SCHEMA_TABLES: tuple[str, ...] = (
    "knowledge_units",
    "knowledge_memory_items",
    "knowledge_provenance",
    "governed_source_profiles",
    "knowledge_gaps",
)

_W4P02_TEST = "backend/tests/test_section30_i5_w4_p02_references.py"

W4P02_RUNTIME_SELECTORS: tuple[str, ...] = (
    f"{_W4P02_TEST}::test_W4P02_T1_package_identity",
    f"{_W4P02_TEST}::test_W4P02_T2_retrieval_to_synthesis_handoff",
    f"{_W4P02_TEST}::test_W4P02_T3_eligible_evidence_synthesis",
    f"{_W4P02_TEST}::test_W4P02_T4_reference_traceability",
    f"{_W4P02_TEST}::test_W4P02_T5_multi_evidence_deterministic",
    f"{_W4P02_TEST}::test_W4P02_T6_unsupported_claim_rejection",
    f"{_W4P02_TEST}::test_W4P02_T7_missing_evidence_fail_closed",
    f"{_W4P02_TEST}::test_W4P02_T8_no_base_model_fallback",
    f"{_W4P02_TEST}::test_W4P02_T9_conflict_disclosure",
    f"{_W4P02_TEST}::test_W4P02_T10_safety_restricted_disclosure",
    f"{_W4P02_TEST}::test_W4P02_T11_stale_exclusion_inheritance",
    f"{_W4P02_TEST}::test_W4P02_T12_provenance_requirement_inheritance",
    f"{_W4P02_TEST}::test_W4P02_T13_personalization_boundary",
    f"{_W4P02_TEST}::test_W4P02_T14_language_boundary",
    f"{_W4P02_TEST}::test_W4P02_T15_mandatory_disclosure_triggers",
    f"{_W4P02_TEST}::test_W4P02_T16_output_envelope",
    f"{_W4P02_TEST}::test_W4P02_T17_brain_care_integration",
    f"{_W4P02_TEST}::test_W4P02_T18_insufficiency_behavior",
    f"{_W4P02_TEST}::test_W4P02_T19_artifact_coverage_invariant",
    f"{_W4P02_TEST}::test_W4P02_T20_warning_precision_invariant",
    f"{_W4P02_TEST}::test_W4P02_T21_show_sources_why_sedi",
)

W4P02_EXPECTED_RUNTIME_NODE_IDS: frozenset[str] = frozenset(
    (
        f"{_W4P02_TEST}::test_W4P02_T1_package_identity",
        f"{_W4P02_TEST}::test_W4P02_T2_retrieval_to_synthesis_handoff",
        f"{_W4P02_TEST}::test_W4P02_T3_eligible_evidence_synthesis",
        f"{_W4P02_TEST}::test_W4P02_T4_reference_traceability",
        f"{_W4P02_TEST}::test_W4P02_T5_multi_evidence_deterministic",
        f"{_W4P02_TEST}::test_W4P02_T6_unsupported_claim_rejection",
        f"{_W4P02_TEST}::test_W4P02_T7_missing_evidence_fail_closed",
        f"{_W4P02_TEST}::test_W4P02_T8_no_base_model_fallback",
        f"{_W4P02_TEST}::test_W4P02_T9_conflict_disclosure[suspected]",
        f"{_W4P02_TEST}::test_W4P02_T9_conflict_disclosure[confirmed]",
        f"{_W4P02_TEST}::test_W4P02_T10_safety_restricted_disclosure",
        f"{_W4P02_TEST}::test_W4P02_T11_stale_exclusion_inheritance",
        f"{_W4P02_TEST}::test_W4P02_T12_provenance_requirement_inheritance",
        f"{_W4P02_TEST}::test_W4P02_T13_personalization_boundary",
        f"{_W4P02_TEST}::test_W4P02_T14_language_boundary",
        f"{_W4P02_TEST}::test_W4P02_T15_mandatory_disclosure_triggers",
        f"{_W4P02_TEST}::test_W4P02_T16_output_envelope",
        f"{_W4P02_TEST}::test_W4P02_T17_brain_care_integration",
        f"{_W4P02_TEST}::test_W4P02_T18_insufficiency_behavior",
        f"{_W4P02_TEST}::test_W4P02_T19_artifact_coverage_invariant",
        f"{_W4P02_TEST}::test_W4P02_T20_warning_precision_invariant",
        f"{_W4P02_TEST}::test_W4P02_T21_show_sources_why_sedi",
    )
)

EXPECTED_RUNTIME_NODE_COUNT = 22
EXPECTED_SELECTOR_COUNT = 21

_IMPORT_GUARD_COMPLETE = False
_ENGINE_REGISTRY: list[Any] = []


@dataclass
class W4P02GitHubPostgresEvidence:
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
class W4P02PluginState:
    collect_only_mode: bool = False
    runtime_mode: bool = False
    manifest_pass: bool = False
    runtime_bootstrapped: bool = False
    active_node_id: Optional[str] = None
    evidence: W4P02GitHubPostgresEvidence = field(default_factory=W4P02GitHubPostgresEvidence)
    engine: Any = None
    handle_error_registered: bool = False
    diagnostic_dedupe: set[tuple[str, Optional[str], Optional[str]]] = field(default_factory=set)
    _handle_error_callable: Optional[Callable[..., None]] = None


class W4P02HarnessError(RuntimeError):
    """Controlled harness failure with governed marker."""


def detect_collect_only_mode(config: Any) -> bool:
    return bool(getattr(config.option, "collectonly", False))


def detect_runtime_mode(config: Any) -> bool:
    return not detect_collect_only_mode(config)


def assert_no_db_bootstrap_in_collect_only(collect_only_mode: bool) -> None:
    if collect_only_mode:
        raise W4P02HarnessError(SENTINEL_RUNTIME_BOOTSTRAP_FORBIDDEN_IN_COLLECT_ONLY)


def scrub_inherited_database_env() -> None:
    for key in (
        "SEDI_W4P02_PG_ADMIN_URL",
        "SEDI_W4P02_PG_TEST_URL",
        "SEDI_W4P02_PG_OWNERSHIP_MARKER",
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
            raise W4P02HarnessError(SENTINEL_GITHUB_POSTGRES_PRODUCTION_IDENTIFIER_REFUSED)
    parsed = urlparse(test_url)
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "::1"}:
        raise W4P02HarnessError(SENTINEL_GITHUB_POSTGRES_TARGET_REFUSED)
    if host != EXPECTED_HOST:
        raise W4P02HarnessError(SENTINEL_GITHUB_POSTGRES_TARGET_REFUSED)
    if parsed.port not in (None, EXPECTED_PORT):
        raise W4P02HarnessError(SENTINEL_GITHUB_POSTGRES_TARGET_REFUSED)


def parse_and_validate_github_test_url(test_url: str) -> dict[str, Any]:
    refuse_production_shared_targets(test_url)
    parsed = urlparse(test_url)
    database = (parsed.path or "").lstrip("/")
    if database != EXPECTED_DATABASE:
        raise W4P02HarnessError(SENTINEL_GITHUB_POSTGRES_TARGET_REFUSED)
    if (parsed.username or "") != EXPECTED_USER:
        raise W4P02HarnessError(SENTINEL_GITHUB_POSTGRES_TARGET_REFUSED)
    return {
        "host": parsed.hostname,
        "port": parsed.port or EXPECTED_PORT,
        "database": database,
        "user": parsed.username,
        "redacted_url": _redact_url(test_url),
    }


def bind_github_database_environment(test_url: str) -> None:
    parse_and_validate_github_test_url(test_url)
    os.environ["DATABASE_URL"] = test_url
    os.environ["TEST_DATABASE_URL"] = test_url
    os.environ["APP_ENV"] = "test_isolated"
    os.environ["ENVIRONMENT"] = "test_isolated"
    os.environ["ENV"] = "test_isolated"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ.setdefault("OPENAI_API_KEY", "w4p02-test-placeholder-not-used")
    # Enforce activation-off for orchestrator contract tests.
    os.environ.pop("SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED", None)
    os.environ.pop("SEDI_I5_SOURCE_ACTIVATION_ENABLED", None)


def verify_bound_environment(expected_db_name: str, expected_host: str) -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    test_url = os.environ.get("TEST_DATABASE_URL", "")
    if not db_url or not test_url:
        raise W4P02HarnessError(SENTINEL_GITHUB_POSTGRES_URL_MISMATCH)
    if db_url != test_url:
        raise W4P02HarnessError(SENTINEL_GITHUB_POSTGRES_URL_MISMATCH)
    parsed = parse_and_validate_github_test_url(db_url)
    if parsed["database"] != expected_db_name or parsed["host"] != expected_host:
        raise W4P02HarnessError(SENTINEL_GITHUB_POSTGRES_URL_MISMATCH)


def mark_import_guard_complete() -> None:
    global _IMPORT_GUARD_COMPLETE
    verify_bound_environment(EXPECTED_DATABASE, EXPECTED_HOST)
    _IMPORT_GUARD_COMPLETE = True


def assert_import_guard_completed() -> None:
    if not _IMPORT_GUARD_COMPLETE:
        raise W4P02HarnessError(SENTINEL_APPLICATION_IMPORT_BEFORE_TEST_DATABASE_BINDING)


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
    expected = expected_ids or W4P02_EXPECTED_RUNTIME_NODE_IDS
    collected = sorted({_normalize_node_id(node_id) for node_id in collected_node_ids})
    if len(collected) != EXPECTED_RUNTIME_NODE_COUNT:
        raise W4P02HarnessError(SENTINEL_RUNTIME_NODE_MANIFEST_MISMATCH)
    missing = sorted(expected - set(collected))
    extra = sorted(set(collected) - expected)
    if missing or extra:
        raise W4P02HarnessError(SENTINEL_RUNTIME_NODE_MANIFEST_MISMATCH)
    return collected


def refuse_schema_start_after_manifest_mismatch(manifest_pass: bool) -> None:
    if not manifest_pass:
        raise W4P02HarnessError(SENTINEL_RUNTIME_NODE_MANIFEST_MISMATCH)


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


def verify_w4p02_schema_tables(engine, expected_tables: tuple[str, ...]) -> None:
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(engine)
    present = set(inspector.get_table_names())
    missing = [t for t in expected_tables if t not in present]
    if missing:
        raise W4P02HarnessError(
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


def set_active_node_id(state: W4P02PluginState, node_id: str) -> None:
    state.active_node_id = node_id


def clear_active_node_id(state: W4P02PluginState) -> None:
    state.active_node_id = None


def correlate_diagnostic_to_node(
    state: W4P02PluginState, node_id: str, diag: dict[str, Any]
) -> dict[str, Any]:
    payload = {"node_id": node_id, **diag}
    key = (node_id, payload.get("sqlstate"), payload.get("constraint_name"))
    if key in state.diagnostic_dedupe:
        return payload
    state.diagnostic_dedupe.add(key)
    state.evidence.diagnostic_events.append(payload)
    return payload


def record_correlated_diagnostic(state: W4P02PluginState, diag: dict[str, Any]) -> None:
    node_id = state.active_node_id
    if not node_id:
        return
    correlate_diagnostic_to_node(state, node_id, diag)


def _make_handle_error_listener(state: W4P02PluginState):
    def _listener(exception_context):
        if not state.runtime_mode or state.collect_only_mode:
            return
        diag = extract_handle_error_diagnostics(exception_context)
        if diag:
            record_correlated_diagnostic(state, diag)

    return _listener


def register_handle_error_listener(engine, state: W4P02PluginState) -> None:
    assert_no_db_bootstrap_in_collect_only(state.collect_only_mode)
    if state.handle_error_registered:
        return
    from sqlalchemy import event

    listener = _make_handle_error_listener(state)
    event.listen(engine, "handle_error", listener)
    state._handle_error_callable = listener
    state.handle_error_registered = True


def remove_handle_error_listener(engine, state: W4P02PluginState) -> None:
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
        raise W4P02HarnessError(BLOCKED_DEPENDENCY_RESOLUTION)


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "backend").is_dir() and (parent / "docs").is_dir():
            return parent
    return here.parents[3]


def _path_is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def resolve_runner_temp_dir(repo_root: Optional[Path] = None) -> Path:
    repo_root = (repo_root or _find_repo_root()).resolve()
    target = (Path(tempfile.gettempdir()) / "sedi_w4p02_postgres_runtime_evidence").resolve()
    target.mkdir(parents=True, exist_ok=True)
    if _path_is_inside(target, repo_root):
        raise W4P02HarnessError("FAIL_UNAUTHORIZED_REPOSITORY_MUTATION evidence path in repo")
    return target


def write_runner_temp_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def capture_redacted_evidence(evidence: W4P02GitHubPostgresEvidence) -> dict[str, Any]:
    return {
        "mode": evidence.mode,
        "run_id": evidence.run_id or os.environ.get("GITHUB_RUN_ID", ""),
        "commit_sha": evidence.commit_sha or os.environ.get("GITHUB_SHA", ""),
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
        "dependency_versions": evidence.dependency_versions,
        "schema_tables": evidence.schema_tables,
        "selector_count": evidence.selector_count,
        "collected_node_ids": evidence.collected_node_ids,
        "manifest_equality_pass": evidence.manifest_equality_pass,
        "pass_count": evidence.pass_count,
        "fail_count": evidence.fail_count,
        "skip_count": evidence.skip_count,
        "failure_markers": evidence.failure_markers,
        "cleanup_result": evidence.cleanup_result,
        "expected_node_count": EXPECTED_RUNTIME_NODE_COUNT,
        "package_id": "I5-IMPL-W4-P02",
        "controlled_network": "DEFERRED_W6_P01",
        "activation": "OFF",
    }


def initialize_evidence_context(state: W4P02PluginState, *, mode: str) -> None:
    state.evidence.mode = mode
    state.evidence.run_id = os.environ.get("GITHUB_RUN_ID", "")
    state.evidence.commit_sha = os.environ.get("GITHUB_SHA", "")
    state.evidence.runner_os = platform.platform()
    state.evidence.python_version = sys.version.split()[0]
    state.evidence.selector_count = EXPECTED_SELECTOR_COUNT


def configure_environment_from_urls(state: W4P02PluginState) -> None:
    scrub_inherited_database_env()
    test_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    if not test_url:
        if state.collect_only_mode:
            # Collect-only may proceed without DB bootstrap; binding deferred.
            return
        raise W4P02HarnessError(SENTINEL_GITHUB_POSTGRES_URL_MISMATCH)
    parsed = parse_and_validate_github_test_url(test_url)
    bind_github_database_environment(test_url)
    mark_import_guard_complete()
    state.evidence.database_name = parsed["database"]
    state.evidence.target_host = parsed["host"]
    state.evidence.target_port = int(parsed["port"])
    state.evidence.test_url_redacted = parsed["redacted_url"]
    state.evidence.url_equality_pass = True
    state.evidence.production_refusal_pass = True
    state.evidence.import_guard_pass = True


def runtime_bootstrap_after_manifest(state: W4P02PluginState) -> None:
    assert_no_db_bootstrap_in_collect_only(state.collect_only_mode)
    refuse_schema_start_after_manifest_mismatch(state.manifest_pass)
    if state.runtime_bootstrapped:
        return
    if not _IMPORT_GUARD_COMPLETE:
        configure_environment_from_urls(state)
    engine = create_test_engine()
    tables = create_all_schema(engine)
    verify_w4p02_schema_tables(engine, W4P02_EXPECTED_SCHEMA_TABLES)
    register_handle_error_listener(engine, state)
    state.engine = engine
    state.evidence.schema_tables = sorted(
        t for t in tables if t in set(W4P02_EXPECTED_SCHEMA_TABLES) or True
    )
    state.runtime_bootstrapped = True


def independent_db_resource_cleanup(
    state: W4P02PluginState,
    *,
    session: Any = None,
    outer_transaction: Any = None,
    connection: Any = None,
) -> list[str]:
    errors: list[str] = []
    for label, action in (
        ("session_close", lambda: session.close() if session is not None else None),
        (
            "outer_rollback",
            lambda: outer_transaction.rollback() if outer_transaction is not None else None,
        ),
        ("connection_close", lambda: connection.close() if connection is not None else None),
    ):
        try:
            action()
            state.evidence.cleanup_events.append({"step": label, "ok": True})
        except Exception as exc:
            errors.append(f"{label}:{type(exc).__name__}")
            state.evidence.cleanup_events.append(
                {"step": label, "ok": False, "error": type(exc).__name__}
            )
    return errors


def dispose_all_engines() -> None:
    while _ENGINE_REGISTRY:
        engine = _ENGINE_REGISTRY.pop()
        try:
            engine.dispose()
        except Exception:
            pass
