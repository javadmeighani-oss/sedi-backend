"""W3-P01 adapter framework pytest plugin (deterministic; no DB; no network)."""
from __future__ import annotations

from typing import Any, Generator

import pytest

import backend.tests.helpers.w3p01_adapter_runtime as rt

STATE_ATTR = "_w3p01_plugin_state"


def _get_state(config: pytest.Config) -> rt.W3P01PluginState:
    state = getattr(config, STATE_ATTR, None)
    if state is None:
        state = rt.W3P01PluginState()
        setattr(config, STATE_ATTR, state)
    return state


def pytest_configure(config: pytest.Config) -> None:
    state = _get_state(config)
    state.collect_only_mode = rt.detect_collect_only_mode(config)
    state.runtime_mode = not state.collect_only_mode
    mode = "collect_only" if state.collect_only_mode else "runtime"
    rt.initialize_evidence(state, mode=mode)


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    state = _get_state(config)
    collected_ids = [item.nodeid for item in items]
    try:
        verified = rt.verify_runtime_selector_manifest(collected_ids)
        state.manifest_pass = True
        state.evidence.manifest_equality_pass = True
        state.evidence.collected_node_ids = verified
    except rt.W3P01HarnessError as exc:
        state.manifest_pass = False
        state.evidence.failure_markers.append(str(exc))
        raise


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator[None, Any, None]:
    outcome = yield
    if item.config.getoption("collectonly"):
        return
    state = _get_state(item.config)
    report = outcome.get_result()
    if report.when == "call":
        if report.passed:
            state.evidence.pass_count += 1
        elif report.failed:
            state.evidence.fail_count += 1
        elif report.skipped:
            state.evidence.skip_count += 1


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    state = _get_state(session.config)
    try:
        rt.write_evidence(state, exitstatus)
    except Exception as exc:  # noqa: BLE001
        state.evidence.failure_markers.append(type(exc).__name__)
