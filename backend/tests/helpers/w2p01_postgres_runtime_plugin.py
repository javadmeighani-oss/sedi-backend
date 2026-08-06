"""W2-P01 GitHub PostgreSQL knowledge retention runtime pytest plugin."""
from __future__ import annotations

import sys
from typing import Any, Generator

import pytest

import backend.tests.helpers.w2p01_postgres_runtime as rt

STATE_ATTR = "_w2p01_plugin_state"


def _get_state(config: pytest.Config) -> rt.W2P01PluginState:
    state = getattr(config, STATE_ATTR, None)
    if state is None:
        state = rt.W2P01PluginState()
        setattr(config, STATE_ATTR, state)
    return state


def pytest_configure(config: pytest.Config) -> None:
    state = _get_state(config)
    state.collect_only_mode = rt.detect_collect_only_mode(config)
    state.runtime_mode = rt.detect_runtime_mode(config)
    mode = "collect_only" if state.collect_only_mode else "runtime"
    rt.initialize_evidence_context(state, mode=mode)
    rt.configure_environment_from_urls(state)


def pytest_sessionstart(session: pytest.Session) -> None:
    state = _get_state(session.config)
    if state.collect_only_mode:
        return
    # Runtime: dependency gate only; schema bootstrap occurs after manifest PASS.
    rt.verify_sqlalchemy_version_minimum()
    state.evidence.dependency_versions = rt.capture_dependency_versions()


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    state = _get_state(config)
    collected_ids = [item.nodeid for item in items]
    state.evidence.collected_node_ids = sorted(collected_ids)
    try:
        verified = rt.verify_runtime_selector_manifest(collected_ids)
        state.manifest_pass = True
        state.evidence.manifest_equality_pass = True
        state.evidence.collected_node_ids = verified
    except rt.W2P01HarnessError as exc:
        state.manifest_pass = False
        state.evidence.failure_markers.append(str(exc))
        raise
    if state.runtime_mode and state.manifest_pass:
        rt.runtime_bootstrap_after_manifest(state)


def pytest_runtest_setup(item: pytest.Item) -> None:
    state = _get_state(item.config)
    if state.collect_only_mode:
        return
    rt.set_active_node_id(state, item.nodeid)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator[None, Any, None]:
    outcome = yield
    if item.config.getoption("collectonly"):
        return
    state = _get_state(item.config)
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)
    if report.when == "call":
        if report.passed:
            state.evidence.pass_count += 1
        elif report.failed:
            state.evidence.fail_count += 1
        elif report.skipped:
            state.evidence.skip_count += 1


def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> None:
    state = _get_state(item.config)
    if state.collect_only_mode:
        return
    rt.clear_active_node_id(state)


@pytest.fixture(scope="session")
def w2p01_github_postgres_evidence(pytestconfig: pytest.Config) -> rt.W2P01GitHubPostgresEvidence:
    if pytestconfig.getoption("collectonly"):
        pytest.skip("w2p01_github_postgres_evidence unavailable in collect-only mode")
    state = _get_state(pytestconfig)
    rt.refuse_schema_start_after_manifest_mismatch(state.manifest_pass)
    return state.evidence


@pytest.fixture(scope="session")
def w2p01_postgres_engine(pytestconfig: pytest.Config):
    if pytestconfig.getoption("collectonly"):
        pytest.skip("w2p01_postgres_engine unavailable in collect-only mode")
    state = _get_state(pytestconfig)
    rt.refuse_schema_start_after_manifest_mismatch(state.manifest_pass)
    if state.engine is None:
        rt.runtime_bootstrap_after_manifest(state)
    yield state.engine


def _prior_primary_failure_exists(request: pytest.FixtureRequest) -> bool:
    """Combine active exception with per-item setup/call TestReports.

    PRIMARY_FAILURE_SOURCE = COMBINED_REPORTS_AND_ACTIVE_EXCEPTION
    rep_teardown is intentionally not authoritative for this decision.
    """
    active_exception = sys.exc_info()[1] is not None
    rep_setup = getattr(request.node, "rep_setup", None)
    rep_call = getattr(request.node, "rep_call", None)
    setup_failed = bool(rep_setup is not None and getattr(rep_setup, "failed", False))
    call_failed = bool(rep_call is not None and getattr(rep_call, "failed", False))
    return active_exception or setup_failed or call_failed


@pytest.fixture()
def db(request: pytest.FixtureRequest, w2p01_postgres_engine) -> Generator[Any, None, None]:
    """Option 2 outer-transaction session with failure-safe acquisition and cleanup."""
    state = _get_state(request.config)
    connection = None
    outer_transaction = None
    session = None
    try:
        connection = w2p01_postgres_engine.connect()
        outer_transaction = connection.begin()
        session = rt.create_db_session(connection)
        yield session
    finally:
        cleanup_errors = rt.independent_db_resource_cleanup(
            state,
            session=session,
            outer_transaction=outer_transaction,
            connection=connection,
        )
        if cleanup_errors and not _prior_primary_failure_exists(request):
            # Cleanup-only failure: raise after all cleanup attempts complete.
            raise rt.W2P01HarnessError(rt.CONTROLLED_FIXTURE_CLEANUP_FAILED)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    state = _get_state(session.config)
    try:
        if state.engine is not None:
            rt.remove_handle_error_listener(state.engine, state)
        rt.dispose_all_engines()
        if not state.evidence.cleanup_result:
            state.evidence.cleanup_result = "engines_disposed"
    except Exception as exc:
        state.evidence.cleanup_result = f"cleanup_error:{type(exc).__name__}"
        state.evidence.failure_markers.append(str(type(exc).__name__))
    payload = rt.capture_redacted_evidence(state.evidence)
    payload["exitstatus"] = exitstatus
    try:
        evidence_dir = rt.resolve_runner_temp_dir()
        out = evidence_dir / (
            "w2p01_collect_only_evidence.json"
            if state.collect_only_mode
            else "w2p01_runtime_evidence.json"
        )
        rt.write_runner_temp_evidence(out, payload)
    except rt.W2P01HarnessError as exc:
        state.evidence.failure_markers.append(str(exc))
    rt.clear_active_node_id(state)
