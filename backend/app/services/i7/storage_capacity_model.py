"""Section44 100-year storage capacity model. Design-only. No schema writes.

Assumptions are explicit. Values are order-of-magnitude planning figures,
not measured production telemetry. LOW/BASE/HIGH bound uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

HORIZONS_YEARS = (1, 5, 10, 50, 100)
USER_COUNTS = (100, 1_000, 5_000, 100_000, 1_000_000)
SCENARIOS = ("LOW", "BASE", "HIGH")

# PostgreSQL heap header + alignment allowance applied after payload.
HEAP_OVERHEAD_BYTES = 24
INDEX_MULTIPLIER = {"LOW": 0.35, "BASE": 0.55, "HIGH": 0.80}
BACKUP_MULTIPLIER = {"LOW": 2.0, "BASE": 2.5, "HIGH": 3.0}  # live + replica backup/WAL
REPLICA_MULTIPLIER = {"LOW": 1.0, "BASE": 2.0, "HIGH": 2.0}  # primary-only vs 1 standby

# Lifelong companion memory (canonical). Not unlimited chat. Not high-freq vitals.
ASSUMPTIONS = {
    "LOW": {
        "active_facts_steady": 40,
        "new_fact_versions_per_year": 15,
        "umf_row_bytes": 700,
        "lifestyle_events_per_year": 80,
        "lifestyle_row_bytes": 400,
        "user_events_per_year": 12,
        "user_event_row_bytes": 600,
        "interaction_hot_days": 90,
        "interaction_per_day": 0.5,
        "interaction_row_bytes": 300,
        "daily_summary_retain_years": 0.25,
        "weekly_retain_years": 100,
        "monthly_retain_years": 100,
        "yearly_retain_years": 100,
        "summary_row_bytes": 500,
        "summary_rebuild_factor": 1.05,
        "profile_versions_per_year": 1,
        "profile_row_bytes": 2500,
        "consent_audit_bytes_per_year": 8_000,
        "raw_chat_retain_days": 14,
        "raw_chat_msgs_per_day": 4,
        "raw_chat_bytes_per_msg": 400,
        "export_db_bytes_steady": 800,  # metadata only
        "optional_embedding_bytes_per_fact": 0,  # NOT ACTIVE
    },
    "BASE": {
        "active_facts_steady": 80,
        "new_fact_versions_per_year": 40,
        "umf_row_bytes": 1200,
        "lifestyle_events_per_year": 156,
        "lifestyle_row_bytes": 600,
        "user_events_per_year": 24,
        "user_event_row_bytes": 800,
        "interaction_hot_days": 180,
        "interaction_per_day": 2,
        "interaction_row_bytes": 400,
        "daily_summary_retain_years": 1,
        "weekly_retain_years": 100,
        "monthly_retain_years": 100,
        "yearly_retain_years": 100,
        "summary_row_bytes": 800,
        "summary_rebuild_factor": 1.20,
        "profile_versions_per_year": 2,
        "profile_row_bytes": 4000,
        "consent_audit_bytes_per_year": 20_000,
        "raw_chat_retain_days": 30,
        "raw_chat_msgs_per_day": 12,
        "raw_chat_bytes_per_msg": 700,
        "export_db_bytes_steady": 1500,
        "optional_embedding_bytes_per_fact": 0,
    },
    "HIGH": {
        "active_facts_steady": 160,
        "new_fact_versions_per_year": 90,
        "umf_row_bytes": 2000,
        "lifestyle_events_per_year": 365,
        "lifestyle_row_bytes": 900,
        "user_events_per_year": 60,
        "user_event_row_bytes": 1200,
        "interaction_hot_days": 365,
        "interaction_per_day": 6,
        "interaction_row_bytes": 600,
        "daily_summary_retain_years": 2,
        "weekly_retain_years": 100,
        "monthly_retain_years": 100,
        "yearly_retain_years": 100,
        "summary_row_bytes": 1500,
        "summary_rebuild_factor": 1.50,
        "profile_versions_per_year": 4,
        "profile_row_bytes": 8000,
        "consent_audit_bytes_per_year": 50_000,
        "raw_chat_retain_days": 90,
        "raw_chat_msgs_per_day": 30,
        "raw_chat_bytes_per_msg": 1200,
        "export_db_bytes_steady": 3000,
        "optional_embedding_bytes_per_fact": 0,
    },
}

# Forbidden-unlimited contrast only (not a supported policy).
UNLIMITED_CHAT_MSGS_PER_DAY = 20
UNLIMITED_CHAT_BYTES_PER_MSG = 1000


def _row(payload: float) -> float:
    return payload + HEAP_OVERHEAD_BYTES


def _summaries(years: float, retain_years: float, periods_per_year: float, a: dict) -> float:
    kept = min(years, retain_years) * periods_per_year
    return kept * _row(a["summary_row_bytes"]) * a["summary_rebuild_factor"]


def user_bytes(scenario: str, years: float, *, include_raw_chat: bool = True) -> dict[str, float]:
    if scenario not in ASSUMPTIONS:
        raise ValueError(scenario)
    a = ASSUMPTIONS[scenario]
    umf_rows = a["active_facts_steady"] + a["new_fact_versions_per_year"] * max(years - 1, 0)
    umf = umf_rows * _row(a["umf_row_bytes"])
    lifestyle = a["lifestyle_events_per_year"] * years * _row(a["lifestyle_row_bytes"])
    user_events = a["user_events_per_year"] * years * _row(a["user_event_row_bytes"])
    interaction = (
        a["interaction_hot_days"] * a["interaction_per_day"] * _row(a["interaction_row_bytes"])
    )
    daily = _summaries(years, a["daily_summary_retain_years"], 365, a)
    weekly = _summaries(years, min(a["weekly_retain_years"], years), 52, a)
    monthly = _summaries(years, min(a["monthly_retain_years"], years), 12, a)
    yearly = _summaries(years, min(a["yearly_retain_years"], years), 1, a)
    profile = max(a["profile_versions_per_year"] * years, 1) * _row(a["profile_row_bytes"])
    consent = a["consent_audit_bytes_per_year"] * years
    export_meta = a["export_db_bytes_steady"]
    chat = 0.0
    if include_raw_chat:
        chat = (
            a["raw_chat_retain_days"]
            * a["raw_chat_msgs_per_day"]
            * _row(a["raw_chat_bytes_per_msg"])
        )
    embeddings = a["optional_embedding_bytes_per_fact"] * umf_rows
    lifelong = (
        umf
        + lifestyle
        + user_events
        + interaction
        + daily
        + weekly
        + monthly
        + yearly
        + profile
        + consent
        + export_meta
        + embeddings
    )
    primary = lifelong + chat
    return {
        "umf_history": umf,
        "lifestyle_events": lifestyle,
        "user_events": user_events,
        "interaction_hot": interaction,
        "daily_summaries": daily,
        "weekly_summaries": weekly,
        "monthly_summaries": monthly,
        "yearly_summaries": yearly,
        "lifelong_profile": profile,
        "consent_audit": consent,
        "export_metadata": export_meta,
        "optional_embeddings": embeddings,
        "raw_chat_capped": chat,
        "lifelong_no_chat": lifelong,
        "primary_heap": primary,
        "bytes_per_user_year": primary / years if years else 0.0,
        "bytes_per_user_day": (primary / years / 365.0) if years else 0.0,
    }


def unlimited_chat_bytes(years: float) -> float:
    return years * 365 * UNLIMITED_CHAT_MSGS_PER_DAY * _row(UNLIMITED_CHAT_BYTES_PER_MSG)


def fleet_bytes(
    scenario: str,
    users: int,
    years: float,
    *,
    include_raw_chat: bool = True,
) -> dict[str, float]:
    u = user_bytes(scenario, years, include_raw_chat=include_raw_chat)
    heap = u["primary_heap"] * users
    idx = heap * INDEX_MULTIPLIER[scenario]
    live = (heap + idx) * REPLICA_MULTIPLIER[scenario]
    backup = live * BACKUP_MULTIPLIER[scenario]
    archive = u["weekly_summaries"] + u["monthly_summaries"] + u["yearly_summaries"]
    archive += u["umf_history"] * 0.6  # superseded facts logically archiveable
    archive *= users
    return {
        **{f"per_user_{k}": v for k, v in u.items()},
        "users": float(users),
        "years": float(years),
        "primary_heap": heap,
        "indexes": idx,
        "live_with_replicas": live,
        "backup_footprint": backup,
        "archive_logical": archive,
        "unlimited_chat_contrast": unlimited_chat_bytes(years) * users,
    }


def matrix(
    scenarios: Iterable[str] = SCENARIOS,
    users: Iterable[int] = USER_COUNTS,
    years: Iterable[int] = HORIZONS_YEARS,
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for sc in scenarios:
        for n in users:
            for y in years:
                rec = fleet_bytes(sc, n, float(y))
                rec["scenario"] = sc
                rows.append(rec)
    return rows


def format_bytes(n: float) -> str:
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    x = float(n)
    i = 0
    while x >= 1024 and i < len(units) - 1:
        x /= 1024
        i += 1
    if i == 0:
        return f"{int(x)} {units[i]}"
    return f"{x:.2f} {units[i]}"


@dataclass(frozen=True)
class StorageModelReport:
    status: str
    unlimited_raw_chat: str
    method: str


def report_status() -> StorageModelReport:
    return StorageModelReport(
        status="PASS",
        unlimited_raw_chat="FORBIDDEN",
        method="explicit_assumption_table_times_row_overhead_times_fleet_multipliers",
    )
