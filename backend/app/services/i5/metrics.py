"""I5-IMPL-W6-P03 / P12 — AA metrics emitters + alert evaluation.

Authority:
- package_sequence.json → I5-IMPL-W6-P03 (AA metrics defined and emitted in dry unit)
- safety_security_observability_plan.json → required_metrics (17 AA names)
- target_architecture_map.json → BC-24 (alert on silent zero improvement; alert high-risk gaps)
- file_allowlist_matrix.json → CREATE this module; MODIFY weekly_orchestrator.py
- OUT_OF_SCOPE → pagerDuty prod wiring unless approved

Observability observes/report; it must not mutate crawler/governance decisions.
No third-party metrics platform. No secrets / PHI / raw medical text in labels.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional

PACKAGE_ID = "I5-IMPL-W6-P03"
MANAGEMENT_ALIAS = "P12"
PACKAGE_TITLE = "Monitoring metrics emitters + alerts"
CAPABILITY_ID = "CAP-OPEN-26"
MISSING_COMPONENT_ID = "MISS-17"
ARCHITECTURE_CONTEXT_ID = "BC-24"

# Exact AA names from safety_security_observability_plan.json#required_metrics
AA_METRIC_NAMES: tuple[str, ...] = (
    "SOURCES_CHECKED",
    "NEW_SOURCES",
    "UPDATED_SOURCES",
    "FAILED_SOURCES",
    "BLOCKED_SOURCES",
    "NEW_KNOWLEDGE_UNITS",
    "UPDATED_UNITS",
    "SUPERSEDED_UNITS",
    "REJECTED_UNITS",
    "KNOWLEDGE_GAPS_CLOSED",
    "HIGH_RISK_GAPS_REMAINING",
    "CONFLICTS",
    "SAFETY_REJECTIONS",
    "COVERAGE_SCORE",
    "FRESHNESS_SCORE",
    "RUN_DURATION",
    "DATABASE_WRITE_COUNT",
)
AA_METRIC_NAME_SET = frozenset(AA_METRIC_NAMES)

# Bounded non-sensitive label keys only (no PHI / secrets / raw text).
ALLOWED_LABEL_KEYS = frozenset(
    {
        "logical_run_key",
        "outcome",
        "dry_run",
        "package_id",
    }
)

ALERT_SILENT_ZERO_IMPROVEMENT = "SILENT_ZERO_IMPROVEMENT"
ALERT_HIGH_RISK_GAPS = "HIGH_RISK_GAPS_REMAINING"
ALERT_POLICY_THRESHOLD_REVIEW = "POLICY_THRESHOLD_REVIEW"

# Conservative fail-closed review trigger for undefined §137.24 "policy threshold":
# any safety rejection or conflict count > 0 requires review alert (not paging).
# Numeric production pager thresholds remain unspecified / not invented here.
POLICY_REVIEW_SAFETY_REJECTIONS_MIN = 1
POLICY_REVIEW_CONFLICTS_MIN = 1


class MetricsError(ValueError):
    """Fail-closed metrics / alert contract error."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        message = code if not detail else f"{code}:{detail}"
        super().__init__(message)


@dataclass(frozen=True)
class MetricSample:
    name: str
    value: float
    labels: Mapping[str, str] = field(default_factory=dict)
    emitted_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class AlertDecision:
    alert_id: str
    triggered: bool
    reason: str
    metric_snapshot: Mapping[str, float] = field(default_factory=dict)


def _sanitize_labels(labels: Optional[Mapping[str, Any]]) -> dict[str, str]:
    if not labels:
        return {"package_id": PACKAGE_ID}
    out: dict[str, str] = {"package_id": PACKAGE_ID}
    for key, raw in labels.items():
        if key not in ALLOWED_LABEL_KEYS:
            raise MetricsError("LABEL_NOT_ALLOWED", key)
        if raw is None:
            continue
        text = str(raw)
        if len(text) > 256:
            raise MetricsError("LABEL_VALUE_TOO_LONG", key)
        # Refuse obvious secret-like payloads.
        lowered = text.lower()
        if any(tok in lowered for tok in ("password", "secret", "token=", "bearer ", "api_key")):
            raise MetricsError("LABEL_SENSITIVE_REFUSED", key)
        out[key] = text
    return out


def empty_aa_metric_values() -> dict[str, float]:
    return {name: 0.0 for name in AA_METRIC_NAMES}


