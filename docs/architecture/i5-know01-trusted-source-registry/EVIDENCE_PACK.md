# I5-KNOW-01 Evidence Pack — Source Seeds + CAP24

```text
GATE = SEDI-V1 I5-KNOW-01
AUTHORITY = DATABASE after seed (i5_source_registry_extensions)
COMPETING_YAML_SOT = NO
DIABETES_D20_RUNTIME_MUTATION = NO
PRODUCTION_MIGRATION = NO
PRODUCTION_CRAWLER = NO
PRODUCTION_RAG = NO
```

## Evidence classes

| Class | Meaning |
|---|---|
| FACT | Confirmed publisher identity / official home URL family used as seed locator |
| INFERENCE | Reasonable role/authority mapping pending formal rights review |
| UNVERIFIED | Automation/TDM/retention/robots not verified for activation |
| REVIEW_REQUIRED | Must pass rights review before any automation |

## Global seed families (registry entry ≠ automation approved)

All global seeds land with `processing_permission_mode=FULLTEXT_AUTOMATION_BLOCKED` and rights dimensions `UNKNOWN` unless noted.

| key | publisher | authority_class | roles (abbrev) | P0 tags | endpoints (FACT home/API) | automation |
|---|---|---|---|---|---|---|
| who_int | WHO | GLOBAL_INTERGOVERNMENTAL | PUBLIC_HEALTH, GUIDELINE | DM IMPORTANT; ALS/MS SUPPORTING | https://www.who.int | BLOCKED |
| nih_nlm | NIH/NLM | NATIONAL_MEDICAL_LIBRARY | LITERATURE, REF_BOOK | SUPPORTING×3 | https://www.nlm.nih.gov | BLOCKED |
| pubmed_ncbi_eutils | PubMed | NATIONAL_MEDICAL_LIBRARY | LITERATURE | IMPORTANT×3 | eutils API | BLOCKED (KNOW-04) |
| pubmed_central | PMC | OPEN_ACCESS_REPOSITORY | LITERATURE | IMPORTANT×3 | pmc home; JATS/PDF | BLOCKED |
| ncbi_bookshelf | Bookshelf | NATIONAL_MEDICAL_LIBRARY | REF_BOOK | SUPPORTING×3 | books home | BLOCKED |
| medlineplus | MedlinePlus | NATIONAL_MEDICAL_LIBRARY | PUBLIC_HEALTH, LIFESTYLE | DM IMPORTANT | medlineplus.gov | BLOCKED |
| cdc_gov | CDC | OFFICIAL_PUBLIC_HEALTH | PUBLIC_HEALTH, PREVENTION | DM PRIMARY | cdc.gov | BLOCKED |
| nimh_nih | NIMH | OFFICIAL_PUBLIC_HEALTH | MENTAL_HEALTH, PSYCHOLOGY | SUPPORTING×3 | nimh.nih.gov | BLOCKED |
| fda_openfda | FDA | REGULATORY_AUTHORITY | REGULATORY, DRUG | DM IMPORTANT | api.fda.gov | BLOCKED |
| clinicaltrials_gov_api_v2 | CT.gov | CLINICAL_TRIAL_REGISTRY | CLINICAL_TRIAL | IMPORTANT×3 | api/v2 | BLOCKED (KNOW-04; I8 matching) |
| nice_uk | NICE | SPECIALTY_GUIDELINE_BODY | GUIDELINE | IMPORTANT×3 | nice.org.uk | BLOCKED |
| nhs_uk | NHS | NATIONAL_HEALTH_AUTHORITY | PUBLIC_HEALTH | DM IMPORTANT | nhs.uk | BLOCKED |
| cochrane | Cochrane | SYSTEMATIC_REVIEW_AUTHORITY | SYSTEMATIC_REVIEW | IMPORTANT×3 | cochranelibrary.com | BLOCKED |
| aan | AAN | PROFESSIONAL_MEDICAL_SOCIETY | GUIDELINE | ALS/MS PRIMARY | aan.com | BLOCKED |
| ean | EAN | PROFESSIONAL_MEDICAL_SOCIETY | GUIDELINE | ALS/MS IMPORTANT | ean.org | BLOCKED |
| ectrims | ECTRIMS | SPECIALTY_GUIDELINE_BODY | GUIDELINE | MS PRIMARY | ectrims.eu | BLOCKED |
| ada_diabetes | ADA | SPECIALTY_GUIDELINE_BODY | GUIDELINE, NUTRITION | DM PRIMARY | diabetes.org | BLOCKED |

## Iran local directory seeds

Invariant: `IRAN_LOCAL_DIRECTORY != CLINICAL_KU`.

| key | entity | authority_class | credential_authority | notes |
|---|---|---|---|---|
| iran_irimc_physician_licensing | PHYSICIAN | IRAN_PROVIDER_LICENSING_AUTHORITY | YES (candidate) | REVIEW_REQUIRED bulk rights |
| iran_moh_hospital_authority | HOSPITAL | IRAN_MINISTRY_HEALTH | YES (candidate) | not clinical KU |
| iran_clinic_directory_candidate | CLINIC | IRAN_HOSPITAL_AUTHORITY | NO | NEXT_SCHEMA_GATE_REQUIRED clinic entity |
| iran_lab_authority_candidate_moh | LAB | IRAN_REFERENCE_LAB_AUTHORITY | NO | CAP24 candidate only |
| iran_lab_secondary_corroboration | LAB | SECONDARY_CORROBORATION | NO | not primary |
| iran_commercial_directory_example | LOCAL_SERVICE | COMMERCIAL_DIRECTORY | NO | cannot be primary credential |

## CAP24

```text
CAP24_STATUS = BLOCKED_WITH_EXACT_EVIDENCE
CAP24_PRIMARY_AUTHORITY_FOUND = False
CAP24_MACHINE_READABLE = False
CAP24_RIGHTS_VERIFIED = False
CAP24_AUTOMATION_PATH = NONE
```

See `backend/app/services/i5/know01/cap24.py` for structured pack.

## Reference books

| book_key | rights_class | fulltext_automation | note |
|---|---|---|---|
| ncbi_bookshelf_open_example | OPEN_LICENSE_RESTRICTED | REVIEW_REQUIRED | library authority ≠ automation |
| commercial_medical_reference_metadata_only | METADATA_ONLY | DENIED | HIGH authority + blocked fulltext |

## Roadmap boundary recorded

```text
I5 = global governed knowledge
I6/I7/I8 = personal memory / longitudinal / applicability
user_clinical_feature_index + user_evidence_matches = NOT I5 implementation ownership
```
