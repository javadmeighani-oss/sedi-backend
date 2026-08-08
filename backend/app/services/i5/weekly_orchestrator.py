"""I5-IMPL-W3-P02/W6-P01 — weekly orchestrator.

Owns run/attempt/source-result/gap-result ledger wiring against W1-P01 models,
discovery invocation, adapter resolution reuse, and prepare-only handoffs to
W1-P02 raw/provenance surfaces.

Controlled live network (W6-P01) is fail-closed behind TWO independent env
flags (`SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED` AND `SEDI_I5_SOURCE_ACTIVATION_ENABLED`).
`orchestrate_weekly_run(..., enforce_activation_off=True)` (the W3-P02 /
W6-P02 offline-E2E default) is fixture-only and unchanged. Only the explicit
`live_network=True` path (reached via `run_controlled_scheduled_tick` /
`run_controlled_live_orchestration`, or a direct authorized caller that also
passes `enforce_activation_off=False`) performs a real HTTPS fetch, and only
through `PublicWebFetchAdapter.fetch_live`.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional, Sequence

from backend.app.services.i5 import source_discovery as discovery
from backend.app.services.i5.adapters.base import (
    AdapterFrameworkError,
    FixtureTransportResponse,
    default_registry,
)
from backend.app.services.i5.adapters.live_transport import HttpGet
from backend.app.services.i5.enums import (
    RunGapResultType,
    RunSourceResultStatus,
    WeeklyRunAttemptStatus,
    WeeklyRunApprovalState,
    WeeklyRunStatus,
    WeeklyRunTriggerType,
    WeeklyRunType,
)
from backend.app.services.i5.metrics import (
    PACKAGE_ID as METRICS_PACKAGE_ID,
    build_aa_metrics_from_run_counters,
    observe_weekly_run_metrics,
)
from backend.app.services.i5.source_discovery import (
    DiscoveryPlan,
    DiscoveryWorkItem,
    SourceCandidateDescriptor,
    plan_discovery,
)

PACKAGE_ID = "I5-IMPL-W3-P02"
MANAGEMENT_ALIAS = "P07"
PACKAGE_TITLE = discovery.PACKAGE_TITLE

# Dormant activation flag — default false; W3-P02 must not set true.
WEEKLY_ORCHESTRATOR_ENABLE_ENV = "SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED"
WEEKLY_ORCHESTRATOR_JOB_ID = "weekly_international_knowledge_crawler"
WEEKLY_ORCHESTRATOR_SCHEDULE_KEY = "weekly_international_knowledge_crawler"
SOURCE_ACTIVATION_ENV = "SEDI_I5_SOURCE_ACTIVATION_ENABLED"
CONTROLLED_NETWORK_OWNED_BY = "I5-IMPL-W6-P01"
RAW_PROVENANCE_OWNED_BY = "I5-IMPL-W1-P02"

RUN_TERMINAL = frozenset(
    {
        WeeklyRunStatus.COMPLETED.value,
        WeeklyRunStatus.COMPLETED_WITH_WARNINGS.value,
        WeeklyRunStatus.FAILED.value,
        WeeklyRunStatus.CANCELLED.value,
        WeeklyRunStatus.SUPERSEDED.value,
    }
)
ATTEMPT_TERMINAL = frozenset(
    {
        WeeklyRunAttemptStatus.COMPLETED.value,
        WeeklyRunAttemptStatus.COMPLETED_WITH_WARNINGS.value,
        WeeklyRunAttemptStatus.FAILED.value,
        WeeklyRunAttemptStatus.CANCELLED.value,
        WeeklyRunAttemptStatus.SUPERSEDED.value,
        WeeklyRunAttemptStatus.BLOCKED.value,
        WeeklyRunAttemptStatus.DEFERRED.value,
    }
)
ATTEMPT_SUCCESS_TERMINAL = frozenset(
    {
        WeeklyRunAttemptStatus.COMPLETED.value,
        WeeklyRunAttemptStatus.COMPLETED_WITH_WARNINGS.value,
    }
)

# Authority-frozen transition matrix (W1-P01 vocabularies; service-enforced).
ATTEMPT_ALLOWED_TRANSITIONS: Mapping[str, frozenset[str]] = {
    WeeklyRunAttemptStatus.CREATED.value: frozenset(
        {
            WeeklyRunAttemptStatus.STARTED.value,
            WeeklyRunAttemptStatus.CANCELLED.value,
            WeeklyRunAttemptStatus.BLOCKED.value,
            WeeklyRunAttemptStatus.DEFERRED.value,
        }
    ),
    WeeklyRunAttemptStatus.STARTED.value: frozenset(
        {
            WeeklyRunAttemptStatus.RUNNING.value,
            WeeklyRunAttemptStatus.FAILED.value,
            WeeklyRunAttemptStatus.CANCELLED.value,
            WeeklyRunAttemptStatus.BLOCKED.value,
        }
    ),
    WeeklyRunAttemptStatus.RUNNING.value: frozenset(
        {
            WeeklyRunAttemptStatus.COMPLETED.value,
            WeeklyRunAttemptStatus.COMPLETED_WITH_WARNINGS.value,
            WeeklyRunAttemptStatus.FAILED.value,
            WeeklyRunAttemptStatus.BLOCKED.value,
            WeeklyRunAttemptStatus.DEFERRED.value,
            WeeklyRunAttemptStatus.CANCELLED.value,
        }
    ),
}


class WeeklyOrchestratorError(ValueError):
    """Fail-closed orchestrator error."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        message = code if not detail else f"{code}:{detail}"
        super().__init__(message)


@dataclass
class HandoffRequest:
    """Prepare-only write request — execution owned by W1-P02 / later Gates."""

    handoff_kind: str
    request_key: str
    payload: dict[str, Any]
    execute: bool = False


