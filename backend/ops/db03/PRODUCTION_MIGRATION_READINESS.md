# DB-03 / DB-PROD-01 Production Migration Readiness Package
#
# ROLE_CONNECTION_MODEL = DIRECT_LOGIN
# ROLE_MODEL_RATIONALE =
#   Production sedi-backend authenticates via DATABASE_URL LOGIN identity from
#   /etc/sedi/sedi-backend.env. One-off Alembic containers use the same LOGIN URL
#   on sedi-net. Privilege-group NOLOGIN roles would require an extra membership
#   layer not present in current deployment mechanics.

## Status

- DB-03 implementation: Green (repository + CI rehearsal)
- DB-PROD-01: authorized to apply schema 056→060 and role hardening on Production

## Role hardening (fail-closed)

Preferred applicator:

```bash
export DATABASE_URL=...   # privileged admin session (env/secret store only)
export SEDI_APP_RUNTIME_PASSWORD=...
export SEDI_MIGRATION_ADMIN_PASSWORD=...
export SEDI_DBEAVER_READONLY_PASSWORD=...
python backend/ops/db03/apply_roles_sedi_v1.py
```

Companion SQL (psql meta; used by shell path / documentation):

```text
backend/ops/db03/roles_sedi_v1.sql
```

Invariants:

- `sedi_app_runtime` LOGIN NOSUPERUSER — DML only, no schema CREATE
- `sedi_migration_admin` LOGIN NOSUPERUSER — DDL/DML for Alembic / ownership path
- `sedi_dbeaver_readonly` LOGIN NOSUPERUSER — SELECT/catalog only
- No `WHEN OTHERS THEN NULL`
- No passwords in git

## Preflight (read-only)

```bash
# Use env DATABASE_URL — never embed credentials
alembic current
psql "$DATABASE_URL" -c "SELECT version_num FROM alembic_version;"
psql "$DATABASE_URL" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
```

Confirm: Alembic=056 before apply, table count baseline known, no unexpected drift.

## Migration order

1. Backup + restore-test
2. Freeze writers (`sedi-backend` stop/pause)
3. Final cutover backup if practical
4. Alembic upgrade head through digest-pinned one-off container (057→060)
5. Verify schema / backfills / clinical windows / no pgvector
6. Apply role hardening via `apply_roles_sedi_v1.py`
7. Cut over `/etc/sedi/sedi-backend.env` DATABASE_URL user to `sedi_app_runtime`
8. Controlled `sedi-backend` recreate (credential cutover only)
9. Prove runtime role + health; harden legacy `sedi_user` only after Green

## Commands (secrets from env)

```bash
export DATABASE_URL=...   # from secret store
cd workspace
alembic -c backend/alembic.ini upgrade head
```

Production authoritative path uses SSH + `docker run --network sedi-net --env-file /etc/sedi/sedi-backend.env` digest-pinned image.

## Post-migration verification

- `alembic current` == `060_db03_w4_w6_scale_inspect_roles`
- Target tables/indexes/views present
- `care_response_policies` windows NULL unless prior approved authority
- No `rag_embeddings`; no `vector` extension
- `db03_migration_conflicts` reviewed; unexplained loss = 0
- Role invariants proven via `pg_roles` / `has_*_privilege`

## Rollback / forward-fix

| Wave | Strategy |
|------|----------|
| 0–1 | Fully reversible (drop new cols/tables) |
| 2 | Logically reversible (source tables retained) |
| 3 | Forward-fix with dual-read fallback |
| Role cutover | Restore prior DATABASE_URL + recreate backend; schema stays |

## Explicit non-actions

- No force-push / main merge
- No pgvector / rag_embeddings
- No clinical window seeding
- No crawler / RAG / caregiver escalation activation
- No unrelated application deploy
