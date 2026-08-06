"""W3-P01 deterministic adapter-framework runtime helper (no PostgreSQL / no network)."""
from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

SENTINEL_RUNTIME_NODE_MANIFEST_MISMATCH = "SENTINEL_RUNTIME_NODE_MANIFEST_MISMATCH"

_TEST = "backend/tests/test_section30_i5_w3_p01_adapters_extract.py"

W3P01_RUNTIME_SELECTORS: tuple[str, ...] = (
    f"{_TEST}::test_W3P01_T1_package_identity",
    f"{_TEST}::test_W3P01_T2_registry_register_and_resolve",
    f"{_TEST}::test_W3P01_T3_public_web_wraps_fetcher_symbol",
    f"{_TEST}::test_W3P01_T4_governance_fail_closed",
    f"{_TEST}::test_W3P01_T5_network_safety_url_policy",
    f"{_TEST}::test_W3P01_T6_fetch_envelope_statuses",
    f"{_TEST}::test_W3P01_T7_official_api_and_rss_content_types",
    f"{_TEST}::test_W3P01_T8_normalize_and_dedupe_idempotency",
    f"{_TEST}::test_W3P01_T9_extraction_html_json_rss_and_failures",
    f"{_TEST}::test_W3P01_T10_no_activation_no_production_write_markers",
    f"{_TEST}::test_W3P01_T11_conditional_fetch_etag_passthrough",
)

W3P01_EXPECTED_RUNTIME_NODE_IDS: frozenset[str] = frozenset(
    (
        f"{_TEST}::test_W3P01_T1_package_identity",
        f"{_TEST}::test_W3P01_T2_registry_register_and_resolve",
        f"{_TEST}::test_W3P01_T3_public_web_wraps_fetcher_symbol",
        f"{_TEST}::test_W3P01_T4_governance_fail_closed[unknown_rights]",
        f"{_TEST}::test_W3P01_T4_governance_fail_closed[robots_blocked]",
        f"{_TEST}::test_W3P01_T4_governance_fail_closed[rate_undefined]",
        f"{_TEST}::test_W3P01_T4_governance_fail_closed[registry_blocked]",
        f"{_TEST}::test_W3P01_T5_network_safety_url_policy[http_scheme]",
        f"{_TEST}::test_W3P01_T5_network_safety_url_policy[localhost]",
        f"{_TEST}::test_W3P01_T5_network_safety_url_policy[private_ip]",
        f"{_TEST}::test_W3P01_T5_network_safety_url_policy[domain_mismatch]",
        f"{_TEST}::test_W3P01_T6_fetch_envelope_statuses[ok_200]",
        f"{_TEST}::test_W3P01_T6_fetch_envelope_statuses[not_modified_304]",
        f"{_TEST}::test_W3P01_T6_fetch_envelope_statuses[not_found_404]",
        f"{_TEST}::test_W3P01_T6_fetch_envelope_statuses[gone_410]",
        f"{_TEST}::test_W3P01_T6_fetch_envelope_statuses[rate_429]",
        f"{_TEST}::test_W3P01_T6_fetch_envelope_statuses[server_500]",
        f"{_TEST}::test_W3P01_T6_fetch_envelope_statuses[oversize]",
        f"{_TEST}::test_W3P01_T7_official_api_and_rss_content_types",
        f"{_TEST}::test_W3P01_T8_normalize_and_dedupe_idempotency",
        f"{_TEST}::test_W3P01_T9_extraction_html_json_rss_and_failures",
        f"{_TEST}::test_W3P01_T10_no_activation_no_production_write_markers",
        f"{_TEST}::test_W3P01_T11_conditional_fetch_etag_passthrough",
    )
)

EXPECTED_RUNTIME_NODE_COUNT = 23
EXPECTED_SELECTOR_COUNT = 11


class W3P01HarnessError(RuntimeError):
    pass


@dataclass
class W3P01Evidence:
    mode: str = ""
    run_id: str = ""
    commit_sha: str = ""
    python_version: str = ""
    runner_os: str = ""
    selector_count: int = 0
    collected_node_ids: list[str] = field(default_factory=list)
    manifest_equality_pass: bool = False
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    controlled_network_validation: str = "NOT_OWNED_DEFERRED_TO_W6_P01"
    live_network_used: bool = False
    source_activation: bool = False
    production_write: bool = False
    failure_markers: list[str] = field(default_factory=list)


@dataclass
class W3P01PluginState:
    collect_only_mode: bool = False
    runtime_mode: bool = False
    manifest_pass: bool = False
    evidence: W3P01Evidence = field(default_factory=W3P01Evidence)


def detect_collect_only_mode(config: Any) -> bool:
    return bool(getattr(config.option, "collectonly", False))


def _normalize_node_id(node_id: str) -> str:
    return node_id.replace("\\", "/")


def verify_runtime_selector_manifest(
    collected_node_ids: Iterable[str],
) -> list[str]:
    collected = sorted({_normalize_node_id(n) for n in collected_node_ids})
    if len(collected) != EXPECTED_RUNTIME_NODE_COUNT:
        raise W3P01HarnessError(SENTINEL_RUNTIME_NODE_MANIFEST_MISMATCH)
    missing = sorted(W3P01_EXPECTED_RUNTIME_NODE_IDS - set(collected))
    extra = sorted(set(collected) - W3P01_EXPECTED_RUNTIME_NODE_IDS)
    if missing or extra:
        raise W3P01HarnessError(SENTINEL_RUNTIME_NODE_MANIFEST_MISMATCH)
    return collected


def initialize_evidence(state: W3P01PluginState, *, mode: str) -> None:
    state.evidence.mode = mode
    state.evidence.run_id = os.environ.get("GITHUB_RUN_ID", "")
    state.evidence.commit_sha = os.environ.get("GITHUB_SHA", "")
    state.evidence.python_version = sys.version.split()[0]
    state.evidence.runner_os = platform.platform()
    state.evidence.selector_count = len(W3P01_RUNTIME_SELECTORS)


def resolve_evidence_dir() -> Path:
    target = (Path(tempfile.gettempdir()) / "sedi_w3p01_adapter_framework_evidence").resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_evidence(state: W3P01PluginState, exitstatus: int) -> None:
    payload = {
        "mode": state.evidence.mode,
        "run_id": state.evidence.run_id,
        "commit_sha": state.evidence.commit_sha,
        "python_version": state.evidence.python_version,
        "runner_os": state.evidence.runner_os,
        "selector_count": state.evidence.selector_count,
        "expected_node_count": EXPECTED_RUNTIME_NODE_COUNT,
        "collected_node_ids": list(state.evidence.collected_node_ids),
        "manifest_equality_pass": state.evidence.manifest_equality_pass,
        "pass_count": state.evidence.pass_count,
        "fail_count": state.evidence.fail_count,
        "skip_count": state.evidence.skip_count,
        "controlled_network_validation": state.evidence.controlled_network_validation,
        "live_network_used": state.evidence.live_network_used,
        "source_activation": state.evidence.source_activation,
        "production_write": state.evidence.production_write,
        "failure_markers": list(state.evidence.failure_markers),
        "exitstatus": exitstatus,
        "final_verdict": "PASS"
        if exitstatus == 0 and state.evidence.skip_count == 0
        else "FAIL",
    }
    out = resolve_evidence_dir() / (
        "w3p01_collect_only_evidence.json"
        if state.collect_only_mode
        else "w3p01_runtime_evidence.json"
    )
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
