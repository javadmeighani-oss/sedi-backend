"""R-044 step 5 — weekly knowledge-growth report of the I5 crawler (read-only).

R-044 asks that every growth claim is shown with ELIGIBLE counts per domain and language. This module answers, after
each weekly run and on demand, with aggregate counts only (no statement text, no user data):

- the run: status and what every source returned (EXTRACTED / SKIPPED / FAILED ..., new / updated / rejected, failure
  codes);
- knowledge now: units per runtime eligibility, ELIGIBLE per domain x language;
- growth since the run started: units created, and how many of them are ELIGIBLE, per domain x language, with the
  ELIGIBLE count before the run;
- psychology first (mental_health_psychology + wellbeing): the same numbers for those domains;
- controlled link discovery (if any source holds discoveries) and knowledge gaps.

It never writes. The weekly hook logs one ``i5_weekly_growth_report`` line and is fail-open; the CLI prints one
``PROBE|growth_report|...`` line for the read-only production probe.
"""
from __future__ import annotations

import json
import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

PACKAGE_ID = "I5-R044-WEEKLY-GROWTH-REPORT-V1"
PSYCHOLOGY_DOMAINS: tuple[str, ...] = ("mental_health_psychology", "wellbeing")
MAX_FAILURE_CODES = 10


def _utc_naive(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is None:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def _iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.replace(microsecond=0).isoformat() if moment is not None else None


def _key(domain: Any, language: Any) -> str:
    return f"{domain or 'unknown'}|{language or 'unknown'}"


def _sorted(counter: Mapping[str, int]) -> dict[str, int]:
    return {k: int(v) for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])) if v}


def _sorted_signed(counter: Mapping[str, int]) -> dict[str, int]:
    return {k: int(v) for k, v in sorted(counter.items(), key=lambda kv: (-abs(kv[1]), kv[0])) if v}


