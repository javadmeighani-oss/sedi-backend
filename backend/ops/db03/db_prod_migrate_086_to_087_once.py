#!/usr/bin/env python3
"""One-shot Alembic upgrade helper for A4 prod migrate 086→087.

Runs as sedi_migration_admin. Never force-logouts. Never deploys.
"""
from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import quote, urlsplit, urlunsplit

from sqlalchemy.engine import make_url


def main() -> int:
    target = os.environ["MIG_TARGET_REV"]
    raw = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
    parts = urlsplit(raw)
    pw = os.environ["SEDI_MIGRATION_ADMIN_PASSWORD"]
    auth = f"sedi_migration_admin:{quote(pw, safe='')}"
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{auth}@{host}{port}"
    mig_url = urlunsplit(
        ("postgresql+psycopg2", netloc, parts.path, parts.query, parts.fragment)
    )
    u = make_url(mig_url)
    assert u.username == "sedi_migration_admin", u.username
    env = os.environ.copy()
    env["DATABASE_URL"] = mig_url
    env["TEST_DATABASE_URL"] = ""
    print("MIG086087|migration_role|sedi_migration_admin", flush=True)
    print(f"MIG086087|migration_command|alembic upgrade {target}", flush=True)
    return subprocess.call(
        ["python", "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", target],
        env=env,
    )


if __name__ == "__main__":
    sys.exit(main())
