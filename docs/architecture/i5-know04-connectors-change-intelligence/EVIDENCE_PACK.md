# I5-KNOW-04 Evidence Assurance Pack

GATE = SEDI-V1 I5-KNOW-04 OFFICIAL SCIENTIFIC CONNECTORS + PUBMED/PMC + CLINICALTRIALS.GOV + GUIDELINE FEEDS + TERMINOLOGY INGESTION + CHANGE/RETRACTION INTELLIGENCE + SCIENTIFIC INGESTION INTEGRITY HARDENING

- Predecessor Master Log section 281 / handoff v572 / continuity v582
- Migration: 065_i5_know04_connectors_change_intelligence (down_revision 064)
- Production migration/crawler/RAG/scheduler: NO

## W0 Findings

| ID | Finding | Fix |
|----|---------|-----|
| NF7 | Cross-study effect FK ownership | Composite FKs (pop/si/sc/so, study_id) |
| NF8 | Recommendation evidence multi-target | ck_crel_target_xor + service XOR |
| NF9 | Invalid p_value domain | ck_see_p_value + service [0,1] |
| NF10 | Silent terminology remap | Conflict ledger + raise |
| NF11 | Master Log prefix mutation risk | Append-only byte-prefix guard |

## Connectors

- PubMed E-utilities (tool/email/api_key from env)
- PMC OA rights-aware (PMC_PRESENT != FULLTEXT_STORAGE)
- ClinicalTrials.gov API v2
- Guideline framework + WHO RSS canary
- Terminology contracts: ICD-11/MeSH/RxNorm/LOINC/ICF/ICHI

## Hard zeroes preserved

PRODUCTION_* = 0; MASS_INGESTION = NO; P0 branching = 0; UNKNOWN rights automation = 0
