"""Section 30 / W6-P03 — AA metrics emitters + alert rules (dry unit).

Authority:
- package_sequence.json → TESTS_TO_AUTHOR: metric emission unit
- CLOSURE_CRITERIA: AA metrics defined and emitted in dry unit
- safety_security_observability_plan.json → 17 AA metric names
- BC-24 → silent zero improvement; high-risk gaps alerts
- Proof-quality law: no `or True`, no self-equality, no disposition tautology
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.i5 import metrics as m
from backend.app.services.i5 import weekly_orchestrator as orch
from backend.app.services.i5.adapters.base import FixtureTransportResponse
from backend.app.services.i5.source_discovery import SourceCandidateDescriptor

PLAN_METRICS_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "evidence"
    / "section30"
    / "i5_implementation_acceleration_plan_01"
    / "safety_security_observability_plan.json"
)


@pytest.fixture(autouse=True)
def _reset_emitter():
    m.reset_metrics_emitter()
    yield
    m.reset_metrics_emitter()


def _authority_metric_names() -> list[str]:
    data = json.loads(PLAN_METRICS_PATH.read_text(encoding="utf-8"))
    names = list(data["required_metrics"])
    assert data["metric_count"] == 17
    assert len(names) == 17
    return names


def _ok_candidate(**overrides) -> SourceCandidateDescriptor:
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


def _transport() -> FixtureTransportResponse:
    return FixtureTransportResponse(
        status_code=200,
        body=(
            b"<html><title>T</title><body>"
            b"<p>Enough visible medical guidance text for extraction threshold.</p>"
            b"</body></html>"
        ),
        content_type="text/html; charset=utf-8",
    )


def test_W6P03_T01_package_identity_and_aa_metric_set_matches_authority():
    assert m.PACKAGE_ID == "I5-IMPL-W6-P03"
    assert m.MANAGEMENT_ALIAS == "P12"
    assert m.CAPABILITY_ID == "CAP-OPEN-26"
    assert m.MISSING_COMPONENT_ID == "MISS-17"
    assert m.ARCHITECTURE_CONTEXT_ID == "BC-24"
    authority = _authority_metric_names()
    assert list(m.AA_METRIC_NAMES) == authority
    assert len(m.AA_METRIC_NAME_SET) == 17


def test_W6P03_T02_emit_rejects_unknown_and_negative_metric():
    emitter = m.get_metrics_emitter()
    with pytest.raises(m.MetricsError) as unknown:
        emitter.emit("NOT_AN_AA_METRIC", 1)
    assert unknown.value.code == "UNKNOWN_METRIC"
    with pytest.raises(m.MetricsError) as negative:
        emitter.emit("SOURCES_CHECKED", -1)
    assert negative.value.code == "METRIC_VALUE_NEGATIVE"
    assert emitter.emit_count() == 0


def test_W6P03_T03_emit_run_snapshot_emits_all_seventeen_and_updates_latest():
    emitter = m.get_metrics_emitter()
    values = m.build_aa_metrics_from_run_counters(
        sources_checked=4,
        failed_sources=1,
        blocked_sources=1,
        new_knowledge_units=2,
        updated_units=1,
        knowledge_gaps_closed=1,
        run_duration=12.5,
        database_write_count=3,
        total_sources=5,
    )
    samples = emitter.emit_run_snapshot(
        values,
        labels={"logical_run_key": "run-a", "outcome": "COMPLETED", "dry_run": "true"},
    )
    assert len(samples) == 17
    assert {s.name for s in samples} == set(m.AA_METRIC_NAMES)
    latest = emitter.latest()
    assert latest["SOURCES_CHECKED"] == 4.0
    assert latest["NEW_KNOWLEDGE_UNITS"] == 2.0
    assert latest["RUN_DURATION"] == 12.5
    assert emitter.emit_count() == 17


def test_W6P03_T04_labels_refuse_disallowed_and_sensitive_keys():
    emitter = m.get_metrics_emitter()
    with pytest.raises(m.MetricsError) as bad_key:
        emitter.emit("SOURCES_CHECKED", 1, labels={"patient_id": "x"})
    assert bad_key.value.code == "LABEL_NOT_ALLOWED"
    with pytest.raises(m.MetricsError) as secret:
        emitter.emit("SOURCES_CHECKED", 1, labels={"outcome": "token=abc"})
    assert secret.value.code == "LABEL_SENSITIVE_REFUSED"


def test_W6P03_T05_silent_zero_improvement_alert_positive_and_negative():
    silent = m.build_aa_metrics_from_run_counters(
        sources_checked=3,
        new_knowledge_units=0,
        updated_units=0,
        knowledge_gaps_closed=0,
        total_sources=3,
    )
    decisions = m.evaluate_alerts(silent)
    by_id = {d.alert_id: d for d in decisions}
    assert by_id[m.ALERT_SILENT_ZERO_IMPROVEMENT].triggered is True

    improved = m.build_aa_metrics_from_run_counters(
        sources_checked=3,
        new_knowledge_units=1,
        total_sources=3,
    )
    decisions2 = m.evaluate_alerts(improved)
    by_id2 = {d.alert_id: d for d in decisions2}
    assert by_id2[m.ALERT_SILENT_ZERO_IMPROVEMENT].triggered is False

    no_sources = m.build_aa_metrics_from_run_counters(sources_checked=0, total_sources=0)
    decisions3 = m.evaluate_alerts(no_sources)
    by_id3 = {d.alert_id: d for d in decisions3}
    assert by_id3[m.ALERT_SILENT_ZERO_IMPROVEMENT].triggered is False


def test_W6P03_T06_high_risk_gap_alert_positive_and_negative():
    hot = m.build_aa_metrics_from_run_counters(high_risk_gaps_remaining=2)
    cold = m.build_aa_metrics_from_run_counters(high_risk_gaps_remaining=0)
    assert m.triggered_alerts(hot)[0].alert_id == m.ALERT_HIGH_RISK_GAPS or any(
        d.alert_id == m.ALERT_HIGH_RISK_GAPS and d.triggered for d in m.evaluate_alerts(hot)
    )
    hot_dec = {d.alert_id: d for d in m.evaluate_alerts(hot)}
    cold_dec = {d.alert_id: d for d in m.evaluate_alerts(cold)}
    assert hot_dec[m.ALERT_HIGH_RISK_GAPS].triggered is True
    assert cold_dec[m.ALERT_HIGH_RISK_GAPS].triggered is False


def test_W6P03_T07_policy_threshold_review_alert_positive_and_negative():
    review = m.build_aa_metrics_from_run_counters(safety_rejections=1)
    ok = m.build_aa_metrics_from_run_counters(safety_rejections=0, conflicts=0)
    conflict = m.build_aa_metrics_from_run_counters(conflicts=2)
    r = {d.alert_id: d for d in m.evaluate_alerts(review)}
    o = {d.alert_id: d for d in m.evaluate_alerts(ok)}
    c = {d.alert_id: d for d in m.evaluate_alerts(conflict)}
    assert r[m.ALERT_POLICY_THRESHOLD_REVIEW].triggered is True
    assert o[m.ALERT_POLICY_THRESHOLD_REVIEW].triggered is False
    assert c[m.ALERT_POLICY_THRESHOLD_REVIEW].triggered is True


def test_W6P03_T08_observe_weekly_run_metrics_idempotent_duplicate_snapshot():
    values = m.build_aa_metrics_from_run_counters(sources_checked=1, new_knowledge_units=1)
    first = m.observe_weekly_run_metrics(counters=values, labels={"outcome": "COMPLETED", "dry_run": "true"})
    second = m.observe_weekly_run_metrics(counters=values, labels={"outcome": "COMPLETED", "dry_run": "true"})
    assert first["samples_emitted"] == 17
    assert second["samples_emitted"] == 17
    assert m.get_metrics_emitter().emit_count() == 34
    assert m.get_metrics_emitter().latest()["NEW_KNOWLEDGE_UNITS"] == 1.0


def test_W6P03_T09_orchestrator_dry_unit_emits_aa_metrics_without_network_or_activation():
    cand = _ok_candidate()
    result = orch.orchestrate_weekly_run(
        db=None,
        models=None,
        candidates=[cand],
        transports={1: _transport()},
        persist_ledger=False,
        dry_run=True,
        enforce_activation_off=True,
    )
    assert result.network_executed is False
    assert result.activation_enabled is False
    assert result.scheduler_activation is False
    assert result.production_write is False
    assert set(result.aa_metrics) == set(m.AA_METRIC_NAMES)
    assert result.aa_metrics["SOURCES_CHECKED"] >= 1.0
    assert len(result.alert_decisions) == 3
    assert all("alert_id" in d and "triggered" in d for d in result.alert_decisions)
    # Emitter received a full AA snapshot from the orchestrator hook.
    assert m.get_metrics_emitter().emit_count() == 17
    assert m.get_metrics_emitter().latest()["SOURCES_CHECKED"] == result.aa_metrics["SOURCES_CHECKED"]


def test_W6P03_T10_orchestrator_metrics_do_not_change_outcome_classification():
    cand = _ok_candidate()
    # First run with metrics path
    a = orch.orchestrate_weekly_run(
        db=None,
        models=None,
        candidates=[cand],
        transports={1: _transport()},
        persist_ledger=False,
        dry_run=True,
    )
    # Recompute outcome from source rows alone — must match attached outcome.
    extracted = sum(
        1
        for s in a.source_results
        if s["result_status"] in {"EXTRACTED", "FETCHED"}
    )
    recomputed = orch.classify_run_outcome(
        total_sources=len(a.source_results),
        failed_sources=sum(1 for s in a.source_results if s["result_status"] == "FAILED"),
        blocked_sources=sum(1 for s in a.source_results if s["result_status"] == "BLOCKED"),
        skipped_sources=sum(1 for s in a.source_results if s["result_status"] == "SKIPPED"),
        warning_count=0,
        extracted_or_fetched=extracted,
    )
    assert a.outcome == recomputed


def test_W6P03_T11_normalize_requires_complete_aa_set():
    with pytest.raises(m.MetricsError) as missing:
        m.normalize_aa_metric_values({"SOURCES_CHECKED": 1})
    assert missing.value.code == "MISSING_METRIC"
    with pytest.raises(m.MetricsError) as unknown:
        full = m.empty_aa_metric_values()
        full["EXTRA"] = 1
        m.normalize_aa_metric_values(full)
    assert unknown.value.code == "UNKNOWN_METRIC"


def test_W6P03_T12_no_pagerduty_or_network_side_effects_in_metrics_module():
    src = Path(m.__file__).read_text(encoding="utf-8")
    # Docstring may mention OUT_OF_SCOPE prod paging; executable surface must not import/call it.
    assert "import pagerduty" not in src.lower()
    assert "from pagerduty" not in src.lower()
    assert "requests." not in src
    assert "import httpx" not in src
    assert "import urllib" not in src
    assert "import socket" not in src
    assert "urlopen(" not in src
    # Evaluate alerts must not perform I/O — pure decision objects only.
    values = m.build_aa_metrics_from_run_counters(sources_checked=1, high_risk_gaps_remaining=1)
    decisions = m.evaluate_alerts(values)
    assert all(isinstance(d.triggered, bool) for d in decisions)
    assert any(d.triggered for d in decisions)