def normalize_aa_metric_values(values: Mapping[str, Any]) -> dict[str, float]:
    """Require the full AA set; reject unknown metric names."""
    unknown = set(values) - AA_METRIC_NAME_SET
    if unknown:
        raise MetricsError("UNKNOWN_METRIC", ",".join(sorted(unknown)))
    missing = AA_METRIC_NAME_SET - set(values)
    if missing:
        raise MetricsError("MISSING_METRIC", ",".join(sorted(missing)))
    out: dict[str, float] = {}
    for name in AA_METRIC_NAMES:
        try:
            out[name] = float(values[name])
        except (TypeError, ValueError) as exc:
            raise MetricsError("METRIC_VALUE_NOT_NUMERIC", name) from exc
        if out[name] < 0:
            raise MetricsError("METRIC_VALUE_NEGATIVE", name)
    return out


def build_aa_metrics_from_run_counters(
    *,
    sources_checked: int = 0,
    new_sources: int = 0,
    updated_sources: int = 0,
    failed_sources: int = 0,
    blocked_sources: int = 0,
    new_knowledge_units: int = 0,
    updated_units: int = 0,
    superseded_units: int = 0,
    rejected_units: int = 0,
    knowledge_gaps_closed: int = 0,
    high_risk_gaps_remaining: int = 0,
    conflicts: int = 0,
    safety_rejections: int = 0,
    coverage_score: Optional[float] = None,
    freshness_score: Optional[float] = None,
    run_duration: float = 0.0,
    database_write_count: int = 0,
    total_sources: Optional[int] = None,
) -> dict[str, float]:
    """Map ledger-like counters onto the authoritative AA metric names.

    COVERAGE_SCORE / FRESHNESS_SCORE: when not supplied, derive bounded [0,1]
    provisional ratios from available counters (measurement-law placeholders
    until a separate product formula is authorized). No PHI.
    """
    total = int(total_sources) if total_sources is not None else int(sources_checked)
    if coverage_score is None:
        coverage_score = (float(sources_checked) / float(total)) if total > 0 else 0.0
    knowledge_touch = int(new_knowledge_units) + int(updated_units) + int(superseded_units)
    if freshness_score is None:
        freshness_score = (
            float(new_knowledge_units + updated_units) / float(knowledge_touch)
            if knowledge_touch > 0
            else 0.0
        )
    return normalize_aa_metric_values(
        {
            "SOURCES_CHECKED": sources_checked,
            "NEW_SOURCES": new_sources,
            "UPDATED_SOURCES": updated_sources,
            "FAILED_SOURCES": failed_sources,
            "BLOCKED_SOURCES": blocked_sources,
            "NEW_KNOWLEDGE_UNITS": new_knowledge_units,
            "UPDATED_UNITS": updated_units,
            "SUPERSEDED_UNITS": superseded_units,
            "REJECTED_UNITS": rejected_units,
            "KNOWLEDGE_GAPS_CLOSED": knowledge_gaps_closed,
            "HIGH_RISK_GAPS_REMAINING": high_risk_gaps_remaining,
            "CONFLICTS": conflicts,
            "SAFETY_REJECTIONS": safety_rejections,
            "COVERAGE_SCORE": coverage_score,
            "FRESHNESS_SCORE": freshness_score,
            "RUN_DURATION": run_duration,
            "DATABASE_WRITE_COUNT": database_write_count,
        }
    )


def evaluate_alerts(metrics: Mapping[str, Any]) -> list[AlertDecision]:
    """Evaluate BC-24 / MISS-17 alert rules against an AA metric snapshot.

    Proves both trigger and no-trigger sides via deterministic predicates.
    Does not send notifications / PagerDuty.
    """
    values = normalize_aa_metric_values(metrics)
    decisions: list[AlertDecision] = []

    silent = (
        values["SOURCES_CHECKED"] > 0
        and values["NEW_KNOWLEDGE_UNITS"] == 0
        and values["UPDATED_UNITS"] == 0
        and values["KNOWLEDGE_GAPS_CLOSED"] == 0
    )
    decisions.append(
        AlertDecision(
            alert_id=ALERT_SILENT_ZERO_IMPROVEMENT,
            triggered=silent,
            reason=(
                "sources_checked_with_zero_knowledge_or_gap_improvement"
                if silent
                else "improvement_or_no_sources_checked"
            ),
            metric_snapshot=values,
        )
    )

    high_risk = values["HIGH_RISK_GAPS_REMAINING"] > 0
    decisions.append(
        AlertDecision(
            alert_id=ALERT_HIGH_RISK_GAPS,
            triggered=high_risk,
            reason="high_risk_gaps_remaining_gt_zero" if high_risk else "no_high_risk_gaps",
            metric_snapshot=values,
        )
    )

    policy = (
        values["SAFETY_REJECTIONS"] >= POLICY_REVIEW_SAFETY_REJECTIONS_MIN
        or values["CONFLICTS"] >= POLICY_REVIEW_CONFLICTS_MIN
    )
    decisions.append(
        AlertDecision(
            alert_id=ALERT_POLICY_THRESHOLD_REVIEW,
            triggered=policy,
            reason=(
                "safety_rejection_or_conflict_requires_review"
                if policy
                else "below_review_threshold"
            ),
            metric_snapshot=values,
        )
    )
    return decisions


