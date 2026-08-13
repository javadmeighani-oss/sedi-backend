# DESIGN_CHANGE_REQUEST — I8 patient applicability persistence

```text
GATE=SEDI-V1 POST-I5 MASTER GATE-01
STATUS=RECORDED_NOT_IMPLEMENTED
SCHEMA_CHANGE_REQUIRED=YES
MIGRATION_REQUIRED=YES
IMPLEMENTED=NO
```

Full I8 applicability (KNOW-06) needs new tables that this Gate must not create:

- `user_clinical_feature_index`
- `user_evidence_matches`
- `evidence_applicability_rules`
- optional nutrition/meal-plan persistence tables

This Gate implemented only the schema-safe ephemeral I8 slice:

- consent + I6 facts readiness
- W4 fail-closed when no ELIGIBLE knowledge
- no diagnosis / no medication change
- no new Alembic revision
- PRODUCTION_RAG=NO / ANN=NO / MIGRATION_066=NO