@dataclass
class OrchestrationOutcome:
    outcome: str
    run_id: Optional[int] = None
    attempt_id: Optional[int] = None
    logical_run_key: Optional[str] = None
    source_results: list[dict[str, Any]] = field(default_factory=list)
    gap_results: list[dict[str, Any]] = field(default_factory=list)
    handoffs: list[HandoffRequest] = field(default_factory=list)
    discovery: Optional[DiscoveryPlan] = None
    activation_enabled: bool = False
    scheduler_activation: bool = False
    production_write: bool = False
    network_executed: bool = False
    detail: str = ""
    # W6-P03 observability only — does not alter crawler/governance decisions.
    aa_metrics: dict[str, float] = field(default_factory=dict)
    alert_decisions: list[dict[str, Any]] = field(default_factory=list)


def utc_now() -> datetime:
    return datetime.utcnow()


def weekly_orchestrator_enabled() -> bool:
    return os.environ.get(WEEKLY_ORCHESTRATOR_ENABLE_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def source_activation_enabled() -> bool:
    return os.environ.get(SOURCE_ACTIVATION_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def assert_activation_off_contract() -> None:
    """W3-P02 closure requires activation-off evidence; enabling is W6-P01."""
    if weekly_orchestrator_enabled():
        raise WeeklyOrchestratorError(
            "ACTIVATION_NOT_AUTHORIZED_IN_W3_P02",
            WEEKLY_ORCHESTRATOR_ENABLE_ENV,
        )
    if source_activation_enabled():
        raise WeeklyOrchestratorError(
            "SOURCE_ACTIVATION_NOT_AUTHORIZED_IN_W3_P02",
            SOURCE_ACTIVATION_ENV,
        )


def run_dormant_scheduled_tick(
    db: Any = None,
    models: Any = None,
    *,
    candidates: Optional[Sequence[SourceCandidateDescriptor]] = None,
    persist_ledger: bool = False,
    live_http_get: Optional[HttpGet] = None,
) -> OrchestrationOutcome:
    """Scheduler entrypoint. W6-P01 fail-closed two-flag activation ladder:

    1. `SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED` off -> DORMANT_NO_OP (no I/O).
    2. weekly ON, `SEDI_I5_SOURCE_ACTIVATION_ENABLED` off -> SOURCE_ACTIVATION_DISABLED
       (no I/O). One flag alone is never sufficient to reach the network.
    3. Both ON -> `run_controlled_scheduled_tick` (only path that may touch a socket).
    """
    if not weekly_orchestrator_enabled():
        return OrchestrationOutcome(
            outcome="DORMANT_NO_OP",
            activation_enabled=False,
            scheduler_activation=False,
            production_write=False,
            network_executed=False,
            detail="weekly orchestrator activation off",
        )
    if not source_activation_enabled():
        return OrchestrationOutcome(
            outcome="SOURCE_ACTIVATION_DISABLED",
            activation_enabled=True,
            scheduler_activation=False,
            production_write=False,
            network_executed=False,
            detail=f"weekly orchestrator on but {SOURCE_ACTIVATION_ENV} off",
        )
    return run_controlled_scheduled_tick(
        db,
        models,
        candidates=candidates,
        persist_ledger=persist_ledger,
        live_http_get=live_http_get,
    )


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_logical_run_key(
    *,
    schedule_key: str,
    planned_window_start: datetime,
    planned_window_end: datetime,
    source_scope_hash: str,
    domain_scope_hash: str,
    gap_scope_hash: str,
    config_hash: str,
) -> str:
    material = "|".join(
        [
            schedule_key,
            planned_window_start.isoformat(),
            planned_window_end.isoformat(),
            source_scope_hash,
            domain_scope_hash,
            gap_scope_hash,
            config_hash,
        ]
    )
    return _sha256_hex(material)


def transition_attempt_status(current: str, target: str) -> str:
    allowed = ATTEMPT_ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise WeeklyOrchestratorError(
            "INVALID_ATTEMPT_TRANSITION",
            f"{current}->{target}",
        )
    return target


def classify_run_outcome(
    *,
    total_sources: int,
    failed_sources: int,
    blocked_sources: int,
    skipped_sources: int,
    warning_count: int,
    extracted_or_fetched: int,
) -> str:
    """Partial-failure aware terminal classification (frozen vocabularies)."""
    if total_sources == 0:
        return "NO_ELIGIBLE_SOURCES"
    if blocked_sources == total_sources:
        return "GOVERNANCE_BLOCKED"
    if failed_sources == total_sources:
        return "FULL_FAILURE"
    if extracted_or_fetched == 0 and failed_sources == 0 and blocked_sources == 0:
        if skipped_sources == total_sources:
            return "NO_MATERIAL_CHANGE"
        return "NO_MATERIAL_CHANGE"
    if failed_sources > 0 or blocked_sources > 0 or warning_count > 0:
        if extracted_or_fetched > 0:
            return "PARTIAL_SUCCESS"
        return "FULL_FAILURE"
    return "FULL_SUCCESS"


def map_outcome_to_attempt_status(outcome: str) -> str:
    return {
        "FULL_SUCCESS": WeeklyRunAttemptStatus.COMPLETED.value,
        "PARTIAL_SUCCESS": WeeklyRunAttemptStatus.COMPLETED_WITH_WARNINGS.value,
        "NO_MATERIAL_CHANGE": WeeklyRunAttemptStatus.COMPLETED.value,
        "NO_ELIGIBLE_SOURCES": WeeklyRunAttemptStatus.COMPLETED.value,
        "GOVERNANCE_BLOCKED": WeeklyRunAttemptStatus.BLOCKED.value,
        "FULL_FAILURE": WeeklyRunAttemptStatus.FAILED.value,
    }.get(outcome, WeeklyRunAttemptStatus.FAILED.value)


def map_outcome_to_run_status(outcome: str) -> str:
    return {
        "FULL_SUCCESS": WeeklyRunStatus.COMPLETED.value,
        "PARTIAL_SUCCESS": WeeklyRunStatus.COMPLETED_WITH_WARNINGS.value,
        "NO_MATERIAL_CHANGE": WeeklyRunStatus.COMPLETED.value,
        "NO_ELIGIBLE_SOURCES": WeeklyRunStatus.COMPLETED.value,
        "GOVERNANCE_BLOCKED": WeeklyRunStatus.BLOCKED.value,
        "FULL_FAILURE": WeeklyRunStatus.FAILED.value,
    }.get(outcome, WeeklyRunStatus.FAILED.value)


def map_discovery_error_to_source_status(category: str) -> str:
    if category in {
        "GOVERNANCE_BLOCKED",
        "ROBOTS_BLOCKED",
        "TERMS_BLOCKED",
        "UNSAFE_URL",
    }:
        return RunSourceResultStatus.BLOCKED.value
    if category == "NO_MATERIAL_CHANGE":
        return RunSourceResultStatus.SKIPPED.value
    return RunSourceResultStatus.FAILED.value


def prepare_raw_evidence_handoff(
    *,
    attempt_id: int,
    work: DiscoveryWorkItem,
    content_sha256: str,
    dry_run: bool,
) -> HandoffRequest:
    key = _sha256_hex(f"raw|{attempt_id}|{work.work_key}|{content_sha256}")
    return HandoffRequest(
        handoff_kind="RAW_EVIDENCE",
        request_key=key,
        payload={
            "owner_package": RAW_PROVENANCE_OWNED_BY,
            "attempt_id": attempt_id,
            "source_profile_id": work.source_profile_id,
            "adapter_id": work.adapter_id,
            "adapter_version": work.adapter_version,
            "canonical_url": work.canonical_url,
            "content_sha256": content_sha256,
            "execute": False,
            "dry_run": dry_run,
        },
        execute=False,
    )


def prepare_provenance_handoff(
    *,
    attempt_id: int,
    work: DiscoveryWorkItem,
    raw_request_key: str,
    dry_run: bool,
) -> HandoffRequest:
    key = _sha256_hex(f"prov|{attempt_id}|{work.work_key}|{raw_request_key}")
    return HandoffRequest(
        handoff_kind="PROVENANCE",
        request_key=key,
        payload={
            "owner_package": RAW_PROVENANCE_OWNED_BY,
            "attempt_id": attempt_id,
            "source_profile_id": work.source_profile_id,
            "raw_evidence_request_key": raw_request_key,
            "execute": False,
            "dry_run": dry_run,
        },
        execute=False,
    )


def prepare_candidate_handoff(
    *,
    attempt_id: int,
    work: DiscoveryWorkItem,
    candidate_fingerprint: str,
    dry_run: bool,
) -> HandoffRequest:
    key = _sha256_hex(f"cand|{attempt_id}|{work.work_key}|{candidate_fingerprint}")
    return HandoffRequest(
        handoff_kind="CANDIDATE",
        request_key=key,
        payload={
            "owner_package": "I5-IMPL-W3-P01",
            "attempt_id": attempt_id,
            "source_profile_id": work.source_profile_id,
            "adapter_id": work.adapter_id,
            "candidate_fingerprint": candidate_fingerprint,
            "approved_knowledge": False,
            "execute": False,
            "dry_run": dry_run,
        },
        execute=False,
    )


def create_or_get_weekly_run(
    db,
    models,
    *,
    logical_run_key: str,
    schedule_key: str,
    trigger_type: str,
    planned_window_start: datetime,
    planned_window_end: datetime,
    source_scope: str,
    domain_scope: str,
    gap_scope: str,
    source_scope_hash: str,
    domain_scope_hash: str,
    gap_scope_hash: str,
    config_version: str,
    config_hash: str,
    approval_state: str = WeeklyRunApprovalState.NOT_REQUIRED.value,
    status: str = WeeklyRunStatus.PLANNED.value,
):
    """Idempotent run create on logical_run_key; mismatch fails closed."""
    existing = (
        db.query(models.WeeklyKnowledgeRun)
        .filter(models.WeeklyKnowledgeRun.logical_run_key == logical_run_key)
        .one_or_none()
    )
    if existing is not None:
        identity = (
            existing.schedule_key,
            existing.trigger_type,
            existing.source_scope_hash,
            existing.domain_scope_hash,
            existing.gap_scope_hash,
            existing.config_hash,
        )
        incoming = (
            schedule_key,
            trigger_type,
            source_scope_hash,
            domain_scope_hash,
            gap_scope_hash,
            config_hash,
        )
        if identity != incoming:
            raise WeeklyOrchestratorError("LOGICAL_RUN_KEY_PAYLOAD_MISMATCH", logical_run_key)
        return existing, False
    run = models.WeeklyKnowledgeRun(
        logical_run_key=logical_run_key,
        canonicalization_version="v1",
        hash_algorithm="SHA-256",
        schedule_key=schedule_key,
        run_type=WeeklyRunType.WEEKLY_GOVERNED.value,
        trigger_type=trigger_type,
        planned_window_start=planned_window_start,
        planned_window_end=planned_window_end,
        approval_state=approval_state,
        source_scope_hash=source_scope_hash,
        domain_scope_hash=domain_scope_hash,
        gap_scope_hash=gap_scope_hash,
        config_version=config_version,
        config_hash=config_hash,
        source_scope=source_scope,
        domain_scope=domain_scope,
        gap_scope=gap_scope,
        status=status,
    )
    db.add(run)
    db.flush()
    return run, True


def create_attempt(
    db,
    models,
    *,
    run,
    retry_of_attempt_id: Optional[int] = None,
    worker_reference: Optional[str] = None,
):
    """Allocate next attempt_number under run; enforce successful-terminal rule."""
    prior_success = (
        db.query(models.WeeklyKnowledgeRunAttempt)
        .filter(models.WeeklyKnowledgeRunAttempt.weekly_run_id == run.id)
        .filter(models.WeeklyKnowledgeRunAttempt.status.in_(tuple(ATTEMPT_SUCCESS_TERMINAL)))
        .first()
    )
    if prior_success is not None and retry_of_attempt_id is not None:
        raise WeeklyOrchestratorError("RETRY_AFTER_SUCCESSFUL_TERMINAL", str(run.id))
    max_row = (
        db.query(models.WeeklyKnowledgeRunAttempt.attempt_number)
        .filter(models.WeeklyKnowledgeRunAttempt.weekly_run_id == run.id)
        .order_by(models.WeeklyKnowledgeRunAttempt.attempt_number.desc())
        .first()
    )
    next_number = 1 if max_row is None else int(max_row[0]) + 1
    if retry_of_attempt_id is not None:
        parent = (
            db.query(models.WeeklyKnowledgeRunAttempt)
            .filter(models.WeeklyKnowledgeRunAttempt.id == retry_of_attempt_id)
            .filter(models.WeeklyKnowledgeRunAttempt.weekly_run_id == run.id)
            .one_or_none()
        )
        if parent is None:
            raise WeeklyOrchestratorError("RETRY_PARENT_NOT_FOUND", str(retry_of_attempt_id))
        if parent.status in ATTEMPT_SUCCESS_TERMINAL:
            raise WeeklyOrchestratorError("RETRY_OF_SUCCESSFUL_ATTEMPT", str(retry_of_attempt_id))
        if next_number <= parent.attempt_number:
            raise WeeklyOrchestratorError("RETRY_ATTEMPT_NUMBER_INVALID", str(next_number))
    attempt = models.WeeklyKnowledgeRunAttempt(
        weekly_run_id=run.id,
        attempt_number=next_number,
        retry_of_attempt_id=retry_of_attempt_id,
        status=WeeklyRunAttemptStatus.CREATED.value,
        worker_reference=worker_reference,
        canonicalization_version="v1",
        hash_algorithm="SHA-256",
    )
    db.add(attempt)
    db.flush()
    run.latest_attempt_id = attempt.id
    run.status = WeeklyRunStatus.IN_PROGRESS.value
    run.updated_at = utc_now()
    db.flush()
    return attempt


def start_attempt(db, attempt) -> Any:
    transition_attempt_status(attempt.status, WeeklyRunAttemptStatus.STARTED.value)
    attempt.status = WeeklyRunAttemptStatus.STARTED.value
    attempt.started_at = utc_now()
    attempt.updated_at = utc_now()
    db.flush()
    transition_attempt_status(attempt.status, WeeklyRunAttemptStatus.RUNNING.value)
    attempt.status = WeeklyRunAttemptStatus.RUNNING.value
    attempt.updated_at = utc_now()
    db.flush()
    return attempt


def record_source_result(
    db,
    models,
    *,
    attempt_id: int,
    source_profile_id: int,
    result_status: str,
    source_version_id: Optional[int] = None,
    fetch_outcome: Optional[str] = None,
    extraction_outcome: Optional[str] = None,
    failure_code: Optional[str] = None,
    failure_reason: Optional[str] = None,
    evidence_reference: Optional[str] = None,
    content_fingerprint: Optional[str] = None,
    knowledge_new_count: int = 0,
    gap_created_count: int = 0,
    warning_count: int = 0,
    error_count: int = 0,
):
    if result_status not in {s.value for s in RunSourceResultStatus}:
        raise WeeklyOrchestratorError("INVALID_SOURCE_RESULT_STATUS", result_status)
    existing = (
        db.query(models.WeeklyRunSourceResult)
        .filter(models.WeeklyRunSourceResult.attempt_id == attempt_id)
        .filter(models.WeeklyRunSourceResult.source_profile_id == source_profile_id)
        .one_or_none()
    )
    if existing is not None:
        return existing, False
    row = models.WeeklyRunSourceResult(
        attempt_id=attempt_id,
        source_profile_id=source_profile_id,
        source_version_id=source_version_id,
        result_status=result_status,
        checked_at=utc_now(),
        fetch_outcome=fetch_outcome,
        extraction_outcome=extraction_outcome,
        failure_code=failure_code,
        failure_reason=failure_reason,
        evidence_reference=evidence_reference,
        content_fingerprint=content_fingerprint,
        knowledge_new_count=knowledge_new_count,
        gap_created_count=gap_created_count,
        warning_count=warning_count,
        error_count=error_count,
    )
    db.add(row)
    db.flush()
    return row, True


def record_gap_result(
    db,
    models,
    *,
    attempt_id: int,
    gap_id: int,
    result_type: str,
    previous_status: Optional[str] = None,
    new_status: Optional[str] = None,
    evidence_reference: Optional[str] = None,
):
    if result_type not in {s.value for s in RunGapResultType}:
        raise WeeklyOrchestratorError("INVALID_GAP_RESULT_TYPE", result_type)
    existing = (
        db.query(models.WeeklyRunGapResult)
        .filter(models.WeeklyRunGapResult.attempt_id == attempt_id)
        .filter(models.WeeklyRunGapResult.gap_id == gap_id)
        .one_or_none()
    )
    if existing is not None:
        return existing, False
    row = models.WeeklyRunGapResult(
        attempt_id=attempt_id,
        gap_id=gap_id,
        result_type=result_type,
        previous_status=previous_status,
        new_status=new_status,
        evidence_reference=evidence_reference,
    )
    db.add(row)
    db.flush()
    return row, True


def _apply_fixture_source(
    *,
    work: DiscoveryWorkItem,
    transports: Mapping[int, FixtureTransportResponse],
) -> tuple[str, Optional[str], list[HandoffRequest]]:
    """Deterministic fixture path — never opens a network socket."""
    handoffs: list[HandoffRequest] = []
    transport = transports.get(work.source_profile_id)
    if transport is None:
        return RunSourceResultStatus.FAILED.value, "FIXTURE_TRANSPORT_MISSING", handoffs
    registry = default_registry()
    adapter = registry.get(work.adapter_id)

    def _transport(_url: str) -> FixtureTransportResponse:
        return transport

    try:
        envelope = adapter.fetch_fixture(
            request_id=work.work_key[:32],
            url=work.canonical_url,
            transport=_transport,
            governance=work.governance,
        )
    except AdapterFrameworkError as exc:
        return map_discovery_error_to_source_status(exc.category), exc.category, handoffs
    if envelope.error_category == "NO_MATERIAL_CHANGE" or int(envelope.http_status or 0) == 304:
        return RunSourceResultStatus.SKIPPED.value, "NO_MATERIAL_CHANGE", handoffs
    if envelope.error_category:
        return (
            map_discovery_error_to_source_status(envelope.error_category),
            envelope.error_category,
            handoffs,
        )
    body = envelope.body or b""
    content_sha = hashlib.sha256(body).hexdigest()
    raw = prepare_raw_evidence_handoff(
        attempt_id=0,
        work=work,
        content_sha256=content_sha,
        dry_run=True,
    )
    prov = prepare_provenance_handoff(
        attempt_id=0,
        work=work,
        raw_request_key=raw.request_key,
        dry_run=True,
    )
    cand = prepare_candidate_handoff(
        attempt_id=0,
        work=work,
        candidate_fingerprint=content_sha,
        dry_run=True,
    )
    handoffs.extend([raw, prov, cand])
    return RunSourceResultStatus.EXTRACTED.value, None, handoffs


def _apply_live_source(
    *,
    work: DiscoveryWorkItem,
    trust_level: str = "official",
    review_required: bool = True,
    max_bytes: int = 2_097_152,
    timeout: int = 15,
    http_get: Optional[HttpGet] = None,
) -> tuple[str, Optional[str], list[HandoffRequest]]:
    """Controlled live path (W6-P01) — same shape/handoffs as `_apply_fixture_source`
    but performs (or, under test, simulates via injected `http_get`) a real HTTPS
    fetch through the resolved adapter's `fetch_live`. Only adapters that expose
    `fetch_live` (currently `PublicWebFetchAdapter`) support this path; any other
    adapter mode fails closed rather than silently falling back to a fixture.
    """
    handoffs: list[HandoffRequest] = []
    registry = default_registry()
    adapter = registry.get(work.adapter_id)
    fetch_live = getattr(adapter, "fetch_live", None)
    if fetch_live is None:
        return RunSourceResultStatus.FAILED.value, "LIVE_ADAPTER_UNSUPPORTED", handoffs
    try:
        envelope = fetch_live(
            request_id=work.work_key[:32],
            url=work.canonical_url,
            governance=work.governance,
            max_bytes=max_bytes,
            timeout=timeout,
            trust_level=trust_level,
            review_required=review_required,
            http_get=http_get,
        )
    except AdapterFrameworkError as exc:
        return map_discovery_error_to_source_status(exc.category), exc.category, handoffs
    if envelope.error_category == "NO_MATERIAL_CHANGE" or int(envelope.http_status or 0) == 304:
        return RunSourceResultStatus.SKIPPED.value, "NO_MATERIAL_CHANGE", handoffs
    if envelope.error_category:
        return (
            map_discovery_error_to_source_status(envelope.error_category),
            envelope.error_category,
            handoffs,
        )
    body = envelope.body or b""
    content_sha = hashlib.sha256(body).hexdigest()
    raw = prepare_raw_evidence_handoff(
        attempt_id=0,
        work=work,
        content_sha256=content_sha,
        dry_run=True,
    )
    prov = prepare_provenance_handoff(
        attempt_id=0,
        work=work,
        raw_request_key=raw.request_key,
        dry_run=True,
    )
    cand = prepare_candidate_handoff(
        attempt_id=0,
        work=work,
        candidate_fingerprint=content_sha,
        dry_run=True,
    )
    handoffs.extend([raw, prov, cand])
    return RunSourceResultStatus.EXTRACTED.value, None, handoffs


def finalize_attempt_counters(attempt, source_rows: Sequence[Any]) -> None:
    attempt.total_sources = len(source_rows)
    attempt.checked_sources = sum(
        1 for r in source_rows if r.result_status != RunSourceResultStatus.SKIPPED.value
    )
    attempt.fetched_sources = sum(
        1
        for r in source_rows
        if r.result_status
        in {
            RunSourceResultStatus.FETCHED.value,
            RunSourceResultStatus.EXTRACTED.value,
            RunSourceResultStatus.PUBLISHED.value,
        }
    )
    attempt.skipped_sources = sum(
        1 for r in source_rows if r.result_status == RunSourceResultStatus.SKIPPED.value
    )
    attempt.blocked_sources = sum(
        1 for r in source_rows if r.result_status == RunSourceResultStatus.BLOCKED.value
    )
    attempt.failed_sources = sum(
        1 for r in source_rows if r.result_status == RunSourceResultStatus.FAILED.value
    )
    attempt.warning_count = sum(int(r.warning_count or 0) for r in source_rows)
    attempt.error_count = sum(int(r.error_count or 0) for r in source_rows)
    attempt.created_gap_count = sum(int(r.gap_created_count or 0) for r in source_rows)


def _count_source_statuses(source_rows: Sequence[Any]) -> dict[str, int]:
    """Count source result statuses from ORM rows or dry-unit summary dicts."""
    def _status(row: Any) -> str:
        if isinstance(row, Mapping):
            return str(row.get("result_status") or "")
        return str(getattr(row, "result_status", "") or "")

    statuses = [_status(r) for r in source_rows]
    checked = sum(1 for s in statuses if s != RunSourceResultStatus.SKIPPED.value)
    failed = sum(1 for s in statuses if s == RunSourceResultStatus.FAILED.value)
    blocked = sum(1 for s in statuses if s == RunSourceResultStatus.BLOCKED.value)
    return {
        "total": len(statuses),
        "checked": checked,
        "failed": failed,
        "blocked": blocked,
    }


def emit_post_run_aa_observability(
    *,
    logical_run_key: Optional[str],
    outcome: str,
    dry_run: bool,
    source_rows: Sequence[Any],
    gap_results: Sequence[Any] = (),
    new_knowledge_count: int = 0,
    updated_knowledge_count: int = 0,
    superseded_knowledge_count: int = 0,
    rejected_knowledge_count: int = 0,
    resolved_gap_count: int = 0,
    high_risk_gaps_remaining: int = 0,
    conflicts: int = 0,
    safety_rejections: int = 0,
    run_duration: float = 0.0,
    database_write_count: int = 0,
    new_sources: int = 0,
    updated_sources: int = 0,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Emit AA metrics + alerts after orchestration. Does not alter outcome semantics."""
    counts = _count_source_statuses(source_rows)
    closed_gaps = int(resolved_gap_count)
    if not closed_gaps and gap_results:
        closed_gaps = 0
        for g in gap_results:
            result_type = (
                g.get("result_type") if isinstance(g, Mapping) else getattr(g, "result_type", None)
            )
            if result_type == RunGapResultType.RESOLVED.value:
                closed_gaps += 1
    metrics = build_aa_metrics_from_run_counters(
        sources_checked=counts["checked"],
        new_sources=new_sources,
        updated_sources=updated_sources,
        failed_sources=counts["failed"],
        blocked_sources=counts["blocked"],
        new_knowledge_units=new_knowledge_count,
        updated_units=updated_knowledge_count,
        superseded_units=superseded_knowledge_count,
        rejected_units=rejected_knowledge_count,
        knowledge_gaps_closed=closed_gaps,
        high_risk_gaps_remaining=high_risk_gaps_remaining,
        conflicts=conflicts,
        safety_rejections=safety_rejections,
        run_duration=run_duration,
        database_write_count=database_write_count,
        total_sources=counts["total"],
    )
    observed = observe_weekly_run_metrics(
        counters=metrics,
        labels={
            "logical_run_key": logical_run_key or "",
            "outcome": outcome,
            "dry_run": "true" if dry_run else "false",
            "package_id": METRICS_PACKAGE_ID,
        },
    )
    alert_payload = [
        {
            "alert_id": d.alert_id,
            "triggered": d.triggered,
            "reason": d.reason,
        }
        for d in observed["alerts"]
    ]
    return metrics, alert_payload


def orchestrate_weekly_run(
    db,
    models,
    *,
    candidates: Sequence[SourceCandidateDescriptor],
    logical_run_key: Optional[str] = None,
    schedule_key: str = WEEKLY_ORCHESTRATOR_SCHEDULE_KEY,
    trigger_type: str = WeeklyRunTriggerType.MANUAL.value,
    planned_window_start: Optional[datetime] = None,
    planned_window_end: Optional[datetime] = None,
    config_version: str = "w3p02-v1",
    config_hash: Optional[str] = None,
    transports: Optional[Mapping[int, FixtureTransportResponse]] = None,
    gap_bindings: Optional[Sequence[tuple[int, str]]] = None,
    dry_run: bool = True,
    persist_ledger: bool = True,
    enforce_activation_off: bool = True,
    live_network: bool = False,
    live_http_get: Optional[HttpGet] = None,
) -> OrchestrationOutcome:
    """Discovery + ledger orchestration. Default dry_run=True; no production write.

    persist_ledger=True writes run/attempt/source/gap rows to the bound test/app DB
    session. Raw/provenance/candidate handoffs are always prepare-only (execute=False).

    `live_network` defaults to False (fixture-only; unchanged W3-P02/W6-P02
    behavior). Setting it True requires `enforce_activation_off=False` from the
    caller (this function does not itself re-check the env flags — that is the
    job of `run_dormant_scheduled_tick` / `run_controlled_scheduled_tick`) and
    routes eligible sources through `_apply_live_source` (real HTTPS fetch,
    or an injected `live_http_get` fake under test) instead of the fixture path.
    """
    if enforce_activation_off:
        assert_activation_off_contract()
        if live_network:
            raise WeeklyOrchestratorError(
                "LIVE_NETWORK_REQUIRES_ACTIVATION_OFF_FALSE",
                "enforce_activation_off=True cannot be combined with live_network=True",
            )

    start = planned_window_start or utc_now()
    end = planned_window_end or (start + timedelta(days=7))
    source_scope = json.dumps(
        [{"source_profile_id": c.source_profile_id, "adapter_mode": c.adapter_mode} for c in candidates],
        sort_keys=True,
    )
    domain_scope = "{}"
    gap_scope = "{}"
    source_scope_hash = _sha256_hex(source_scope)
    domain_scope_hash = _sha256_hex(domain_scope)
    gap_scope_hash = _sha256_hex(gap_scope)
    cfg_hash = config_hash or _sha256_hex(config_version)
    run_key = logical_run_key or compute_logical_run_key(
        schedule_key=schedule_key,
        planned_window_start=start,
        planned_window_end=end,
        source_scope_hash=source_scope_hash,
        domain_scope_hash=domain_scope_hash,
        gap_scope_hash=gap_scope_hash,
        config_hash=cfg_hash,
    )

    plan = plan_discovery(candidates)
    transports = transports or {}

    if not persist_ledger:
        # Pure dry-unit path: no ORM writes.
        source_summaries: list[dict[str, Any]] = []
        handoffs: list[HandoffRequest] = []
        for item in plan.selected:
            if live_network:
                status, code, item_handoffs = _apply_live_source(work=item, http_get=live_http_get)
            else:
                status, code, item_handoffs = _apply_fixture_source(work=item, transports=transports)
            source_summaries.append(
                {
                    "source_profile_id": item.source_profile_id,
                    "result_status": status,
                    "failure_code": code,
                    "adapter_id": item.adapter_id,
                }
            )
            handoffs.extend(item_handoffs)
        for blocked in plan.blocked:
            source_summaries.append(
                {
                    "source_profile_id": blocked["source_profile_id"],
                    "result_status": RunSourceResultStatus.BLOCKED.value,
                    "failure_code": blocked.get("error_category"),
                }
            )
        for failed in plan.failed:
            source_summaries.append(
                {
                    "source_profile_id": failed["source_profile_id"],
                    "result_status": RunSourceResultStatus.FAILED.value,
                    "failure_code": failed.get("error_category"),
                }
            )
        for skipped in plan.skipped:
            source_summaries.append(
                {
                    "source_profile_id": skipped["source_profile_id"],
                    "result_status": RunSourceResultStatus.SKIPPED.value,
                    "failure_code": skipped.get("reason"),
                }
            )
        extracted = sum(
            1
            for s in source_summaries
            if s["result_status"]
            in {
                RunSourceResultStatus.EXTRACTED.value,
                RunSourceResultStatus.FETCHED.value,
            }
        )
        outcome = classify_run_outcome(
            total_sources=len(source_summaries),
            failed_sources=sum(
                1 for s in source_summaries if s["result_status"] == RunSourceResultStatus.FAILED.value
            ),
            blocked_sources=sum(
                1 for s in source_summaries if s["result_status"] == RunSourceResultStatus.BLOCKED.value
            ),
            skipped_sources=sum(
                1 for s in source_summaries if s["result_status"] == RunSourceResultStatus.SKIPPED.value
            ),
            warning_count=0,
            extracted_or_fetched=extracted,
        )
        aa_metrics, alert_decisions = emit_post_run_aa_observability(
            logical_run_key=run_key,
            outcome=outcome,
            dry_run=True,
            source_rows=source_summaries,
            database_write_count=0,
        )
        return OrchestrationOutcome(
            outcome=outcome,
            logical_run_key=run_key,
            source_results=source_summaries,
            handoffs=handoffs,
            discovery=plan,
            activation_enabled=False,
            scheduler_activation=False,
            production_write=False,
            network_executed=bool(live_network and plan.selected),
            detail="dry_unit_no_ledger_persist",
            aa_metrics=aa_metrics,
            alert_decisions=alert_decisions,
        )

    run, _created = create_or_get_weekly_run(
        db,
        models,
        logical_run_key=run_key,
        schedule_key=schedule_key,
        trigger_type=trigger_type,
        planned_window_start=start,
        planned_window_end=end,
        source_scope=source_scope,
        domain_scope=domain_scope,
        gap_scope=gap_scope,
        source_scope_hash=source_scope_hash,
        domain_scope_hash=domain_scope_hash,
        gap_scope_hash=gap_scope_hash,
        config_version=config_version,
        config_hash=cfg_hash,
    )
    attempt = create_attempt(db, models, run=run, worker_reference=f"{PACKAGE_ID}:orchestrator")
    start_attempt(db, attempt)

    source_rows = []
    handoffs: list[HandoffRequest] = []
    gap_rows = []

    for item in plan.selected:
        if live_network:
            status, code, item_handoffs = _apply_live_source(work=item, http_get=live_http_get)
        else:
            status, code, item_handoffs = _apply_fixture_source(work=item, transports=transports)
        for h in item_handoffs:
            h.payload["attempt_id"] = attempt.id
            h.payload["dry_run"] = dry_run
            # Never execute W1-P02 writes from W3-P02.
            h.execute = False
        handoffs.extend(item_handoffs)
        row, _ = record_source_result(
            db,
            models,
            attempt_id=attempt.id,
            source_profile_id=item.source_profile_id,
            source_version_id=item.source_version_id,
            result_status=status,
            fetch_outcome=(
                None
                if status == RunSourceResultStatus.FAILED.value
                else ("LIVE" if live_network else "FIXTURE")
            ),
            extraction_outcome="CANDIDATE_ONLY"
            if status == RunSourceResultStatus.EXTRACTED.value
            else None,
            failure_code=code,
            failure_reason=code,
            evidence_reference=item.work_key,
            content_fingerprint=item.work_key,
            error_count=1 if status == RunSourceResultStatus.FAILED.value else 0,
        )
        source_rows.append(row)

    for blocked in plan.blocked:
        row, _ = record_source_result(
            db,
            models,
            attempt_id=attempt.id,
            source_profile_id=int(blocked["source_profile_id"]),
            result_status=RunSourceResultStatus.BLOCKED.value,
            failure_code=str(blocked.get("error_category") or "GOVERNANCE_BLOCKED"),
            failure_reason=str(blocked.get("detail") or ""),
            error_count=1,
        )
        source_rows.append(row)

    for failed in plan.failed:
        row, _ = record_source_result(
            db,
            models,
            attempt_id=attempt.id,
            source_profile_id=int(failed["source_profile_id"]),
            result_status=RunSourceResultStatus.FAILED.value,
            failure_code=str(failed.get("error_category") or "FAILED"),
            failure_reason=str(failed.get("detail") or ""),
            error_count=1,
        )
        source_rows.append(row)

    for skipped in plan.skipped:
        # Structurally ineligible sources are recorded as SKIPPED for audit.
        # They require a GSP row when FK is enforced — callers must supply only
        # profiles that exist when persist_ledger=True, or omit skipped from FK path.
        # Here we only record skipped if a matching candidate id exists as GSP in session.
        gsp = (
            db.query(models.GovernedSourceProfile)
            .filter(models.GovernedSourceProfile.id == int(skipped["source_profile_id"]))
            .one_or_none()
        )
        if gsp is None:
            continue
        row, _ = record_source_result(
            db,
            models,
            attempt_id=attempt.id,
            source_profile_id=gsp.id,
            result_status=RunSourceResultStatus.SKIPPED.value,
            failure_code=str(skipped.get("reason") or "NOT_ELIGIBLE"),
        )
        source_rows.append(row)

    for gap_id, result_type in gap_bindings or ():
        grow, _ = record_gap_result(
            db,
            models,
            attempt_id=attempt.id,
            gap_id=gap_id,
            result_type=result_type,
            evidence_reference=f"{PACKAGE_ID}:gap:{gap_id}",
        )
        gap_rows.append(grow)

    finalize_attempt_counters(attempt, source_rows)
    extracted = int(attempt.fetched_sources or 0)
    outcome = classify_run_outcome(
        total_sources=int(attempt.total_sources or 0),
        failed_sources=int(attempt.failed_sources or 0),
        blocked_sources=int(attempt.blocked_sources or 0),
        skipped_sources=int(attempt.skipped_sources or 0),
        warning_count=int(attempt.warning_count or 0),
        extracted_or_fetched=extracted,
    )
    attempt_status = map_outcome_to_attempt_status(outcome)
    # RUNNING -> terminal
    if attempt.status != WeeklyRunAttemptStatus.RUNNING.value:
        raise WeeklyOrchestratorError("ATTEMPT_NOT_RUNNING", attempt.status)
    if attempt_status not in ATTEMPT_ALLOWED_TRANSITIONS[WeeklyRunAttemptStatus.RUNNING.value]:
        raise WeeklyOrchestratorError("INVALID_ATTEMPT_TRANSITION", attempt_status)
    attempt.status = attempt_status
    attempt.completed_at = utc_now()
    attempt.updated_at = utc_now()
    if attempt_status == WeeklyRunAttemptStatus.FAILED.value:
        attempt.failure_code = outcome
        attempt.failure_reason = outcome
    if attempt_status == WeeklyRunAttemptStatus.BLOCKED.value:
        attempt.block_reason = outcome

    run_status = map_outcome_to_run_status(outcome)
    run.status = run_status
    if attempt_status in ATTEMPT_SUCCESS_TERMINAL:
        run.successful_attempt_id = attempt.id
    run.latest_attempt_id = attempt.id
    run.updated_at = utc_now()
    db.flush()

    aa_metrics, alert_decisions = emit_post_run_aa_observability(
        logical_run_key=run.logical_run_key,
        outcome=outcome,
        dry_run=bool(dry_run),
        source_rows=source_rows,
        gap_results=gap_rows,
        new_knowledge_count=int(attempt.new_knowledge_count or 0),
        updated_knowledge_count=int(attempt.updated_knowledge_count or 0),
        superseded_knowledge_count=int(attempt.superseded_knowledge_count or 0),
        rejected_knowledge_count=int(attempt.rejected_knowledge_count or 0),
        resolved_gap_count=int(attempt.resolved_gap_count or 0),
        database_write_count=len(source_rows) + len(gap_rows) + 2,  # run+attempt rows observed
    )

    return OrchestrationOutcome(
        outcome=outcome,
        run_id=run.id,
        attempt_id=attempt.id,
        logical_run_key=run.logical_run_key,
        source_results=[
            {
                "id": r.id,
                "source_profile_id": r.source_profile_id,
                "result_status": r.result_status,
                "failure_code": r.failure_code,
            }
            for r in source_rows
        ],
        gap_results=[
            {
                "id": g.id,
                "gap_id": g.gap_id,
                "result_type": g.result_type,
            }
            for g in gap_rows
        ],
        handoffs=handoffs,
        discovery=plan,
        activation_enabled=False,
        scheduler_activation=False,
        production_write=False,
        network_executed=bool(live_network and plan.selected),
        detail="ledger_persisted_handoffs_prepare_only",
        aa_metrics=aa_metrics,
        alert_decisions=alert_decisions,
    )


def run_controlled_live_orchestration(
    db: Any,
    models: Any,
    *,
    candidates: Sequence[SourceCandidateDescriptor],
    schedule_key: str = WEEKLY_ORCHESTRATOR_SCHEDULE_KEY,
    trigger_type: str = WeeklyRunTriggerType.SCHEDULED.value,
    logical_run_key: Optional[str] = None,
    persist_ledger: bool = False,
    live_http_get: Optional[HttpGet] = None,
) -> OrchestrationOutcome:
    """W6-P01 controlled live orchestration core.

    Does NOT itself re-check `weekly_orchestrator_enabled()` /
    `source_activation_enabled()` — the caller (`run_dormant_scheduled_tick`)
    is the fail-closed gate. This split lets an explicitly authorized manual
    admin action reuse the same controlled-live path with its own db session
    without going through the scheduler tick.

    - No `candidates` -> NO_ELIGIBLE_SOURCES (no discovery/network attempted).
    - `persist_ledger=True` with no `db` -> LIVE_PATH_REQUIRES_DB (fail closed;
      never silently falls back to a dry/no-op run when persistence was asked for).
    - Otherwise delegates to `orchestrate_weekly_run(..., live_network=True,
      enforce_activation_off=False)` and marks the result as activation-driven.
    """
    if not candidates:
        return OrchestrationOutcome(
            outcome="NO_ELIGIBLE_SOURCES",
            activation_enabled=True,
            scheduler_activation=True,
            production_write=False,
            network_executed=False,
            detail="no controlled live source candidates supplied",
        )
    if persist_ledger and db is None:
        return OrchestrationOutcome(
            outcome="LIVE_PATH_REQUIRES_DB",
            activation_enabled=True,
            scheduler_activation=True,
            production_write=False,
            network_executed=False,
            detail="controlled live ledger persistence requires a bound db session",
        )
    outcome = orchestrate_weekly_run(
        db,
        models,
        candidates=candidates,
        schedule_key=schedule_key,
        trigger_type=trigger_type,
        logical_run_key=logical_run_key,
        transports={},
        dry_run=not persist_ledger,
        persist_ledger=persist_ledger,
        enforce_activation_off=False,
        live_network=True,
        live_http_get=live_http_get,
    )
    outcome.activation_enabled = True
    outcome.scheduler_activation = True
    return outcome


def run_controlled_scheduled_tick(
    db: Any = None,
    models: Any = None,
    *,
    candidates: Optional[Sequence[SourceCandidateDescriptor]] = None,
    persist_ledger: bool = False,
    live_http_get: Optional[HttpGet] = None,
) -> OrchestrationOutcome:
    """W6-P01 scheduler-facing controlled-live entrypoint.

    Reached only once both `run_dormant_scheduled_tick` env flags are ON. No
    implicit DB acquisition is attempted here: a bare scheduler tick with no
    `db`/`candidates` supplied is a safe structural NO_ELIGIBLE_SOURCES no-op
    rather than an error, since the scheduler has no admin-selected scope yet.
    """
    return run_controlled_live_orchestration(
        db,
        models,
        candidates=list(candidates or ()),
        persist_ledger=persist_ledger,
        live_http_get=live_http_get,
    )
