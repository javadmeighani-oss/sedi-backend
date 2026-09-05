"""I10-B14 CARE_STATUS_DIGEST — factual general-status digest for authorized caregivers."""

from __future__ import annotations

from datetime import date

from backend.app.services.i10.care_subject_status_facts import (
    CareSubjectDataStatus,
    CareSubjectStatusFacts,
    assemble_care_subject_status_facts,
)
from backend.app.services.i10.policy_types import I10PrivacyClass, I10SemanticFamily

PRODUCER_OWNER = "I10_CARE_STATUS_DIGEST"
FORBIDDEN_PHRASES = (
    "healthy",
    "normal",
    "nothing to worry",
    "no reason to worry",
    "all clear",
    "medical emergency",
    "diagnosis",
)


def build_care_status_digest_occurrence_key(*, health_subject_id: int, period_date: date) -> str:
    return f"i10:care:status_digest:{health_subject_id}:{period_date.isoformat()}"


def render_care_status_digest_body(facts: CareSubjectStatusFacts) -> str:
    """Deterministic factual copy — no diagnosis, healthy/normal, or false reassurance."""
    parts = [facts.coverage_summary, facts.recency_summary, facts.alert_summary]
    if facts.baseline_comparison:
        parts.append(facts.baseline_comparison)
    if facts.monitoring_status == "DATA_INSUFFICIENT" and not facts.baseline_comparison:
        parts.append("Available heart-rate data is not sufficient to determine the monitoring status.")
    if facts.data_status in (CareSubjectDataStatus.PARTIAL_DATA, CareSubjectDataStatus.NO_DATA):
        parts.append("Available information is insufficient for a fuller summary.")
    if facts.data_status in (CareSubjectDataStatus.STALE_DATA, CareSubjectDataStatus.NO_DATA):
        parts.append("Data continuity may be limited according to available rollup information.")
    if facts.limitations:
        parts.append(facts.limitations[0])
    return " ".join(p for p in parts if p)


def build_care_status_digest_metadata(facts: CareSubjectStatusFacts, *, body: str) -> dict:
    return {
        "title": "Care status digest",
        "body": body,
        "template_key": "care_status_digest",
        "trigger_reason": "care_status_digest",
        "schedule_label": facts.observation_period_start.date().isoformat(),
        "data_status": facts.data_status.value,
        "signal_scope": facts.signal_scope,
        "monitoring_status": facts.monitoring_status,
        "baseline_quality": facts.baseline_quality,
        "context": {
            "template_key": "care_status_digest",
            "trigger_reason": "care_status_digest",
            "schedule_label": facts.observation_period_start.date().isoformat(),
            "data_status": facts.data_status.value,
            "signal_scope": facts.signal_scope,
            "monitoring_status": facts.monitoring_status,
            "baseline_quality": facts.baseline_quality,
        },
        "semantic_family": I10SemanticFamily.CARE_STATUS_DIGEST.value,
        "privacy_class": I10PrivacyClass.HEALTH_SENSITIVE.value,
        "source_entity_type": PRODUCER_OWNER,
        "source_entity_id": facts.observation_period_start.date().isoformat(),
    }


def assemble_care_status_digest_facts(
    db,
    *,
    health_subject_id: int,
    when=None,
) -> CareSubjectStatusFacts:
    return assemble_care_subject_status_facts(db, health_subject_id=health_subject_id, when=when)
