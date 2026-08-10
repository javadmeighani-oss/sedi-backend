-- DB-03 / §270.P — Target role design artifacts (NOT applied to Production in DB-03)
-- Passwords MUST be supplied from environment / secret manager. Never commit passwords.
-- Apply only on isolated PostgreSQL during ops/Production Migration Gate.

-- Example (env-held):
--   \set sedi_app_runtime_password `echo "$SEDI_APP_RUNTIME_PASSWORD"`
-- Do not embed credentials in this file.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sedi_app_runtime') THEN
    CREATE ROLE sedi_app_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sedi_migration_admin') THEN
    CREATE ROLE sedi_migration_admin NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sedi_dbeaver_readonly') THEN
    CREATE ROLE sedi_dbeaver_readonly NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
EXCEPTION
  WHEN others THEN
    NULL;
END $$;

-- Correct readonly role (explicit NOSUPERUSER)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sedi_dbeaver_readonly') THEN
    CREATE ROLE sedi_dbeaver_readonly NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  ELSE
    ALTER ROLE sedi_dbeaver_readonly NOSUPERUSER;
  END IF;
  ALTER ROLE sedi_app_runtime NOSUPERUSER;
END $$;

-- Grants (design). Database name is environment-specific.
-- GRANT CONNECT ON DATABASE current_database TO sedi_app_runtime, sedi_migration_admin, sedi_dbeaver_readonly;
-- GRANT USAGE ON SCHEMA public TO sedi_app_runtime, sedi_migration_admin, sedi_dbeaver_readonly;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sedi_app_runtime;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO sedi_dbeaver_readonly;
-- GRANT ALL ON ALL TABLES IN SCHEMA public TO sedi_migration_admin;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO sedi_dbeaver_readonly;

COMMENT ON ROLE sedi_app_runtime IS 'DB-03 target app runtime: DML only; NEVER SUPERUSER';
COMMENT ON ROLE sedi_migration_admin IS 'DB-03 target migration admin: DDL/DML for migrations only';
COMMENT ON ROLE sedi_dbeaver_readonly IS 'DB-03 DBeaver inspectability: SELECT + catalog; NEVER app runtime role';

-- Invariant documentation:
-- sedi_app_runtime != SUPERUSER
-- sedi_dbeaver_readonly != sedi_app_runtime
-- Production sedi_user SUPERUSER remediation is deferred to Production Migration Gate
