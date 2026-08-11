# I5-KNOW-05 Evidence Assurance Pack (NF18–NF21 Remediation)

GATE = SEDI-V1 I5-KNOW-05 DB KNOWLEDGE AUTHORITY + REAL BOUNDED INGESTION E2E + COVERAGE-DRIVEN SOURCE SELECTION + GOVERNED PUBLICATION + DB↔SCIS/RAG REAL COHERENCE + CONTINUITY CORRECTION

- Predecessor Master Log §284 / handoff v575 / ChatGPT independent authority **v587** (not v585)
- Closure Master Log §285 / handoff v576 / ChatGPT successor required from v587
- Migration: NONE (reuse 065; NEW_MIGRATION=NO)
- Production crawler/scheduler/RAG/migration: NO

## Authority (§285 Green)

- START_HEAD = 4396959fd94cbb1d894e1d2425acc57a7b9365ab
- IMPL = e20ef60541f396ab3deb7149c644ead6cda1aa56
- REMEDIATION = 9363f95 → 0acde5d → bd1b901 → f94fac6
- HEAD_AT_GREEN = f94fac6c9b1c5331bad56f05a091259971484467
- CI_RUN = 31484552803
- CI_JOB_DETERMINISTIC = 93756852593
- CI_JOB_LIVE = 93757031645
- ARTIFACT_ID_DETERMINISTIC = 9098573580
- ARTIFACT_DIGEST_DETERMINISTIC = sha256:14754ae6485953b33bc39886ef74909779f50eca59af680ef626bf08a52f3582
- ARTIFACT_ID_LIVE = 9098590735
- ARTIFACT_DIGEST_LIVE = sha256:bc05639fa7d06f71279ec55d9e15a13622a24f4f212043c1bc7e87a095fa9f2f
- PYTEST_DETERMINISTIC = 37 passed
- PYTEST_LIVE = 6 passed
- RAW_LOG_AUDIT = PASS
- FRESH_065 = PASS

## Findings

| ID | Before | After |
|----|--------|-------|
| NF18 | False-zero RAG / rights+supersession incomplete | CLOSED — DB-derived auditor + negative fixtures |
| NF19 | Stopped at READY_FOR_BOUNDED_FETCH | CLOSED — CT.gov bounded E2E + publication |
| NF20 | Gap without source-family selection | CLOSED — source_selection + orchestrator |
| NF21 | Static storage_matrix duplicate=0 | CLOSED — authority_audit introspection |
| NF16 ops | Missing NCBI email | Implementation CLOSED; LIVE_READY=NO |

## Key modules

- `backend/app/services/i5/know05/rag_coherence.py`
- `backend/app/services/i5/know05/authority_audit.py`
- `backend/app/services/i5/know05/source_selection.py`
- `backend/app/services/i5/know05/bounded_ingestion.py`
- `backend/app/services/i5/know05/orchestrator.py`
- `backend/app/services/i5/know05/availability.py`

## Production

All Production writes/migrations/crawler/scheduler/RAG activation = NO.
