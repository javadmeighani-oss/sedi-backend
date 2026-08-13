# Next protected implementation package (proposal only)

```text
PROPOSED_GATE=SEDI-V1 I7 MEMORY PERSISTENCE 067
AUTHORIZED=NO
MIGRATION_ID_PROPOSAL=067_i7_lifelong_memory_foundation
MIGRATION_066=FORBIDDEN_RESERVED
PRODUCTION_I7_ACTIVATION_BOUNDARY=SEPARATE_OPS_GATE
PRODUCTION_I8_ACTIVATION_BOUNDARY=NOT_IN_067
```

## NEW_TABLES

- `user_lifelong_profiles` (DCR-01)
- `user_memory_export_jobs` (DCR-03)

## NEW_COLUMNS

- `memory.retain_until` timestamptz nullable (DCR-02)
- optional `user_memory_facts.source_content_sha256` (DCR-02)

## MODEL_CHANGES

ORM mirrors only after migration. No ownership change of UMF.

## ENUM_CHANGES

None on existing CHECKs. New tables use their own status vocab CHECKs.

## CHECK_CHANGES

No change to existing UPS/UMF CHECKs.

## INDEXES

- `user_lifelong_profiles (user_id, status)`
- `user_memory_export_jobs (user_id, status, expires_at)`
- `memory (user_id, created_at)` if missing
- `memory (retain_until)`

## VIEW

- `user_lifelong_timeline` UNION view (DCR-05) — same 067 or immediate follow-on

## BACKFILL

- no destructive backfill
- DCR-04 merge is **not** in 067 (separate reconciliation Gate)
- no profile backfill of inferred clinical state

## DATA_RECONCILIATION

- export jobs start empty
- profiles built on-demand after consent
- chat retain_until default = created_at + 30 days for new rows only

## ROLLBACK

- drop new tables/view/columns
- leave UMF/UPS/consents untouched

## TESTS

- profile rebuild/invalidation/isolation/not-diagnosis
- export expire/revoke/not-SoT
- chat prune dry-run
- timeline view user isolation
- freeze 066 still absent

## CI

KNOW-04 path + backend tests. No freeze OpenAPI regen unless a dedicated Gate.

## PRODUCTION_ACTIVATION_BOUNDARY

067 may ship dormant (flags off). I7 job enablement and chat prune enablement
are separate. I8 tables are not in 067.

If this package is not later authorized: existing schema remains sufficient for
dormant I7 jobs + ephemeral I8.
