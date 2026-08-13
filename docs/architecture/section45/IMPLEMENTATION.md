# Section45 implementation (067)

```text
MIGRATION=067_i7_lifelong_memory_foundation
DOWN_REVISION=065_i5_know04_connectors_change_intelligence
CREATE_066=NO
I8_TABLES=NO
SQL_TIMELINE_VIEW=DEFERRED
SOURCE_CONTENT_HASH_COLUMN=DEFERRED_NAME_CONFLICT
RECONCILIATION_IN_ALEMBIC=NO
PRODUCTION_I7_JOBS=OFF
```

Implemented:

- `user_lifelong_profiles` (DCR-01 exact columns)
- `user_memory_export_jobs` (DCR-03 exact columns; `bytes` SQL name)
- `memory.retain_until` timestamptz nullable + indexes (DCR-02)
- legacy write freeze default ON (`SEDI_LEGACY_FACT_WRITES_ENABLED` to bypass)
- consent-fail-closed reconciliation service (not Alembic)
- derived invalidation for summaries/profile/export jobs
- week-start helper (fa=Saturday, else Monday); scheduler unchanged
- timeline **service only** (no VIEW; privacy_class/timezone not on all sources)

Not implemented: I8 tables, 066, RAG/ANN, chat prune job, object store, production apply.
