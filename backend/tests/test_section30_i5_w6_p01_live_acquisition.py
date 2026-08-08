"""Section 30 / I5-IMPL-W6-P01 — controlled live acquisition (fail-closed, no real network).

Pure unit coverage for the live HTTPS transport, the `PublicWebFetchAdapter.fetch_live`
governance wrapper, and the weekly-orchestrator controlled-live wiring. No test in this
file opens a real socket: DNS resolution and the Gate3 robots.txt check are patched the
same way `test_gate3g_kb_crawler_v1.py` already does (`socket.getaddrinfo` /
`robots_checker.requests.get`), and the main content fetch always goes through an
injected `http_get` fake.

Run without a Postgres instance:
    pytest backend/tests/test_section30_i5_w6_p01_live_acquisition.py -q --noconftest
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Mapping, Optional

import pytest
import requests

from backend.app.schemas.i5_adapters import SourceGovernanceSnapshot
from backend.app.services.i5 import weekly_orchestrator as orch
from backend.app.services.i5.adapters import live_transport
from backend.app.services.i5.adapters.base import AdapterFrameworkError, FixtureTransportResponse
from backend.app.services.i5.adapters.public_web_fetch import PublicWebFetchAdapter
from backend.app.services.i5.source_discovery import SourceCandidateDescriptor

_DNS_PATH = "backend.app.services.gate3.fetch_security.socket.getaddrinfo"
_ROBOTS_GET_PATH = "backend.app.services.gate3.robots_checker.requests.get"


class _FakeResponse:
    """Minimal stand-in for `requests.Response` (content-fetch and robots-fetch shapes)."""

    def __init__(
        self,
        status_code: int,
        body: bytes = b"",
        headers: Optional[Mapping[str, str]] = None,
        text: Optional[str] = None,
    ) -> None:
        self.status_code = status_code
        self.content = body
        self.headers = dict(headers or {})
        self.text = text if text is not None else body.decode("utf-8", errors="replace")


def _patch_dns(monkeypatch: pytest.MonkeyPatch, ip: str = "93.184.216.34") -> None:
    """No real DNS lookups — resolve any hostname to one fixed, non-blocked IP."""
    monkeypatch.setattr(
        _DNS_PATH,
        lambda *a, **k: [(2, 1, 6, "", (ip, 0))],
    )


def _patch_robots(monkeypatch: pytest.MonkeyPatch, *, allow: bool) -> None:
    """No real robots.txt fetch — canned allow-all / disallow-all body."""
    body = "User-agent: *\nAllow: /" if allow else "User-agent: *\nDisallow: /"
    monkeypatch.setattr(
        _ROBOTS_GET_PATH,
        lambda *a, **k: _FakeResponse(200, text=body),
    )


def _unused_get(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("http_get must not be invoked once a fail-closed gate is hit")


def _ok_gov(**overrides: Any) -> SourceGovernanceSnapshot:
    base = dict(
        source_profile_id=1,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        rights_terms_state="ACCEPTABLE",
        robots_access_state="ALLOWED",
        rate_limit_policy="DEFINED",
        allowed_domain="example.org",
    )
    base.update(overrides)
    return SourceGovernanceSnapshot(**base)


def _ok_candidate(**overrides: Any) -> SourceCandidateDescriptor:
    base = dict(
        source_profile_id=1,
        adapter_mode="PUBLIC_WEB_FETCH",
        url="https://example.org/page",
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        rights_terms_state="ACCEPTABLE",
        robots_access_state="ALLOWED",
        rate_limit_policy="DEFINED",
        allowed_domain="example.org",
    )
    base.update(overrides)
    return SourceCandidateDescriptor(**base)


_HTML_BODY = (
    b"<html><title>T</title><body>"
    b"<p>Enough visible medical guidance text for extraction threshold.</p>"
    b"</body></html>"
)


# ---------------------------------------------------------------------------
# 1-2. Two-flag scheduler activation ladder — no network unless BOTH flags on.
# ---------------------------------------------------------------------------


def test_W6P01_T1_activation_off_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(orch.WEEKLY_ORCHESTRATOR_ENABLE_ENV, raising=False)
    monkeypatch.delenv(orch.SOURCE_ACTIVATION_ENV, raising=False)
    tick = orch.run_dormant_scheduled_tick()
    assert tick.outcome == "DORMANT_NO_OP"
    assert tick.network_executed is False
    assert tick.scheduler_activation is False


def test_W6P01_T2_weekly_on_source_activation_off_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(orch.WEEKLY_ORCHESTRATOR_ENABLE_ENV, "true")
    monkeypatch.delenv(orch.SOURCE_ACTIVATION_ENV, raising=False)
    tick = orch.run_dormant_scheduled_tick()
    assert tick.outcome == "SOURCE_ACTIVATION_DISABLED"
    assert tick.network_executed is False
    assert tick.scheduler_activation is False
    assert tick.activation_enabled is True


def test_W6P01_T2b_both_on_no_candidates_is_structural_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(orch.WEEKLY_ORCHESTRATOR_ENABLE_ENV, "true")
    monkeypatch.setenv(orch.SOURCE_ACTIVATION_ENV, "true")
    tick = orch.run_dormant_scheduled_tick()
    assert tick.outcome == "NO_ELIGIBLE_SOURCES"
    assert tick.network_executed is False


def test_W6P01_T2c_persist_ledger_without_db_fails_closed() -> None:
    outcome = orch.run_controlled_live_orchestration(
        None, None, candidates=[_ok_candidate()], persist_ledger=True
    )
    assert outcome.outcome == "LIVE_PATH_REQUIRES_DB"
    assert outcome.network_executed is False


def test_W6P01_T2d_live_network_requires_activation_off_false() -> None:
    with pytest.raises(orch.WeeklyOrchestratorError, match="LIVE_NETWORK_REQUIRES_ACTIVATION_OFF_FALSE"):
        orch.orchestrate_weekly_run(
            None, None, candidates=[], live_network=True, enforce_activation_off=True
        )


# ---------------------------------------------------------------------------
# 3. Bad URL / wrong host / private IP — blocked before any network attempt.
# ---------------------------------------------------------------------------


def test_W6P01_T3_http_scheme_rejected_before_gate3() -> None:
    with pytest.raises(AdapterFrameworkError, match="UNSAFE_URL"):
        live_transport.fetch_live_https(
            url="http://example.org/page", allowed_domain="example.org", http_get=_unused_get
        )


def test_W6P01_T3b_wrong_host_domain_mismatch() -> None:
    with pytest.raises(AdapterFrameworkError, match="UNSAFE_URL"):
        live_transport.fetch_live_https(
            url="https://evil.example/page", allowed_domain="example.org", http_get=_unused_get
        )


def test_W6P01_T3c_private_ip_literal_blocked() -> None:
    with pytest.raises(AdapterFrameworkError, match="UNSAFE_URL"):
        live_transport.fetch_live_https(
            url="https://127.0.0.1/page", allowed_domain=None, http_get=_unused_get
        )


def test_W6P01_T3d_dns_resolves_to_private_ip_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_dns(monkeypatch, ip="10.1.2.3")
    with pytest.raises(AdapterFrameworkError, match="UNSAFE_URL"):
        live_transport.fetch_live_https(
            url="https://example.org/page", allowed_domain="example.org", http_get=_unused_get
        )


# ---------------------------------------------------------------------------
# 4. Robots denied / rights denied / unknown rights|robots|rate -> fail closed.
# ---------------------------------------------------------------------------


def test_W6P01_T4_robots_txt_denies_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_dns(monkeypatch)
    _patch_robots(monkeypatch, allow=False)
    with pytest.raises(AdapterFrameworkError, match="ROBOTS_BLOCKED"):
        live_transport.fetch_live_https(
            url="https://example.org/page", allowed_domain="example.org", http_get=_unused_get
        )


@pytest.mark.parametrize(
    "case_id",
    ["unknown_rights", "unknown_robots", "unknown_rate", "robots_denied_governance", "rights_rejected"],
)
def test_W6P01_T5_governance_fail_closed_before_any_network(case_id: str) -> None:
    overrides = {
        "unknown_rights": dict(rights_terms_state="UNKNOWN"),
        "unknown_robots": dict(robots_access_state="UNKNOWN"),
        "unknown_rate": dict(rate_limit_policy="UNKNOWN"),
        "robots_denied_governance": dict(robots_access_state="BLOCKED"),
        "rights_rejected": dict(rights_terms_state="REJECTED"),
    }[case_id]
    gov = _ok_gov(**overrides)
    adapter = PublicWebFetchAdapter()
    with pytest.raises(AdapterFrameworkError) as ei:
        adapter.fetch_live(
            request_id="r1", url="https://example.org/page", governance=gov, http_get=_unused_get
        )
    assert ei.value.category in {"GOVERNANCE_BLOCKED", "ROBOTS_BLOCKED", "TERMS_BLOCKED"}


# ---------------------------------------------------------------------------
# 5. Timeout, 429, oversized, redirect-to-blocked-host.
# ---------------------------------------------------------------------------


def test_W6P01_T6_timeout_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_dns(monkeypatch)
    _patch_robots(monkeypatch, allow=True)

    def _get(*_a: Any, **_k: Any) -> Any:
        raise requests.Timeout("simulated timeout")

    with pytest.raises(AdapterFrameworkError, match="TIMEOUT"):
        live_transport.fetch_live_https(
            url="https://example.org/page", allowed_domain="example.org", http_get=_get
        )


def test_W6P01_T7_rate_limited_429_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_dns(monkeypatch)
    _patch_robots(monkeypatch, allow=True)

    def _get(*_a: Any, **_k: Any) -> Any:
        return _FakeResponse(429, b"", {})

    with pytest.raises(AdapterFrameworkError, match="RATE_LIMITED"):
        live_transport.fetch_live_https(
            url="https://example.org/page", allowed_domain="example.org", http_get=_get
        )


def test_W6P01_T8_oversized_body_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_dns(monkeypatch)
    _patch_robots(monkeypatch, allow=True)

    def _get(*_a: Any, **_k: Any) -> Any:
        return _FakeResponse(200, b"x" * 4096, {"Content-Type": "text/html"})

    with pytest.raises(AdapterFrameworkError, match="CONTENT_TOO_LARGE"):
        live_transport.fetch_live_https(
            url="https://example.org/page",
            allowed_domain="example.org",
            max_bytes=1024,
            http_get=_get,
        )


def test_W6P01_T9_redirect_to_unregistered_host_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_dns(monkeypatch)
    _patch_robots(monkeypatch, allow=True)
    calls: list[str] = []

    def _get(url: str, **_k: Any) -> Any:
        calls.append(url)
        if len(calls) == 1:
            return _FakeResponse(302, b"", {"Location": "https://evil.example/page"})
        raise AssertionError("must not follow an unsafe redirect target")

    with pytest.raises(AdapterFrameworkError, match="UNSAFE_URL"):
        live_transport.fetch_live_https(
            url="https://example.org/page", allowed_domain="example.org", http_get=_get
        )
    assert len(calls) == 1


def test_W6P01_T9b_redirect_to_same_registered_host_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_dns(monkeypatch)
    _patch_robots(monkeypatch, allow=True)
    calls: list[str] = []

    def _get(url: str, **_k: Any) -> Any:
        calls.append(url)
        if len(calls) == 1:
            return _FakeResponse(302, b"", {"Location": "https://example.org/final"})
        return _FakeResponse(200, _HTML_BODY, {"Content-Type": "text/html; charset=utf-8"})

    resp = live_transport.fetch_live_https(
        url="https://example.org/page", allowed_domain="example.org", http_get=_get
    )
    assert resp.status_code == 200
    assert resp.body == _HTML_BODY
    assert resp.final_url == "https://example.org/final"
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# 6. Valid controlled source -> live transport invoked; content hash deterministic.
# ---------------------------------------------------------------------------


def test_W6P01_T10_valid_source_invokes_injected_http_get(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_dns(monkeypatch)
    _patch_robots(monkeypatch, allow=True)
    calls: list[str] = []

    def _get(url: str, **_k: Any) -> Any:
        calls.append(url)
        return _FakeResponse(200, _HTML_BODY, {"Content-Type": "text/html; charset=utf-8"})

    gov = _ok_gov()
    adapter = PublicWebFetchAdapter()
    envelope = adapter.fetch_live(
        request_id="r1", url="https://example.org/page", governance=gov, http_get=_get
    )
    assert calls == ["https://example.org/page"]
    assert envelope.http_status == 200
    assert envelope.error_category is None
    assert envelope.body == _HTML_BODY


def test_W6P01_T11_content_hash_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_dns(monkeypatch)
    _patch_robots(monkeypatch, allow=True)

    def _get(*_a: Any, **_k: Any) -> Any:
        return _FakeResponse(200, _HTML_BODY, {"Content-Type": "text/html; charset=utf-8"})

    gov = _ok_gov()
    adapter = PublicWebFetchAdapter()
    e1 = adapter.fetch_live(request_id="r1", url="https://example.org/page", governance=gov, http_get=_get)
    e2 = adapter.fetch_live(request_id="r2", url="https://example.org/page", governance=gov, http_get=_get)
    assert e1.content_hash == e2.content_hash == hashlib.sha256(_HTML_BODY).hexdigest()


# ---------------------------------------------------------------------------
# 7. Orchestrator wiring: controlled live path end to end (dry, no db).
# ---------------------------------------------------------------------------


def test_W6P01_T12_controlled_live_orchestration_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_dns(monkeypatch)
    _patch_robots(monkeypatch, allow=True)

    def _get(*_a: Any, **_k: Any) -> Any:
        return _FakeResponse(200, _HTML_BODY, {"Content-Type": "text/html; charset=utf-8"})

    outcome = orch.run_controlled_live_orchestration(
        None, None, candidates=[_ok_candidate()], persist_ledger=False, live_http_get=_get
    )
    assert outcome.activation_enabled is True
    assert outcome.scheduler_activation is True
    assert outcome.production_write is False
    assert outcome.network_executed is True
    statuses = {r["result_status"] for r in outcome.source_results}
    assert "EXTRACTED" in statuses
    kinds = {h.handoff_kind for h in outcome.handoffs}
    assert {"RAW_EVIDENCE", "PROVENANCE", "CANDIDATE"} <= kinds
    assert all(h.execute is False for h in outcome.handoffs)


def test_W6P01_T13_run_dormant_scheduled_tick_reaches_live_when_both_flags_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(orch.WEEKLY_ORCHESTRATOR_ENABLE_ENV, "true")
    monkeypatch.setenv(orch.SOURCE_ACTIVATION_ENV, "true")
    _patch_dns(monkeypatch)
    _patch_robots(monkeypatch, allow=True)

    def _get(*_a: Any, **_k: Any) -> Any:
        return _FakeResponse(200, _HTML_BODY, {"Content-Type": "text/html; charset=utf-8"})

    tick = orch.run_dormant_scheduled_tick(candidates=[_ok_candidate()], live_http_get=_get)
    assert tick.outcome in {"FULL_SUCCESS", "PARTIAL_SUCCESS"}
    assert tick.network_executed is True
    assert tick.scheduler_activation is True


def test_W6P01_T14_blocked_candidate_never_reaches_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(orch.WEEKLY_ORCHESTRATOR_ENABLE_ENV, "true")
    monkeypatch.setenv(orch.SOURCE_ACTIVATION_ENV, "true")
    tick = orch.run_dormant_scheduled_tick(
        candidates=[_ok_candidate(rights_terms_state="UNKNOWN")],
        live_http_get=_unused_get,
    )
    assert tick.network_executed is False
    statuses = {r["result_status"] for r in tick.source_results}
    assert "BLOCKED" in statuses


# ---------------------------------------------------------------------------
# 8. Fixture transport path is unchanged by the live path additions.
# ---------------------------------------------------------------------------


def test_W6P01_T15_fixture_transport_unchanged_no_network() -> None:
    candidate = _ok_candidate()
    outcome = orch.orchestrate_weekly_run(
        None,
        None,
        candidates=[candidate],
        transports={
            1: FixtureTransportResponse(
                status_code=200, body=_HTML_BODY, content_type="text/html; charset=utf-8"
            )
        },
        dry_run=True,
        persist_ledger=False,
    )
    assert outcome.network_executed is False
    assert outcome.outcome in {"FULL_SUCCESS", "PARTIAL_SUCCESS", "NO_MATERIAL_CHANGE"}
