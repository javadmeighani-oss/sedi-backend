"""CLI helpers for Iran directory production apply (no schema mutation)."""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy.orm import Session


def _load_records(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "records" in data:
        records = data["records"]
    else:
        records = data
    if not isinstance(records, list):
        raise SystemExit("INVALID_PAYLOAD: expected list or {records:[...]}")
    return records


@contextmanager
def open_script_session(*, commit: bool = False) -> Iterator[Session]:
    """Acquire a real SQLAlchemy Session for scripts.

    `SessionLocal` in `backend.app.database` is generator-style (FastAPI `Depends`
    / `next(SessionLocal())`). Scripts must use `SessionFactory()` — the same
    pattern as `seed_medical_data.py` / `seed_i5b2_p1_l1_legacy_companions.py`.
    """
    from backend.app.database import SessionFactory

    db = SessionFactory()
    try:
        yield db
        if commit:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Iran directory dry-run / apply / replay")
    parser.add_argument("mode", choices=["dry-run", "apply", "replay", "search-proof"])
    parser.add_argument("--payload", required=False, help="Path to normalized JSON payload")
    parser.add_argument("--family", default="DOCTOR", choices=["DOCTOR", "LABORATORY", "HOSPITAL"])
    args = parser.parse_args(argv)

    from backend.app.services.i5.iran_directory_import import apply_plan, dry_run_plan
    from backend.app.services.i5.iran_directory_service import (
        search_doctors,
        search_hospitals,
        search_laboratories,
    )

    write_modes = {"apply", "replay"}
    with open_script_session(commit=args.mode in write_modes) as db:
        if args.mode == "search-proof":
            if args.family == "DOCTOR":
                rows = search_doctors(db, limit=5)
            elif args.family == "LABORATORY":
                rows = search_laboratories(db, limit=5)
            else:
                rows = search_hospitals(db, limit=5)
            print(json.dumps({
                "family": args.family,
                "count": len(rows),
                "sample_keys": [r.get("canonical_directory_key") for r in rows[:3]],
                "source_labels": list({r.get("source_system_label") for r in rows if r.get("source_system_label")}),
                "clinical_authority_any": any(r.get("is_clinical_authority") for r in rows),
                "ku_any": any(r.get("is_knowledge_unit") for r in rows),
            }, ensure_ascii=False))
            return 0

        if not args.payload:
            raise SystemExit("--payload required for dry-run/apply/replay")
        records = _load_records(Path(args.payload))
        if args.mode == "dry-run":
            plan = dry_run_plan(records, db)
            print(json.dumps({"mode": "dry-run", "plan": plan}, ensure_ascii=False))
            return 0
        if args.mode == "apply":
            plan = apply_plan(db, records)
            print(json.dumps({"mode": "apply", "plan": plan}, ensure_ascii=False))
            return 0
        # replay
        before = dry_run_plan(records, db)
        plan = apply_plan(db, records)
        after = dry_run_plan(records, db)
        print(json.dumps({
            "mode": "replay",
            "before": before,
            "apply_plan_returned": plan,
            "after": after,
        }, ensure_ascii=False))
        # Material inserts/updates on replay should be zero for same payload.
        for family, counts in after.items():
            if counts.get("insert", 0) != 0:
                raise SystemExit(f"REPLAY_NOT_IDEMPOTENT_INSERT:{family}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
