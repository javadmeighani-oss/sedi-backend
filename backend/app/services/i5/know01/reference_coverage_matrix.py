"""Manifest-wide reference catalog coverage matrix (authority ≠ automation rights).

Every Coverage Manifest entity receives an explicit coverage classification.
Placeholders never count toward completeness.
Harrison's / general IM does not auto-cover specialty entities as COVERED.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.app.services.i5.coverage_manifest_loader import (
    EXPECTED_ENTITY_COUNT,
    load_coverage_manifest,
    manifest_path,
)
from backend.app.services.i5.enums import BookRightsClass, RightDecision
from backend.app.services.i5.know01.v1_reference_catalog import (
    ACQ_DENIED,
    ACQ_FULLTEXT_ALLOWED,
    ACQ_METADATA_ONLY,
    ACQ_REVIEW_REQUIRED,
    ACQ_UNKNOWN,
    PLACEHOLDER_BOOK_KEYS,
    V1_AUTHORITATIVE_REFERENCE_CATALOG,
    V1ReferenceBookSpec,
    acquisition_state_for_book,
)


# Coverage cell states (catalog assurance vocabulary).
COVERED = "COVERED"
PARTIAL = "PARTIAL"
MISSING = "MISSING"
METADATA_ONLY_REFERENCE_AVAILABLE = "METADATA_ONLY_REFERENCE_AVAILABLE"
OPEN_OR_AUTOMATABLE_REFERENCE_AVAILABLE = "OPEN_OR_AUTOMATABLE_REFERENCE_AVAILABLE"
REVIEW_REQUIRED = "REVIEW_REQUIRED"

METADATA_VERIFIED = "METADATA_VERIFIED"
METADATA_PARTIALLY_VERIFIED = "METADATA_PARTIALLY_VERIFIED"
METADATA_REVIEW_REQUIRED = "METADATA_REVIEW_REQUIRED"


# Reasonable specialty / domain tokens per manifest entity (not raw book count).
_ENTITY_RELEVANCE_TOKENS: Dict[str, Tuple[str, ...]] = {
    "D01": ("oncology", "cancer", "supportive_cancer", "palliative"),
    "D02": ("respiratory", "pulmonary", "lung", "asthma", "copd"),
    "D03": ("renal", "kidney", "urinary", "nephrology"),
    "D04": ("gastroenterology", "digestive", "gi", "hepatic", "hepatitis"),
    "D05": ("musculoskeletal", "orthopedic", "pain", "rheumatology"),
    "D06": ("dermatology", "skin"),
    "D07": ("ophthalmology", "vision", "eye"),
    "D08": ("ent", "otolaryngology", "hearing", "vestibular", "ear"),
    "D09": ("dental", "oral", "odontology"),
    "D10": ("womens_health", "reproductive", "obstetric", "gynecolog"),
    "D11": ("pediatrics", "adolescent", "child"),
    "D12": ("geriatrics", "aging", "healthy_aging"),
    "D13": ("infectious", "infection", "communicable", "yellow_book", "travel"),
    "D14": ("rare_disease", "genetics", "genereviews"),
    "D15": ("rehabilitation", "physical_medicine", "functional_recovery"),
    "D16": ("palliative", "hospice", "end_of_life"),
    "D17": ("environmental", "occupational", "toxicology"),
    "D18": ("als", "amyotrophic", "neurology", "rehabilitation", "motor_neuron"),
    "D19": ("ms", "multiple_sclerosis", "neurology", "rehabilitation"),
}

# Broad tokens that alone yield PARTIAL (never COVERED for specialty entities).
_BROAD_ONLY_TOKENS = frozenset(
    {
        "general_medicine",
        "clinical_medicine",
        "internal_medicine",
        "emergency",
        "pharmacotherapy",
        "drug_reference",
    }
)


@dataclass
class CatalogCoverageCell:
    entity_id: str
    entity_name: str
    priority: str
    parent_taxonomy: str
    named_references: List[str] = field(default_factory=list)
    specialties: List[str] = field(default_factory=list)
    knowledge_domains: List[str] = field(default_factory=list)
    authority_notes: List[str] = field(default_factory=list)
    rights_states: List[str] = field(default_factory=list)
    acquisition_states: List[str] = field(default_factory=list)
    coverage_status: str = MISSING
    authority_coverage: str = MISSING
    automated_fulltext_acquisition: str = MISSING
    match_strength: str = "NONE"  # PRIMARY | SUPPORTING | BROAD_ONLY | NONE


@dataclass
class ReferenceMetadataAssurance:
    book_key: str
    title: str
    status: str
    missing_fields: List[str] = field(default_factory=list)


def coverage_manifest_authority() -> dict[str, Any]:
    path = manifest_path()
    data = path.read_bytes()
    return {
        "path": str(path).replace("\\", "/"),
        "sha256": hashlib.sha256(data).hexdigest(),
        "entity_count": EXPECTED_ENTITY_COUNT,
        "manifest_version": load_coverage_manifest().get("manifest_version"),
        "authority": load_coverage_manifest().get("authority"),
    }


def _blob(spec: V1ReferenceBookSpec) -> str:
    return " ".join(
        [
            spec.specialty or "",
            spec.knowledge_domains or "",
            spec.disease_coverage or "",
            spec.family or "",
            spec.book_key or "",
            spec.title or "",
        ]
    ).lower()


def _match_entity(spec: V1ReferenceBookSpec, entity_id: str, alias: Optional[str]) -> str:
    """Return PRIMARY | SUPPORTING | BROAD_ONLY | NONE."""
    blob = _blob(spec)
    tokens = list(_ENTITY_RELEVANCE_TOKENS.get(entity_id, ()))
    if alias:
        tokens = list(tokens) + [alias.lower()]
    primary_hits = []
    broad_hits = []
    for tok in tokens:
        t = tok.lower()
        if t in blob:
            if t in _BROAD_ONLY_TOKENS:
                broad_hits.append(t)
            else:
                primary_hits.append(t)
    # Explicit disease alias (ALS/MS/DIABETES) in disease_coverage is PRIMARY.
    dc = (spec.disease_coverage or "").lower()
    if alias and alias.lower() in dc.split(","):
        return "PRIMARY"
    if alias and alias.lower() in dc:
        return "PRIMARY"
    if entity_id in {"D18", "D19"} and any(x in dc for x in ("als", "ms") if alias and x == alias.lower()):
        return "PRIMARY"
    if primary_hits:
        # Specialty specialty match
        specialty = (spec.specialty or "").lower()
        if any(t in specialty for t in primary_hits):
            return "PRIMARY"
        return "SUPPORTING"
    # Broad IM/general only
    for b in _BROAD_ONLY_TOKENS:
        if b in blob:
            return "BROAD_ONLY"
    return "NONE"


def _cell_status_for_matches(
    matches: List[Tuple[V1ReferenceBookSpec, str]],
) -> Tuple[str, str, str]:
    """Return (coverage_status, authority_coverage, automated_fulltext)."""
    if not matches:
        return MISSING, MISSING, MISSING
    strengths = {m[1] for m in matches}
    specs = [m[0] for m in matches]
    acq = []
    for s in specs:
        # Spec-level acquisition mapping (no DB row required)
        ft = s.fulltext_automation_permission.upper()
        rights = s.rights_class.upper()
        if ft == RightDecision.DENIED.value or rights == BookRightsClass.FULLTEXT_TDM_PROHIBITED.value:
            acq.append(ACQ_DENIED)
        elif ft == RightDecision.REVIEW_REQUIRED.value:
            acq.append(ACQ_REVIEW_REQUIRED)
        elif rights == BookRightsClass.METADATA_ONLY.value:
            acq.append(ACQ_METADATA_ONLY)
        elif ft == RightDecision.ALLOWED.value:
            acq.append(ACQ_FULLTEXT_ALLOWED)
        else:
            acq.append(ACQ_UNKNOWN)

    if ACQ_FULLTEXT_ALLOWED in acq:
        auto = OPEN_OR_AUTOMATABLE_REFERENCE_AVAILABLE
    elif ACQ_REVIEW_REQUIRED in acq:
        auto = REVIEW_REQUIRED
    else:
        auto = METADATA_ONLY_REFERENCE_AVAILABLE

    if "PRIMARY" in strengths:
        authority = COVERED
        coverage = COVERED if auto == OPEN_OR_AUTOMATABLE_REFERENCE_AVAILABLE else METADATA_ONLY_REFERENCE_AVAILABLE
        # Authority covered even when fulltext denied
        if coverage == METADATA_ONLY_REFERENCE_AVAILABLE:
            coverage = METADATA_ONLY_REFERENCE_AVAILABLE
        return coverage, authority, auto
    if "SUPPORTING" in strengths:
        return PARTIAL, PARTIAL, auto
    if "BROAD_ONLY" in strengths:
        return PARTIAL, PARTIAL, auto
    return MISSING, MISSING, MISSING


def build_reference_catalog_coverage_matrix(
    catalog: Sequence[V1ReferenceBookSpec] = V1_AUTHORITATIVE_REFERENCE_CATALOG,
) -> List[CatalogCoverageCell]:
    manifest = load_coverage_manifest()
    entities = manifest["entities"]
    named = [s for s in catalog if s.book_key not in PLACEHOLDER_BOOK_KEYS]
    cells: List[CatalogCoverageCell] = []
    for ent in entities:
        eid = str(ent["id"])
        alias = ent.get("alias")
        matches: List[Tuple[V1ReferenceBookSpec, str]] = []
        for spec in named:
            strength = _match_entity(spec, eid, alias)
            if strength == "NONE":
                continue
            # Do not count broad-only as completeness for disease tracks / specialty families
            # when stronger mapping exists elsewhere; still record for PARTIAL.
            matches.append((spec, strength))
        # Prefer non-broad matches for named_references listing
        primaryish = [m for m in matches if m[1] in {"PRIMARY", "SUPPORTING"}]
        listed = primaryish if primaryish else matches
        cov, auth, auto = _cell_status_for_matches(matches)
        # Disease tracks require PRIMARY disease tag for COVERED authority
        if eid in {"D18", "D19"} and not any(m[1] == "PRIMARY" for m in matches):
            cov, auth = (PARTIAL if matches else MISSING), (PARTIAL if matches else MISSING)
        cell = CatalogCoverageCell(
            entity_id=eid,
            entity_name=str(ent.get("name_en") or ""),
            priority=str(ent.get("priority") or ""),
            parent_taxonomy=str(ent.get("parent_taxonomy") or ""),
            named_references=[m[0].book_key for m in listed],
            specialties=sorted({m[0].specialty for m in listed if m[0].specialty}),
            knowledge_domains=sorted(
                {
                    d.strip()
                    for m in listed
                    for d in (m[0].knowledge_domains or "").split(",")
                    if d.strip()
                }
            ),
            authority_notes=[m[0].medical_authority_note for m in listed if m[0].medical_authority_note],
            rights_states=sorted({m[0].rights_class for m in listed}),
            acquisition_states=sorted(
                {
                    ACQ_DENIED
                    if m[0].fulltext_automation_permission == RightDecision.DENIED.value
                    else ACQ_REVIEW_REQUIRED
                    if m[0].fulltext_automation_permission == RightDecision.REVIEW_REQUIRED.value
                    else ACQ_METADATA_ONLY
                    for m in listed
                }
            ),
            coverage_status=cov,
            authority_coverage=auth,
            automated_fulltext_acquisition=auto,
            match_strength=(
                "PRIMARY"
                if any(m[1] == "PRIMARY" for m in matches)
                else "SUPPORTING"
                if any(m[1] == "SUPPORTING" for m in matches)
                else "BROAD_ONLY"
                if matches
                else "NONE"
            ),
        )
        cells.append(cell)
    return cells


def matrix_summary(cells: Sequence[CatalogCoverageCell]) -> dict[str, Any]:
    unmapped = [c for c in cells if c.coverage_status == MISSING and c.match_strength == "NONE"]
    # UNMAPPED means no classification row — every entity must appear; count those still MISSING content
    return {
        "entity_count": len(cells),
        "expected_entity_count": EXPECTED_ENTITY_COUNT,
        "unmapped_manifest_entity_count": 0 if len(cells) == EXPECTED_ENTITY_COUNT else abs(EXPECTED_ENTITY_COUNT - len(cells)),
        "missing_content_entity_count": len(unmapped),
        "missing_entity_ids": [c.entity_id for c in unmapped],
        "covered_authority": sum(1 for c in cells if c.authority_coverage == COVERED),
        "partial": sum(1 for c in cells if c.coverage_status == PARTIAL),
        "metadata_only": sum(1 for c in cells if c.coverage_status == METADATA_ONLY_REFERENCE_AVAILABLE),
        "placeholder_as_completeness_evidence_count": 0,
        "cells": [
            {
                "entity_id": c.entity_id,
                "name": c.entity_name,
                "authority_coverage": c.authority_coverage,
                "coverage_status": c.coverage_status,
                "automated_fulltext": c.automated_fulltext_acquisition,
                "named_references": list(c.named_references),
                "match_strength": c.match_strength,
            }
            for c in cells
        ],
    }


def assure_reference_metadata(
    catalog: Sequence[V1ReferenceBookSpec] = V1_AUTHORITATIVE_REFERENCE_CATALOG,
) -> List[ReferenceMetadataAssurance]:
    out: List[ReferenceMetadataAssurance] = []
    for spec in catalog:
        if spec.book_key in PLACEHOLDER_BOOK_KEYS:
            continue
        missing: List[str] = []
        if not (spec.title or "").strip():
            missing.append("title")
        if not (spec.publisher or "").strip():
            missing.append("publisher")
        if not (spec.authors_editors or "").strip():
            missing.append("authors_editors")
        if not (spec.edition_label or "").strip():
            missing.append("edition")
        if spec.publication_year is None:
            missing.append("year")
        if not spec.isbn and (spec.edition_label or "").lower() != "living":
            missing.append("isbn")
        if missing:
            status = METADATA_REVIEW_REQUIRED if "title" in missing or "publisher" in missing else METADATA_PARTIALLY_VERIFIED
        else:
            status = METADATA_VERIFIED
        out.append(
            ReferenceMetadataAssurance(
                book_key=spec.book_key,
                title=spec.title,
                status=status,
                missing_fields=missing,
            )
        )
    return out
