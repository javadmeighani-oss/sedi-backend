"""Seed ephemeral synthetic users for controlled-load validation (no PHI)."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List

from sqlalchemy import create_engine, text

PREFIX = "syn_cl_"


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL/TEST_DATABASE_URL required")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def seed_registered_users(
    *,
    n_users: int = 1000,
    family_subset: int = 20,
) -> Dict[str, Any]:
    """Create n_users Accounts + SELF HS; family_subset with managed Mother HS.

    Uses bulk SQL for speed on ephemeral CI. Preserves identity law:
    Son Account != Mother; Mother linked_user_id=NULL; no fake Mother Account.
    """
    engine = create_engine(_db_url(), pool_pre_ping=True, pool_size=5, max_overflow=5)
    t0 = time.perf_counter()

    with engine.begin() as conn:
        # Best-effort cleanup for harness re-runs.
        try:
            conn.execute(
                text(
                    """
                    DELETE FROM account_health_subject_access
                    WHERE account_user_id IN (SELECT id FROM users WHERE name LIKE :pfx)
                    """
                ),
                {"pfx": f"{PREFIX}%"},
            )
            conn.execute(
                text(
                    """
                    DELETE FROM health_subjects
                    WHERE display_name LIKE :mpfx
                       OR linked_user_id IN (SELECT id FROM users WHERE name LIKE :pfx)
                    """
                ),
                {"pfx": f"{PREFIX}%", "mpfx": f"{PREFIX}mother_%"},
            )
            conn.execute(text("DELETE FROM users WHERE name LIKE :pfx"), {"pfx": f"{PREFIX}%"})
        except Exception as exc:  # noqa: BLE001
            print(f"[seed] cleanup_warning={type(exc).__name__}", flush=True)

        conn.execute(
            text(
                """
                INSERT INTO users (name, secret_key, preferred_language, created_at, account_type)
                SELECT
                  :pfx || lpad(g::text, 4, '0'),
                  'synth_secret_' || g::text,
                  'en',
                  now(),
                  'normal'
                FROM generate_series(1, :n) g
                """
            ),
            {"pfx": PREFIX, "n": int(n_users)},
        )

        # SELF HealthSubjects linked to each account
        conn.execute(
            text(
                """
                INSERT INTO health_subjects (display_name, linked_user_id, subject_kind, status, created_at)
                SELECT
                  'SELF_' || lpad(row_number() OVER (ORDER BY u.id)::text, 4, '0'),
                  u.id,
                  'self',
                  'active',
                  now()
                FROM users u
                WHERE u.name LIKE :pfx
                ORDER BY u.id
                """
            ),
            {"pfx": f"{PREFIX}%"},
        )

        conn.execute(
            text(
                """
                INSERT INTO account_health_subject_access
                  (account_user_id, health_subject_id, access_role, is_active, created_at)
                SELECT
                  hs.linked_user_id,
                  hs.id,
                  'SELF',
                  true,
                  now()
                FROM health_subjects hs
                JOIN users u ON u.id = hs.linked_user_id
                WHERE u.name LIKE :pfx AND hs.subject_kind = 'self'
                """
            ),
            {"pfx": f"{PREFIX}%"},
        )

        # Family subset: managed Mother HS (linked_user_id NULL)
        conn.execute(
            text(
                """
                WITH sons AS (
                  SELECT u.id AS son_id, row_number() OVER (ORDER BY u.id) AS rn
                  FROM users u
                  WHERE u.name LIKE :pfx
                  ORDER BY u.id
                  LIMIT :fam
                ),
                mothers AS (
                  INSERT INTO health_subjects (display_name, linked_user_id, subject_kind, status, created_at)
                  SELECT :mpfx || lpad(s.rn::text, 4, '0'), NULL, 'managed', 'active', now()
                  FROM sons s
                  RETURNING id, display_name
                )
                INSERT INTO account_health_subject_access
                  (account_user_id, health_subject_id, access_role, is_active, created_at)
                SELECT
                  s.son_id,
                  m.id,
                  'MANAGER',
                  true,
                  now()
                FROM sons s
                JOIN mothers m
                  ON m.display_name = :mpfx || lpad(s.rn::text, 4, '0')
                """
            ),
            {"pfx": f"{PREFIX}%", "mpfx": f"{PREFIX}mother_", "fam": int(family_subset)},
        )

        user_ids = [
            int(r[0])
            for r in conn.execute(
                text("SELECT id FROM users WHERE name LIKE :pfx ORDER BY id"),
                {"pfx": f"{PREFIX}%"},
            ).fetchall()
        ]
        family_n = int(
            conn.execute(
                text(
                    """
                    SELECT count(*) FROM health_subjects
                    WHERE display_name LIKE :mpfx AND linked_user_id IS NULL
                    """
                ),
                {"mpfx": f"{PREFIX}mother_%"},
            ).scalar_one()
        )
        fake_mother_accounts = int(
            conn.execute(
                text("SELECT count(*) FROM users WHERE name LIKE :mpfx"),
                {"mpfx": f"{PREFIX}mother_%"},
            ).scalar_one()
        )
        if fake_mother_accounts != 0:
            raise RuntimeError("FAKE_MOTHER_ACCOUNT_CREATED")
        null_link_ok = int(
            conn.execute(
                text(
                    """
                    SELECT count(*) FROM health_subjects
                    WHERE display_name LIKE :mpfx AND linked_user_id IS NOT NULL
                    """
                ),
                {"mpfx": f"{PREFIX}mother_%"},
            ).scalar_one()
        )
        if null_link_ok != 0:
            raise RuntimeError("MOTHER_LINKED_USER_ID_NOT_NULL")

        maxc = int(conn.execute(text("SHOW max_connections")).scalar_one())
        pgver = str(conn.execute(text("SHOW server_version")).scalar_one())

    engine.dispose()
    return {
        "registered_users_seeded": len(user_ids),
        "user_ids": user_ids,
        "family_subset": family_n,
        "family_pairs": [],
        "fake_mother_accounts": fake_mother_accounts,
        "postgres_max_connections": maxc,
        "postgres_server_version": pgver,
        "seed_duration_s": round(time.perf_counter() - t0, 3),
        "prefix": PREFIX,
    }


if __name__ == "__main__":
    import json

    out = seed_registered_users(
        n_users=int(os.environ.get("REGISTERED_USERS", "1000")),
        family_subset=int(os.environ.get("FAMILY_SUBSET", "20")),
    )
    slim = {k: v for k, v in out.items() if k not in ("user_ids", "family_pairs")}
    slim["user_ids_count"] = len(out["user_ids"])
    print(json.dumps(slim, indent=2))
