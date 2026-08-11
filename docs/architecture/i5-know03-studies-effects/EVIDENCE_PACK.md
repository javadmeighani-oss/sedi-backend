# I5-KNOW-03 Evidence Assurance Pack

GATE = SEDI-V1 I5-KNOW-03 DATA-INTEGRITY HARDENING + STRUCTURED CLINICAL STUDIES + PICO + EFFECTS + RECOMMENDATIONS + TERMINOLOGY FOUNDATION

## Authority start (reconstructed)

- HEAD at gate start: `e293bfffbb83c99af9868bc6fb109c29dbef4b48`
- Predecessor Master Log §280 / handoff v571 / continuity v581
- Repo Alembic was `063`; next revision `064_i5_know03_studies_effects_recs`
- Production Alembic remains `060` — no Production apply

## Database matrix (selected)

| Structure | Class |
|---|---|
| KnowledgeUnit / Provenance / KNOW-01/02 tables | REUSE_EXISTING |
| Artifact version drift events + NULLS NOT DISTINCT + supersedes FK/trigger | EXTEND_EXISTING / NEW_REQUIRED (W0) |
| i5_clinical_studies + artifact/condition links | NEW_REQUIRED |
| populations + criteria | NEW_REQUIRED |
| interventions + study_interventions + mappings | NEW_REQUIRED |
| outcomes + study_outcomes + effect_estimates | NEW_REQUIRED |
| clinical_recommendations + evidence/condition links | NEW_REQUIRED |
| terminology_import_contracts | NEW_REQUIRED (foundation) |
| clinical_trials* CT.gov full schema | DEFER → KNOW-04 |
| user_clinical_feature_index / user_evidence_matches | REJECT (I8) |

## W0 NF5/NF6

- SAME_LABEL_SAME_HASH → idempotent return
- SAME_LABEL_DIFFERENT_HASH → ContentDriftConflict + drift event row (no silent overwrite)
- supersedes_version_id FK + no self-supersede + same-artifact trigger
- UNIQUE NULLS NOT DISTINCT on mappings / coverage cells / priority overlays

## Deferred

```text
ICD11_FULL_IMPORT = NEXT_TERMINOLOGY_WAVE
KNOW-04 connectors unauthorized
```
