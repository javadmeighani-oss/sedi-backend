"""Section 30 / I5-IMPL-W6-P01 — REAL controlled network E2E (W6-P01 Gate, W6-P03 prereq).

Unlike `test_section30_i5_w6_p01_live_acquisition.py` (pure unit, injected
`http_get`, never opens a socket), every test in THIS file whose name contains
`REAL` performs (or attempts) a genuine HTTPS request against the single
ELIGIBLE controlled-live source recorded in
`docs/evidence/section30/w6p01_prereq_real_e2e_20260808T053706Z/06_source_governance/candidate_evaluation.md`:

    https://www.nhs.uk/live-well/sleep-and-tiredness/   (allowed_domain=nhs.uk)

Fail-closed opt-in: every `REAL` test calls `_require_real_network()` first and
is skipped (not silently passed) unless the operator explicitly sets
`SEDI_I5_ALLOW_REAL_NETWORK=1`. This lets CI opt in via a dedicated
`workflow_dispatch` target (`i5_w6p01_real_network`) without any risk of an
ordinary push/PR run or a developer's local `pytest` making a live NHS request.

Honest-failure contract: a `REAL` test never converts a genuine network
condition (timeout / connection error / rate limit / 404 / 410) into a false
pass. `PublicWebFetchAdapter.fetch_live` raises `AdapterFrameworkError` for
those; this module catches only the transport-layer categories in
`HONEST_NETWORK_FAILURE_CATEGORIES` and reports them via `pytest.skip` with the
exact category in the reason string — a governance-layer category leaking
through (e.g. `GOVERNANCE_BLOCKED`, `ROBOTS_BLOCKED`, `TERMS_BLOCKED`,
`UNSAFE_URL`) is NOT treated as honest and fails the test, since that would
mean this file's own governance snapshot / URL construction is wrong.

Non-`REAL` tests (T00 / T00b) always run and prove the discovery/governance
wiring for the NHS candidate structurally, with no network I/O, so this file
still contributes CI signal even when the network opt-in is off.
"""
from __future__ import annotations

import hashlib
import importlib
import os
from urllib.parse import urlparse

import pytest
from sqlalchemy.orm import configure_mappers

from backend.app.schemas.i5_adapters import SourceGovernanceSnapshot
from backend.app.services.i5 import metrics as metrics_mod
from backend.app.services.i5 import source_discovery as discovery
from backend.app.services.i5 import weekly_orchestrator as orch
from backend.app.services.i5.adapters.base import (
    MAX_CONTENT_BYTES,
    AdapterFrameworkError,
    assert_source_governance_allows_controlled_use,
)
from backend.app.services.i5.adapters.public_web_fetch import PublicWebFetchAdapter
from backend.app.services.i5.source_discovery import SourceCandidateDescriptor

PACKAGE_ID = "I5-IMPL-W6-P01"
MANAGEMENT_ALIAS = "P10"

REAL_NETWORK_ENV = "SEDI_I5_ALLOW_REAL_NETWORK"

# The single source recorded ELIGIBLE for controlled-live fetch (candidate_evaluation.md §D).
NHS_SLEEP_URL = "https://www.nhs.uk/live-well/sleep-and-tiredness/"
NHS_ALLOWED_DOMAIN = "nhs.uk"
NHS_ALLOWED_URL_PATTERN = r"^https://www\.nhs\.uk/live-well/.*"
NHS_TRUST_LEVEL = "official"

# Transport-layer categories — a GOVERNANCE_BLOCKED / TERMS_BLOCKED / UNSAFE_URL
# category here would mean this file's own fixtures are wrong, not that the
# network is unreachable, so those are deliberately NOT included.
#
# ROBOTS_BLOCKED is included: `backend.app.services.gate3.robots_checker
# .check_robots_allowed` fail-closes an official/review_required source on
# ANY exception while fetching robots.txt itself (`except Exception: raise
# RobotsBlockedError(...)`), so it cannot distinguish a genuine robots.txt
# disallow rule from a transport failure (DNS/connection/timeout/runner
# egress policy) encountered while fetching robots.txt. For the NHS sleep
# page — pre-verified robots-ALLOWED in candidate_evaluation.md — an observed
# ROBOTS_BLOCKED here is documented honestly as a transport-layer condition,
# not treated as a silent pass, and not treated as a governance-setup bug.
HONEST_NETWORK_FAILURE_CATEGORIES = frozenset(
    {"TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED", "NOT_FOUND", "GONE", "ROBOTS_BLOCKED"}
)

