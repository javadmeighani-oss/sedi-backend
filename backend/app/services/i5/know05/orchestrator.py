"""KNOW-05 weekly orchestration — extends existing WeeklyKnowledgeRun ledger (no parallel SoT)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    WeeklyRunApprovalState,
    WeeklyRunAttemptStatus,
    WeeklyRunStatus,
    WeeklyRunTriggerType,
    WeeklyRunType,
)
from backend.app.services.i5.know05.budgets import plan_bounded_ingestion
from backend.app.services.i5.know05.coverage_engine import ensure_gaps_from_coverage, prioritize_coverage_cells
from backend.app.services.i5.know05.modes import Know05Mode, assert_mode_authorized, production_activation_flags
from backend.app.services.i5.know05.ncbi_identity import load_ncbi_operational_identity
from backend.app.services.i5.know05.publication import (
    PublicationCandidate,
    PublicationStage,
    advance_stage,
    assert_no_direct_runtime_publish,
)


SCHEDULE_KEY = "weekly_international_knowledge_crawler"


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
    production_flags: dict[str, bool] = field(default_factory=production_activation_flags)
    existing_weekly_governance_reused: bool = True

    def as_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["source_results"] = list(self.source_results)
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
) -> Know05RunResult:
    """Coverage-driven weekly cycle in authorized rehearsal modes only."""
    m = assert_mode_authorized(mode)
    plan = plan_bounded_ingestion(m)
    identity = load_ncbi_operational_identity(require_for_weekly=True)
    tag = window_tag or datetime.utcnow().strftime("%Y%m%d%H%M%S")
    logical = _logical_run_key(m, tag)

    prioritized = prioritize_coverage_cells(db, limit=plan.budget.max_records or 10)
    gap_stats = ensure_gaps_from_coverage(db, items=prioritized, limit=plan.budget.max_records or 10)

    source_results: list[dict[str, Any]] = []
    for ck in plan.connectors:
        blocked = False
        block_reason = None
        if ck.startswith("pubmed") and identity.weekly_operation_status != "LIVE_READY":
            blocked = True
            block_reason = identity.weekly_operation_status
        # Simulate dry/bounded path without Production network when DRY_RUN
        if m == Know05Mode.DRY_RUN:
            status = "PLANNED_DRY_RUN"
        elif blocked:
            status = "BLOCKED"
        else:
            status = "READY_FOR_BOUNDED_FETCH"
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

    # Publication pipeline invariant is enforced in unit tests (no SOURCE→RUNTIME jump).
    _ = (PublicationCandidate, PublicationStage, advance_stage, assert_no_direct_runtime_publish)

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
                source_scope=json.dumps({"connectors": list(plan.connectors), "mode": m.value}),
                domain_scope=json.dumps({"coverage_driven": True}),
                gap_scope=json.dumps({"from_cells": True, "count": gap_stats["items_considered"]}),
                source_scope_hash=hashlib.sha256(m.value.encode()).hexdigest()[:32],
                domain_scope_hash=hashlib.sha256(b"coverage").hexdigest()[:32],
                gap_scope_hash=hashlib.sha256(str(gap_stats).encode()).hexdigest()[:32],
                config_version="know05-v1",
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
            # Idempotent rehearsal: reuse successful terminal attempt for same logical run
            attempt_id = existing_attempt.id
            existing_attempt.created_gap_count = max(
                existing_attempt.created_gap_count or 0, gap_stats["gaps_created"]
            )
            db.flush()
        else:
            next_n = 1 if existing_attempt is None else int(existing_attempt.attempt_number) + 1
            attempt = models.WeeklyKnowledgeRunAttempt(
                weekly_run_id=run.id,
                attempt_number=next_n,
                status=WeeklyRunAttemptStatus.COMPLETED.value,
                total_sources=len(plan.connectors),
                checked_sources=len(plan.connectors),
                fetched_sources=0,
                skipped_sources=0,
                blocked_sources=sum(1 for s in source_results if s["status"] == "BLOCKED"),
                failed_sources=0,
                new_knowledge_count=0,
                updated_knowledge_count=0,
                created_gap_count=gap_stats["gaps_created"],
                resolved_gap_count=0,
                warning_count=0,
                error_count=0,
                evidence_reference=f"know05:{m.value}:{logical}",
            )
            db.add(attempt)
            db.flush()
            attempt_id = attempt.id
            run.latest_attempt_id = attempt.id
            run.successful_attempt_id = attempt.id
            db.flush()

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
    )
