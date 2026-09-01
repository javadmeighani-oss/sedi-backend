"""I10-B14 CARE_DATA_GAP — bounded device/data continuity semantic for caregivers."""

from __future__ import annotations

from backend.app.services.i10.care_subject_status_facts import (
    CareSubjectDataStatus,
    CareSubjectStatusFacts,
    assemble_care_subject_status_facts,
)
from backend.app.services.i10.policy_types import I10PrivacyClass, I10SemanticFamily

PRODUCER_OWNER = "I10_CARE_DATA_GAP"
DATA_GAP_TRIGGER_STATES = frozenset(
    {
        CareSubjectDataStatus.STALE_DATA.value,
        CareSubjectDataStatus.NO_DATA.value,
    }
)


def build_care_data_gap_occurrence_key(
    *,
    health_subject_id: int,
    gap_state: str,
    episode_end_iso: str,
) -> str:
    return f"i10:care:data_gap:{health_subject_id}:{gap_state}:{episode_end_iso}"


def is_care_data_gap_candidate(facts: CareSubjectStatusFacts) -> bool:
    if facts.data_status not in (CareSubjectDataStatus.STALE_DATA, CareSubjectDataStatus.NO_DATA):
        return False
    if not facts.has_expected_data_source:
        return False
    return True


def render_care_data_gap_body(facts: CareSubjectStatusFacts) -> str:
    if facts.data_status == CareSubjectDataStatus.STALE_DATA:
        return (
            "Device-reported data for your care recipient appears stale according to the latest "
            "daily rollup. This is a data continuity notice, not a medical emergency assessment."
        )
    return (
        "No recent device-reported samples were recorded in the daily rollup for your care recipient. "
        "This is a data continuity notice, not a medical emergency assessment."
    )


def build_care_data_gap_metadata(facts: CareSubjectStatusFacts, *, body: str) -> dict:
    episode_end = (
        facts.latest_bucket_end.date().isoformat()
        if facts.latest_bucket_end is not None
        else facts.observation_period_start.date().isoformat()
    )
    return {
        "title": "Care data continuity",
        "body": body,
        "template_key": "care_data_gap",
        "trigger_reason": "care_data_gap",
        "data_status": facts.data_status.value,
        "gap_episode_end": episode_end,
        "context": {
            "template_key": "care_data_gap",
            "trigger_reason": "care_data_gap",
            "data_status": facts.data_status.value,
        },
        "semantic_family": I10SemanticFamily.CARE_DATA_GAP.value,
        "privacy_class": I10PrivacyClass.HEALTH_SENSITIVE.value,
        "source_entity_type": PRODUCER_OWNER,
        "source_entity_id": episode_end,
    }


def data_gap_occurrence_key_for_facts(facts: CareSubjectStatusFacts) -> str:
    episode_end = (
        facts.latest_bucket_end.date().isoformat()
        if facts.latest_bucket_end is not None
        else facts.observation_period_start.date().isoformat()
    )
    return build_care_data_gap_occurrence_key(
        health_subject_id=facts.health_subject_id,
        gap_state=facts.data_status.value,
        episode_end_iso=episode_end,
    )