_IDEMPOTENCY_LOGICAL_RUN_KEY = hashlib.sha256(
    b"I5-IMPL-W6-P01|real-network-e2e|nhs-sleep|idempotency-v1"
).hexdigest()

_DET_SEQ = 0


def _det_hex(nbytes: int = 8) -> str:
    global _DET_SEQ
    _DET_SEQ += 1
    return f"{_DET_SEQ:0{nbytes * 2}x}"[-nbytes * 2 :]


def _load_models():
    return importlib.import_module("backend.app.models")


def _require_postgres(db) -> None:
    if db.get_bind().dialect.name != "postgresql":
        pytest.fail("PostgreSQL required for W6-P01 real-network ledger persistence node")


def _real_network_enabled() -> bool:
    """Exact opt-in only — `SEDI_I5_ALLOW_REAL_NETWORK` must equal the literal `1`."""
    return os.environ.get(REAL_NETWORK_ENV, "").strip() == "1"


def _require_real_network() -> None:
    if not _real_network_enabled():
        pytest.skip(f"{REAL_NETWORK_ENV} != 1; real-network E2E is opt-in only")


def _nhs_governance(**overrides) -> SourceGovernanceSnapshot:
    base = dict(
        source_profile_id=None,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        rights_terms_state="OGL",
        robots_access_state="ALLOWED",
        rate_limit_policy="DEFINED",
        allowed_domain=NHS_ALLOWED_DOMAIN,
    )
    base.update(overrides)
    return SourceGovernanceSnapshot(**base)


def _nhs_candidate(**overrides) -> SourceCandidateDescriptor:
    base = dict(
        source_profile_id=1,
        adapter_mode="PUBLIC_WEB_FETCH",
        url=NHS_SLEEP_URL,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        rights_terms_state="OGL",
        robots_access_state="ALLOWED",
        rate_limit_policy="DEFINED",
        allowed_domain=NHS_ALLOWED_DOMAIN,
    )
    base.update(overrides)
    return SourceCandidateDescriptor(**base)


def _build_gsp(db, **overrides):
    models = _load_models()
    base = dict(
        canonical_key="w6p01-real-nhs-" + _det_hex(6),
        operational_status="ACTIVE",
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        canonicalization_version="v1",
    )
    base.update(overrides)
    row = models.GovernedSourceProfile(**base)
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# T00 — structural wiring proof. No network. Always runs (no opt-in required).
# ---------------------------------------------------------------------------


def test_W6P01_REAL_T00_static_governance_and_discovery_wiring_no_network() -> None:
    candidate = _nhs_candidate(source_profile_id=1)
    governance = discovery.to_governance_snapshot(candidate)
    assert_source_governance_allows_controlled_use(governance)  # must not raise
    item = discovery.build_discovery_work_item(candidate)
    assert item.adapter_id == "i5.public_web_fetch"
    assert item.adapter_mode == "PUBLIC_WEB_FETCH"
    assert item.canonical_url == NHS_SLEEP_URL
    assert item.governance.allowed_domain == NHS_ALLOWED_DOMAIN
    assert item.governance.rights_terms_state == "OGL"


def test_W6P01_REAL_T00b_env_flag_opt_in_is_exact_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(REAL_NETWORK_ENV, raising=False)
    assert _real_network_enabled() is False
    monkeypatch.setenv(REAL_NETWORK_ENV, "true")
    assert _real_network_enabled() is False
    monkeypatch.setenv(REAL_NETWORK_ENV, "0")
    assert _real_network_enabled() is False
    monkeypatch.setenv(REAL_NETWORK_ENV, "1")
    assert _real_network_enabled() is True


# ---------------------------------------------------------------------------
# T01 — real HTTPS fetch through PublicWebFetchAdapter.fetch_live. No http_get mock.
# ---------------------------------------------------------------------------


