"""KNOW-05 weekly orchestration — coverage → source selection → bounded ingestion → ledger."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    WeeklyRunApprovalState,
    WeeklyRunAttemptStatus,
    WeeklyRunStatus,
    WeeklyRunTriggerType,
    WeeklyRunType,
)
from backend.app.services.i5.know05.bounded_ingestion import (
    ingest_clinicaltrials_bounded,
    ingest_pubmed_bounded_or_block,
    ingest_who_catalogue_bounded,
)
from backend.app.services.i5.know05.budgets import plan_bounded_ingestion
from backend.app.services.i5.know05.coverage_engine import ensure_gaps_from_coverage, prioritize_coverage_cells
from backend.app.services.i5.know05.modes import Know05Mode, assert_mode_authorized, production_activation_flags
from backend.app.services.i5.know05.ncbi_identity import load_ncbi_operational_identity
from backend.app.services.i5.know05.source_selection import select_sources_for_coverage
from backend.app.services.i5.know05.write_path_ledger import (
    count_fetched_sources,
    count_knowledge_accepted,
    count_publication_outcomes,
    fetch_publication_conflation_count,
    map_to_wrsr_status,
)


SCHEDULE_KEY = "weekly_international_knowledge_crawler"


def _source_profile_id_for_connector(db: Session, connector_key: str) -> Optional[int]:
    from backend.app.services.i5.know05.canonical_rights import resolve_canonical_source

    gsp = resolve_canonical_source(db, connector_key)
    return int(gsp.id) if gsp is not None else None


def _append_specialized_result(
    db: Session,
    source_results: list[dict[str, Any]],
    *,
    r: Any,
) -> None:
    sp_id = getattr(r, "source_profile_id", None)
    if sp_id is None:
        sp_id = _source_profile_id_for_connector(db, r.connector_key)
    source_results.append(
        {
            "connector_key": r.connector_key,
            "status": r.status,
            "block_reason": r.block_reason,
            "http_status": r.http_status,
            "bytes_received": r.bytes_received,
            "request_count": r.request_count,
            "page_count": r.page_count,
            "external_ids": list(r.external_ids),
            "records_discovered": r.records_discovered,
            "records_normalized": r.records_normalized,
            "records_accepted": r.records_accepted,
            "records_rejected": r.records_rejected,
            "records_changed": r.records_changed,
            "rights_decision": r.rights_decision,
            "storage_decision": r.storage_decision,
            "transient_raw_residue": r.transient_raw_residue,
            "knowledge_unit_id": r.knowledge_unit_id,
            "source_profile_id": sp_id,
            "publication_stages": list(r.publication_stages),
            "specialized_handler": True,
            "publication_outcome": "NOT_PUBLISHED",
        }
    )


def _persist_weekly_source_results(
    db: Session,
    *,
    attempt_id: int,
    source_results: list[dict[str, Any]],
) -> None:
    """Write WeeklyRunSourceResult with truthful fetch≠publish vocabulary."""
    for s in source_results:
        sp_id = s.get("source_profile_id")
        if sp_id is None:
            continue
        wrsr_status = map_to_wrsr_status(str(s.get("status") or ""))
        if wrsr_status is None:
            continue
        existing = (
            db.query(models.WeeklyRunSourceResult)
            .filter_by(attempt_id=attempt_id, source_profile_id=int(sp_id))
            .first()
        )
        if existing is not None:
            continue
        pub_out = "NOT_PUBLISHED"
        if wrsr_status == "PUBLISHED":
            pub_out = "PUBLISHED"
        row = models.WeeklyRunSourceResult(
            attempt_id=attempt_id,
            source_profile_id=int(sp_id),
            result_status=wrsr_status,
            checked_at=datetime.utcnow(),
            fetch_outcome=str(s.get("status") or ""),
            extraction_outcome="STORED" if str(s.get("status")) == "STORED" else None,
            publication_outcome=pub_out,
            knowledge_new_count=int(s.get("records_accepted") or 0),
            knowledge_updated_count=0,
            knowledge_superseded_count=0,
            knowledge_rejected_count=int(s.get("records_rejected") or 0),
            gap_created_count=0,
            warning_count=1 if str(s.get("status")) == "BLOCKED" else 0,
            error_count=1 if str(s.get("status")) == "FAILED" else 0,
            failure_code=s.get("block_reason"),
            failure_reason=s.get("block_reason"),
            evidence_reference=f"know05:{s.get('connector_key')}",
            content_fingerprint=(s.get("diagnostics") or {}).get("ACQUISITION_RAW_EVIDENCE_ID")
            if isinstance(s.get("diagnostics"), dict)
            else None,
        )
        db.add(row)
    db.flush()


@dataclass
class Know05RunResult:
    mode: str
    logical_run_key: str
    weekly_run_id: Optional[int]
    attempt_id: Optional[int]
    gaps_created: int
    gaps_reused: int
    prioritized: int
    ncbi_weekly_status: str
    source_results: list[dict[str, Any]] = field(default_factory=list)
    source_selections: list[dict[str, Any]] = field(default_factory=list)
    production_flags: dict[str, bool] = field(default_factory=production_activation_flags)
    existing_weekly_governance_reused: bool = True

    def as_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["source_results"] = list(self.source_results)
        d["source_selections"] = list(self.source_selections)
        d["production_flags"] = dict(self.production_flags)
        return d


def _logical_run_key(mode: Know05Mode, window_tag: str) -> str:
    raw = f"know05:{mode.value}:{window_tag}:{SCHEDULE_KEY}"
    return "wkr:" + hashlib.sha256(raw.encode()).hexdigest()[:40]


def run_know05_cycle(
    db: Session,
    *,
    mode: Know05Mode | str = Know05Mode.DRY_RUN,
    window_tag: Optional[str] = None,
    persist_ledger: bool = True,
    execute_ingestion: bool = True,
    http_get: Optional[Callable[..., Any]] = None,
) -> Know05RunResult:
    """Coverage-driven weekly cycle: gap → source selection → bounded fetch → ledger."""
    m = assert_mode_authorized(mode)
    plan = plan_bounded_ingestion(m)
    identity = load_ncbi_operational_identity(require_for_weekly=True)
    tag = window_tag or datetime.utcnow().strftime("%Y%m%d%H%M%S")
    logical = _logical_run_key(m, tag)

    prioritized = prioritize_coverage_cells(db, limit=plan.budget.max_records or 10)
    gap_stats = ensure_gaps_from_coverage(db, items=prioritized, limit=plan.budget.max_records or 10)
    selections = select_sources_for_coverage(db, items=prioritized, limit=plan.budget.max_records or 10)

    # Prefer Registry-selected unblocked connectors within CI budget (max 2).
    # Never fall back to plan.connectors / hardcoded PubMed/WHO/CT.gov keys.
    from backend.app.services.i5.know05.source_selection import NO_ELIGIBLE_GOVERNED_SOURCE

    chosen_keys: list[str] = []
    for sel in selections:
        if sel.connector_key in chosen_keys:
            continue
        if sel.connector_key == NO_ELIGIBLE_GOVERNED_SOURCE:
            continue
        if sel.block_reason and sel.connector_key.startswith("pubmed"):
            continue
        if sel.automation_decision != "AUTOMATION_ALLOWED" and m != Know05Mode.DRY_RUN:
            # Record blocked pubmed only when Registry selected it
            if sel.connector_key.startswith("pubmed") and sel.connector_key not in chosen_keys:
                chosen_keys.append(sel.connector_key)
            continue
        chosen_keys.append(sel.connector_key)
        if len(chosen_keys) >= min(2, plan.budget.max_sources or 2):
            break

    source_results: list[dict[str, Any]] = []
    if not chosen_keys:
        source_results.append(
            {
                "connector_key": NO_ELIGIBLE_GOVERNED_SOURCE,
                "status": "BLOCKED",
                "block_reason": NO_ELIGIBLE_GOVERNED_SOURCE,
                "records_discovered": 0,
                "records_accepted": 0,
                "records_rejected": 0,
                "records_changed": 0,
                "transient_raw_residue": 0,
            }
        )
    elif m == Know05Mode.DRY_RUN or not execute_ingestion:
        for ck in chosen_keys[:2]:
            blocked = False
            block_reason = None
            if ck.startswith("pubmed") and identity.weekly_operation_status != "LIVE_READY":
                blocked = True
                block_reason = identity.weekly_operation_status
            status = "PLANNED_DRY_RUN" if m == Know05Mode.DRY_RUN else (
                "BLOCKED" if blocked else "READY_FOR_BOUNDED_FETCH"
            )
            source_results.append(
                {
                    "connector_key": ck,
                    "status": status,
                    "block_reason": block_reason,
                    "records_discovered": 0,
                    "records_accepted": 0,
                    "records_rejected": 0,
                    "records_changed": 0,
                    "transient_raw_residue": 0,
                }
            )
    else:
        # Real bounded path — at least one connector beyond READY_FOR_BOUNDED_FETCH
        executed = set()
        for ck in chosen_keys[:2]:
            if ck in executed:
                continue
            executed.add(ck)
            if ck.startswith("pubmed"):
                r = ingest_pubmed_bounded_or_block(mode=m, db=db)
                _append_specialized_result(db, source_results, r=r)
            elif ck == "clinicaltrials_gov_api_v2":
                r = ingest_clinicaltrials_bounded(
                    db, mode=m, query="diabetes", http_get=http_get, max_records=2
                )
                _append_specialized_result(db, source_results, r=r)
            elif ck == "who_guideline_catalogue":
                r = ingest_who_catalogue_bounded(db, mode=m, http_get=http_get, max_records=1)
                _append_specialized_result(db, source_results, r=r)
            else:
                # Generic Registry → AdapterRegistry bridge (no source-key handler required).
                from backend.app.services.i5.know05.generic_execution_bridge import (
                    execute_generic_registry_source,
                )

                bridge = execute_generic_registry_source(
                    db, connector_key=ck, http_get=http_get
                )
                # Preserve truthful NO_BOUNDED_HANDLER only when no adapter contract exists.
                if (
                    bridge.status == "BLOCKED"
                    and (bridge.block_reason or "").startswith("NO_VERIFIED_ADAPTER_CONTRACT")
                ):
                    # Keep vocabulary distinguishable from supported-dynamic miss.
                    pass
                elif bridge.status == "BLOCKED" and bridge.block_reason == "NO_BOUNDED_TRANSPORT":
                    bridge.block_reason = "NO_BOUNDED_HANDLER"
                source_results.append(bridge.as_orchestrator_dict())
                continue
        # Do not inject pubmed/WHO/CT.gov when Registry selection yielded nothing.

    weekly_run_id = None
    attempt_id = None
    if persist_ledger:
        run = db.query(models.WeeklyKnowledgeRun).filter_by(logical_run_key=logical).first()
        created_new_run = False
        if run is None:
            created_new_run = True
            run = models.WeeklyKnowledgeRun(
                logical_run_key=logical,
                schedule_key=SCHEDULE_KEY,
                run_type=WeeklyRunType.WEEKLY_GOVERNED.value,
                trigger_type=WeeklyRunTriggerType.AD_HOC.value,
                planned_window_start=datetime.utcnow(),
                planned_window_end=datetime.utcnow(),
                approval_state=WeeklyRunApprovalState.APPROVED.value
                if m != Know05Mode.PRODUCTION_WEEKLY
                else WeeklyRunApprovalState.NOT_REQUIRED.value,
                source_scope=json.dumps({"connectors": list(chosen_keys), "mode": m.value}),
                domain_scope=json.dumps({"coverage_driven": True}),
                gap_scope=json.dumps({"from_cells": True, "count": gap_stats["items_considered"]}),
                source_scope_hash=hashlib.sha256(m.value.encode()).hexdigest()[:32],
                domain_scope_hash=hashlib.sha256(b"coverage").hexdigest()[:32],
                gap_scope_hash=hashlib.sha256(str(gap_stats).encode()).hexdigest()[:32],
                config_version="know05-v2",
                config_hash=hashlib.sha256(json.dumps(plan.as_dict(), sort_keys=True).encode()).hexdigest()[:32],
                status=WeeklyRunStatus.COMPLETED.value
                if m == Know05Mode.DRY_RUN
                else WeeklyRunStatus.COMPLETED_WITH_WARNINGS.value,
            )
            db.add(run)
            db.flush()
        weekly_run_id = run.id
        existing_attempt = (
            db.query(models.WeeklyKnowledgeRunAttempt)
            .filter_by(weekly_run_id=run.id)
            .order_by(models.WeeklyKnowledgeRunAttempt.attempt_number.desc())
            .first()
        )
        if existing_attempt is not None and not created_new_run:
            attempt_id = existing_attempt.id
            existing_attempt.created_gap_count = max(
                existing_attempt.created_gap_count or 0, gap_stats["gaps_created"]
            )
            db.flush()
        else:
            next_n = 1 if existing_attempt is None else int(existing_attempt.attempt_number) + 1
            fetched = count_fetched_sources(source_results)
            accepted = count_knowledge_accepted(source_results)
            published = count_publication_outcomes(source_results)
            assert fetch_publication_conflation_count(source_results) == 0
            blocked = sum(1 for s in source_results if s["status"] == "BLOCKED")
            failed = sum(1 for s in source_results if s["status"] == "FAILED")
            attempt = models.WeeklyKnowledgeRunAttempt(
                weekly_run_id=run.id,
                attempt_number=next_n,
                status=WeeklyRunAttemptStatus.COMPLETED.value,
                total_sources=len(source_results),
                checked_sources=len(source_results),
                fetched_sources=fetched,
                skipped_sources=0,
                blocked_sources=blocked,
                failed_sources=failed,
                new_knowledge_count=accepted,
                updated_knowledge_count=0,
                created_gap_count=gap_stats["gaps_created"],
                resolved_gap_count=0,
                warning_count=blocked + failed,
                error_count=failed,
                evidence_reference=(
                    f"know05:{m.value}:{logical}:fetched={fetched}:"
                    f"accepted={accepted}:published={published}"
                ),
            )
            db.add(attempt)
            db.flush()
            attempt_id = attempt.id
            run.latest_attempt_id = attempt.id
            run.successful_attempt_id = attempt.id
            db.flush()
            _persist_weekly_source_results(
                db, attempt_id=attempt.id, source_results=source_results
            )

    return Know05RunResult(
        mode=m.value,
        logical_run_key=logical,
        weekly_run_id=weekly_run_id,
        attempt_id=attempt_id,
        gaps_created=gap_stats["gaps_created"],
        gaps_reused=gap_stats["gaps_reused"],
        prioritized=len(prioritized),
        ncbi_weekly_status=identity.weekly_operation_status,
        source_results=source_results,
        source_selections=[s.as_dict() for s in selections],
    )
