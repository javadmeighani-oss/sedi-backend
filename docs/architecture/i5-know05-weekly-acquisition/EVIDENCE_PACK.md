# I5-KNOW-05 Evidence Assurance Pack

GATE = SEDI-V1 I5-KNOW-05 GOVERNED WEEKLY KNOWLEDGE ACQUISITION + COVERAGE-DRIVEN DISCOVERY + CONTROLLED INGESTION + DB↔SCIS/RAG COHERENCE

- Predecessor Master Log §283 / handoff v574 / continuity v584
- Closure Master Log §284 / handoff v575 / continuity v585 (when Green)
- Migration: NONE (reuse 065; NEW_MIGRATION=NO)
- Production crawler/scheduler/RAG/migration: NO

## Authority

- START_HEAD = 79e61f05efce2c740e45f3cde7e0ae27a5857b23
- REPO_ALEMBIC_HEAD = 065_i5_know04_connectors_change_intelligence
- PRODUCTION_ALEMBIC = 060

## W0

| ID | Finding | Fix |
|----|---------|-----|
| NF16 | `.test` NCBI operational email | Reject disallowed emails; weekly ops = BLOCKED_MISSING_VALID_OPERATIONAL_IDENTITY without valid secret; CI uses secrets.SEDI_NCBI_EMAIL |
| NF17 | Hardcoded HTTP 200 / bytes=0 | ObservingHttpGet records actual status/bytes/content-type/request_count |

## Reuse matrix

- WeeklyKnowledgeRun ledger: REUSE
- Coverage cells → KnowledgeGap: NEW (know05.coverage_engine)
- Parallel crawler schema: REJECT_REDUNDANT
- Production weekly: DEFER / NOT AUTHORIZED

## Knowledge storage / availability

See `backend/app/services/i5/know05/storage_matrix.py` and `availability.py`.

## Zeroes

DUPLICATE_KNOWLEDGE_AUTHORITY=0; RUNTIME_ELIGIBLE_NO_RETRIEVAL_PATH=0; PRODUCTION_*=0; MODEL_INVENTED_COVERAGE=0
