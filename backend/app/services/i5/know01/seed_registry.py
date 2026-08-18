"""I5-KNOW-01 initial Trusted Source Registry seeds (listing ≠ automation approval).

BOOTSTRAP ONLY: runtime crawler activation authority is
``backend/config/i5/multisource_activation_allowlist_v1.yaml`` (trusted_source_manifest).
This module seeds GSP/registry overlay for discovery; it MUST NOT independently
enable fetch or runtime eligibility.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from sqlalchemy.orm import Session

from backend.app.services.i5.enums import (
    BookRightsClass,
    P0DiseaseRelevance,
    ProcessingPermissionMode,
    RightDecision,
    SourceAuthorityClass,
    SourceRole,
    SourceUniverse,
)
from backend.app.services.i5.know01.book_registry import add_edition, upsert_reference_book
from backend.app.services.i5.know01.coverage_gaps import detect_p0_foundation_gaps
from backend.app.services.i5.know01.registry_service import ensure_gsp, upsert_registry_extension
from backend.app.services.i5.know01.v1_reference_catalog import seed_v1_authoritative_reference_catalog

_U = RightDecision.UNKNOWN.value
_BLOCKED = ProcessingPermissionMode.FULLTEXT_AUTOMATION_BLOCKED.value


def _rights_unknown(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "access_right": _U,
        "automation_right": _U,
        "tdm_right": _U,
        "transform_right": _U,
        "retain_raw_right": _U,
        "retain_derived_right": _U,
        "redistribution_right": _U,
        "robots_state": "UNKNOWN",
        "processing_permission_mode": _BLOCKED,
        "review_stage": "RIGHTS_REVIEW",
        "registry_status": "DISCOVERED",
        "current_rights_review": (
            "FACT: endpoints listed; INFERENCE:none; UNVERIFIED:automation/TDM; REVIEW_REQUIRED=YES"
        ),
    }
    base.update(overrides)
    return base


GLOBAL_SEEDS: Sequence[Dict[str, Any]] = (
    {
        "key": "who_int",
        "publisher_family": "WHO",
        "authority_class": SourceAuthorityClass.GLOBAL_INTERGOVERNMENTAL.value,
        "roles": [SourceRole.PUBLIC_HEALTH.value, SourceRole.CLINICAL_GUIDELINE.value],
        "canonical_home": "https://www.who.int",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.SUPPORTING.value,
            "MS": P0DiseaseRelevance.SUPPORTING.value,
            "DIABETES": P0DiseaseRelevance.IMPORTANT.value,
        },
        "knowledge_domains": "public_health,guidelines,prevention",
    },
    {
        # Alias identity for KNOW-04/05 connector key (registry bootstrap ≠ activation).
        "key": "who_guideline_catalogue",
        "publisher_family": "WHO",
        "authority_class": SourceAuthorityClass.GLOBAL_INTERGOVERNMENTAL.value,
        "roles": [SourceRole.CLINICAL_GUIDELINE.value],
        "canonical_home": "https://www.who.int",
        "supported_formats": "HTML,RSS,ATOM",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.SUPPORTING.value,
            "MS": P0DiseaseRelevance.SUPPORTING.value,
            "DIABETES": P0DiseaseRelevance.IMPORTANT.value,
        },
        "knowledge_domains": "guidelines",
        "notes": "REGISTRY_ALIAS_FOR_KNOW04_CONNECTOR; REGISTRY_ENTRY!=AUTOMATION_APPROVED",
    },
    {
        "key": "nih_nlm",
        "publisher_family": "NIH/NLM",
        "authority_class": SourceAuthorityClass.NATIONAL_MEDICAL_LIBRARY.value,
        "roles": [SourceRole.SCIENTIFIC_LITERATURE.value, SourceRole.MEDICAL_REFERENCE_BOOK.value],
        "canonical_home": "https://www.nlm.nih.gov",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.SUPPORTING.value,
            "MS": P0DiseaseRelevance.SUPPORTING.value,
            "DIABETES": P0DiseaseRelevance.SUPPORTING.value,
        },
    },
    {
        "key": "pubmed_ncbi_eutils",
        "publisher_family": "NCBI/NLM PubMed",
        "authority_class": SourceAuthorityClass.NATIONAL_MEDICAL_LIBRARY.value,
        "roles": [SourceRole.SCIENTIFIC_LITERATURE.value],
        "canonical_home": "https://pubmed.ncbi.nlm.nih.gov",
        "api_endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        "supported_formats": "JSON,XML",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.IMPORTANT.value,
            "MS": P0DiseaseRelevance.IMPORTANT.value,
            "DIABETES": P0DiseaseRelevance.IMPORTANT.value,
        },
        "notes": "KNOW-04 owns full PubMed connector; KNOW-01 registers identity only",
    },
    {
        "key": "pubmed_central",
        "publisher_family": "PMC",
        "authority_class": SourceAuthorityClass.OPEN_ACCESS_REPOSITORY.value,
        "roles": [SourceRole.SCIENTIFIC_LITERATURE.value],
        "canonical_home": "https://www.ncbi.nlm.nih.gov/pmc",
        "supported_formats": "JATS_XML,PDF_TEXT,HTML",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.IMPORTANT.value,
            "MS": P0DiseaseRelevance.IMPORTANT.value,
            "DIABETES": P0DiseaseRelevance.IMPORTANT.value,
        },
    },
    {
        "key": "ncbi_bookshelf",
        "publisher_family": "NCBI Bookshelf",
        "authority_class": SourceAuthorityClass.NATIONAL_MEDICAL_LIBRARY.value,
        "roles": [SourceRole.MEDICAL_REFERENCE_BOOK.value],
        "canonical_home": "https://www.ncbi.nlm.nih.gov/books",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.SUPPORTING.value,
            "MS": P0DiseaseRelevance.SUPPORTING.value,
            "DIABETES": P0DiseaseRelevance.SUPPORTING.value,
        },
    },
    {
        "key": "medlineplus",
        "publisher_family": "MedlinePlus",
        "authority_class": SourceAuthorityClass.NATIONAL_MEDICAL_LIBRARY.value,
        "roles": [SourceRole.PUBLIC_HEALTH.value, SourceRole.LIFESTYLE.value],
        "canonical_home": "https://medlineplus.gov",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.SUPPORTING.value,
            "MS": P0DiseaseRelevance.SUPPORTING.value,
            "DIABETES": P0DiseaseRelevance.IMPORTANT.value,
        },
    },
    {
        "key": "cdc_gov",
        "publisher_family": "CDC",
        "authority_class": SourceAuthorityClass.OFFICIAL_PUBLIC_HEALTH.value,
        "roles": [SourceRole.PUBLIC_HEALTH.value, SourceRole.PREVENTION.value],
        "canonical_home": "https://www.cdc.gov",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.SUPPORTING.value,
            "MS": P0DiseaseRelevance.SUPPORTING.value,
            "DIABETES": P0DiseaseRelevance.PRIMARY.value,
        },
    },
    {
        "key": "nimh_nih",
        "publisher_family": "NIMH",
        "authority_class": SourceAuthorityClass.OFFICIAL_PUBLIC_HEALTH.value,
        "roles": [SourceRole.MENTAL_HEALTH.value, SourceRole.PSYCHOLOGY.value],
        "canonical_home": "https://www.nimh.nih.gov",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.SUPPORTING.value,
            "MS": P0DiseaseRelevance.SUPPORTING.value,
            "DIABETES": P0DiseaseRelevance.SUPPORTING.value,
        },
    },
    {
        "key": "fda_openfda",
        "publisher_family": "FDA/openFDA",
        "authority_class": SourceAuthorityClass.REGULATORY_AUTHORITY.value,
        "roles": [SourceRole.REGULATORY.value, SourceRole.DRUG_INFORMATION.value],
        "canonical_home": "https://open.fda.gov",
        "api_endpoint": "https://api.fda.gov",
        "supported_formats": "JSON",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.SUPPORTING.value,
            "MS": P0DiseaseRelevance.SUPPORTING.value,
            "DIABETES": P0DiseaseRelevance.IMPORTANT.value,
        },
    },
    {
        "key": "clinicaltrials_gov_api_v2",
        "publisher_family": "ClinicalTrials.gov",
        "authority_class": SourceAuthorityClass.CLINICAL_TRIAL_REGISTRY.value,
        "roles": [SourceRole.CLINICAL_TRIAL.value],
        "canonical_home": "https://clinicaltrials.gov",
        "api_endpoint": "https://clinicaltrials.gov/api/v2",
        "supported_formats": "JSON",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.IMPORTANT.value,
            "MS": P0DiseaseRelevance.IMPORTANT.value,
            "DIABETES": P0DiseaseRelevance.IMPORTANT.value,
        },
        "notes": "KNOW-04 connector; patient matching is I8 — not I5",
    },
    {
        "key": "nice_uk",
        "publisher_family": "NICE",
        "authority_class": SourceAuthorityClass.SPECIALTY_GUIDELINE_BODY.value,
        "roles": [SourceRole.CLINICAL_GUIDELINE.value],
        "canonical_home": "https://www.nice.org.uk",
        "country": "GB",
        "jurisdiction": "UK",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.IMPORTANT.value,
            "MS": P0DiseaseRelevance.IMPORTANT.value,
            "DIABETES": P0DiseaseRelevance.IMPORTANT.value,
        },
    },
    {
        "key": "nhs_uk",
        "publisher_family": "NHS",
        "authority_class": SourceAuthorityClass.NATIONAL_HEALTH_AUTHORITY.value,
        "roles": [SourceRole.PUBLIC_HEALTH.value, SourceRole.LIFESTYLE.value],
        "canonical_home": "https://www.nhs.uk",
        "country": "GB",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.SUPPORTING.value,
            "MS": P0DiseaseRelevance.SUPPORTING.value,
            "DIABETES": P0DiseaseRelevance.IMPORTANT.value,
        },
    },
    {
        "key": "cochrane",
        "publisher_family": "Cochrane",
        "authority_class": SourceAuthorityClass.SYSTEMATIC_REVIEW_AUTHORITY.value,
        "roles": [SourceRole.SYSTEMATIC_REVIEW.value],
        "canonical_home": "https://www.cochranelibrary.com",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.IMPORTANT.value,
            "MS": P0DiseaseRelevance.IMPORTANT.value,
            "DIABETES": P0DiseaseRelevance.IMPORTANT.value,
        },
    },
    {
        "key": "aan",
        "publisher_family": "AAN",
        "authority_class": SourceAuthorityClass.PROFESSIONAL_MEDICAL_SOCIETY.value,
        "roles": [SourceRole.CLINICAL_GUIDELINE.value],
        "canonical_home": "https://www.aan.com",
        "specialty_domains": "neurology",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.PRIMARY.value,
            "MS": P0DiseaseRelevance.PRIMARY.value,
            "DIABETES": P0DiseaseRelevance.NOT_SPECIFIC.value,
        },
    },
    {
        "key": "ean",
        "publisher_family": "EAN",
        "authority_class": SourceAuthorityClass.PROFESSIONAL_MEDICAL_SOCIETY.value,
        "roles": [SourceRole.CLINICAL_GUIDELINE.value],
        "canonical_home": "https://www.ean.org",
        "specialty_domains": "neurology",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.IMPORTANT.value,
            "MS": P0DiseaseRelevance.IMPORTANT.value,
            "DIABETES": P0DiseaseRelevance.NOT_SPECIFIC.value,
        },
    },
    {
        "key": "ectrims",
        "publisher_family": "ECTRIMS",
        "authority_class": SourceAuthorityClass.SPECIALTY_GUIDELINE_BODY.value,
        "roles": [SourceRole.CLINICAL_GUIDELINE.value],
        "canonical_home": "https://www.ectrims.eu",
        "specialty_domains": "multiple_sclerosis",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.NOT_SPECIFIC.value,
            "MS": P0DiseaseRelevance.PRIMARY.value,
            "DIABETES": P0DiseaseRelevance.NOT_SPECIFIC.value,
        },
    },
    {
        "key": "ada_diabetes",
        "publisher_family": "ADA",
        "authority_class": SourceAuthorityClass.SPECIALTY_GUIDELINE_BODY.value,
        "roles": [SourceRole.CLINICAL_GUIDELINE.value, SourceRole.NUTRITION.value],
        "canonical_home": "https://diabetes.org",
        "specialty_domains": "diabetes",
        "p0_tags": {
            "ALS": P0DiseaseRelevance.NOT_SPECIFIC.value,
            "MS": P0DiseaseRelevance.NOT_SPECIFIC.value,
            "DIABETES": P0DiseaseRelevance.PRIMARY.value,
        },
        "notes": "DIABETES_D20_RUNTIME_MUTATION=NO in KNOW-01",
    },
)

from backend.app.services.i5.know01.catalog12_specialty_authorities import (  # noqa: E402
    catalog12_registry_seeds,
)

GLOBAL_SEEDS = tuple(GLOBAL_SEEDS) + catalog12_registry_seeds()

IRAN_SEEDS: Sequence[Dict[str, Any]] = (
    {
        "key": "iran_irimc_physician_licensing",
        "publisher_family": "IRIMC",
        "authority_class": SourceAuthorityClass.IRAN_PROVIDER_LICENSING_AUTHORITY.value,
        "roles": [SourceRole.IRAN_PHYSICIAN_DIRECTORY.value, SourceRole.LOCAL_SERVICE_METADATA.value],
        "canonical_home": "https://irimc.org",
        "country": "IR",
        "jurisdiction": "IR",
        "credential_authority": True,
        "languages": "fa",
        "notes": (
            "FACT: Medical Council is licensing-class candidate; "
            "UNVERIFIED: machine-readable bulk export; REVIEW_REQUIRED rights"
        ),
    },
    {
        "key": "iran_moh_hospital_authority",
        "publisher_family": "Iran MoHME",
        "authority_class": SourceAuthorityClass.IRAN_MINISTRY_HEALTH.value,
        "roles": [SourceRole.IRAN_HOSPITAL_DIRECTORY.value, SourceRole.LOCAL_SERVICE_METADATA.value],
        "canonical_home": "https://behdasht.gov.ir",
        "country": "IR",
        "credential_authority": True,
        "languages": "fa",
        "notes": "Hospital/facility authority candidate; not clinical KU",
    },
    {
        "key": "iran_clinic_directory_candidate",
        "publisher_family": "Iran MoHME / University directories",
        "authority_class": SourceAuthorityClass.IRAN_HOSPITAL_AUTHORITY.value,
        "roles": [SourceRole.IRAN_CLINIC_DIRECTORY.value, SourceRole.LOCAL_SERVICE_METADATA.value],
        "canonical_home": "https://behdasht.gov.ir",
        "country": "IR",
        "credential_authority": False,
        "notes": (
            "NEXT_SCHEMA_GATE_REQUIRED: clinic/outpatient facility entity model; "
            "source registry only in KNOW-01"
        ),
    },
    {
        "key": "iran_lab_authority_candidate_moh",
        "publisher_family": "Iran MoHME laboratory regulation candidate",
        "authority_class": SourceAuthorityClass.IRAN_REFERENCE_LAB_AUTHORITY.value,
        "roles": [SourceRole.IRAN_LABORATORY_DIRECTORY.value],
        "canonical_home": "https://behdasht.gov.ir",
        "country": "IR",
        "credential_authority": False,
        "notes": "CAP24: candidate only; nationwide machine-readable clinical lab directory NOT verified",
    },
    {
        "key": "iran_lab_secondary_corroboration",
        "publisher_family": "Secondary lab directory corroboration",
        "authority_class": SourceAuthorityClass.SECONDARY_CORROBORATION.value,
        "roles": [SourceRole.IRAN_LABORATORY_DIRECTORY.value],
        "country": "IR",
        "credential_authority": False,
        "notes": "Must not become primary credential authority",
    },
    {
        "key": "iran_commercial_directory_example",
        "publisher_family": "Commercial healthcare directory (example seed)",
        "authority_class": SourceAuthorityClass.COMMERCIAL_DIRECTORY.value,
        "roles": [SourceRole.LOCAL_SERVICE_METADATA.value],
        "country": "IR",
        "credential_authority": False,
        "notes": "COMMERCIAL_DIRECTORY cannot be primary credential authority",
    },
)


def seed_know01_registry(db: Session) -> Dict[str, Any]:
    """Seed GSP + registry overlay + books + coverage gaps. Does not activate automation."""
    seeded_keys: List[str] = []
    for spec in GLOBAL_SEEDS:
        gsp = ensure_gsp(db, canonical_key=f"know01:{spec['key']}", locator=None)
        fields = _rights_unknown(
            country=spec.get("country"),
            jurisdiction=spec.get("jurisdiction"),
            languages=spec.get("languages", "en"),
            knowledge_domains=spec.get("knowledge_domains"),
            specialty_domains=spec.get("specialty_domains"),
            canonical_home=spec.get("canonical_home"),
            api_endpoint=spec.get("api_endpoint"),
            supported_formats=spec.get("supported_formats"),
            notes=spec.get("notes") or "REGISTRY_ENTRY!=AUTOMATION_APPROVED",
            credential_authority=False,
        )
        fields = {k: v for k, v in fields.items() if v is not None}
        upsert_registry_extension(
            db,
            source_profile_id=gsp.id,
            source_universe=SourceUniverse.GLOBAL_KNOWLEDGE.value,
            authority_class=spec["authority_class"],
            publisher_family=spec["publisher_family"],
            roles=spec["roles"],
            p0_tags=spec.get("p0_tags"),
            **fields,
        )
        seeded_keys.append(spec["key"])

    for spec in IRAN_SEEDS:
        gsp = ensure_gsp(db, canonical_key=f"know01:{spec['key']}", locator=None)
        fields = _rights_unknown(
            country=spec.get("country", "IR"),
            jurisdiction=spec.get("jurisdiction", "IR"),
            languages=spec.get("languages", "fa"),
            canonical_home=spec.get("canonical_home"),
            notes=(spec.get("notes") or "") + " | IRAN_DIRECTORY!=CLINICAL_KU",
            credential_authority=bool(spec.get("credential_authority", False)),
        )
        fields = {k: v for k, v in fields.items() if v is not None}
        upsert_registry_extension(
            db,
            source_profile_id=gsp.id,
            source_universe=SourceUniverse.IRAN_LOCAL_DIRECTORY.value,
            authority_class=spec["authority_class"],
            publisher_family=spec["publisher_family"],
            roles=spec["roles"],
            **fields,
        )
        seeded_keys.append(spec["key"])

    open_book = upsert_reference_book(
        db,
        book_key="ncbi_bookshelf_open_example",
        title="NCBI Bookshelf open/reference seed",
        publisher="NCBI Bookshelf",
        rights_class=BookRightsClass.OPEN_LICENSE_RESTRICTED.value,
        specialty="general",
        disease_coverage="ALS,MS,DIABETES",
        medical_authority_note="HIGH_LIBRARY_AUTHORITY",
        automation_tdm_permission=RightDecision.UNKNOWN.value,
        fulltext_automation_permission=RightDecision.REVIEW_REQUIRED.value,
        retention_policy="UNKNOWN_PENDING_RIGHTS",
        canonical_access_route="https://www.ncbi.nlm.nih.gov/books",
    )
    add_edition(db, book_id=open_book.id, edition_label="current", is_current=True, publication_year=2024)

    commercial = upsert_reference_book(
        db,
        book_key="commercial_medical_reference_metadata_only",
        title="Commercial medical reference (metadata-only seed)",
        publisher="Licensed commercial publisher",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        specialty="clinical_medicine",
        medical_authority_note="HIGH",
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    )
    add_edition(db, book_id=commercial.id, edition_label="latest", is_current=True)
    add_edition(db, book_id=commercial.id, edition_label="prior", is_current=False)

    catalog = seed_v1_authoritative_reference_catalog(db)

    gaps = detect_p0_foundation_gaps(db)
    db.flush()
    return {
        "seeded_source_keys": seeded_keys,
        "books": [open_book.book_key, commercial.book_key] + list(catalog["book_keys"]),
        "v1_authoritative_catalog": catalog,
        "coverage_gaps": len(gaps),
        "automation_approved_count": 0,
        "diabetes_d20_runtime_mutation": False,
    }
