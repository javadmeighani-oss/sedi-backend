#!/usr/bin/env python3
"""DB-PROD-01 — Apply DIRECT_LOGIN role hardening (fail-closed).

Never prints password values. Never commits secrets.
Required env:
  DATABASE_URL (admin / migration-capable connection)
  SEDI_APP_RUNTIME_PASSWORD
  SEDI_MIGRATION_ADMIN_PASSWORD
  SEDI_DBEAVER_READONLY_PASSWORD

Exit codes:
  0 PASS
  2 missing env
  3 password too short
  4 apply failure
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql


MIN_PW = 16
ROLES = (
    ("sedi_app_runtime", "SEDI_APP_RUNTIME_PASSWORD"),
    ("sedi_migration_admin", "SEDI_MIGRATION_ADMIN_PASSWORD"),
    ("sedi_dbeaver_readonly", "SEDI_DBEAVER_READONLY_PASSWORD"),
)


def _require_pw(name: str) -> str:
    val = os.environ.get(name, "")
    if not val:
        print(f"ROLE_APPLY_FAIL: missing {name}", file=sys.stderr)
        raise SystemExit(2)
    if len(val) < MIN_PW:
        print(f"ROLE_APPLY_FAIL: {name} too short (min {MIN_PW})", file=sys.stderr)
        raise SystemExit(3)
    return val


def _normalize_url(url: str) -> str:
    return (
        url.replace("postgresql+psycopg2://", "postgresql://", 1)
        .replace("postgres+psycopg2://", "postgresql://", 1)
    )


def main() -> int:
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        print("ROLE_APPLY_FAIL: missing DATABASE_URL", file=sys.stderr)
        return 2

    passwords = {role: _require_pw(env) for role, env in ROLES}
    print(
        "ROLE_APPLY: password_lengths "
        + " ".join(f"{role}={len(passwords[role])}" for role, _ in ROLES)
    )

    conn = psycopg2.connect(_normalize_url(raw))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for role, _env in ROLES:
                pw = passwords[role]
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
                exists = cur.fetchone() is not None
                if not exists:
                    cur.execute(
                        sql.SQL(
                            "CREATE ROLE {} LOGIN PASSWORD {} "
                            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION INHERIT"
                        ).format(sql.Identifier(role), sql.Literal(pw))
                    )
                else:
                    cur.execute(
                        sql.SQL(
                            "ALTER ROLE {} WITH LOGIN PASSWORD {} "
                            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION INHERIT"
                        ).format(sql.Identifier(role), sql.Literal(pw))
                    )

            grants_path = Path(__file__).with_name("roles_sedi_v1.sql")
            sql_text = grants_path.read_text(encoding="utf-8")
            # Strip psql meta-commands; execute remaining statements via server.
            # roles_sedi_v1.sql uses \set / \gexec — apply equivalent in Python.
            cur.execute("SELECT current_database()")
            dbname = cur.fetchone()[0]
            print(f"ROLE_APPLY: dbname={dbname}")

            for role, _ in ROLES:
                cur.execute(
                    sql.SQL(
                        "ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION"
                    ).format(sql.Identifier(role))
                )

            cur.execute(
                sql.SQL(
                    "GRANT CONNECT ON DATABASE {} TO sedi_app_runtime, sedi_migration_admin, sedi_dbeaver_readonly"
                ).format(sql.Identifier(dbname))
            )
            cur.execute(
                "GRANT USAGE ON SCHEMA public TO sedi_app_runtime, sedi_migration_admin, sedi_dbeaver_readonly"
            )
            cur.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sedi_app_runtime"
            )
            cur.execute(
                "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sedi_app_runtime"
            )
            cur.execute("REVOKE CREATE ON SCHEMA public FROM sedi_app_runtime")

            cur.execute(
                "GRANT SELECT ON ALL TABLES IN SCHEMA public TO sedi_dbeaver_readonly"
            )
            cur.execute(
                "GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO sedi_dbeaver_readonly"
            )
            cur.execute(
                "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM sedi_dbeaver_readonly"
            )
            cur.execute("REVOKE CREATE ON SCHEMA public FROM sedi_dbeaver_readonly")

            cur.execute(
                "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO sedi_migration_admin"
            )
            cur.execute(
                "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO sedi_migration_admin"
            )
            cur.execute("GRANT CREATE ON SCHEMA public TO sedi_migration_admin")

            # Default privileges
            for stmt in (
                "ALTER DEFAULT PRIVILEGES FOR ROLE sedi_migration_admin IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sedi_app_runtime",
                "ALTER DEFAULT PRIVILEGES FOR ROLE sedi_migration_admin IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO sedi_app_runtime",
                "ALTER DEFAULT PRIVILEGES FOR ROLE sedi_migration_admin IN SCHEMA public GRANT SELECT ON TABLES TO sedi_dbeaver_readonly",
                "ALTER DEFAULT PRIVILEGES FOR ROLE sedi_migration_admin IN SCHEMA public GRANT SELECT ON SEQUENCES TO sedi_dbeaver_readonly",
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sedi_app_runtime",
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO sedi_app_runtime",
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO sedi_dbeaver_readonly",
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO sedi_dbeaver_readonly",
            ):
                cur.execute(stmt)

            # Invariant assertions
            cur.execute(
                """
                SELECT rolname, rolsuper, rolcanlogin
                FROM pg_roles
                WHERE rolname IN ('sedi_app_runtime', 'sedi_migration_admin', 'sedi_dbeaver_readonly')
                """
            )
            rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
            for role, _ in ROLES:
                if role not in rows:
                    raise RuntimeError(f"ROLE_INVARIANT_FAIL: {role} missing")
                is_super, can_login = rows[role]
                if is_super:
                    raise RuntimeError(f"ROLE_INVARIANT_FAIL: {role} is SUPERUSER")
                if not can_login:
                    raise RuntimeError(f"ROLE_INVARIANT_FAIL: {role} is not LOGIN")

            # Catalog comments (best-effort comments don't use passwords)
            cur.execute(
                "COMMENT ON ROLE sedi_app_runtime IS 'DB-PROD-01 app runtime LOGIN: DML only; NEVER SUPERUSER; NEVER DDL'"
            )
            cur.execute(
                "COMMENT ON ROLE sedi_migration_admin IS 'DB-PROD-01 migration LOGIN: DDL/DML for Alembic; NEVER SUPERUSER'"
            )
            cur.execute(
                "COMMENT ON ROLE sedi_dbeaver_readonly IS 'DB-PROD-01 DBeaver LOGIN: SELECT + catalog; NEVER WRITE/DDL'"
            )

        print("ROLE_APPLY: PASS")
        print(f"ROLE_SQL_ARTIFACT={grants_path.name}")
        _ = sql_text  # retained for audit that SQL artifact exists
        return 0
    except Exception as exc:  # noqa: BLE001 — fail-closed, do not swallow
        print(f"ROLE_APPLY_FAIL: {type(exc).__name__}", file=sys.stderr)
        return 4
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