def assemble_report(
    *,
    generated_at: datetime,
    since: datetime,
    run: Optional[Mapping[str, Any]],
    source_results: Sequence[Mapping[str, Any]],
    unit_counts: Iterable[tuple[str, str, str, int]],
    created_counts: Iterable[tuple[str, str, str, int]],
    discovery: Sequence[Mapping[str, Any]] = (),
    gaps_total: int = 0,
    gaps_created: int = 0,
    baseline_counts: Optional[Iterable[tuple[str, str, str, int]]] = None,
    attempt_counters: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Pure: aggregate already-fetched rows into the report. ``*_counts`` rows are (domain, language, eligibility, n)."""
    by_result: Counter[str] = Counter()
    failure_codes: Counter[str] = Counter()
    counters = attempt_counters or {}
    per_source: dict[str, dict[str, Any]] = {}
    totals = Counter()
    for row in source_results:
        key = str(row.get("source_key") or "unknown")
        status = str(row.get("result_status") or "UNKNOWN")
        by_result[status] += 1
        if row.get("failure_code"):
            failure_codes[str(row["failure_code"])] += 1
        entry = per_source.setdefault(key, {"source_key": key, "urls": 0, "by_result": Counter()})
        entry["urls"] += 1
        entry["by_result"][status] += 1
        for name, column in (("new", "knowledge_new_count"), ("updated", "knowledge_updated_count"), ("rejected", "knowledge_rejected_count"), ("errors", "error_count")):
            totals[name] += int(row.get(column) or 0)

    by_eligibility: Counter[str] = Counter()
    eligible_now: Counter[str] = Counter()
    psych_now: Counter[str] = Counter()
    for domain, language, eligibility, n in unit_counts:
        by_eligibility[str(eligibility)] += int(n)
        if str(eligibility) == "ELIGIBLE":
            eligible_now[_key(domain, language)] += int(n)
        if domain in PSYCHOLOGY_DOMAINS:
            psych_now[str(eligibility)] += int(n)

    created_by_eligibility: Counter[str] = Counter()
    eligible_created: Counter[str] = Counter()
    psych_created = 0
    for domain, language, eligibility, n in created_counts:
        created_by_eligibility[str(eligibility)] += int(n)
        if str(eligibility) == "ELIGIBLE":
            eligible_created[_key(domain, language)] += int(n)
            if domain in PSYCHOLOGY_DOMAINS:
                psych_created += int(n)

    eligible_total = sum(eligible_now.values())
    eligible_new = sum(eligible_created.values())
    created_total = sum(created_by_eligibility.values())
    # The real "before" is the count captured before the run (a replaced unit makes the old version NOT_ELIGIBLE, so
    # "now minus created" would understate it). Without a baseline no before / net claim is made.
    baseline_by_dl: Counter[str] = Counter()
    eligible_before: Optional[int] = None
    if baseline_counts is not None:
        for domain, language, eligibility, n in baseline_counts:
            if str(eligibility) == "ELIGIBLE":
                baseline_by_dl[_key(domain, language)] += int(n)
        eligible_before = sum(baseline_by_dl.values())
    if eligible_before is None:
        verdict = "NO_BASELINE" if created_total else "NO_NEW_UNITS"
        net = None
        net_by_dl = None
    else:
        net = eligible_total - eligible_before
        verdict = "GREW" if net > 0 else "DECLINED" if net < 0 else "NO_NET_GROWTH"
        net_by_dl = _sorted_signed(
            {k: eligible_now.get(k, 0) - baseline_by_dl.get(k, 0) for k in set(eligible_now) | set(baseline_by_dl)}
        )

    discovered_total = sum(int(d.get("discovered") or 0) for d in discovery)
    return {
        "package_id": PACKAGE_ID,
        "generated_at": _iso(generated_at),
        "since": _iso(since),
        "verdict": verdict,
        "run": dict(run) if run else None,
        "sources": {
            "checked": sum(by_result.values()),
            "by_result": _sorted(by_result),
            # Aggregate outcomes come from the attempt ledger (the source-result rows do not carry mutation counts).
            "new": int(counters.get("new_knowledge_count", totals["new"]) or 0),
            "updated": int(counters.get("updated_knowledge_count", totals["updated"]) or 0),
            "superseded": int(counters.get("superseded_knowledge_count", 0) or 0),
            "rejected": int(counters.get("rejected_knowledge_count", totals["rejected"]) or 0),
            "errors": int(counters.get("error_count", totals["errors"]) or 0),
            "failure_codes": dict(list(_sorted(failure_codes).items())[:MAX_FAILURE_CODES]),
            "per_source": [
                {**e, "by_result": _sorted(e["by_result"])} for _, e in sorted(per_source.items())
            ],
        },
        "knowledge": {
            "by_eligibility": _sorted(by_eligibility),
            "eligible_total": eligible_total,
            "eligible_by_domain_language": _sorted(eligible_now),
        },
        "growth": {
            "created_by_eligibility": _sorted(created_by_eligibility),
            "eligible_created": eligible_new,
            "eligible_created_by_domain_language": _sorted(eligible_created),
            "eligible_before": eligible_before,
            "eligible_net": net,
            "eligible_net_by_domain_language": net_by_dl,
        },
        "psychology": {
            "domains": list(PSYCHOLOGY_DOMAINS),
            "by_eligibility": _sorted(psych_now),
            "eligible_created": psych_created,
        },
        "discovery": {
            "enabled": os.environ.get("SEDI_I5_LINK_DISCOVERY_ENABLED", "").strip().lower() in {"1", "true", "yes"},
            "discovered_urls_total": discovered_total,
            "per_source": list(discovery),
        },
        "gaps": {"total": int(gaps_total), "created": int(gaps_created)},
    }


def _discovery_rows(db: Any, models: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    rows = (
        db.query(models.KnowledgeSource.slug, models.KnowledgeSource.crawl_policy_json)
        .filter(models.KnowledgeSource.source_fetch_enabled.is_(True))
        .all()
    )
    for slug, raw in rows:
        try:
            policy = json.loads(raw or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(policy, dict):
            continue
        discovered = policy.get("discovered_urls") or []
        last = policy.get("link_discovery_last")
        if discovered or last:
            out.append({"source_key": str(slug), "discovered": len(discovered), "last": last})
    return sorted(out, key=lambda d: d["source_key"])


def capture_eligible_baseline(db: Any, models: Any) -> Optional[list[tuple[str, str, str, int]]]:
    """Unit counts per domain x language x eligibility BEFORE a run (fail-open: None when they cannot be read)."""
    try:
        from sqlalchemy import func

        ku = models.KnowledgeUnit
        group = (ku.domain, ku.language, ku.runtime_eligibility)
        return [tuple(r) for r in db.query(*group, func.count(ku.id)).group_by(*group).all()]
    except Exception:  # noqa: BLE001
        return None


def build_weekly_growth_report(
    db: Any,
    models: Any,
    *,
    now: Optional[datetime] = None,
    baseline_counts: Optional[Iterable[tuple[str, str, str, int]]] = None,
) -> dict[str, Any]:
    """Read-only collection for ``assemble_report`` (latest weekly run; growth since its attempt started)."""
    from sqlalchemy import func

    m = models
    generated_at = _utc_naive(now) or datetime.now(timezone.utc).replace(tzinfo=None)
    run = db.query(m.WeeklyKnowledgeRun).order_by(m.WeeklyKnowledgeRun.id.desc()).first()
    attempt = None
    if run is not None:
        attempt_id = run.latest_attempt_id or run.successful_attempt_id
        if attempt_id:
            attempt = db.query(m.WeeklyKnowledgeRunAttempt).filter(m.WeeklyKnowledgeRunAttempt.id == attempt_id).one_or_none()
    since = (
        _utc_naive(getattr(attempt, "started_at", None))
        or _utc_naive(getattr(run, "created_at", None))
        or generated_at - timedelta(days=7)
    )

    source_results: list[dict[str, Any]] = []
    if attempt is not None:
        r = m.WeeklyRunSourceResult
        rows = (
            db.query(
                r.source_profile_id,
                r.result_status,
                r.failure_code,
                r.knowledge_new_count,
                r.knowledge_updated_count,
                r.knowledge_rejected_count,
                r.error_count,
            )
            .filter(r.attempt_id == attempt.id)
            .all()
        )
        ids = {row[0] for row in rows if row[0] is not None}
        keys = {}
        if ids:
            gsp = m.GovernedSourceProfile
            keys = dict(db.query(gsp.id, gsp.canonical_key).filter(gsp.id.in_(ids)).all())
        for row in rows:
            source_results.append(
                {
                    "source_key": keys.get(row[0], "unknown"),
                    "result_status": row[1],
                    "failure_code": row[2],
                    "knowledge_new_count": row[3],
                    "knowledge_updated_count": row[4],
                    "knowledge_rejected_count": row[5],
                    "error_count": row[6],
                }
            )

    ku = m.KnowledgeUnit
    group = (ku.domain, ku.language, ku.runtime_eligibility)
    unit_counts = db.query(*group, func.count(ku.id)).group_by(*group).all()
    created_counts = db.query(*group, func.count(ku.id)).filter(ku.created_at >= since).group_by(*group).all()
    gap = m.KnowledgeGap
    gaps_total = int(db.query(func.count(gap.id)).scalar() or 0)
    gaps_created = int(db.query(func.count(gap.id)).filter(gap.created_at >= since).scalar() or 0)

    counters = (
        {
            name: getattr(attempt, name, 0)
            for name in (
                "new_knowledge_count",
                "updated_knowledge_count",
                "superseded_knowledge_count",
                "rejected_knowledge_count",
                "error_count",
            )
        }
        if attempt is not None
        else None
    )
    return assemble_report(
        baseline_counts=baseline_counts,
        attempt_counters=counters,
        generated_at=generated_at,
        since=since,
        run=(
            {
                "id": int(run.id),
                "status": str(run.status),
                "trigger_type": str(run.trigger_type),
                "planned_window_start": _iso(_utc_naive(run.planned_window_start)),
                "attempt_status": str(attempt.status) if attempt is not None else None,
            }
            if run is not None
            else None
        ),
        source_results=source_results,
        unit_counts=[tuple(r) for r in unit_counts],
        created_counts=[tuple(r) for r in created_counts],
        discovery=_discovery_rows(db, m),
        gaps_total=gaps_total,
        gaps_created=gaps_created,
    )


def log_weekly_growth_report(
    db: Any, models: Any, *, baseline_counts: Optional[Iterable[tuple[str, str, str, int]]] = None
) -> Optional[dict[str, Any]]:
    """Weekly-tick hook: one log line with the report; never breaks the weekly run."""
    if db is None or models is None:
        return None
    try:
        report = build_weekly_growth_report(db, models, baseline_counts=baseline_counts)
        logger.info("i5_weekly_growth_report %s", json.dumps(report, sort_keys=True, ensure_ascii=False))
        return report
    except Exception as exc:  # noqa: BLE001 — the report is observability only
        logger.warning("i5_weekly_growth_report_failed %s", type(exc).__name__)
        return None


def main() -> int:
    """Read-only CLI for the production probe: prints one PROBE line, writes nothing."""
    import importlib

    from backend.app.database import get_db

    models = importlib.import_module("backend.app.models")
    db = next(get_db())
    try:
        report = build_weekly_growth_report(db, models)
        print("PROBE|growth_report|" + json.dumps(report, sort_keys=True, ensure_ascii=False))
        return 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "PACKAGE_ID",
    "PSYCHOLOGY_DOMAINS",
    "assemble_report",
    "capture_eligible_baseline",
    "build_weekly_growth_report",
    "log_weekly_growth_report",
    "main",
]
