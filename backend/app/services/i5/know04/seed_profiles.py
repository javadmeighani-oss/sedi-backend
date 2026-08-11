"""Seed KNOW-04 connector profiles into DB (registry-linked, not a second source registry)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.know04.guidelines import GUIDELINE_SOURCE_CLASSIFICATIONS
from backend.app.services.i5.know04.terminology import all_terminology_statuses

PROFILES = [
    {
        "connector_key": "pubmed_ncbi_eutils",
        "source_profile_key": "pubmed_ncbi_eutils",
        "source_role": "SCIENTIFIC_LITERATURE",
        "access_mechanism": "OFFICIAL_API",
        "official_authority_note": "NCBI E-utilities (PubMed)",
        "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        "connector_state": "CONNECTOR_READY",
        "live_status": "NOT_EXECUTED",
    },
    {
        "connector_key": "pubmed_central",
        "source_profile_key": "pubmed_central",
        "source_role": "SCIENTIFIC_LITERATURE",
        "access_mechanism": "OFFICIAL_API",
        "official_authority_note": "NCBI PMC OA + E-utilities (rights-aware fulltext)",
        "base_url": "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi",
        "connector_state": "CONNECTOR_READY",
        "live_status": "NOT_EXECUTED",
        "notes": "PMC_PRESENT != FULL_TEXT_STORAGE_ALLOWED",
    },
    {
        "connector_key": "clinicaltrials_gov_api_v2",
        "source_profile_key": "clinicaltrials_gov_api_v2",
        "source_role": "CLINICAL_TRIAL",
        "access_mechanism": "OFFICIAL_API",
        "official_authority_note": "ClinicalTrials.gov API v2",
        "base_url": "https://clinicaltrials.gov/api/v2",
        "connector_state": "CONNECTOR_READY",
        "live_status": "NOT_EXECUTED",
        "notes": "TRIAL_REGISTRATION != PROVEN_TREATMENT",
    },
    {
        "connector_key": "who_news_discovery",
        "source_profile_key": "who_news",
        "source_role": "NEWS_OR_DISCOVERY_SIGNAL",
        "access_mechanism": "OFFICIAL_FEED",
        "official_authority_note": "WHO official news RSS — discovery signal only (NOT guideline authority)",
        "base_url": "https://www.who.int/rss-feeds/news-english.xml",
        "connector_state": "CONNECTOR_READY",
        "live_status": "NOT_EXECUTED",
        "notes": "NEWS != GUIDELINE; NF14 semantics",
    },
    {
        "connector_key": "who_guideline_catalogue",
        "source_profile_key": "who_guideline_catalogue",
        "source_role": "CLINICAL_GUIDELINE",
        "access_mechanism": "OFFICIAL_HTML_ONLY",
        "official_authority_note": "WHO GRC publications catalogue — guideline pointer (NOT recommendation parser)",
        "base_url": "https://www.who.int/publications/who-guidelines",
        "connector_state": "CONNECTOR_READY",
        "live_status": "NOT_EXECUTED",
        "notes": "catalogue_semantics=OFFICIAL_HTML_CATALOGUE; recommendation_extraction=NOT_EXERCISED at canary",
    },
]


def seed_know04_connector_profiles(db: Session) -> dict[str, Any]:
    for p in PROFILES:
        row = db.query(models.I5ConnectorProfile).filter_by(connector_key=p["connector_key"]).first()
        if row is None:
            row = models.I5ConnectorProfile(connector_key=p["connector_key"])
            db.add(row)
        for k, v in p.items():
            setattr(row, k, v)
        row.updated_at = datetime.utcnow()

    # Registry-ready guideline families with honest blockers
    for key, meta in GUIDELINE_SOURCE_CLASSIFICATIONS.items():
        ck = f"guideline:{key}"
        row = db.query(models.I5ConnectorProfile).filter_by(connector_key=ck).first()
        if row is None:
            row = models.I5ConnectorProfile(connector_key=ck)
            db.add(row)
        row.source_profile_key = key
        if key == "who_news":
            row.source_role = "NEWS_OR_DISCOVERY_SIGNAL"
        else:
            row.source_role = "CLINICAL_GUIDELINE"
        row.access_mechanism = meta["access_mechanism"]
        row.official_authority_note = meta["authority"]
        row.base_url = meta.get("canary_url") or meta.get("canary_feed") or None
        row.rights_blocker = meta.get("blocker") or None
        if meta["access_mechanism"] in {"MANUAL_REVIEW_REQUIRED", "NO_SUPPORTED_AUTOMATION"}:
            row.connector_state = "BLOCKED_BY_RIGHTS"
            row.live_status = "NOT_EXECUTED_RIGHTS_BLOCK"
        elif meta.get("blocker"):
            row.connector_state = "CONNECTOR_READY"
            row.live_status = "NOT_EXECUTED_RIGHTS_BLOCK" if "RIGHTS" in meta["blocker"] else "NOT_EXECUTED"
        else:
            row.connector_state = "CONNECTOR_READY"
            row.live_status = "NOT_EXECUTED"
        row.updated_at = datetime.utcnow()

    for st in all_terminology_statuses():
        ck = f"terminology:{st.system.lower()}"
        row = db.query(models.I5ConnectorProfile).filter_by(connector_key=ck).first()
        if row is None:
            row = models.I5ConnectorProfile(connector_key=ck)
            db.add(row)
        row.source_profile_key = st.system
        row.source_role = "BIOMEDICAL_TERMINOLOGY"
        row.access_mechanism = "OFFICIAL_API" if st.system in {"ICD11", "MESH"} else "OFFICIAL_DOWNLOAD"
        row.official_authority_note = st.notes
        row.connector_state = st.connector_state
        row.live_status = st.live_status
        row.rights_blocker = st.rights_status
        row.updated_at = datetime.utcnow()

    db.flush()
    return {
        "profiles": db.query(models.I5ConnectorProfile).count(),
        "production_crawler_activated": False,
        "production_rag_activated": False,
        "mass_ingestion_executed": False,
        "p0_specific_branching": 0,
    }
