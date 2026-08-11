"""Machine-readable source taxonomy export — database is runtime authority."""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import SourceRole, SourceUniverse

TAXONOMY_VERSION = "know01-taxonomy-v1"


def export_source_taxonomy(db: Session) -> Dict[str, Any]:
    extensions = db.query(models.I5SourceRegistryExtension).all()
    roles = db.query(models.I5SourceRegistryRole).all()
    books = db.query(models.I5ReferenceBook).all()
    role_by_profile: Dict[int, List[str]] = {}
    for r in roles:
        role_by_profile.setdefault(r.source_profile_id, []).append(r.role)

    global_sources: List[Dict[str, Any]] = []
    iran_sources: List[Dict[str, Any]] = []
    structured: List[Dict[str, Any]] = []
    trials: List[Dict[str, Any]] = []
    terminology: List[Dict[str, Any]] = []
    regulatory: List[Dict[str, Any]] = []

    for ext in extensions:
        item = {
            "source_profile_id": ext.source_profile_id,
            "publisher_family": ext.publisher_family,
            "authority_class": ext.authority_class,
            "source_universe": ext.source_universe,
            "roles": role_by_profile.get(ext.source_profile_id, []),
            "canonical_home": ext.canonical_home,
            "api_endpoint": ext.api_endpoint,
            "automation_right": ext.automation_right,
            "processing_permission_mode": ext.processing_permission_mode,
            "registry_status": ext.registry_status,
            "credential_authority": ext.credential_authority,
        }
        rs = set(item["roles"])
        if ext.source_universe == SourceUniverse.IRAN_LOCAL_DIRECTORY.value:
            iran_sources.append(item)
        else:
            global_sources.append(item)
        if SourceRole.CLINICAL_TRIAL.value in rs:
            trials.append(item)
        if SourceRole.BIOMEDICAL_TERMINOLOGY.value in rs:
            terminology.append(item)
        if SourceRole.REGULATORY.value in rs:
            regulatory.append(item)
        if ext.api_endpoint or (ext.supported_formats and "JSON" in (ext.supported_formats or "")):
            structured.append(item)

    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "authority": "DATABASE_i5_source_registry_extensions",
        "competing_yaml_source_of_truth": False,
        "GLOBAL_KNOWLEDGE_SOURCES": global_sources,
        "LOCAL_IRAN_DIRECTORY_SOURCES": iran_sources,
        "REFERENCE_BOOK_SOURCES": [
            {
                "book_key": b.book_key,
                "title": b.title,
                "rights_class": b.rights_class,
                "fulltext_automation_permission": b.fulltext_automation_permission,
                "medical_authority_note": b.medical_authority_note,
            }
            for b in books
        ],
        "STRUCTURED_DATA_SOURCES": structured,
        "CLINICAL_TRIAL_SOURCES": trials,
        "TERMINOLOGY_SOURCES": terminology,
        "REGULATORY_SOURCES": regulatory,
    }
