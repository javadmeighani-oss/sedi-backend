"""Lineage SoT map for KNOW-06 feature projection inputs (reuse only; no duplicate SoT)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LineageSourceOfTruth:
    source: str
    owner_layer: str
    can_project_what: tuple[str, ...]
    lineage_id_available: bool
    verification_state_available: bool
    confidence_available: bool
    gap: Optional[str] = None


# Exact existing authoritative SoTs — never invent LLM patient facts; never duplicate.
EXISTING_SOT_MAP: tuple[LineageSourceOfTruth, ...] = (
    LineageSourceOfTruth(
        source="user_conditions",
        owner_layer="I6/profile",
        can_project_what=("diagnosis", "subtype", "phenotype", "stage", "comorbidity", "disease_duration"),
        lineage_id_available=True,
        verification_state_available=False,
        confidence_available=False,
        gap="verification_state/confidence not native; runtime must surface UNKNOWN when absent",
    ),
    LineageSourceOfTruth(
        source="user_medications",
        owner_layer="I6/profile",
        can_project_what=("prior_current_treatment", "contraindication"),
        lineage_id_available=True,
        verification_state_available=False,
        confidence_available=False,
        gap="contraindication inference not authorized here; treatment assignment lineage only",
    ),
    LineageSourceOfTruth(
        source="user_memory_facts",
        owner_layer="I6",
        can_project_what=(
            "phenotype",
            "comorbidity",
            "pregnancy",
            "lifestyle",
            "contraindication",
            "functional_score",
        ),
        lineage_id_available=True,
        verification_state_available=False,
        confidence_available=True,
        gap="verification_state not native; provenance_class/source only; no silent canonicalization",
    ),
    LineageSourceOfTruth(
        source="physiological_measurements",
        owner_layer="I6/DB03",
        can_project_what=("biomarker", "lab_threshold"),
        lineage_id_available=True,
        verification_state_available=False,
        confidence_available=False,
        gap="current vocab limited (e.g. heart_rate); labs/biomarkers beyond type vocab are GAP",
    ),
    LineageSourceOfTruth(
        source="user_profile_core",
        owner_layer="I6/profile",
        can_project_what=("age", "sex"),
        lineage_id_available=True,
        verification_state_available=False,
        confidence_available=False,
        gap="age derived from birth fields; verification_state not native",
    ),
    LineageSourceOfTruth(
        source="user_profile_knowledge",
        owner_layer="I6/profile",
        can_project_what=("constraints", "preferences"),
        lineage_id_available=True,
        verification_state_available=False,
        confidence_available=False,
        gap="not a clinical diagnosis SoT; constraints only when lineage-backed",
    ),
    LineageSourceOfTruth(
        source="care_episodes",
        owner_layer="I6/care",
        can_project_what=("longitudinal_context_hook",),
        lineage_id_available=True,
        verification_state_available=False,
        confidence_available=False,
        gap="not a diagnosis; I7 owns longitudinal intelligence over episode spine",
    ),
)

LINEAGE_REQUIRED = True
DUPLICATE_SOT_CREATED = False
LLM_INVENTED_USER_FACT_PATH_ALLOWED = False
SILENT_CANONICALIZATION_ALLOWED = False

ALLOWED_SOURCE_RECORD_TYPES = frozenset(s.source for s in EXISTING_SOT_MAP)


def sot_by_source(source: str) -> LineageSourceOfTruth | None:
    for row in EXISTING_SOT_MAP:
        if row.source == source:
            return row
    return None
