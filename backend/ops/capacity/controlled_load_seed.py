"""Seed ephemeral synthetic users for controlled-load validation (no PHI)."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)


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
    """Create n_users Accounts + SELF HS; family_subset with managed Mother HS."""
    engine = create_engine(_db_url(), pool_pre_ping=True, pool_size=5, max_overflow=5)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    t0 = time.perf_counter()
    user_ids: List[int] = []
    family_pairs: List[Dict[str, int]] = []
    fake_mother_accounts = 0

    with engine.begin() as conn:
        # Best-effort cleanup for harness re-runs on ephemeral DBs.
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
            # Fresh ephemeral DB may not need cleanup; continue.
            print(f"[seed] cleanup_warning={type(exc).__name__}", flush=True)

    db = Session()
    try:
        for i in range(1, n_users + 1):
            u = models.User(
                name=f"{PREFIX}{i:04d}",
                secret_key=f"synth_secret_{i}",
                preferred_language="en",
            )
            db.add(u)
            db.flush()
            ensure_self_subject_for_account(db, u.id, display_name=f"SELF_{i:04d}", commit=False)
            user_ids.append(int(u.id))
            if i <= family_subset:
                mother = create_managed_subject_without_account(
                    db,
                    account_user_id=u.id,
                    display_name=f"{PREFIX}mother_{i:04d}",
                    access_role="MANAGER",
                    commit=False,
                )
                assert mother.linked_user_id is None
                family_pairs.append(
                    {
                        "son_user_id": int(u.id),
                        "mother_hs_id": int(mother.id),
                    }
                )
            if i % 100 == 0:
                db.commit()
        db.commit()

        # Identity invariant: no Mother Account rows
        mothers = (
            db.query(models.User)
            .filter(models.User.name.like(f"{PREFIX}mother_%"))
            .count()
        )
        fake_mother_accounts = int(mothers)
        if fake_mother_accounts != 0:
            raise RuntimeError("FAKE_MOTHER_ACCOUNT_CREATED")

        maxc = int(db.execute(text("SHOW max_connections")).scalar_one())
        pgver = str(db.execute(text("SHOW server_version")).scalar_one())
    finally:
        db.close()
        engine.dispose()

    return {
        "registered_users_seeded": len(user_ids),
        "user_ids": user_ids,
        "family_subset": len(family_pairs),
        "family_pairs": family_pairs,
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
    # Don't dump all ids to stdout in CI logs by default
    slim = {k: v for k, v in out.items() if k not in ("user_ids", "family_pairs")}
    slim["user_ids_count"] = len(out["user_ids"])
    print(json.dumps(slim, indent=2))
