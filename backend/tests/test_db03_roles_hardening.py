"""DB-PROD-01 role artifact + isolated privilege contract tests."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops" / "db03"


def test_role_sql_fail_closed_no_others_null():
    text = (OPS / "roles_sedi_v1.sql").read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("--")
    )
    assert re.search(r"(?is)when\s+others\s+then\s+null", executable) is None
    assert "PASSWORD '" not in executable.upper()
    assert "DIRECT_LOGIN" in text


def test_role_applicator_exists_and_documents_env():
    py = (OPS / "apply_roles_sedi_v1.py").read_text(encoding="utf-8")
    assert "SEDI_APP_RUNTIME_PASSWORD" in py
    assert "SEDI_MIGRATION_ADMIN_PASSWORD" in py
    assert "SEDI_DBEAVER_READONLY_PASSWORD" in py
    assert "NOSUPERUSER" in py
    assert "WHEN others" not in py.lower() or "when others then null" not in py.lower()


def test_readiness_doc_matches_direct_login():
    md = (OPS / "PRODUCTION_MIGRATION_READINESS.md").read_text(encoding="utf-8")
    assert "DIRECT_LOGIN" in md or "sedi_app_runtime" in md
    assert "SEDI_APP_RUNTIME_PASSWORD" in md


@pytest.mark.skipif(
    os.environ.get("DB03_ALLOW_DESTRUCTIVE_REHEARSAL") != "YES"
    or not (os.environ.get("TEST_DATABASE_URL") or os.environ.get("DB03_REHEARSAL_DATABASE_URL")),
    reason="Isolated role rehearsal requires TEST_DATABASE_URL + DB03_ALLOW_DESTRUCTIVE_REHEARSAL=YES",
)
def test_isolated_role_hardening_rehearsal():
    import subprocess
    import uuid

    from sqlalchemy import create_engine, text

    url = os.environ.get("DB03_REHEARSAL_DATABASE_URL") or os.environ["TEST_DATABASE_URL"]
    # Use strong synthetic passwords (never Production secrets)
    app_pw = "app-runtime-rehearsal-" + uuid.uuid4().hex
    mig_pw = "mig-admin-rehearsal-" + uuid.uuid4().hex
    ro_pw = "dbeaver-ro-rehearsal-" + uuid.uuid4().hex

    eng = create_engine(url)
    with eng.connect() as conn:
        # Ensure baseline public objects exist for GRANT ALL TABLES
        conn.execute(text("CREATE TABLE IF NOT EXISTS db03_role_probe (id int primary key, v text)"))
        conn.commit()

    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["SEDI_APP_RUNTIME_PASSWORD"] = app_pw
    env["SEDI_MIGRATION_ADMIN_PASSWORD"] = mig_pw
    env["SEDI_DBEAVER_READONLY_PASSWORD"] = ro_pw
    proc = subprocess.run(
        ["python", str(OPS / "apply_roles_sedi_v1.py")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "ROLE_APPLY: PASS" in proc.stdout
    assert app_pw not in proc.stdout and app_pw not in proc.stderr

    # Privilege proofs via catalog (no password echo)
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT rolname, rolsuper, rolcanlogin, rolcreatedb, rolcreaterole
                FROM pg_roles
                WHERE rolname IN ('sedi_app_runtime','sedi_migration_admin','sedi_dbeaver_readonly')
                ORDER BY 1
                """
            )
        ).fetchall()
        assert len(rows) == 3
        for r in rows:
            assert r.rolsuper is False
            assert r.rolcanlogin is True
            assert r.rolcreatedb is False
            assert r.rolcreaterole is False

        # App cannot create tables (hascreate on schema)
        create_priv = conn.execute(
            text(
                """
                SELECT has_schema_privilege('sedi_app_runtime', 'public', 'CREATE')
                """
            )
        ).scalar()
        assert create_priv is False

        dml = conn.execute(
            text(
                """
                SELECT
                  has_table_privilege('sedi_app_runtime', 'db03_role_probe', 'SELECT')
                  AND has_table_privilege('sedi_app_runtime', 'db03_role_probe', 'INSERT')
                  AND has_table_privilege('sedi_app_runtime', 'db03_role_probe', 'UPDATE')
                  AND has_table_privilege('sedi_app_runtime', 'db03_role_probe', 'DELETE')
                """
            )
        ).scalar()
        assert dml is True

        ro_sel = conn.execute(
            text("SELECT has_table_privilege('sedi_dbeaver_readonly', 'db03_role_probe', 'SELECT')")
        ).scalar()
        ro_ins = conn.execute(
            text("SELECT has_table_privilege('sedi_dbeaver_readonly', 'db03_role_probe', 'INSERT')")
        ).scalar()
        assert ro_sel is True
        assert ro_ins is False

        mig_ddl = conn.execute(
            text("SELECT has_schema_privilege('sedi_migration_admin', 'public', 'CREATE')")
        ).scalar()
        assert mig_ddl is True

    # Fail-closed: missing password must non-zero
    env_bad = env.copy()
    del env_bad["SEDI_APP_RUNTIME_PASSWORD"]
    bad = subprocess.run(
        ["python", str(OPS / "apply_roles_sedi_v1.py")],
        env=env_bad,
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode != 0
