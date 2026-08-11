"""KNOW-05 ledger status vocabulary — fetch ≠ accept ≠ publish."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from backend.app.services.i5.enums import RunSourceResultStatus

# Truthful fetch successes (NOT clinical publication).
FETCH_SUCCESS_STATUSES = frozenset(
    {
        "FETCHED",
        "STORED",
        "GOVERNED_FETCH_COMPLETED",
        "EXTRACTED",
    }
)

# Clinical / knowledge publication only.
PUBLICATION_STATUSES = frozenset({"PUBLISHED"})

# Map KNOW-05 connector statuses onto WeeklyRunSourceResult vocabulary.
_STATUS_TO_WRSR: dict[str, str] = {
    "GOVERNED_FETCH_COMPLETED": RunSourceResultStatus.FETCHED.value,
    "STORED": RunSourceResultStatus.EXTRACTED.value,
    "FETCHED": RunSourceResultStatus.FETCHED.value,
    "EXTRACTED": RunSourceResultStatus.EXTRACTED.value,
    "PUBLISHED": RunSourceResultStatus.PUBLISHED.value,
    "BLOCKED": RunSourceResultStatus.BLOCKED.value,
    "FAILED": RunSourceResultStatus.FAILED.value,
    "SKIPPED": RunSourceResultStatus.SKIPPED.value,
    "WARNING": RunSourceResultStatus.WARNING.value,
    "CHECKED": RunSourceResultStatus.CHECKED.value,
    "REJECTED": RunSourceResultStatus.FAILED.value,
}


def is_fetch_success(status: str) -> bool:
    return (status or "").strip().upper() in FETCH_SUCCESS_STATUSES


def is_publication_success(status: str) -> bool:
    return (status or "").strip().upper() in PUBLICATION_STATUSES


def count_fetched_sources(source_results: list[Mapping[str, Any]]) -> int:
    """Count fetch successes without conflating PUBLISHED-only rows as fetch."""
    return sum(1 for s in source_results if is_fetch_success(str(s.get("status") or "")))


def count_knowledge_accepted(source_results: list[Mapping[str, Any]]) -> int:
    return sum(int(s.get("records_accepted") or 0) for s in source_results)


def count_publication_outcomes(source_results: list[Mapping[str, Any]]) -> int:
    """Explicit publication outcomes only — GOVERNED_FETCH_COMPLETED never counts."""
    return sum(1 for s in source_results if is_publication_success(str(s.get("status") or "")))


def fetch_publication_conflation_count(source_results: list[Mapping[str, Any]]) -> int:
    """Detect rows that treat fetch-terminal statuses as PUBLISHED."""
    bad = 0
    for s in source_results:
        st = str(s.get("status") or "")
        pub_out = str(s.get("publication_outcome") or "")
        if st in {"GOVERNED_FETCH_COMPLETED", "FETCHED", "STORED"} and pub_out == "PUBLISHED":
            bad += 1
        if st == "GOVERNED_FETCH_COMPLETED" and is_publication_success(st):
            bad += 1
    return bad


def map_to_wrsr_status(status: str) -> Optional[str]:
    key = (status or "").strip().upper()
    return _STATUS_TO_WRSR.get(key)
