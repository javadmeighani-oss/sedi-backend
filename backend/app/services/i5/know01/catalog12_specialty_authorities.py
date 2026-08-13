"""Catalog-12 specialty authorities (KNOW01 closure + governed one-shot canary).

Listing a source here is NOT weekly enablement.
UNATTENDED_WEEKLY_ENABLED=NO for every Catalog-12 source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from backend.app.services.i5.enums import (
    BookRightsClass,
    P0DiseaseRelevance,
    RightDecision,
    SourceAuthorityClass,
    SourceRole,
)

CATALOG12_CELL_IDS: Tuple[str, ...] = (
    "D01",
    "D02",
    "D03",
    "D05",
    "D06",
    "D07",
    "D09",
    "D10",
    "D11",
    "D13",
    "D16",
    "D17",
)

WAVE_1: Tuple[str, ...] = ("D01", "D02", "D03", "D10")
WAVE_2: Tuple[str, ...] = ("D11", "D13", "D16", "D05")
WAVE_3: Tuple[str, ...] = ("D06", "D07", "D09", "D17")


@dataclass(frozen=True)
class Catalog12CellAuthority:
    cell_id: str
    cell_name: str
    original_closure_criterion: str
    book_key: str
    source_key: str
    primary_authority: str
    primary_organization: str
    primary_domain: str
    authority_tier: str
    secondary_authority: str
    access_route: str
    automation_state: str
    rights_state: str
    raw_retention: str
    derived_retention: str
    canary_url: str
    canonical_home: str
    specialty: str
    knowledge_domains: str
    disease_coverage: str
    title: str
    publisher: str
    medical_authority_note: str
    authority_class: str
    roles: Tuple[str, ...]
    unattended_weekly_enabled: bool = False


_PD = BookRightsClass.PUBLIC_DOMAIN.value
_ALLOWED = RightDecision.ALLOWED.value
_REVIEW = RightDecision.REVIEW_REQUIRED.value


CATALOG12_CELLS: Sequence[Catalog12CellAuthority] = (
    Catalog12CellAuthority(
        cell_id="D01",
        cell_name="Oncology and supportive cancer care",
        original_closure_criterion="specialty oncology reference in catalog (PRIMARY, not BROAD_ONLY)",
        book_key="nci_pdq_cancer_information",
        source_key="nci_pdq_oncology",
        primary_authority="NCI PDQ Cancer Information Summaries",
        primary_organization="National Cancer Institute (NIH)",
        primary_domain="cancer.gov",
        authority_tier="NATIONAL_SPECIALTY_INSTITUTE",
        secondary_authority="NONE",
        access_route="OFFICIAL_PUBLIC_WEB",
        automation_state="ONE_SHOT_CANARY_ALLOWED",
        rights_state="US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
        raw_retention="DENIED",
        derived_retention="ALLOWED",
        canary_url="https://www.cancer.gov/publications/pdq",
        canonical_home="https://www.cancer.gov",
        specialty="oncology",
        knowledge_domains="oncology,cancer,supportive_cancer",
        disease_coverage="cancer,oncology",
        title="NCI PDQ Cancer Information Summaries (living)",
        publisher="National Cancer Institute",
        medical_authority_note="HIGH_OFFICIAL_ONCOLOGY_PDQ",
        authority_class=SourceAuthorityClass.NATIONAL_HEALTH_AUTHORITY.value,
        roles=(SourceRole.PUBLIC_HEALTH.value, SourceRole.MEDICAL_REFERENCE_BOOK.value),
    ),
    Catalog12CellAuthority(
        cell_id="D02",
        cell_name="Respiratory health and diseases",
        original_closure_criterion="specialty respiratory reference in catalog (PRIMARY, not BROAD_ONLY)",
        book_key="nhlbi_lung_health_information",
        source_key="nhlbi_respiratory",
        primary_authority="NHLBI Lung Health Information",
        primary_organization="National Heart, Lung, and Blood Institute (NIH)",
        primary_domain="nhlbi.nih.gov",
        authority_tier="NATIONAL_SPECIALTY_INSTITUTE",
        secondary_authority="NONE",
        access_route="OFFICIAL_PUBLIC_WEB",
        automation_state="ONE_SHOT_CANARY_ALLOWED",
        rights_state="US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
        raw_retention="DENIED",
        derived_retention="ALLOWED",
        canary_url="https://www.nhlbi.nih.gov/health/lungs/lung-health",
        canonical_home="https://www.nhlbi.nih.gov",
        specialty="respiratory",
        knowledge_domains="respiratory,pulmonary,lung",
        disease_coverage="asthma,copd,respiratory",
        title="NHLBI Lung Diseases and Lung Health Information (living)",
        publisher="National Heart, Lung, and Blood Institute",
        medical_authority_note="HIGH_OFFICIAL_RESPIRATORY_NHLBI",
        authority_class=SourceAuthorityClass.NATIONAL_HEALTH_AUTHORITY.value,
        roles=(SourceRole.PUBLIC_HEALTH.value,),
    ),
    Catalog12CellAuthority(
        cell_id="D03",
        cell_name="Kidney and urinary tract health",
        original_closure_criterion="specialty renal reference in catalog (PRIMARY, not BROAD_ONLY)",
        book_key="niddk_kidney_health_information",
        source_key="niddk_kidney",
        primary_authority="NIDDK Kidney Disease Health Information",
        primary_organization="National Institute of Diabetes and Digestive and Kidney Diseases (NIH)",
        primary_domain="niddk.nih.gov",
        authority_tier="NATIONAL_SPECIALTY_INSTITUTE",
        secondary_authority="NONE",
        access_route="OFFICIAL_PUBLIC_WEB",
        automation_state="ONE_SHOT_CANARY_ALLOWED",
        rights_state="US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
        raw_retention="DENIED",
        derived_retention="ALLOWED",
        canary_url="https://www.niddk.nih.gov/health-information/kidney-disease",
        canonical_home="https://www.niddk.nih.gov",
        specialty="renal",
        knowledge_domains="renal,kidney,nephrology",
        disease_coverage="chronic_kidney_disease,kidney",
        title="NIDDK Kidney Disease Health Information (living)",
        publisher="National Institute of Diabetes and Digestive and Kidney Diseases",
        medical_authority_note="HIGH_OFFICIAL_RENAL_NIDDK",
        authority_class=SourceAuthorityClass.NATIONAL_HEALTH_AUTHORITY.value,
        roles=(SourceRole.PUBLIC_HEALTH.value,),
    ),
    Catalog12CellAuthority(
        cell_id="D05",
        cell_name="Musculoskeletal health and pain",
        original_closure_criterion="specialty MSK/pain reference in catalog (PRIMARY, not BROAD_ONLY)",
        book_key="niams_arthritis_msk_information",
        source_key="niams_msk",
        primary_authority="NIAMS Arthritis and Musculoskeletal Health Topics",
        primary_organization="National Institute of Arthritis and Musculoskeletal and Skin Diseases (NIH)",
        primary_domain="niams.nih.gov",
        authority_tier="NATIONAL_SPECIALTY_INSTITUTE",
        secondary_authority="NONE",
        access_route="OFFICIAL_PUBLIC_WEB",
        automation_state="ONE_SHOT_CANARY_ALLOWED",
        rights_state="US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
        raw_retention="DENIED",
        derived_retention="ALLOWED",
        canary_url="https://www.niams.nih.gov/health-topics/arthritis",
        canonical_home="https://www.niams.nih.gov",
        specialty="musculoskeletal",
        knowledge_domains="musculoskeletal,arthritis,pain,rheumatology",
        disease_coverage="arthritis,musculoskeletal,pain",
        title="NIAMS Arthritis and Musculoskeletal Health Topics (living)",
        publisher="National Institute of Arthritis and Musculoskeletal and Skin Diseases",
        medical_authority_note="HIGH_OFFICIAL_MSK_NIAMS",
        authority_class=SourceAuthorityClass.NATIONAL_HEALTH_AUTHORITY.value,
        roles=(SourceRole.PUBLIC_HEALTH.value,),
    ),
    Catalog12CellAuthority(
        cell_id="D06",
        cell_name="Dermatology and skin health",
        original_closure_criterion="specialty dermatology reference in catalog (PRIMARY, not BROAD_ONLY)",
        book_key="niams_skin_diseases_information",
        source_key="niams_dermatology",
        primary_authority="NIAMS Skin Diseases Health Topics",
        primary_organization="National Institute of Arthritis and Musculoskeletal and Skin Diseases (NIH)",
        primary_domain="niams.nih.gov",
        authority_tier="NATIONAL_SPECIALTY_INSTITUTE",
        secondary_authority="NONE",
        access_route="OFFICIAL_PUBLIC_WEB",
        automation_state="ONE_SHOT_CANARY_ALLOWED",
        rights_state="US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
        raw_retention="DENIED",
        derived_retention="ALLOWED",
        canary_url="https://www.niams.nih.gov/health-topics/skin-diseases",
        canonical_home="https://www.niams.nih.gov",
        specialty="dermatology",
        knowledge_domains="dermatology,skin",
        disease_coverage="skin,dermatology",
        title="NIAMS Skin Diseases Health Topics (living)",
        publisher="National Institute of Arthritis and Musculoskeletal and Skin Diseases",
        medical_authority_note="HIGH_OFFICIAL_DERMATOLOGY_NIAMS",
        authority_class=SourceAuthorityClass.NATIONAL_HEALTH_AUTHORITY.value,
        roles=(SourceRole.PUBLIC_HEALTH.value,),
    ),
    Catalog12CellAuthority(
        cell_id="D07",
        cell_name="Ophthalmology and vision",
        original_closure_criterion="specialty ophthalmology reference in catalog (PRIMARY, not SUPPORTING-only)",
        book_key="nei_eye_health_information",
        source_key="nei_ophthalmology",
        primary_authority="NEI Eye Health Information",
        primary_organization="National Eye Institute (NIH)",
        primary_domain="nei.nih.gov",
        authority_tier="NATIONAL_SPECIALTY_INSTITUTE",
        secondary_authority="NONE",
        access_route="OFFICIAL_PUBLIC_WEB",
        automation_state="ONE_SHOT_CANARY_ALLOWED",
        rights_state="US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
        raw_retention="DENIED",
        derived_retention="ALLOWED",
        canary_url="https://www.nei.nih.gov/learn-about-eye-health",
        canonical_home="https://www.nei.nih.gov",
        specialty="ophthalmology",
        knowledge_domains="ophthalmology,vision,eye",
        disease_coverage="vision,eye,ophthalmology",
        title="NEI Eye Health Information (living)",
        publisher="National Eye Institute",
        medical_authority_note="HIGH_OFFICIAL_OPHTHALMOLOGY_NEI",
        authority_class=SourceAuthorityClass.NATIONAL_HEALTH_AUTHORITY.value,
        roles=(SourceRole.PUBLIC_HEALTH.value,),
    ),
    Catalog12CellAuthority(
        cell_id="D09",
        cell_name="Oral and dental health",
        original_closure_criterion="specialty dental reference in catalog (PRIMARY, not psychiatry-supporting)",
        book_key="nidcr_oral_health_information",
        source_key="nidcr_oral_health",
        primary_authority="NIDCR Oral and Craniofacial Health Information",
        primary_organization="National Institute of Dental and Craniofacial Research (NIH)",
        primary_domain="nidcr.nih.gov",
        authority_tier="NATIONAL_SPECIALTY_INSTITUTE",
        secondary_authority="NONE",
        access_route="OFFICIAL_PUBLIC_WEB",
        automation_state="ONE_SHOT_CANARY_ALLOWED",
        rights_state="US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
        raw_retention="DENIED",
        derived_retention="ALLOWED",
        canary_url="https://www.nidcr.nih.gov/health-info",
        canonical_home="https://www.nidcr.nih.gov",
        specialty="dental",
        knowledge_domains="dental,oral,odontology",
        disease_coverage="oral,dental",
        title="NIDCR Oral and Craniofacial Health Information (living)",
        publisher="National Institute of Dental and Craniofacial Research",
        medical_authority_note="HIGH_OFFICIAL_DENTAL_NIDCR",
        authority_class=SourceAuthorityClass.NATIONAL_HEALTH_AUTHORITY.value,
        roles=(SourceRole.PUBLIC_HEALTH.value,),
    ),
    Catalog12CellAuthority(
        cell_id="D10",
        cell_name="Women's health and reproductive health",
        original_closure_criterion="specialty women's-health reference in catalog (PRIMARY, not BROAD_ONLY)",
        book_key="owh_womens_health_information",
        source_key="owh_womens_health",
        primary_authority="HHS Office on Women's Health",
        primary_organization="Office on Women's Health, HHS/OASH",
        primary_domain="womenshealth.gov",
        authority_tier="NATIONAL_HEALTH_AUTHORITY",
        secondary_authority="NONE",
        access_route="OFFICIAL_PUBLIC_WEB",
        automation_state="ONE_SHOT_CANARY_ALLOWED",
        rights_state="US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
        raw_retention="DENIED",
        derived_retention="ALLOWED",
        canary_url="https://www.womenshealth.gov/menopause",
        canonical_home="https://www.womenshealth.gov",
        specialty="womens_health",
        knowledge_domains="womens_health,reproductive",
        disease_coverage="womens_health,reproductive,menopause",
        title="HHS Office on Women's Health — Menopause and Women's Health Information (living)",
        publisher="Office on Women's Health, U.S. Department of Health and Human Services",
        medical_authority_note="HIGH_OFFICIAL_WOMENS_HEALTH_OWH",
        authority_class=SourceAuthorityClass.NATIONAL_HEALTH_AUTHORITY.value,
        roles=(SourceRole.PUBLIC_HEALTH.value,),
    ),
    Catalog12CellAuthority(
        cell_id="D11",
        cell_name="Pediatrics and adolescent health",
        original_closure_criterion="specialty pediatrics reference in catalog (PRIMARY, not BROAD_ONLY)",
        book_key="cdc_child_development",
        source_key="cdc_child_development",
        primary_authority="CDC Child Development",
        primary_organization="Centers for Disease Control and Prevention",
        primary_domain="cdc.gov",
        authority_tier="NATIONAL_PUBLIC_HEALTH_AUTHORITY",
        secondary_authority="NONE",
        access_route="OFFICIAL_PUBLIC_WEB",
        automation_state="ONE_SHOT_CANARY_ALLOWED",
        rights_state="US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
        raw_retention="DENIED",
        derived_retention="ALLOWED",
        canary_url="https://www.cdc.gov/child-development/index.html",
        canonical_home="https://www.cdc.gov/child-development",
        specialty="pediatrics",
        knowledge_domains="pediatrics,adolescent,child",
        disease_coverage="pediatrics,child,adolescent",
        title="CDC Child Development Health Information (living)",
        publisher="Centers for Disease Control and Prevention",
        medical_authority_note="HIGH_OFFICIAL_PEDIATRICS_CDC",
        authority_class=SourceAuthorityClass.OFFICIAL_PUBLIC_HEALTH.value,
        roles=(SourceRole.PUBLIC_HEALTH.value,),
    ),
    Catalog12CellAuthority(
        cell_id="D13",
        cell_name="Infectious diseases beyond hepatitis",
        original_closure_criterion="broader ID authority than travel/yellow-book (PRIMARY infectious specialty)",
        book_key="cdc_ncezid_infectious_diseases",
        source_key="cdc_ncezid_infectious",
        primary_authority="CDC NCEZID Infectious Disease Topics",
        primary_organization="National Center for Emerging and Zoonotic Infectious Diseases (CDC)",
        primary_domain="cdc.gov",
        authority_tier="NATIONAL_SPECIALTY_CENTER",
        secondary_authority="cdc_yellow_book",
        access_route="OFFICIAL_PUBLIC_WEB",
        automation_state="ONE_SHOT_CANARY_ALLOWED",
        rights_state="US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
        raw_retention="DENIED",
        derived_retention="ALLOWED",
        canary_url="https://www.cdc.gov/ncezid/topics-programs/index.html",
        canonical_home="https://www.cdc.gov/ncezid",
        specialty="infectious",
        knowledge_domains="infectious,infection,communicable",
        disease_coverage="infectious_disease,communicable",
        title="CDC NCEZID Infectious Disease Topics (living)",
        publisher="Centers for Disease Control and Prevention / NCEZID",
        medical_authority_note="HIGH_OFFICIAL_INFECTIOUS_NCEZID",
        authority_class=SourceAuthorityClass.OFFICIAL_PUBLIC_HEALTH.value,
        roles=(SourceRole.PUBLIC_HEALTH.value,),
    ),
    Catalog12CellAuthority(
        cell_id="D16",
        cell_name="Palliative care",
        original_closure_criterion="specialty palliative reference in catalog (PRIMARY, not BROAD_ONLY)",
        book_key="nci_pdq_supportive_palliative_care",
        source_key="nci_pdq_palliative",
        primary_authority="NCI PDQ Supportive and Palliative Care Summaries",
        primary_organization="National Cancer Institute (NIH)",
        primary_domain="cancer.gov",
        authority_tier="NATIONAL_SPECIALTY_INSTITUTE",
        secondary_authority="NONE",
        access_route="OFFICIAL_PUBLIC_WEB",
        automation_state="ONE_SHOT_CANARY_ALLOWED",
        rights_state="US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
        raw_retention="DENIED",
        derived_retention="ALLOWED",
        canary_url="https://www.cancer.gov/publications/pdq/information-summaries/supportive-care",
        canonical_home="https://www.cancer.gov",
        specialty="palliative",
        knowledge_domains="palliative,hospice,end_of_life",
        disease_coverage="palliative,hospice",
        title="NCI PDQ Supportive and Palliative Care Summaries (living)",
        publisher="National Cancer Institute",
        medical_authority_note="HIGH_OFFICIAL_PALLIATIVE_PDQ",
        authority_class=SourceAuthorityClass.NATIONAL_HEALTH_AUTHORITY.value,
        roles=(SourceRole.PUBLIC_HEALTH.value, SourceRole.MEDICAL_REFERENCE_BOOK.value),
    ),
    Catalog12CellAuthority(
        cell_id="D17",
        cell_name="Environmental and occupational health",
        original_closure_criterion="specialty occupational/environmental reference in catalog (PRIMARY, not BROAD_ONLY)",
        book_key="niosh_occupational_health_information",
        source_key="niosh_occupational",
        primary_authority="NIOSH Workplace Safety and Health",
        primary_organization="National Institute for Occupational Safety and Health (CDC)",
        primary_domain="cdc.gov",
        authority_tier="NATIONAL_SPECIALTY_INSTITUTE",
        secondary_authority="NONE",
        access_route="OFFICIAL_PUBLIC_WEB",
        automation_state="ONE_SHOT_CANARY_ALLOWED",
        rights_state="US_GOV_PUBLIC_DOMAIN_TEXT; RAW_HTML=NO; DERIVED=YES",
        raw_retention="DENIED",
        derived_retention="ALLOWED",
        canary_url="https://www.cdc.gov/niosh/",
        canonical_home="https://www.cdc.gov/niosh",
        specialty="occupational",
        knowledge_domains="occupational,environmental,toxicology",
        disease_coverage="occupational,environmental",
        title="NIOSH Occupational Safety and Health Information (living)",
        publisher="National Institute for Occupational Safety and Health / CDC",
        medical_authority_note="HIGH_OFFICIAL_OCCUPATIONAL_NIOSH",
        authority_class=SourceAuthorityClass.OFFICIAL_PUBLIC_HEALTH.value,
        roles=(SourceRole.PUBLIC_HEALTH.value, SourceRole.PREVENTION.value),
    ),
)


def cell_by_id(cell_id: str) -> Catalog12CellAuthority:
    for cell in CATALOG12_CELLS:
        if cell.cell_id == cell_id:
            return cell
    raise KeyError(cell_id)


def catalog12_book_specs():
    from backend.app.services.i5.know01.v1_reference_catalog import V1ReferenceBookSpec

    specs = []
    for cell in CATALOG12_CELLS:
        specs.append(
            V1ReferenceBookSpec(
                book_key=cell.book_key,
                title=cell.title,
                authors_editors=cell.primary_organization,
                publisher=cell.publisher,
                edition_label="living",
                publication_year=2026,
                isbn=None,
                specialty=cell.specialty,
                knowledge_domains=cell.knowledge_domains,
                disease_coverage=cell.disease_coverage,
                family="priority_disease",
                medical_authority_note=cell.medical_authority_note,
                rights_class=_PD,
                automation_tdm_permission=_ALLOWED,
                fulltext_automation_permission=_REVIEW,
                retention_policy="DERIVED_KNOWLEDGE_ONLY_NO_RAW_HTML",
                canonical_access_route=cell.canary_url,
                justification="national_international_medical_authority",
            )
        )
    return tuple(specs)


def catalog12_registry_seeds() -> Tuple[Dict[str, object], ...]:
    seeds: List[Dict[str, object]] = []
    for cell in CATALOG12_CELLS:
        seeds.append(
            {
                "key": cell.source_key,
                "publisher_family": cell.primary_organization,
                "authority_class": cell.authority_class,
                "roles": list(cell.roles),
                "canonical_home": cell.canonical_home,
                "supported_formats": "HTML",
                "specialty_domains": cell.specialty,
                "knowledge_domains": cell.knowledge_domains,
                "p0_tags": {
                    "ALS": P0DiseaseRelevance.SUPPORTING.value,
                    "MS": P0DiseaseRelevance.SUPPORTING.value,
                    "DIABETES": P0DiseaseRelevance.SUPPORTING.value,
                },
                "notes": (
                    f"CATALOG12_{cell.cell_id}; UNATTENDED_WEEKLY_ENABLED=NO; "
                    "ONE_SHOT_CANARY_ALLOWED=YES; RAW_HTML=DENIED; DERIVED=ALLOWED"
                ),
            }
        )
    return tuple(seeds)


def scorecard(cell: Catalog12CellAuthority) -> Dict[str, str]:
    return {
        "CELL_ID": cell.cell_id,
        "CELL_NAME": cell.cell_name,
        "ORIGINAL_CLOSURE_CRITERION": cell.original_closure_criterion,
        "PRIMARY_AUTHORITY": cell.primary_authority,
        "PRIMARY_ORGANIZATION": cell.primary_organization,
        "PRIMARY_DOMAIN": cell.primary_domain,
        "AUTHORITY_TIER": cell.authority_tier,
        "SECONDARY_AUTHORITY": cell.secondary_authority,
        "ACCESS_ROUTE": cell.access_route,
        "AUTOMATION_STATE": cell.automation_state,
        "RIGHTS_STATE": cell.rights_state,
        "RAW_RETENTION": cell.raw_retention,
        "DERIVED_RETENTION": cell.derived_retention,
        "UNATTENDED_WEEKLY_ENABLED": "NO",
        "CURRENT_OFFICIAL_DOMAIN": cell.primary_domain,
        "CURRENT_ORGANIZATION": cell.primary_organization,
        "CURRENT_SPECIALTY_AUTHORITY": cell.primary_authority,
        "CURRENT_CONTENT_STATUS": "LIVE_OFFICIAL_PUBLIC_PAGES_VERIFIED_2026_08_13",
        "CURRENT_API_FEED_DATASET_STATE": "PUBLIC_HTML_OFFICIAL_PAGES",
        "CURRENT_TERMS": "US_FEDERAL_PUBLIC_DOMAIN_TEXT_ATTRIBUTION_APPRECIATED",
        "CURRENT_AUTOMATION_STATE": "BOUNDED_ONE_SHOT_ONLY",
        "CURRENT_RIGHTS_STATE": cell.rights_state,
        "CURRENT_UPDATE_STATE": "LIVING_FEDERAL_HEALTH_INFORMATION",
    }
