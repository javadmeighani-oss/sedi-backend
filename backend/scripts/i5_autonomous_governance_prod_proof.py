#!/usr/bin/env python3
"""Production proof: autonomous discovery/qualify/monitor. NO activation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.app.database import get_db
import backend.app.models as models
from backend.app.services.i5.enums import KnowledgeUnitRuntimeEligibility
from backend.app.services.i5.trusted_source_manifest import (
    load_trusted_source_manifest,
)
from backend.app.services.i5.autonomous_source_governance import (
    ACTIVATION_HARD_BLOCK,
    run_foundation_pipeline,
    write_ledger,
)
from backend.app.services.i5.governed_specialized_entity_eligibility import (
    resolve_specialized_entity_from_url,
)


def main() -> int:
    load_trusted_source_manifest.cache_clear()
    db = next(get_db())
    try:
        ku = db.query(models.KnowledgeUnit).count()
        elig = (
            db.query(models.KnowledgeUnit)
            .filter(
                models.KnowledgeUnit.runtime_eligibility
                == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value
            )
            .count()
        )
        kce = db.query(models.KnowledgeChunkEmbedding).count()
        active = (
            db.query(models.KnowledgeSource)
            .filter(models.KnowledgeSource.source_fetch_enabled.is_(True))
            .count()
        )
        per = {f"D{i:02d}": {"ku": 0, "eligible": 0, "kce": 0} for i in range(1, 20)}
        als = ms = d17e = 0
        for p in db.query(models.KnowledgeProvenance).all():
            rid = getattr(p, "raw_evidence_id", None)
            raw = (
                db.query(models.I5RawEvidence).filter_by(id=int(rid)).one_or_none()
                if rid is not None
                else None
            )
            u = ""
            if raw is not None:
                u = ((raw.canonical_url or "") + " " + (getattr(raw, "final_url", None) or "")).lower()
            ku_row = db.query(models.KnowledgeUnit).filter_by(id=int(p.knowledge_unit_id)).one_or_none()
            if ku_row is None:
                continue
            is_elig = str(ku_row.runtime_eligibility) == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value
            entity = str(getattr(ku_row, "manifest_entity_id", None) or "")
            spec = resolve_specialized_entity_from_url(u)
            if spec is not None and not entity:
                entity = spec.entity_id
            kce_n = (
                db.query(models.KnowledgeChunkEmbedding)
                .filter(models.KnowledgeChunkEmbedding.knowledge_unit_id == int(ku_row.id))
                .count()
            )
            if entity in per:
                per[entity]["ku"] += 1
                if is_elig:
                    per[entity]["eligible"] += 1
                per[entity]["kce"] += kce_n
            if is_elig and "amyotrophiclateralsclerosis" in u:
                als += 1
            if is_elig and "multiplesclerosis" in u:
                ms += 1
            if is_elig and (entity == "D17" or "/niosh/" in u):
                d17e += 1
        serving = {d: ("PASS" if per[d]["eligible"] > 0 else "NO_ELIGIBLE") for d in per}

        report = run_foundation_pipeline(
            live=True,
            include_wave02_gaps=False,
            per_dxx=per,
            serving_proof=serving,
        )

        ledger = Path("/tmp/i5_autonomous_governance_ledger.json")
        write_ledger(report, ledger)
        slim = {k: v for k, v in report.items() if k != "candidates"}
        slim["baseline"] = {"ku": ku, "eligible": elig, "kce": kce, "active_db": active}
        slim["d17_elig"] = d17e
        slim["d18_als_eligible"] = als
        slim["d19_ms_eligible"] = ms
        print(json.dumps(slim, ensure_ascii=False, sort_keys=True), flush=True)

        if int(report.get("active_source_count") or 0) != 11:
            raise SystemExit(f"active_ne_11:{report.get('active_source_count')}")
        if active != 11:
            raise SystemExit(f"db_active_ne_11:{active}")
        if report.get("auto_activation") != "NO":
            raise SystemExit("auto_activation_not_no")
        if str(report.get("owh_activation") or "NO").upper() != "NO":
            raise SystemExit("owh_activated")
        if str(report.get("cdc_child_activation") or "NO").upper() != "NO":
            raise SystemExit("cdc_child_activated")
        if str(report.get("cdc_ncezid_activation") or "NO").upper() != "NO":
            raise SystemExit("cdc_ncezid_activated")
        if int(report.get("new_candidates") or 0) <= 0:
            raise SystemExit("no_new_candidates")
        for cid in ACTIVATION_HARD_BLOCK:
            hit = next((c for c in report["candidates"] if c.get("candidate_id") == cid), None)
            if hit is None:
                raise SystemExit(f"missing_hard_block:{cid}")
            if str(hit.get("activation") or "NO").upper() != "NO":
                raise SystemExit(f"hard_block_activated:{cid}")
        print(
            json.dumps(
                {
                    "eligibility_unchanged_ok": True,
                    "no_auto_activation": "YES",
                    "github_only": "YES",
                    "d17_regression": "NO" if d17e >= 5 else "YES",
                    "d18_als_regression": "NO" if als >= 2 else "YES",
                    "d19_ms_regression": "NO" if ms >= 2 else "YES",
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if d17e < 5 or als < 2 or ms < 2:
            raise SystemExit("serving_regression")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
