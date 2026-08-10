# DB-03 Production Migration Readiness Package

**Status:** Prepared by DB-03. **NOT AUTHORIZED TO EXECUTE** against Production.

## Preconditions

1. DB-03 implementation Green (ORM + Alembic + CI + rehearsal)
2. Current Production Alembic still `056_i5_w2_p02_conflict_safety` (reverify read-only)
3. Logical backup / `pg_dump` completed and restore-tested on isolated host
4. Deployment freeze window agreed
5. Role passwords held only in environment / secret manager

## Preflight (read-only)

```bash
# Use env DATABASE_URL — never embed credentials
alembic current
psql "$DATABASE_URL" -c "SELECT version_num FROM alembic_version;"
psql "$DATABASE_URL" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
```

Confirm: Alembic=056, table count baseline known, no unexpected drift.

## Migration order

1. Take backup
2. Stop writers that target deprecated authorities (or enable dual-write already shipped)
3. Apply Alembic: `057` → `058` → `059` → `060` (upgrade head)
4. Verify schema contract / row counts / conflict ledger
5. Cutover service reads (already dual-prefer in code)
6. Role hardening (separate step): create `sedi_app_runtime`, `sedi_migration_admin`, `sedi_dbeaver_readonly` from `roles_sedi_v1.sql` using env passwords
7. Dual-role period before removing SUPERUSER from `sedi_user`

## Commands (secrets from env)

```bash
export DATABASE_URL=...   # from secret store
cd workspace
alembic -c backend/alembic.ini upgrade head
```

## Post-migration verification

- `alembic current` == `060_db03_w4_w6_scale_inspect_roles`
- Target tables exist; HR indexes present with DESC measured_at
- `care_response_policies` windows all NULL unless prior approved authority
- No `rag_embeddings`; no `vector` extension required
- `db03_migration_conflicts` reviewed; unexplained loss = 0
- Smoke: consent insert, measurement idempotency, care episode link, vitals prefer PM

## Rollback / forward-fix

| Wave | Strategy |
|------|----------|
| 0–1 | Fully reversible (drop new cols/tables) |
| 2 | Logically reversible (source tables retained) |
| 3 | Forward-fix with dual-read fallback |
| 5 DROP | Forward-fix only after signoff (not in DB-03) |

## Explicit non-actions for DB-03

- No Production apply in DB-03
- No Production role GRANT/REVOKE in DB-03
- No SUPERUSER removal in DB-03
- No clinical window seeding
