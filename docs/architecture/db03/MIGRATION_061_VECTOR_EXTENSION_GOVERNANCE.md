# Migration 061 — vector extension governance (normalized)

## Status

```text
CLASSIFICATION=GOVERNANCE_DEVIATION_ONLY
TECHNICAL_MIGRATION_DEFECT=NO
MIGRATION_061_REPO_PRODUCTION_SEMANTIC_ALIGNMENT=PASS
```

## History

| Revision state | Commit | Behavior |
|---|---|---|
| Original | `d760035` | `CREATE EXTENSION IF NOT EXISTS vector` |
| Production-path fix | `3c367dd` | DO-block: create only if missing; comment documents bootstrap precreate |

## Accepted Production semantics

1. Bootstrap/`POSTGRES_USER` (superuser) may `CREATE EXTENSION vector` before Alembic.
2. Alembic runs as `sedi_migration_admin` (LOGIN, not superuser).
3. Revision `061` must continue safely when `vector` already exists (DO-block skip path).
4. Fresh/rehearsal environments where the migration role is effectively privileged may still create `vector` inside the DO-block when absent.

## Production execution evidence (Gate §297 / CI `31618843964`)

- Precreate: `CREATE EXTENSION IF NOT EXISTS vector` as bootstrap → version `0.8.6`
- Override mount of repo `061` into migration image
- Alembic as `sedi_migration_admin` completed through `065`

## Invariants

- Do not rewrite 061 solely to erase history.
- Do not require `sedi_migration_admin` to be SUPERUSER.
- Schema objects after 061 remain owned per DB03 ownership model (`sedi_migration_admin` for public DDL objects).

## Open technical findings

```text
MIGRATION_061_OPEN_TECHNICAL_FINDING_COUNT=0
```
