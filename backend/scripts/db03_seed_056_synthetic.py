#!/usr/bin/env python
"""Seed bounded synthetic rows at Alembic 056 baseline for DB-03 upgrade rehearsal.

Never uses real PHI/PII. Never prints DATABASE_URL.
"""
from __future__ import annotations

import hashlib
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def main() -> int:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        print("SEED_SKIPPED_NO_URL")
        return 2
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        row = db.execute(text("SELECT id FROM users WHERE name = 'synth_a' LIMIT 1")).fetchone()
        if row is None:
            row = db.execute(
                text(
                    """
                    INSERT INTO users (name, secret_key, preferred_language, created_at, account_type)
                    VALUES ('synth_a', 'x', 'en', now(), 'normal')
                    RETURNING id
                    """
                )
            ).fetchone()
        user_id = int(row[0])

        db.execute(
            text(
                """
                INSERT INTO devices (user_id, device_id, device_type, status, token_hash, created_at)
                SELECT :uid, 'synth-device-1', 'heart_rate', 'active', :th, now()
                WHERE NOT EXISTS (SELECT 1 FROM devices WHERE device_id = 'synth-device-1')
                """
            ),
            {"uid": user_id, "th": hashlib.sha256(b"synth").hexdigest()},
        )
        db.execute(
            text(
                """
                INSERT INTO user_facts (user_id, key, value_json, source, confidence, updated_at)
                SELECT :uid, 'favorite_tea', '"chamomile"', 'manual', 0.8, now()
                WHERE NOT EXISTS (
                  SELECT 1 FROM user_facts WHERE user_id = :uid AND key = 'favorite_tea'
                )
                """
            ),
            {"uid": user_id},
        )
        db.execute(
            text(
                """
                INSERT INTO daily_memory_summaries (user_id, summary, mood, context, created_at)
                SELECT :uid, 'Synthetic daily summary', 'calm', 'seed', now()
                WHERE NOT EXISTS (
                  SELECT 1 FROM daily_memory_summaries
                  WHERE user_id = :uid AND summary = 'Synthetic daily summary'
                )
                """
            ),
            {"uid": user_id},
        )
        db.execute(
            text(
                """
                INSERT INTO health_data (user_id, heart_rate, temperature, spo2, created_at)
                SELECT :uid, '72', '36.6', '98', now()
                WHERE NOT EXISTS (
                  SELECT 1 FROM health_data WHERE user_id = :uid AND heart_rate = '72'
                )
                """
            ),
            {"uid": user_id},
        )
        db.commit()
        print("SEED_OK")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print("SEED_FAIL", type(exc).__name__)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
