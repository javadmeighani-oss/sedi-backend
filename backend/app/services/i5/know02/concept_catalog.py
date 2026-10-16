"""Governed clinical concept catalog: concepts, EN/FA/AR labels and KU semantic links.

Reuses the KNOW02 taxonomy tables (I5ClinicalConcept / Label / KnowledgeUnitConcept /
KnowledgeUnitDimension). No classifier, no translation service: concept identity comes
from governed URL needles, dimensions from section headings, and a label is verified only
when its status is OFFICIAL_SOURCE_TITLE or FOUNDER_APPROVED (ledger D-010).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.know02.taxonomy import (
    link_ku_concept,
    link_ku_dimension,
    upsert_concept,
    upsert_label,
)

CATALOG_RELATIVE = Path("backend/config/i5/clinical_concept_catalog_v1.yaml")
VERIFIED_LABEL_STATUSES = frozenset({"OFFICIAL_SOURCE_TITLE", "FOUNDER_APPROVED"})
LABEL_STATUSES = VERIFIED_LABEL_STATUSES | {"MODEL_ASSISTED_DRAFT"}

# Section heading / key keywords -> KnowledgeDimensionCode (first match wins).
_DIMENSION_RULES: tuple[tuple[str, str], ...] = (
    (r"symptom|signs?\b", "SYMPTOMS"),
    (r"diagnos|tests?\b|screening", "DIAGNOSIS"),
    (r"medicine|medication|drug", "PHARMACOLOGICAL_TREATMENT"),
    (r"treat|therap|surgery", "OTHER_INTERVENTION"),
    (r"cause|why .* happen", "ETIOLOGY"),
    (r"risk", "RISK_FACTORS"),
    (r"prevent|lower your|reduce your|protect", "PREVENTION"),
    (r"inherit|genetic|gene", "GENETICS"),
    (r"complication", "COMPLICATIONS"),
    (r"outlook|prognosis|progress", "PROGNOSIS"),
    (r"how common|frequency|statistic|epidemiolog", "EPIDEMIOLOGY"),
    (r"types?\b|kinds? of", "SUBTYPES"),
    (r"living with|coping|cope|self[- ]help|tips|manag|things you can try|what you can do", "SELF_CARE"),
    (r"care|support|help", "CARE"),
    (r"diet|eat|food|nutrition|sugar|fat\b|vitamin", "DIET"),
    (r"exercise|activity|strength|balance|fitness", "PHYSICAL_ACTIVITY"),
    (r"sleep", "SLEEP"),
    (r"stress|anxiety|mood|wellbeing|mental", "MENTAL_HEALTH"),
    (r"intro|overview|summary|description|what is|what are|about|basics|key points", "DEFINITION"),
)


class ConceptCatalogError(ValueError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


@lru_cache(maxsize=1)
def load_concept_catalog() -> dict[str, Any]:
    path = _repo_root() / CATALOG_RELATIVE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    keys: set[str] = set()
    for concept in data.get("concepts") or []:
        key = str(concept.get("concept_key") or "")
        if not key or key in keys:
            raise ConceptCatalogError(f"CONCEPT_KEY_INVALID_OR_DUPLICATE:{key}")
        keys.add(key)
        for label in concept.get("labels") or []:
            if str(label.get("status")) not in LABEL_STATUSES:
                raise ConceptCatalogError(f"LABEL_STATUS_INVALID:{key}:{label.get('status')}")
            if str(label.get("language")) not in {"en", "fa", "ar"}:
                raise ConceptCatalogError(f"LABEL_LANGUAGE_INVALID:{key}:{label.get('language')}")
    return data


def concept_key_for_url(url: Optional[str]) -> Optional[str]:
    """First catalog concept whose governed URL needle occurs in the URL."""
    sample = (url or "").casefold()
    if not sample:
        return None
    for concept in load_concept_catalog().get("concepts") or []:
        if any(str(n).casefold() in sample for n in concept.get("url_needles") or []):
            return str(concept["concept_key"])
    return None


def dimension_for_section(section_key: Optional[str]) -> Optional[str]:
    """Dimension code implied by a section key/heading slug (None when no rule applies)."""
    text = (section_key or "").split(":", 1)[-1].replace("-", " ").casefold()
    if not text:
        return None
    for pattern, code in _DIMENSION_RULES:
        if re.search(pattern, text):
            return code
    return None


def ensure_concept_catalog(db: Session) -> dict[str, int]:
    """Idempotently upsert catalog concepts and labels (verification follows status)."""
    concepts = labels = verified = 0
    for item in load_concept_catalog().get("concepts") or []:
        concept = upsert_concept(
            db,
            concept_key=str(item["concept_key"]),
            preferred_name=str(item["preferred_name"]),
            concept_type=str(item["concept_type"]),
            root_category=item.get("root_category"),
        )
        concepts += 1
        for label in item.get("labels") or []:
            status = str(label["status"])
            is_verified = status in VERIFIED_LABEL_STATUSES
            note = f"{status}"
            if label.get("source"):
                note += f";source={label['source']}"
            if label.get("approved_on"):
                note += f";approved_on={label['approved_on']}"
            upsert_label(
                db,
                concept_id=int(concept.id),
                language=str(label["language"]),
                label_kind=str(label.get("kind") or "PREFERRED"),
                label_text=str(label["text"]),
                verified=is_verified,
                provenance_note=f"{note};catalog={load_concept_catalog().get('catalog_version')}",
            )
            labels += 1
            verified += int(is_verified)
    return {"concepts": concepts, "labels": labels, "verified_labels": verified}


def link_knowledge_unit_semantics(
    db: Session,
    *,
    knowledge_unit_id: int,
    canonical_url: Optional[str],
    section_key: Optional[str],
) -> dict[str, Optional[str]]:
    """Link a KU to its catalog concept (by URL) and dimension (by section). Idempotent."""
    concept_key = concept_key_for_url(canonical_url)
    dimension = dimension_for_section(section_key)
    linked_concept: Optional[str] = None
    if concept_key:
        concept = db.query(models.I5ClinicalConcept).filter_by(concept_key=concept_key).first()
        if concept is not None:
            link_ku_concept(db, knowledge_unit_id=int(knowledge_unit_id), concept_id=int(concept.id))
            linked_concept = concept_key
    if dimension:
        link_ku_dimension(db, knowledge_unit_id=int(knowledge_unit_id), dimension_code=dimension)
    return {"concept_key": linked_concept, "dimension_code": dimension}


__all__ = [
    "CATALOG_RELATIVE",
    "ConceptCatalogError",
    "VERIFIED_LABEL_STATUSES",
    "concept_key_for_url",
    "dimension_for_section",
    "ensure_concept_catalog",
    "link_knowledge_unit_semantics",
    "load_concept_catalog",
]