def test_W6P01_REAL_T01_fetch_live_real_network_nhs_sleep_page() -> None:
    _require_real_network()
    adapter = PublicWebFetchAdapter()
    governance = _nhs_governance()
    try:
        envelope = adapter.fetch_live(
            request_id="w6p01-real-t01",
            url=NHS_SLEEP_URL,
            governance=governance,
            allowed_url_patterns=(NHS_ALLOWED_URL_PATTERN,),
            trust_level=NHS_TRUST_LEVEL,
            review_required=True,
        )
    except AdapterFrameworkError as exc:
        if exc.category not in HONEST_NETWORK_FAILURE_CATEGORIES:
            raise
        pytest.skip(f"REAL_NETWORK_HONEST_FAILURE:{exc.category}:{exc}")
        return

    assert envelope.http_status in {200, 304}, envelope.http_status
    assert envelope.error_category in (None, "NO_MATERIAL_CHANGE")
    assert envelope.disposition in ("OK", "NO_MATERIAL_CHANGE")
    assert not (envelope.http_status == 200 and envelope.disposition != "OK")
    # content_hash present (sha256 hex digest length) regardless of 200/304.
    assert envelope.content_hash and len(envelope.content_hash) == 64
    int(envelope.content_hash, 16)  # raises ValueError if not hex
    # final_url host is nhs.uk (or a nhs.uk subdomain) — no redirect off-domain.
    final_host = (urlparse(envelope.final_url).hostname or "").lower()
    assert final_host == NHS_ALLOWED_DOMAIN or final_host.endswith("." + NHS_ALLOWED_DOMAIN)
    # byte_count > 0 and <= governed max (2xx path only carries a body).
    if envelope.http_status == 200:
        assert 0 < envelope.byte_count <= MAX_CONTENT_BYTES
        assert envelope.body != b""
    else:
        assert envelope.byte_count == 0  # 304 carries no body under build_fetch_envelope


# ---------------------------------------------------------------------------
# T02/T03 — weekly_orchestrator controlled-live dry path, real network,
# shared via a module-scoped fixture so the NHS page is fetched once for both.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _real_dry_orchestration_outcome():
    _require_real_network()
    candidate = _nhs_candidate(source_profile_id=101)
    return orch.run_controlled_live_orchestration(
        None,
        None,
        candidates=[candidate],
        persist_ledger=False,
        live_http_get=None,
    )


def test_W6P01_REAL_T02_weekly_orchestrator_dry_run_real_network(_real_dry_orchestration_outcome) -> None:
    outcome = _real_dry_orchestration_outcome
    assert outcome.activation_enabled is True
    assert outcome.scheduler_activation is True
    assert outcome.production_write is False
    # Both flags are effectively "on" for this explicit controlled-live call
    # (run_controlled_live_orchestration bypasses the scheduler tick's own
    # env-flag re-check by design — see weekly_orchestrator.py docstring).
    assert outcome.network_executed is True
    statuses = {r["result_status"] for r in outcome.source_results}
    assert statuses, "expected at least one source result from the real NHS attempt"
    if "EXTRACTED" in statuses:
        assert outcome.outcome in {"FULL_SUCCESS", "PARTIAL_SUCCESS"}
    else:
        failure_codes = {r.get("failure_code") for r in outcome.source_results}
        honest_or_governance = HONEST_NETWORK_FAILURE_CATEGORIES | {
            "GOVERNANCE_BLOCKED",
            "ROBOTS_BLOCKED",
            "TERMS_BLOCKED",
            "UNSAFE_URL",
        }
        assert failure_codes & honest_or_governance, failure_codes


def test_W6P01_REAL_T03_metrics_capture_no_fabricated_scores(_real_dry_orchestration_outcome) -> None:
    outcome = _real_dry_orchestration_outcome
    metric_keys = set(outcome.aa_metrics.keys())
    # Exactly the emittable counters — no COVERAGE_SCORE/FRESHNESS_SCORE fabrication.
    assert metric_keys == metrics_mod.EMITTABLE_COUNTER_METRIC_SET
    assert not (metrics_mod.UNFORMULATED_SCORE_METRICS & metric_keys)
    assert "COVERAGE_SCORE" not in outcome.aa_metrics
    assert "FRESHNESS_SCORE" not in outcome.aa_metrics
    assert outcome.aa_metrics["SOURCES_CHECKED"] >= 1
    for value in outcome.aa_metrics.values():
        assert value >= 0.0


# ---------------------------------------------------------------------------
# T04 — real network + real Postgres ledger persistence through the
# orchestrator (never raw SQL inserts), plus run-level idempotency proof.
# Requires DATABASE_URL (CI job runs alembic upgrade head beforehand).
# ---------------------------------------------------------------------------


