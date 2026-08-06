"""Section 30 / W3-P02 — Weekly orchestrator + discovery wiring (activation off).

Runtime selectors are exercised by w3p02-postgresql-weekly-orchestrator-runtime.yml.
Controlled real-source validation is NOT owned / NOT executed (W6-P01).
"""
from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers

from backend.app.services.i5.adapters.base import AdapterFrameworkError, FixtureTransportResponse
from backend.app.services.i5 import source_discovery as discovery
from backend.app.services.i5 import weekly_orchestrator as orch
from backend.app.services.i5.source_discovery import SourceCandidateDescriptor


def _load_models():
    return importlib.import_module("backend.app.models")


def _require_postgres(db) -> None:
    if db.get_bind().dialect.name != "postgresql":
        pytest.fail("PostgreSQL required for W3-P02 runtime node")


_DET_SEQ = 0


def _det_hex(nbytes: int = 32) -> str:
    global _DET_SEQ
    _DET_SEQ += 1
    return f"{_DET_SEQ:0{nbytes * 2}x}"[-nbytes * 2 :]


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


def _transport(
    status: int = 200,
    body: bytes = (
        b"<html><title>T</title><body>"
        b"<p>Enough visible medical guidance text for extraction threshold.</p>"
        b"</body></html>"
    ),
) -> FixtureTransportResponse:
    return FixtureTransportResponse(
        status_code=status,
        body=body,
        content_type="text/html; charset=utf-8",
    )