def triggered_alerts(metrics: Mapping[str, Any]) -> list[AlertDecision]:
    return [d for d in evaluate_alerts(metrics) if d.triggered]


class MetricsEmitter:
    """Thread-safe in-memory AA metrics emitter (no network / no DB side effects)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: list[MetricSample] = []
        self._latest: dict[str, float] = empty_aa_metric_values()
        self._emit_count = 0

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
            self._latest = empty_aa_metric_values()
            self._emit_count = 0

    def emit(
        self,
        name: str,
        value: float,
        labels: Optional[Mapping[str, Any]] = None,
    ) -> MetricSample:
        if name not in AA_METRIC_NAME_SET:
            raise MetricsError("UNKNOWN_METRIC", name)
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise MetricsError("METRIC_VALUE_NOT_NUMERIC", name) from exc
        if numeric < 0:
            raise MetricsError("METRIC_VALUE_NEGATIVE", name)
        sample = MetricSample(
            name=name,
            value=numeric,
            labels=_sanitize_labels(labels),
            emitted_at=datetime.utcnow(),
        )
        with self._lock:
            self._samples.append(sample)
            self._latest[name] = numeric
            self._emit_count += 1
        return sample

    def emit_run_snapshot(
        self,
        values: Mapping[str, Any],
        labels: Optional[Mapping[str, Any]] = None,
    ) -> list[MetricSample]:
        normalized = normalize_aa_metric_values(values)
        safe_labels = _sanitize_labels(labels)
        samples: list[MetricSample] = []
        for name in AA_METRIC_NAMES:
            samples.append(self.emit(name, normalized[name], labels=safe_labels))
        return samples

    def latest(self) -> dict[str, float]:
        with self._lock:
            return dict(self._latest)

    def samples(self) -> list[MetricSample]:
        with self._lock:
            return list(self._samples)

    def emit_count(self) -> int:
        with self._lock:
            return self._emit_count

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "package_id": PACKAGE_ID,
                "metric_names": list(AA_METRIC_NAMES),
                "latest": dict(self._latest),
                "emit_count": self._emit_count,
                "sample_count": len(self._samples),
                "alerts": [
                    {
                        "alert_id": d.alert_id,
                        "triggered": d.triggered,
                        "reason": d.reason,
                    }
                    for d in evaluate_alerts(self._latest)
                ],
            }


_emitter: MetricsEmitter | None = None
_emitter_lock = threading.Lock()


def get_metrics_emitter() -> MetricsEmitter:
    global _emitter
    with _emitter_lock:
        if _emitter is None:
            _emitter = MetricsEmitter()
        return _emitter


def reset_metrics_emitter() -> MetricsEmitter:
    emitter = get_metrics_emitter()
    emitter.reset()
    return emitter


def observe_weekly_run_metrics(
    *,
    counters: Mapping[str, Any],
    labels: Optional[Mapping[str, Any]] = None,
    emitter: Optional[MetricsEmitter] = None,
) -> dict[str, Any]:
    """Emit full AA snapshot + evaluate alerts. Pure observability side-effect on emitter only."""
    target = emitter or get_metrics_emitter()
    values = normalize_aa_metric_values(counters)
    samples = target.emit_run_snapshot(values, labels=labels)
    alerts = evaluate_alerts(values)
    return {
        "metrics": values,
        "samples_emitted": len(samples),
        "alerts": alerts,
        "triggered": [a for a in alerts if a.triggered],
    }
