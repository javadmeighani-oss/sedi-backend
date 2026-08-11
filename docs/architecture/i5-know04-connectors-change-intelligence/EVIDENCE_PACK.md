# I5-KNOW-04 Evidence Assurance Pack

GATE = SEDI-V1 I5-KNOW-04 OFFICIAL SCIENTIFIC CONNECTORS + PUBMED/PMC + CLINICALTRIALS.GOV + GUIDELINE FEEDS + TERMINOLOGY INGESTION + CHANGE/RETRACTION INTELLIGENCE + SCIENTIFIC INGESTION INTEGRITY HARDENING

- Predecessor Master Log section 281 / handoff v572 / continuity v582
- Closure Master Log section 282 / handoff v573 / continuity v583
- Migration: 065_i5_know04_connectors_change_intelligence (down_revision 064)
- Production migration/crawler/RAG/scheduler: NO

## Authority

- START_HEAD = f53295cd8512a69b83e381e96d985006ae72f40a
- IMPL_COMMIT = 7b07e74412918f9c9cd47b32281a22c7573812ee
- HEAD_AT_GREEN = 918d20fdb2603f56b296ccb5552fb9217c396dad
- CI_RUN = 31469303809
- CI_JOB = 93708901137
- ARTIFACT_ID = 9092723768
- ARTIFACT_DIGEST = sha256:4988e73a2989261cfb3ba2d5a88591f5896f85f6e0666098f1a3d8aaf7b37ae8
- PYTEST = 36 passed / 0 failed / 1 deselected
- RAW_LOG_AUDIT = PASS
- FRESH_065 = PASS
- UPGRADE_064_TO_065 = PASS

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
- Guideline framework + WHO RSS canary contract
- Terminology contracts: ICD-11/MeSH/RxNorm/LOINC/ICF/ICHI

## Hard zeroes preserved

PRODUCTION_* = 0; MASS_INGESTION = NO; P0 branching = 0; UNKNOWN rights automation = 0; SILENT_TERMINOLOGY_REMAP = 0; MASTER_LOG_PREFIX_MUTATION = 0
