# I5-KNOW-02 Evidence Assurance Pack

GATE = SEDI-V1 I5-KNOW-02 SCIENTIFIC ARTIFACTS + ARTIFACT VERSIONING + MULTI-EVIDENCE LINKS + STRUCTURED CLAIM DETAILS + UNIVERSAL HUMAN HEALTH TAXONOMY FOUNDATION

## Authority

- Design Freeze: `docs/architecture/i5-final-knowledge-architecture-freeze-01/05_STRUCTURED_CLINICAL_EVIDENCE_DATA_MODEL.md`
- Predecessor: I5-KNOW-01 PASS / CLOSED (§278 + §279 integrity remediation)
- Migration: `063_i5_know02_artifacts_claims_taxonomy` (revises `062_i5_know01_source_registry_rights`)
- Production Alembic remains `060` — **no Production apply**

## Permanent product requirement (recorded)

ALL human diseases / health conditions share one universal taxonomy foundation.
ALS / MS / Diabetes are **P0 priority overlays**, not parallel knowledge systems.
Treatment / care / prevention / nutrition / exercise / lifestyle / sleep / daily-routine are **knowledge dimensions** linked to conditions or healthy populations.

## Schema necessity

| Table | Necessity |
|---|---|
| `i5_terminology_releases` | Versioned terminology metadata (ICD-11/MeSH/ICF/ICHI …) without bulk proprietary import |
| `i5_knowledge_dimensions` | Controlled dimension vocabulary persisted in DB |
| `i5_clinical_concepts` (+ labels/mappings) | Universal disease/condition backbone + multilingual labels + external codes |
| `i5_sedi_priority_overlays` | P0 coverage priority separate from taxonomy identity |
| `i5_scientific_artifacts` / `_versions` | First-class immutable scientific artifact versions |
| `i5_knowledge_unit_evidence_links` | Multi-evidence SUPPORTS/CONTRADICTS … to KU |
| `i5_knowledge_claim_details` | Structured claim layer on existing KnowledgeUnit |
| `i5_knowledge_unit_concepts` / `_dimensions` | Many-to-many KU↔concept / KU↔dimension |
| `i5_knowledge_coverage_cells` | Disease × dimension coverage-gap cells (extends KNOW-01) |

## Deferred (explicit)

```text
ICD11_FULL_IMPORT = NEXT_TERMINOLOGY_WAVE
KNOW-03 = structured studies / populations / interventions / outcomes / recommendations (UNAUTHORIZED)
ALL_HUMAN_MEDICAL_KNOWLEDGE_INGESTED = NO (continuous acquisition)
PRODUCTION_CRAWLER / RAG / SCIS = NO
```

## Proof surfaces

- Package: `backend/app/services/i5/know02/`
- Tests: `backend/tests/test_i5_know02_artifacts_taxonomy.py`
- CI: `.github/workflows/i5-know02-artifacts-taxonomy-runtime.yml` (pipefail, PG16, fresh→063, 062→063, KNOW-01 regression, raw-log audit)

## Completeness distinction

```text
UNIVERSAL_TAXONOMY_FOUNDATION = GREEN   # schema + fixtures + queryability
ALL_HUMAN_MEDICAL_KNOWLEDGE_INGESTED = NO
```