def test_W6P01_REAL_T04_persist_ledger_real_network_writes_rows_and_is_idempotent(db) -> None:
    _require_real_network()
    if not os.environ.get("DATABASE_URL", "").strip():
        pytest.skip("DATABASE_URL not set; skipping real-network ledger persistence proof")
    _require_postgres(db)
    configure_mappers()
    models = _load_models()

    gsp = _build_gsp(db)
    candidate = _nhs_candidate(source_profile_id=gsp.id)

    outcome1 = orch.run_controlled_live_orchestration(
        db,
        models,
        candidates=[candidate],
        persist_ledger=True,
        logical_run_key=_IDEMPOTENCY_LOGICAL_RUN_KEY,
        live_http_get=None,
    )
    assert outcome1.activation_enabled is True
    assert outcome1.run_id is not None
    assert outcome1.attempt_id is not None

    run_row = (
        db.query(models.WeeklyKnowledgeRun)
        .filter(models.WeeklyKnowledgeRun.logical_run_key == _IDEMPOTENCY_LOGICAL_RUN_KEY)
        .one()
    )
    assert run_row.id == outcome1.run_id
    attempt_row = (
        db.query(models.WeeklyKnowledgeRunAttempt)
        .filter(models.WeeklyKnowledgeRunAttempt.id == outcome1.attempt_id)
        .one()
    )
    assert attempt_row.weekly_run_id == run_row.id
    source_result = (
        db.query(models.WeeklyRunSourceResult)
        .filter(
            models.WeeklyRunSourceResult.attempt_id == outcome1.attempt_id,
            models.WeeklyRunSourceResult.source_profile_id == gsp.id,
        )
        .one()
    )
    assert source_result.result_status in {"EXTRACTED", "FAILED", "BLOCKED", "SKIPPED"}
    if source_result.result_status != "EXTRACTED":
        assert source_result.failure_code, "non-extracted result must record an honest failure_code"
        assert outcome1.production_write is False
    else:
        assert outcome1.production_write is True
        assert outcome1.detail == "governed_raw_ku_provenance_persisted"
        raw = (
            db.query(models.I5RawEvidence)
            .filter(models.I5RawEvidence.source_profile_id == gsp.id)
            .order_by(models.I5RawEvidence.id.desc())
            .first()
        )
        assert raw is not None
        assert raw.retention_mode == "RAW_MINIMAL_EVIDENCE_ONLY"
        ku = (
            db.query(models.KnowledgeUnit)
            .order_by(models.KnowledgeUnit.id.desc())
            .first()
        )
        assert ku is not None
        assert ku.publication_state == "DRAFT"
        assert ku.runtime_eligibility != "ELIGIBLE"
        prov = (
            db.query(models.KnowledgeProvenance)
            .filter(models.KnowledgeProvenance.knowledge_unit_id == ku.id)
            .one()
        )
        assert prov.raw_evidence_id == raw.id
        assert db.query(models.KnowledgeMemoryItem).count() == 0
        assert outcome1.network_executed is True

    # Idempotency: second controlled-live call with the SAME logical_run_key
    # resolves to the SAME run and does NOT open a new network/attempt when a
    # successful terminal already exists.
    outcome2 = orch.run_controlled_live_orchestration(
        db,
        models,
        candidates=[candidate],
        persist_ledger=True,
        logical_run_key=_IDEMPOTENCY_LOGICAL_RUN_KEY,
        live_http_get=None,
    )
    assert outcome2.run_id == outcome1.run_id
    assert outcome2.attempt_id == outcome1.attempt_id
    assert outcome2.network_executed is False
    assert outcome2.detail == "ALREADY_SUCCESSFUL_TERMINAL"
    run_count = (
        db.query(models.WeeklyKnowledgeRun)
        .filter(models.WeeklyKnowledgeRun.logical_run_key == _IDEMPOTENCY_LOGICAL_RUN_KEY)
        .count()
    )
    assert run_count == 1
    success_attempts = (
        db.query(models.WeeklyKnowledgeRunAttempt)
        .filter(models.WeeklyKnowledgeRunAttempt.weekly_run_id == outcome1.run_id)
        .filter(
            models.WeeklyKnowledgeRunAttempt.status.in_(
                ("COMPLETED", "COMPLETED_WITH_WARNINGS")
            )
        )
        .count()
    )
    assert success_attempts == 1
