-- DB-PROD-01 / §270.P — Role privilege SQL companion (DIRECT_LOGIN).
-- Applied programmatically by apply_roles_sedi_v1.py (preferred) or
-- apply_roles_sedi_v1.sh + psql -v ON_ERROR_STOP=1 -v dbname=...
--
-- ROLE_CONNECTION_MODEL = DIRECT_LOGIN
-- RATIONALE = matches Production DATABASE_URL login pattern in /etc/sedi/sedi-backend.env
--            and one-off alembic containers that authenticate as a LOGIN role.
--
-- FAIL-CLOSED requirements:
--   - No WHEN OTHERS THEN NULL
--   - No password literals in this file
--   - Unexpected errors must abort the applicator (non-zero exit)
--
-- Passwords are set only by the applicator from env:
--   SEDI_APP_RUNTIME_PASSWORD
--   SEDI_MIGRATION_ADMIN_PASSWORD
--   SEDI_DBEAVER_READONLY_PASSWORD

\set ON_ERROR_STOP on

ALTER ROLE sedi_app_runtime NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE sedi_migration_admin NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE sedi_dbeaver_readonly NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

COMMENT ON ROLE sedi_app_runtime IS 'DB-PROD-01 app runtime LOGIN: DML only; NEVER SUPERUSER; NEVER DDL';
COMMENT ON ROLE sedi_migration_admin IS 'DB-PROD-01 migration LOGIN: DDL/DML for Alembic; NEVER SUPERUSER; not routine app traffic';
COMMENT ON ROLE sedi_dbeaver_readonly IS 'DB-PROD-01 DBeaver LOGIN: SELECT + catalog; NEVER WRITE/DDL; NEVER app runtime';

SELECT format(
  'GRANT CONNECT ON DATABASE %I TO sedi_app_runtime, sedi_migration_admin, sedi_dbeaver_readonly',
  :'dbname'
) AS __grant_connect
\gexec

GRANT USAGE ON SCHEMA public TO sedi_app_runtime, sedi_migration_admin, sedi_dbeaver_readonly;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sedi_app_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sedi_app_runtime;
REVOKE CREATE ON SCHEMA public FROM sedi_app_runtime;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO sedi_dbeaver_readonly;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO sedi_dbeaver_readonly;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM sedi_dbeaver_readonly;
REVOKE CREATE ON SCHEMA public FROM sedi_dbeaver_readonly;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO sedi_migration_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO sedi_migration_admin;
GRANT CREATE ON SCHEMA public TO sedi_migration_admin;

ALTER DEFAULT PRIVILEGES FOR ROLE sedi_migration_admin IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sedi_app_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE sedi_migration_admin IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO sedi_app_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE sedi_migration_admin IN SCHEMA public
  GRANT SELECT ON TABLES TO sedi_dbeaver_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE sedi_migration_admin IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO sedi_dbeaver_readonly;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sedi_app_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO sedi_app_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO sedi_dbeaver_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO sedi_dbeaver_readonly;

DO $assert$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT rolname, rolsuper, rolcanlogin
    FROM pg_roles
    WHERE rolname IN ('sedi_app_runtime', 'sedi_migration_admin', 'sedi_dbeaver_readonly')
  LOOP
    IF r.rolsuper THEN
      RAISE EXCEPTION 'ROLE_INVARIANT_FAIL: % is SUPERUSER', r.rolname;
    END IF;
    IF NOT r.rolcanlogin THEN
      RAISE EXCEPTION 'ROLE_INVARIANT_FAIL: % is not LOGIN', r.rolname;
    END IF;
  END LOOP;
END
$assert$;
