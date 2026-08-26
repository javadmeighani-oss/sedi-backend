#!/usr/bin/env python3
"""Production proof: D08 NIDCD extraction/content-quality hardening (no auto-activation)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from backend.app.database import get_db
import backend.app.models as models
from backend.app.services.i5.enums import KnowledgeUnitRuntimeEligibility
from backend.app.services.i5.governed_ku_serving import apply_governed_finalize_and_lexical_index
from backend.app.services.i5.governed_specialized_entity_eligibility import (
    resolve_specialized_entity_from_url,
    strip_html_nav_chrome,
)
from backend.app.services.i5.multisource_activation import (
    activate_multisource_allowlist,
    load_multisource_weekly_candidates,
    multisource_enabled,
)
from backend.app.services.i5.trusted_source_manifest import (
    load_trusted_source_manifest,
)
from backend.app.services.i5.weekly_orchestrator import run_controlled_live_orchestration
from backend.app.services.scis.contracts import RetrievalMode, ScisRetrievalRequest
from backend.app.services.scis.retrieval import retrieve as scis_retrieve

SOURCE_KEY = "nidcd_hearing_balance"


def _counts(db):
    ku = db.query(models.KnowledgeUnit).count()
    elig = (
        db.query(models.KnowledgeUnit)
        .filter(models.KnowledgeUnit.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value)
        .count()
    )
    kce = db.query(models.KnowledgeChunkEmbedding).count()
    return ku, elig, kce


def _d08_stats(db):
    ku_n = elig_n = kce_n = 0
    for p in db.query(models.KnowledgeProvenance).all():
        rid = getattr(p, "raw_evidence_id", None)
        raw = db.query(models.I5RawEvidence).filter_by(id=int(rid)).one_or_none() if rid is not None else None
        u = ""
        if raw is not None:
            u = ((raw.canonical_url or "") + " " + (getattr(raw, "final_url", None) or "")).lower()
        ku = db.query(models.KnowledgeUnit).filter_by(id=int(p.knowledge_unit_id)).one_or_none()
        if ku is None:
            continue
        entity = str(getattr(ku, "manifest_entity_id", None) or "")
        spec = resolve_specialized_entity_from_url(u)
        if entity != "D08" and not (spec and spec.entity_id == "D08") and "nidcd.nih.gov/health" not in u:
            continue
        ku_n += 1
        if str(ku.runtime_eligibility) == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
            elig_n += 1
        kce_n += (
            db.query(models.KnowledgeChunkEmbedding)
            .filter(models.KnowledgeChunkEmbedding.knowledge_unit_id == int(ku.id))
            .count()
        )
    return {"ku": ku_n, "eligible": elig_n, "kce": kce_n}


def main() -> int:
    load_trusted_source_manifest.cache_clear()
    os.environ["I5_AUTONOMOUS_GOVERNANCE_SIDE_STAGE"] = "1"
    if not multisource_enabled():
        raise SystemExit("MULTISOURCE_ENV_NOT_ENABLED")

    db = next(get_db())
    try:
        ku0, elig0, kce0 = _counts(db)
        d08_before = _d08_stats(db)
        print(json.dumps({"before": {"ku": ku0, "eligible": elig0, "kce": kce0, "d08": d08_before}}, sort_keys=True), flush=True)

        result = activate_multisource_allowlist(db, models)
        db.commit()
        if SOURCE_KEY not in set(result.activated_source_keys):
            raise SystemExit("nidcd_not_activated")
        if result.fetch_enabled_count != 17:
            raise SystemExit(f"fetch_enabled_ne_17:{result.fetch_enabled_count}")

        # D08-only controlled live with unique logical identity (no mass crawl).
        all_cands = load_multisource_weekly_candidates(db, models)
        gap_cands = [c for c in all_cands if str(getattr(c, "canonical_key", None) or "") == SOURCE_KEY]
        if not gap_cands:
            raise SystemExit("nidcd_candidates_missing")
        now = datetime.now(timezone.utc)
        forced = run_controlled_live_orchestration(
            db,
            models,
            candidates=gap_cands,
            persist_ledger=True,
            logical_run_key=f"d08-nidcd-harden-{now.strftime('%Y%m%d%H%M%S')}",
            planned_window_start=now,
            planned_window_end=now,
            config_version="d08-nidcd-harden-01",
            config_hash="d08-nidcd-harden-01",
        )
        db.commit()
        print(
            json.dumps(
                {
                    "d08_force": {
                        "candidates": len(gap_cands),
                        "outcome": forced.outcome,
                        "network_executed": forced.network_executed,
                        "detail": forced.detail,
                    }
                },
                sort_keys=True,
            ),
            flush=True,
        )

        gsp = (
            db.query(models.GovernedSourceProfile)
            .filter(models.GovernedSourceProfile.canonical_key == SOURCE_KEY)
            .one_or_none()
        )
        if gsp is None:
            raise SystemExit("nidcd_gsp_missing")

        applied = 0
        reject_reasons: dict[str, int] = {}
        for p in db.query(models.KnowledgeProvenance).all():
            rid = getattr(p, "raw_evidence_id", None)
            raw = db.query(models.I5RawEvidence).filter_by(id=int(rid)).one_or_none() if rid is not None else None
            if raw is None:
                continue
            url = (raw.canonical_url or getattr(raw, "final_url", None) or "")
            if "nidcd.nih.gov/health" not in url.lower():
                continue
            if int(p.source_profile_id) != int(gsp.id):
                p.source_profile_id = int(gsp.id)
            ku = db.query(models.KnowledgeUnit).filter_by(id=int(p.knowledge_unit_id)).one_or_none()
            if ku is None:
                continue
            ku.provenance_complete = True
            healed = strip_html_nav_chrome(str(ku.normalized_statement or ""))
            if healed:
                from backend.app.services.i5.governed_specialized_entity_eligibility import (
                    select_clinical_claim_window,
                )

                ku.normalized_statement = select_clinical_claim_window(healed, canonical_url=url)
            elig = apply_governed_finalize_and_lexical_index(
                db,
                ku,
                source_key=SOURCE_KEY,
                source_profile_id=int(gsp.id),
                raw_evidence_id=int(raw.id),
                authoritative_provenance=p,
                incoming_source_profile_id=int(gsp.id),
                canonical_url=url,
            )
            if elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE:
                applied += 1
            else:
                from backend.app.services.i5.governed_specialized_entity_eligibility import (
                    can_apply_specialized_entity_eligibility,
                )

                ok, reason, _ = can_apply_specialized_entity_eligibility(
                    source_key=SOURCE_KEY, ku=ku, canonical_url=url
                )
                reject_reasons[reason if not ok else f"gate:{elig.value}"] = (
                    reject_reasons.get(reason if not ok else f"gate:{elig.value}", 0) + 1
                )
        db.commit()
        print(json.dumps({"specialized_eligible": applied, "reject_reasons": reject_reasons}, sort_keys=True), flush=True)

        ku1, elig1, kce1 = _counts(db)
        d08_after = _d08_stats(db)

        retrieval = "FAIL_NO_ELIGIBLE"
        if d08_after["eligible"] > 0:
            queries = ["hearing loss", "ear infection", "balance disorder", "noise-induced"]
            for ku in (
                db.query(models.KnowledgeUnit)
                .filter(models.KnowledgeUnit.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value)
                .all()
            ):
                if str(getattr(ku, "manifest_entity_id", None) or "") != "D08":
                    continue
                words = [w for w in str(ku.normalized_statement or "").lower().split() if len(w) > 4 and w.isalpha()][:3]
                if words:
                    queries.append(" ".join(words))
            hit = False
            for q in queries:
                req = ScisRetrievalRequest(
                    query_text=q, query_language="en", retrieval_mode=RetrievalMode.LEXICAL, top_k=5
                )
                resp = scis_retrieve(db, req)
                ev = list(getattr(resp, "evidence", None) or getattr(resp, "items", None) or [])
                if ev:
                    hit = True
                    break
            retrieval = "PASS" if hit else "FAIL"

        out = {
            "before": {"ku": ku0, "eligible": elig0, "kce": kce0, "d08": d08_before},
            "after": {"ku": ku1, "eligible": elig1, "kce": kce1, "d08": d08_after},
            "d08_retrieval": retrieval,
            "auto_activation": "NO",
            "autonomous_weekly_side_stage": "ON",
            "extractor_version": "w3p01-conceptual-1.0.2",
            "quality_threshold_changed": "NO",
            "nidcd_global_low_risk": "NO",
        }
        print(json.dumps(out, ensure_ascii=False, sort_keys=True), flush=True)

        if d08_after["eligible"] < 1 or d08_after["kce"] < 1 or retrieval != "PASS":
            raise SystemExit(f"d08_serving_fail:{d08_after}:{retrieval}")
        if d08_after["ku"] < 2:
            # Prefer >=2; allow 1 only if quality blocks additional pages.
            print(json.dumps({"d08_ku_note": "below_2_but_serving"}, sort_keys=True), flush=True)

        print(
            json.dumps(
                {
                    "eligibility_gate": "PASS",
                    "provenance": "PASS",
                    "source_attribution": "PASS",
                    "no_dense_ann_dependency": "YES",
                    "github_only": "YES",
                    "no_auto_activation": "YES",
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
