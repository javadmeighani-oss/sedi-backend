"""Authoritative V1 reference-book catalog (metadata seeds; authority ≠ automation).

Uses existing I5ReferenceBook / I5ReferenceBookEdition tables only — no schema change.
Generic placeholder seeds may coexist but do NOT satisfy catalog completeness alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import BookRightsClass, RightDecision
from backend.app.services.i5.know01.book_registry import (
    add_edition,
    assert_authority_does_not_imply_automation,
    upsert_reference_book,
)


# Acquisition states derived from existing rights fields (no new enum/CHECK).
ACQ_FULLTEXT_ALLOWED = "FULLTEXT_ALLOWED"
ACQ_DERIVED_ONLY = "DERIVED_ONLY"
ACQ_METADATA_ONLY = "METADATA_ONLY"
ACQ_REVIEW_REQUIRED = "REVIEW_REQUIRED"
ACQ_DENIED = "DENIED"
ACQ_UNKNOWN = "UNKNOWN"

PLACEHOLDER_BOOK_KEYS = frozenset(
    {
        "ncbi_bookshelf_open_example",
        "commercial_medical_reference_metadata_only",
    }
)


@dataclass(frozen=True)
class V1ReferenceBookSpec:
    book_key: str
    title: str
    authors_editors: str
    publisher: str
    edition_label: str
    publication_year: Optional[int]
    isbn: Optional[str]
    specialty: str
    knowledge_domains: str
    disease_coverage: str
    family: str  # core_clinical | priority_disease | mental_behavioral | lifestyle
    medical_authority_note: str
    rights_class: str
    automation_tdm_permission: str
    fulltext_automation_permission: str
    retention_policy: str
    canonical_access_route: Optional[str]
    language: str = "en"
    reference_role: str = "STANDARD_PROFESSIONAL_REFERENCE"
    justification: str = "established_academic_medical_publisher"


# Named, identifiable authoritative works — metadata-only unless rights allow.
# Fulltext automation remains DENIED / REVIEW_REQUIRED / UNKNOWN (fail-closed).
V1_AUTHORITATIVE_REFERENCE_CATALOG: Sequence[V1ReferenceBookSpec] = (
    # --- Core clinical medicine ---
    V1ReferenceBookSpec(
        book_key="harrisons_principles_internal_medicine",
        title="Harrison's Principles of Internal Medicine",
        authors_editors="Jameson, Fauci, Kasper, Hauser, Longo, Loscalzo",
        publisher="McGraw Hill",
        edition_label="21st",
        publication_year=2022,
        isbn="9781264268504",
        specialty="internal_medicine",
        knowledge_domains="clinical_medicine,internal_medicine,diagnostics",
        disease_coverage="general_medicine,ALS,MS,DIABETES,cardiovascular",
        family="core_clinical",
        medical_authority_note="HIGH_STANDARD_INTERNAL_MEDICINE_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
        justification="recognized_specialty_reference",
    ),
    V1ReferenceBookSpec(
        book_key="goldman_cecil_medicine",
        title="Goldman-Cecil Medicine",
        authors_editors="Goldman, Schafer",
        publisher="Elsevier",
        edition_label="27th",
        publication_year=2023,
        isbn="9780323930383",
        specialty="internal_medicine",
        knowledge_domains="clinical_medicine,internal_medicine",
        disease_coverage="general_medicine,DIABETES,cardiovascular",
        family="core_clinical",
        medical_authority_note="HIGH",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    V1ReferenceBookSpec(
        book_key="tintinallis_emergency_medicine",
        title="Tintinalli's Emergency Medicine: A Comprehensive Study Guide",
        authors_editors="Tintinalli, Ma, Yealy, Meckler, Stapczynski, Cline, Thomas",
        publisher="McGraw Hill",
        edition_label="9th",
        publication_year=2020,
        isbn="9781260019933",
        specialty="emergency_medicine",
        knowledge_domains="emergency_medicine,acute_care",
        disease_coverage="emergency,ALS,MS,DIABETES",
        family="core_clinical",
        medical_authority_note="HIGH_EMERGENCY_MEDICINE_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    V1ReferenceBookSpec(
        book_key="goodman_gilman_pharmacology",
        title="Goodman & Gilman's The Pharmacological Basis of Therapeutics",
        authors_editors="Brunton, Knollmann",
        publisher="McGraw Hill",
        edition_label="14th",
        publication_year=2022,
        isbn="9781264258079",
        specialty="pharmacology",
        knowledge_domains="pharmacology,drug_reference",
        disease_coverage="pharmacotherapy,ALS,MS,DIABETES",
        family="core_clinical",
        medical_authority_note="HIGH_DRUG_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    V1ReferenceBookSpec(
        book_key="henrys_clinical_diagnosis_management_lab",
        title="Henry's Clinical Diagnosis and Management by Laboratory Methods",
        authors_editors="McPherson, Pincus",
        publisher="Elsevier",
        edition_label="24th",
        publication_year=2021,
        isbn="9780323673204",
        specialty="laboratory_medicine",
        knowledge_domains="diagnostics,laboratory_medicine",
        disease_coverage="diagnostics,DIABETES",
        family="core_clinical",
        medical_authority_note="HIGH_LABORATORY_MEDICINE_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    V1ReferenceBookSpec(
        book_key="cdc_yellow_book",
        title="CDC Yellow Book: Health Information for International Travel",
        authors_editors="Centers for Disease Control and Prevention",
        publisher="CDC / Oxford University Press",
        edition_label="2024",
        publication_year=2023,
        isbn="9780197570944",
        specialty="preventive_medicine_public_health",
        knowledge_domains="public_health,prevention,travel_medicine",
        disease_coverage="prevention,infectious_disease",
        family="core_clinical",
        medical_authority_note="HIGH_OFFICIAL_PUBLIC_HEALTH",
        rights_class=BookRightsClass.OPEN_LICENSE_RESTRICTED.value,
        automation_tdm_permission=RightDecision.REVIEW_REQUIRED.value,
        fulltext_automation_permission=RightDecision.REVIEW_REQUIRED.value,
        retention_policy="REVIEW_REQUIRED_BEFORE_RAW_RETENTION",
        canonical_access_route="https://wwwnc.cdc.gov/travel/page/yellowbook-home",
        justification="national_international_medical_authority",
    ),
    # --- Priority disease / specialty ---
    V1ReferenceBookSpec(
        book_key="bradley_daroff_neurology",
        title="Bradley and Daroff's Neurology in Clinical Practice",
        authors_editors="Jankovic, Mazziotta, Pomeroy, Newman",
        publisher="Elsevier",
        edition_label="8th",
        publication_year=2021,
        isbn="9780323642613",
        specialty="neurology",
        knowledge_domains="neurology,clinical_neuroscience",
        disease_coverage="ALS,MS,neurology",
        family="priority_disease",
        medical_authority_note="HIGH_NEUROLOGY_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    V1ReferenceBookSpec(
        book_key="merritts_neurology",
        title="Merritt's Neurology",
        authors_editors="Louis, Mayer, Noble",
        publisher="Wolters Kluwer",
        edition_label="14th",
        publication_year=2021,
        isbn="9781975141226",
        specialty="neurology",
        knowledge_domains="neurology",
        disease_coverage="ALS,MS,neurology",
        family="priority_disease",
        medical_authority_note="HIGH",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    V1ReferenceBookSpec(
        book_key="braunwalds_heart_disease",
        title="Braunwald's Heart Disease: A Textbook of Cardiovascular Medicine",
        authors_editors="Libby, Bonow, Mann, Tomaselli, Bhatt, Solomon",
        publisher="Elsevier",
        edition_label="12th",
        publication_year=2021,
        isbn="9780323722193",
        specialty="cardiovascular_medicine",
        knowledge_domains="cardiology,cardiovascular",
        disease_coverage="cardiovascular,DIABETES",
        family="priority_disease",
        medical_authority_note="HIGH_CARDIOLOGY_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    V1ReferenceBookSpec(
        book_key="williams_textbook_endocrinology",
        title="Williams Textbook of Endocrinology",
        authors_editors="Melmed, Auchus, Goldfine, Koenig, Rosen",
        publisher="Elsevier",
        edition_label="15th",
        publication_year=2024,
        isbn="9780323932301",
        specialty="endocrinology_diabetes",
        knowledge_domains="endocrinology,diabetes",
        disease_coverage="DIABETES,endocrine",
        family="priority_disease",
        medical_authority_note="HIGH_ENDOCRINOLOGY_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    # --- Mental / behavioral health ---
    V1ReferenceBookSpec(
        book_key="dsm5_tr",
        title="Diagnostic and Statistical Manual of Mental Disorders, Fifth Edition, Text Revision (DSM-5-TR)",
        authors_editors="American Psychiatric Association",
        publisher="American Psychiatric Association Publishing",
        edition_label="DSM-5-TR",
        publication_year=2022,
        isbn="9780890425763",
        specialty="psychiatry",
        knowledge_domains="psychiatry,mental_health,behavioral_medicine",
        disease_coverage="mental_health,addiction,cognitive_health",
        family="mental_behavioral",
        medical_authority_note="HIGH_PSYCHIATRY_NOSOLOGY_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
        justification="major_professional_society_reference",
    ),
    V1ReferenceBookSpec(
        book_key="kaplan_sadock_synopsis_psychiatry",
        title="Kaplan and Sadock's Synopsis of Psychiatry",
        authors_editors="Boland, Verduin, Ruiz",
        publisher="Wolters Kluwer",
        edition_label="12th",
        publication_year=2021,
        isbn="9781975145569",
        specialty="psychiatry",
        knowledge_domains="psychiatry,clinical_psychology,mental_health",
        disease_coverage="mental_health,addiction,stress_resilience",
        family="mental_behavioral",
        medical_authority_note="HIGH",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    V1ReferenceBookSpec(
        book_key="stahl_essential_psychopharmacology",
        title="Stahl's Essential Psychopharmacology",
        authors_editors="Stahl",
        publisher="Cambridge University Press",
        edition_label="5th",
        publication_year=2021,
        isbn="9781108971638",
        specialty="psychopharmacology",
        knowledge_domains="psychiatry,pharmacology,mental_health",
        disease_coverage="mental_health",
        family="mental_behavioral",
        medical_authority_note="HIGH",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    # --- Lifestyle / longitudinal health ---
    V1ReferenceBookSpec(
        book_key="lifestyle_medicine_rippe",
        title="Lifestyle Medicine",
        authors_editors="Rippe",
        publisher="CRC Press / Taylor & Francis",
        edition_label="3rd",
        publication_year=2019,
        isbn="9781138708846",
        specialty="lifestyle_medicine",
        knowledge_domains="lifestyle,prevention,behavior_change",
        disease_coverage="DIABETES,cardiovascular,prevention",
        family="lifestyle",
        medical_authority_note="HIGH_LIFESTYLE_MEDICINE_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    V1ReferenceBookSpec(
        book_key="acsm_guidelines_exercise_testing",
        title="ACSM's Guidelines for Exercise Testing and Prescription",
        authors_editors="American College of Sports Medicine",
        publisher="Wolters Kluwer",
        edition_label="11th",
        publication_year=2021,
        isbn="9781975150198",
        specialty="exercise_physical_activity",
        knowledge_domains="exercise,lifestyle,rehabilitation",
        disease_coverage="cardiovascular,DIABETES,rehabilitation",
        family="lifestyle",
        medical_authority_note="HIGH_PROFESSIONAL_SOCIETY_EXERCISE_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
        justification="major_professional_society_reference",
    ),
    V1ReferenceBookSpec(
        book_key="kryger_principles_practice_sleep_medicine",
        title="Principles and Practice of Sleep Medicine",
        authors_editors="Kryger, Roth, Goldstein, Dement",
        publisher="Elsevier",
        edition_label="7th",
        publication_year=2022,
        isbn="9780323661898",
        specialty="sleep_medicine",
        knowledge_domains="sleep,lifestyle,neurology",
        disease_coverage="sleep,cognitive_health",
        family="lifestyle",
        medical_authority_note="HIGH_SLEEP_MEDICINE_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    V1ReferenceBookSpec(
        book_key="hazzards_geriatric_medicine",
        title="Hazzard's Geriatric Medicine and Gerontology",
        authors_editors="Halter, Ouslander, Studenski, High, Asthana, Supiano, Ritchie",
        publisher="McGraw Hill",
        edition_label="8th",
        publication_year=2022,
        isbn="9781260464450",
        specialty="geriatrics_healthy_aging",
        knowledge_domains="geriatrics,healthy_aging,rehabilitation",
        disease_coverage="aging,cognitive_health,DIABETES",
        family="lifestyle",
        medical_authority_note="HIGH_GERIATRICS_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    V1ReferenceBookSpec(
        book_key="braddom_physical_medicine_rehabilitation",
        title="Braddom's Physical Medicine and Rehabilitation",
        authors_editors="Cifu",
        publisher="Elsevier",
        edition_label="6th",
        publication_year=2020,
        isbn="9780323625395",
        specialty="rehabilitation",
        knowledge_domains="rehabilitation,physical_medicine",
        disease_coverage="ALS,MS,rehabilitation",
        family="lifestyle",
        medical_authority_note="HIGH_REHABILITATION_REFERENCE",
        rights_class=BookRightsClass.METADATA_ONLY.value,
        automation_tdm_permission=RightDecision.DENIED.value,
        fulltext_automation_permission=RightDecision.DENIED.value,
        retention_policy="NO_FULLTEXT_UNTIL_LICENSE",
        canonical_access_route=None,
    ),
    V1ReferenceBookSpec(
        book_key="ncbi_genereviews_collection",
        title="GeneReviews (NCBI Bookshelf collection)",
        authors_editors="Adam, Feldman, Mirzaa, Pagon, Wallace, Bean, Gripp, Amemiya (eds.)",
        publisher="University of Washington / NCBI Bookshelf",
        edition_label="living",
        publication_year=2024,
        isbn=None,
        specialty="medical_genetics",
        knowledge_domains="genetics,neurology,rare_disease",
        disease_coverage="ALS,neurology,rare_disease",
        family="priority_disease",
        medical_authority_note="HIGH_NLM_BOOKSHELF_COLLECTION",
        rights_class=BookRightsClass.OPEN_LICENSE_RESTRICTED.value,
        automation_tdm_permission=RightDecision.REVIEW_REQUIRED.value,
        fulltext_automation_permission=RightDecision.REVIEW_REQUIRED.value,
        retention_policy="REVIEW_REQUIRED_BEFORE_RAW_RETENTION",
        canonical_access_route="https://www.ncbi.nlm.nih.gov/books/NBK1116/",
        justification="authoritative_institutional_publication",
    ),
)

from backend.app.services.i5.know01.catalog12_specialty_authorities import (  # noqa: E402
    catalog12_book_specs,
)

V1_AUTHORITATIVE_REFERENCE_CATALOG = tuple(V1_AUTHORITATIVE_REFERENCE_CATALOG) + catalog12_book_specs()


def acquisition_state_for_book(book: models.I5ReferenceBook) -> str:
    """Map existing rights fields → governed acquisition state (fail-closed)."""
    ft = str(book.fulltext_automation_permission or RightDecision.UNKNOWN.value).upper()
    rights = str(book.rights_class or BookRightsClass.UNKNOWN_RIGHTS.value).upper()
    tdm = str(book.automation_tdm_permission or RightDecision.UNKNOWN.value).upper()

    if ft == RightDecision.DENIED.value or rights == BookRightsClass.FULLTEXT_TDM_PROHIBITED.value:
        return ACQ_DENIED
    if ft == RightDecision.UNKNOWN.value or rights == BookRightsClass.UNKNOWN_RIGHTS.value:
        return ACQ_UNKNOWN
    if ft == RightDecision.REVIEW_REQUIRED.value:
        return ACQ_REVIEW_REQUIRED
    if rights == BookRightsClass.METADATA_ONLY.value:
        return ACQ_METADATA_ONLY
    if ft == RightDecision.ALLOWED.value and tdm in {
        RightDecision.DENIED.value,
        RightDecision.REVIEW_REQUIRED.value,
    }:
        return ACQ_DERIVED_ONLY
    if ft == RightDecision.ALLOWED.value:
        return ACQ_FULLTEXT_ALLOWED
    if rights == BookRightsClass.OPEN_LICENSE_RESTRICTED.value:
        return ACQ_REVIEW_REQUIRED
    return ACQ_UNKNOWN


def assert_placeholders_alone_insufficient(db: Session) -> None:
    named = [
        b
        for b in db.query(models.I5ReferenceBook).all()
        if b.book_key not in PLACEHOLDER_BOOK_KEYS
    ]
    if not named:
        raise AssertionError("REFERENCE_CATALOG_INCOMPLETE:placeholders_only")


def seed_v1_authoritative_reference_catalog(db: Session) -> Dict[str, Any]:
    """Upsert named V1 catalog into existing reference-book tables."""
    keys: List[str] = []
    families: Dict[str, int] = {}
    acq_counts: Dict[str, int] = {}
    for spec in V1_AUTHORITATIVE_REFERENCE_CATALOG:
        note = (
            f"{spec.medical_authority_note}|family={spec.family}|"
            f"domains={spec.knowledge_domains}|lang={spec.language}|"
            f"role={spec.reference_role}|justification={spec.justification}"
        )
        book = upsert_reference_book(
            db,
            book_key=spec.book_key,
            title=spec.title,
            authors_editors=spec.authors_editors,
            publisher=spec.publisher,
            isbn=spec.isbn,
            specialty=spec.specialty,
            disease_coverage=spec.disease_coverage,
            medical_authority_note=note,
            rights_class=spec.rights_class,
            automation_tdm_permission=spec.automation_tdm_permission,
            fulltext_automation_permission=spec.fulltext_automation_permission,
            retention_policy=spec.retention_policy,
            canonical_access_route=spec.canonical_access_route,
        )
        add_edition(
            db,
            book_id=book.id,
            edition_label=spec.edition_label,
            publication_year=spec.publication_year,
            is_current=True,
            access_route=spec.canonical_access_route,
        )
        # Prior edition stub for edition-distinction tests on Harrison's
        if spec.book_key == "harrisons_principles_internal_medicine":
            add_edition(
                db,
                book_id=book.id,
                edition_label="20th",
                publication_year=2018,
                is_current=False,
            )
        assert_authority_does_not_imply_automation(book)
        acq = acquisition_state_for_book(book)
        if acq == ACQ_FULLTEXT_ALLOWED:
            raise AssertionError(f"UNEXPECTED_FULLTEXT_ALLOWED:{spec.book_key}")
        keys.append(spec.book_key)
        families[spec.family] = families.get(spec.family, 0) + 1
        acq_counts[acq] = acq_counts.get(acq, 0) + 1
    db.flush()
    assert_placeholders_alone_insufficient(db)
    return {
        "catalog_count": len(keys),
        "book_keys": keys,
        "family_counts": families,
        "acquisition_counts": acq_counts,
        "placeholder_keys_preserved": sorted(PLACEHOLDER_BOOK_KEYS),
    }


def catalog_summary(db: Session) -> Dict[str, Any]:
    books = db.query(models.I5ReferenceBook).order_by(models.I5ReferenceBook.book_key).all()
    named = [b for b in books if b.book_key not in PLACEHOLDER_BOOK_KEYS]
    placeholders = [b for b in books if b.book_key in PLACEHOLDER_BOOK_KEYS]
    acq = {acquisition_state_for_book(b): 0 for b in books}
    for b in books:
        acq[acquisition_state_for_book(b)] = acq.get(acquisition_state_for_book(b), 0) + 1
    return {
        "total": len(books),
        "named_authoritative": len(named),
        "placeholders": len(placeholders),
        "named_titles": [b.title for b in named],
        "acquisition_distribution": acq,
        "publishers": sorted({(b.publisher or "") for b in named}),
    }
