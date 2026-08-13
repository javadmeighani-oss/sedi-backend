"""Bounded Catalog-12 one-shot canary (derived only; no weekly enablement).

Must run with PYTHONPATH=/app inside sedi-backend.
Does not set SEDI_I5_MULTISOURCE_ENABLED. Does not enable weekly for new sources.
"""

from __future__ import annotations

import os
import time
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("PYTHONPATH", "/app")


def _log(key: str, value: Any) -> None:
    print(f"I5_C12|{key}|{value}", flush=True)


def _counts(db):
    from backend.app import models

    mem = 0
    kce = 0
    if hasattr(models, "KnowledgeMemoryItem"):
        mem = db.query(models.KnowledgeMemoryItem).count()
    if hasattr(models, "KnowledgeChunkEmbedding"):
        kce = db.query(models.KnowledgeChunkEmbedding).count()
    elif hasattr(models, "I5KnowledgeChunkEmbedding"):
        kce = db.query(models.I5KnowledgeChunkEmbedding).count()
    eligible = (
        db.query(models.KnowledgeUnit)
        .filter(models.KnowledgeUnit.runtime_eligibility == "ELIGIBLE")
        .count()
    )
    return {
        "raw": db.query(models.I5RawEvidence).count(),
        "artifact": db.query(models.I5ScientificArtifact).count(),
        "ku": db.query(models.KnowledgeUnit).count(),
        "prov": db.query(models.KnowledgeProvenance).count(),
        "memory": mem,
        "kce": kce,
        "eligible": eligible,
    }


def _http_get(url: str, headers=None, timeout=None):
    import urllib.request

    ua = (headers or {}).get("User-Agent") or "SediCatalog12Canary/1.0 (+https://sedi-ai.com)"
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout or 15.0) as resp:  # noqa: S310
        body = resp.read(2_000_000)
        return {
            "status_code": int(getattr(resp, "status", 200)),
            "headers": dict(resp.headers),
            "content": body,
            "url": url,
        }


def main() -> int:
    from backend.app import models
    from backend.app.services.i5.know01.catalog12_specialty_authorities import (
        CATALOG12_CELL_IDS,
        cell_by_id,
        scorecard,
    )
    from backend.app.services.i5.know01.reference_coverage_matrix import (
        PARTIAL,
        build_reference_catalog_coverage_matrix,
    )
    from backend.app.services.i5.know05.catalog12_bounded_ingest import ingest_catalog12_cell

    cells_arg = os.environ.get("CATALOG12_CELLS", "").strip()
    cell_ids = [c.strip() for c in cells_arg.split(",") if c.strip()] or list(CATALOG12_CELL_IDS)
    live = os.environ.get("CATALOG12_LIVE", "NO").strip().upper() == "YES"

    url = os.environ.get("DATABASE_URL")
    if not url:
        _log("database_url", "MISSING")
        return 2
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        alembic = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        _log("alembic", alembic)
        waiting = db.execute(
            text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'")
        ).scalar()
        _log("pool_lock_waiters", int(waiting or 0))
        before = _counts(db)
        for k, v in before.items():
            _log(f"before_{k}", v)

        orch = os.environ.get("SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED", "")
        src = os.environ.get("SEDI_I5_SOURCE_ACTIVATION_ENABLED", "")
        multi = os.environ.get("SEDI_I5_MULTISOURCE_ENABLED", "")
        _log("i5_weekly_orchestrator_enabled", orch)
        _log("i5_source_activation_enabled", src)
        _log("i5_multisource_enabled", multi)
        _log("weekly_multisource_expansion", "NO")
        _log("unattended_weekly_enabled_for_new_sources", "NO")
        if str(multi).strip().lower() in {"1", "true", "yes"}:
            _log("multisource_guard", "FAIL")
            return 5
        _log("multisource_guard", "PASS")

        matrix = {c.entity_id: c for c in build_reference_catalog_coverage_matrix()}
        ok = 0
        fail = 0
        for idx, cid in enumerate(cell_ids):
            cell = cell_by_id(cid)
            card = scorecard(cell)
            _log(f"{cid}_primary", card["PRIMARY_AUTHORITY"])
            _log(f"{cid}_domain", card["PRIMARY_DOMAIN"])
            _log(f"{cid}_weekly", "NO")
            mc = matrix.get(cid)
            _log(f"{cid}_matrix_strength", getattr(mc, "match_strength", "MISSING"))
            _log(f"{cid}_matrix_status", getattr(mc, "coverage_status", "MISSING"))
            if not live:
                _log(f"{cid}_live_skipped", "STATIC_ONLY")
                continue
            if idx:
                time.sleep(1.1)
            try:
                r1 = ingest_catalog12_cell(db, cid, persist=True, http_get=_http_get)
                db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                _log(f"{cid}_status", "FAILED")
                _log(f"{cid}_http", 0)
                _log(f"{cid}_reason", f"UNCAUGHT:{type(exc).__name__}")
                fail += 1
                continue
            try:
                r2 = ingest_catalog12_cell(db, cid, persist=True, http_get=_http_get)
                db.commit()
            except Exception:
                db.rollback()
                r2 = r1
                r2.created_new = True
            _log(f"{cid}_status", r1.status)
            _log(f"{cid}_http", r1.http_status)
            _log(f"{cid}_reason", r1.block_reason or "")
            _log(f"{cid}_ku_id", r1.knowledge_unit_id or 0)
            _log(f"{cid}_artifact_id", r1.artifact_id or 0)
            _log(f"{cid}_raw_id", r1.raw_evidence_id or 0)
            _log(f"{cid}_created_new", r1.created_new)
            _log(
                f"{cid}_idempotent",
                "PASS" if (r2.created_new is False and r2.status == "STORED") else "NO",
            )
            if r1.knowledge_unit_id:
                ku = db.query(models.KnowledgeUnit).filter_by(id=r1.knowledge_unit_id).one()
                _log(f"{cid}_publication", ku.publication_state)
                _log(f"{cid}_review", ku.review_state)
                _log(f"{cid}_eligibility", ku.runtime_eligibility)
            if r1.status == "STORED" and r2.created_new is False:
                ok += 1
            else:
                fail += 1

        after = _counts(db)
        for k, v in after.items():
            _log(f"after_{k}", v)
            _log(f"delta_{k}", v - before[k])
        remaining_partial = [
            eid
            for eid in CATALOG12_CELL_IDS
            if getattr(matrix.get(eid), "coverage_status", None) == PARTIAL
        ]
        _log("live_fetch_success", ok)
        _log("live_fetch_failure", fail)
        _log("catalog12_partial_remaining", ",".join(remaining_partial) or "0")
        _log("eligible_delta", after["eligible"] - before["eligible"])
        _log("memory_delta", after["memory"] - before["memory"])
        _log("kce_delta", after["kce"] - before["kce"])
        waiting2 = db.execute(
            text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'")
        ).scalar()
        _log("pool_lock_waiters_after", int(waiting2 or 0))
        _log("canary_complete", "YES")
        if live and after["eligible"] != before["eligible"]:
            return 6
        if live and (after["memory"] != before["memory"] or after["kce"] != before["kce"]):
            return 7
        return 0 if fail == 0 else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