def _build_gsp(db, **overrides):
    models = _load_models()
    base = dict(
        canonical_key="w3p02-gsp-" + _det_hex(8),
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


def _build_gap(db, **overrides):
    models = _load_models()
    base = dict(
        canonical_gap_key=_det_hex(32),
        canonicalization_version="v1",
        hash_algorithm="SHA-256",
        domain="neurology",
        gap_type="MISSING",
        title="w3p02 gap",
        priority="P2",
        severity="MEDIUM",
        urgency="NORMAL",
        status="OPEN",
    )
    base.update(overrides)
    row = models.KnowledgeGap(**base)
    db.add(row)
    db.flush()
    return row


def test_W3P02_T1_package_identity() -> None:
    assert orch.PACKAGE_ID == "I5-IMPL-W3-P02"
    assert orch.MANAGEMENT_ALIAS == "P07"
    assert discovery.PACKAGE_ID == "I5-IMPL-W3-P02"
    assert discovery.MANAGEMENT_ALIAS == "P07"
    assert "Weekly orchestrator" in orch.PACKAGE_TITLE
    assert orch.CONTROLLED_NETWORK_OWNED_BY == "I5-IMPL-W6-P01"
    assert orch.RAW_PROVENANCE_OWNED_BY == "I5-IMPL-W1-P02"
    assert orch.WEEKLY_ORCHESTRATOR_JOB_ID == "weekly_international_knowledge_crawler"


def test_W3P02_T2_activation_off_and_dormant_scheduler_contract() -> None:
    assert orch.weekly_orchestrator_enabled() is False
    assert orch.source_activation_enabled() is False
    tick = orch.run_dormant_scheduled_tick()
    assert tick.outcome == "DORMANT_NO_OP"
    assert tick.network_executed is False
    assert tick.production_write is False
    assert tick.scheduler_activation is False
    sched_mod = importlib.import_module("backend.app.core.scheduler")
    src = inspect.getsource(sched_mod.start_scheduler)
    assert "weekly_international_knowledge_crawler" in src
    assert "run_dormant_scheduled_tick" in src
    orch.assert_activation_off_contract()


def test_W3P02_T3_discovery_select_eligible() -> None:
    candidates = [
        _ok_candidate(source_profile_id=1),
        _ok_candidate(
            source_profile_id=2,
            registry_state="ACTIVE",
            runtime_eligibility="NOT_ELIGIBLE",
            url="https://example.org/b",
        ),
        _ok_candidate(
            source_profile_id=3,
            registry_state="DISCOVERED",
            runtime_eligibility="ELIGIBLE",
            url="https://example.org/c",
        ),
    ]
    selected, skipped = discovery.select_eligible_sources(candidates)
    assert [c.source_profile_id for c in selected] == [1]
    assert len(skipped) == 2
    plan = discovery.plan_discovery(selected)
    assert plan.eligible_count == 1
    assert plan.selected[0].adapter_id == "i5.public_web_fetch"


@pytest.mark.parametrize(
    "case_id",
    ["unknown_rights", "robots_blocked", "rate_undefined", "registry_blocked"],
)
def test_W3P02_T4_governance_fail_closed(case_id: str) -> None:
    overrides = {
        "unknown_rights": {"rights_terms_state": "UNKNOWN"},
        "robots_blocked": {"robots_access_state": "BLOCKED"},
        "rate_undefined": {"rate_limit_policy": "UNKNOWN"},
        "registry_blocked": {"registry_state": "BLOCKED", "runtime_eligibility": "ELIGIBLE"},
    }[case_id]
    # registry_blocked must still be structurally selected if we bypass select —
    # plan_discovery only governs after select; force ACTIVE+ELIGIBLE then override
    # governance fields for fail-closed.
    if case_id == "registry_blocked":
        candidate = _ok_candidate(
            source_profile_id=10,
            registry_state="ACTIVE",
            runtime_eligibility="ELIGIBLE",
            **{k: v for k, v in overrides.items() if k not in {"registry_state", "runtime_eligibility"}},
        )
        # Direct build with blocked registry
        blocked = _ok_candidate(source_profile_id=10, **overrides)
        with pytest.raises(AdapterFrameworkError) as ei:
            discovery.build_discovery_work_item(blocked)
        assert ei.value.category in {
            "GOVERNANCE_BLOCKED",
            "ROBOTS_BLOCKED",
            "TERMS_BLOCKED",
        }
        return
    candidate = _ok_candidate(source_profile_id=11, **overrides)
    # Make structurally eligible so governance gate is the failure point.
    candidate = SourceCandidateDescriptor(
        source_profile_id=candidate.source_profile_id,
        adapter_mode=candidate.adapter_mode,
        url=candidate.url,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        rights_terms_state=overrides.get("rights_terms_state", "ACCEPTABLE"),
        robots_access_state=overrides.get("robots_access_state", "ALLOWED"),
        rate_limit_policy=overrides.get("rate_limit_policy", "DEFINED"),
        allowed_domain="example.org",
    )
    plan = discovery.plan_discovery([candidate])
    assert plan.eligible_count == 0
    assert len(plan.blocked) + len(plan.failed) >= 1


def test_W3P02_T5_adapter_resolve_and_unknown() -> None:
    adapter = discovery.resolve_adapter_for_mode("PUBLIC_WEB_FETCH")
    assert adapter.metadata().adapter_id == "i5.public_web_fetch"
    with pytest.raises(AdapterFrameworkError, match="ADAPTER_UNKNOWN"):
        discovery.resolve_adapter_for_mode("NOT_A_MODE")
    with pytest.raises(AdapterFrameworkError, match="ADAPTER_DISABLED"):
        discovery.resolve_adapter_for_mode("BLOCKED_OR_EXCLUDED")


def test_W3P02_T6_discovery_dedupe() -> None:
    a = discovery.build_discovery_work_item(_ok_candidate(source_profile_id=1))
    b = discovery.build_discovery_work_item(_ok_candidate(source_profile_id=1))
    c = discovery.build_discovery_work_item(
        _ok_candidate(source_profile_id=2, url="https://example.org/other")
    )
    deduped = discovery.dedupe_discovery_items([a, b, c])
    assert len(deduped) == 2
    assert a.work_key == b.work_key


def test_W3P02_T7_create_run_idempotency(db) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    now = datetime.utcnow()
    key = _det_hex(32)
    run1, created1 = orch.create_or_get_weekly_run(
        db,
        models,
        logical_run_key=key,
        schedule_key=orch.WEEKLY_ORCHESTRATOR_SCHEDULE_KEY,
        trigger_type="MANUAL",
        planned_window_start=now,
        planned_window_end=now + timedelta(days=7),
        source_scope="{}",
        domain_scope="{}",
        gap_scope="{}",
        source_scope_hash=_det_hex(32),
        domain_scope_hash=_det_hex(32),
        gap_scope_hash=_det_hex(32),
        config_version="w3p02-v1",
        config_hash=_det_hex(32),
    )
    assert created1 is True
    run2, created2 = orch.create_or_get_weekly_run(
        db,
        models,
        logical_run_key=key,
        schedule_key=run1.schedule_key,
        trigger_type=run1.trigger_type,
        planned_window_start=run1.planned_window_start,
        planned_window_end=run1.planned_window_end,
        source_scope=run1.source_scope,
        domain_scope=run1.domain_scope,
        gap_scope=run1.gap_scope,
        source_scope_hash=run1.source_scope_hash,
        domain_scope_hash=run1.domain_scope_hash,
        gap_scope_hash=run1.gap_scope_hash,
        config_version=run1.config_version,
        config_hash=run1.config_hash,
    )
    assert created2 is False
    assert run2.id == run1.id
    with pytest.raises(orch.WeeklyOrchestratorError, match="LOGICAL_RUN_KEY_PAYLOAD_MISMATCH"):
        orch.create_or_get_weekly_run(
            db,
            models,
            logical_run_key=key,
            schedule_key="other",
            trigger_type="MANUAL",
            planned_window_start=now,
            planned_window_end=now + timedelta(days=7),
            source_scope="{}",
            domain_scope="{}",
            gap_scope="{}",
            source_scope_hash=run1.source_scope_hash,
            domain_scope_hash=run1.domain_scope_hash,
            gap_scope_hash=run1.gap_scope_hash,
            config_version="w3p02-v1",
            config_hash=run1.config_hash,
        )


def test_W3P02_T8_attempt_transitions_and_invalid(db) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    now = datetime.utcnow()
    run, _ = orch.create_or_get_weekly_run(
        db,
        models,
        logical_run_key=_det_hex(32),
        schedule_key=orch.WEEKLY_ORCHESTRATOR_SCHEDULE_KEY,
        trigger_type="MANUAL",
        planned_window_start=now,
        planned_window_end=now + timedelta(days=7),
        source_scope="{}",
        domain_scope="{}",
        gap_scope="{}",
        source_scope_hash=_det_hex(32),
        domain_scope_hash=_det_hex(32),
        gap_scope_hash=_det_hex(32),
        config_version="w3p02-v1",
        config_hash=_det_hex(32),
    )
    attempt = orch.create_attempt(db, models, run=run)
    assert attempt.status == "CREATED"
    orch.start_attempt(db, attempt)
    assert attempt.status == "RUNNING"
    with pytest.raises(orch.WeeklyOrchestratorError, match="INVALID_ATTEMPT_TRANSITION"):
        orch.transition_attempt_status("RUNNING", "CREATED")
    with pytest.raises(orch.WeeklyOrchestratorError, match="INVALID_ATTEMPT_TRANSITION"):
        orch.transition_attempt_status("COMPLETED", "RUNNING")


def test_W3P02_T9_retry_after_failure(db) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    now = datetime.utcnow()
    run, _ = orch.create_or_get_weekly_run(
        db,
        models,
        logical_run_key=_det_hex(32),
        schedule_key=orch.WEEKLY_ORCHESTRATOR_SCHEDULE_KEY,
        trigger_type="MANUAL",
        planned_window_start=now,
        planned_window_end=now + timedelta(days=7),
        source_scope="{}",
        domain_scope="{}",
        gap_scope="{}",
        source_scope_hash=_det_hex(32),
        domain_scope_hash=_det_hex(32),
        gap_scope_hash=_det_hex(32),
        config_version="w3p02-v1",
        config_hash=_det_hex(32),
    )
    a1 = orch.create_attempt(db, models, run=run)
    orch.start_attempt(db, a1)
    a1.status = "FAILED"
    a1.completed_at = datetime.utcnow()
    db.flush()
    a2 = orch.create_attempt(db, models, run=run, retry_of_attempt_id=a1.id)
    assert a2.attempt_number == 2
    assert a2.retry_of_attempt_id == a1.id
    # Successful terminal blocks further retry.
    a2.status = "COMPLETED"
    a2.completed_at = datetime.utcnow()
    db.flush()
    with pytest.raises(orch.WeeklyOrchestratorError, match="RETRY_AFTER_SUCCESSFUL_TERMINAL"):
        orch.create_attempt(db, models, run=run, retry_of_attempt_id=a2.id)


def test_W3P02_T10_source_result_lifecycle(db) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    gsp = _build_gsp(db)
    now = datetime.utcnow()
    run, _ = orch.create_or_get_weekly_run(
        db,
        models,
        logical_run_key=_det_hex(32),
        schedule_key=orch.WEEKLY_ORCHESTRATOR_SCHEDULE_KEY,
        trigger_type="MANUAL",
        planned_window_start=now,
        planned_window_end=now + timedelta(days=7),
        source_scope="{}",
        domain_scope="{}",
        gap_scope="{}",
        source_scope_hash=_det_hex(32),
        domain_scope_hash=_det_hex(32),
        gap_scope_hash=_det_hex(32),
        config_version="w3p02-v1",
        config_hash=_det_hex(32),
    )
    attempt = orch.create_attempt(db, models, run=run)
    row, created = orch.record_source_result(
        db,
        models,
        attempt_id=attempt.id,
        source_profile_id=gsp.id,
        result_status="EXTRACTED",
        fetch_outcome="FIXTURE",
        extraction_outcome="CANDIDATE_ONLY",
    )
    assert created is True
    row2, created2 = orch.record_source_result(
        db,
        models,
        attempt_id=attempt.id,
        source_profile_id=gsp.id,
        result_status="FAILED",
    )
    assert created2 is False
    assert row2.id == row.id
    assert row2.result_status == "EXTRACTED"


def test_W3P02_T11_gap_result_lifecycle(db) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    gap = _build_gap(db)
    now = datetime.utcnow()
    run, _ = orch.create_or_get_weekly_run(
        db,
        models,
        logical_run_key=_det_hex(32),
        schedule_key=orch.WEEKLY_ORCHESTRATOR_SCHEDULE_KEY,
        trigger_type="MANUAL",
        planned_window_start=now,
        planned_window_end=now + timedelta(days=7),
        source_scope="{}",
        domain_scope="{}",
        gap_scope="{}",
        source_scope_hash=_det_hex(32),
        domain_scope_hash=_det_hex(32),
        gap_scope_hash=_det_hex(32),
        config_version="w3p02-v1",
        config_hash=_det_hex(32),
    )
    attempt = orch.create_attempt(db, models, run=run)
    row, created = orch.record_gap_result(
        db,
        models,
        attempt_id=attempt.id,
        gap_id=gap.id,
        result_type="DISCOVERED",
        previous_status="OPEN",
        new_status="OPEN",
    )
    assert created is True
    row2, created2 = orch.record_gap_result(
        db,
        models,
        attempt_id=attempt.id,
        gap_id=gap.id,
        result_type="UPDATED",
    )
    assert created2 is False
    assert row2.result_type == "DISCOVERED"
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            bad = models.WeeklyRunGapResult(
                attempt_id=attempt.id,
                gap_id=999999,
                result_type="DISCOVERED",
            )
            db.add(bad)
            db.flush()


@pytest.mark.parametrize("case_id", ["partial", "full_failure", "no_eligible"])
def test_W3P02_T12_partial_full_no_eligible(db, case_id: str) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    if case_id == "no_eligible":
        outcome = orch.orchestrate_weekly_run(
            db,
            models,
            candidates=[
                _ok_candidate(
                    source_profile_id=1,
                    registry_state="DISCOVERED",
                    runtime_eligibility="NOT_ELIGIBLE",
                )
            ],
            transports={},
            dry_run=True,
            persist_ledger=True,
            logical_run_key=_det_hex(32),
        )
        # No GSP row → skipped not persisted; total_sources may be 0.
        assert outcome.outcome in {"NO_ELIGIBLE_SOURCES", "NO_MATERIAL_CHANGE"}
        assert outcome.network_executed is False
        return

    gsp_ok = _build_gsp(db)
    gsp_bad = _build_gsp(db)
    if case_id == "partial":
        candidates = [
            _ok_candidate(
                source_profile_id=gsp_ok.id,
                url="https://example.org/ok",
            ),
            _ok_candidate(
                source_profile_id=gsp_bad.id,
                url="https://example.org/bad",
                rights_terms_state="UNKNOWN",
            ),
        ]
        transports = {gsp_ok.id: _transport()}
        expected = "PARTIAL_SUCCESS"
    else:
        candidates = [
            _ok_candidate(
                source_profile_id=gsp_bad.id,
                url="https://example.org/bad",
                adapter_mode="NOT_A_MODE",
            )
        ]
        transports = {}
        expected = "FULL_FAILURE"
    outcome = orch.orchestrate_weekly_run(
        db,
        models,
        candidates=candidates,
        transports=transports,
        dry_run=True,
        persist_ledger=True,
        logical_run_key=_det_hex(32),
    )
    assert outcome.outcome == expected
    assert outcome.run_id is not None
    assert outcome.attempt_id is not None
    if case_id == "partial":
        statuses = {r["result_status"] for r in outcome.source_results}
        assert "EXTRACTED" in statuses
        assert "BLOCKED" in statuses or "FAILED" in statuses


def test_W3P02_T13_handoff_prepare_only(db) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    gsp = _build_gsp(db)
    outcome = orch.orchestrate_weekly_run(
        db,
        models,
        candidates=[_ok_candidate(source_profile_id=gsp.id)],
        transports={gsp.id: _transport()},
        dry_run=True,
        persist_ledger=True,
        logical_run_key=_det_hex(32),
    )
    kinds = {h.handoff_kind for h in outcome.handoffs}
    assert "RAW_EVIDENCE" in kinds
    assert "PROVENANCE" in kinds
    assert "CANDIDATE" in kinds
    assert all(h.execute is False for h in outcome.handoffs)
    assert all(h.payload.get("approved_knowledge") is not True for h in outcome.handoffs)
    assert all(h.payload.get("execute") is False for h in outcome.handoffs)


def test_W3P02_T14_dry_run_no_activation_no_production_write() -> None:
    outcome = orch.orchestrate_weekly_run(
        None,
        None,
        candidates=[_ok_candidate(source_profile_id=1)],
        transports={1: _transport()},
        dry_run=True,
        persist_ledger=False,
        logical_run_key=_det_hex(32),
    )
    assert outcome.production_write is False
    assert outcome.network_executed is False
    assert outcome.activation_enabled is False
    assert outcome.scheduler_activation is False
    assert all(h.execute is False for h in outcome.handoffs)
    assert outcome.outcome in {"FULL_SUCCESS", "PARTIAL_SUCCESS", "NO_MATERIAL_CHANGE"}


def test_W3P02_T15_source_fk_invalid(db) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    now = datetime.utcnow()
    run, _ = orch.create_or_get_weekly_run(
        db,
        models,
        logical_run_key=_det_hex(32),
        schedule_key=orch.WEEKLY_ORCHESTRATOR_SCHEDULE_KEY,
        trigger_type="MANUAL",
        planned_window_start=now,
        planned_window_end=now + timedelta(days=7),
        source_scope="{}",
        domain_scope="{}",
        gap_scope="{}",
        source_scope_hash=_det_hex(32),
        domain_scope_hash=_det_hex(32),
        gap_scope_hash=_det_hex(32),
        config_version="w3p02-v1",
        config_hash=_det_hex(32),
    )
    attempt = orch.create_attempt(db, models, run=run)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            orch.record_source_result(
                db,
                models,
                attempt_id=attempt.id,
                source_profile_id=999999,
                result_status="CHECKED",
            )
