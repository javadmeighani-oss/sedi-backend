"""Bounded ingestion budgets + rehearsal planner (no unbounded crawl)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.services.i5.know05.modes import Know05Mode, assert_mode_authorized


@dataclass(frozen=True)
class IngestionBudget:
    max_sources: int
    max_records: int
    max_bytes: int
    max_pages: int
    max_requests: int
    timeout_seconds: int

    def as_dict(self) -> dict[str, int]:
        return {
            "max_sources": self.max_sources,
            "max_records": self.max_records,
            "max_bytes": self.max_bytes,
            "max_pages": self.max_pages,
            "max_requests": self.max_requests,
            "timeout_seconds": self.timeout_seconds,
        }


# CI Gate max (do not exceed without Javad approval):
# MAX_CONNECTORS=2, MAX_REQUESTS_PER_CONNECTOR=3, MAX_PAGES=1,
# MAX_RECORDS_PER_CONNECTOR=5, MAX_TOTAL_ACCEPTED=5
CI_BOUNDED_BUDGET = IngestionBudget(
    max_sources=2,
    max_records=5,
    max_bytes=512_000,
    max_pages=1,
    max_requests=6,
    timeout_seconds=30,
)

BUDGETS: dict[Know05Mode, IngestionBudget] = {
    Know05Mode.DRY_RUN: IngestionBudget(0, 0, 0, 0, 0, 5),
    Know05Mode.LIVE_CANARY: IngestionBudget(2, 3, 512_000, 1, 6, 20),
    Know05Mode.BOUNDED_INGESTION: CI_BOUNDED_BUDGET,
    Know05Mode.WEEKLY_REHEARSAL: IngestionBudget(2, 5, 512_000, 1, 6, 60),
}


@dataclass
class BoundedIngestionPlan:
    mode: Know05Mode
    budget: IngestionBudget
    connectors: tuple[str, ...]
    production_weekly: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "budget": self.budget.as_dict(),
            "connectors": list(self.connectors),
            "production_weekly": self.production_weekly,
            "unbounded_crawl": False,
        }


DEFAULT_CONNECTORS = (
    "pubmed_ncbi_eutils",
    "pubmed_central",
    "clinicaltrials_gov_api_v2",
    "who_guideline_catalogue",
)


def plan_bounded_ingestion(mode: Know05Mode | str) -> BoundedIngestionPlan:
    m = assert_mode_authorized(mode)
    return BoundedIngestionPlan(mode=m, budget=BUDGETS[m], connectors=DEFAULT_CONNECTORS)


def assert_within_budget(*, records: int, requests: int, pages: int, budget: IngestionBudget) -> None:
    if records > budget.max_records:
        raise ValueError("RECORD_BUDGET_EXCEEDED")
    if requests > budget.max_requests:
        raise ValueError("REQUEST_BUDGET_EXCEEDED")
    if pages > budget.max_pages:
        raise ValueError("PAGE_BUDGET_EXCEEDED")
