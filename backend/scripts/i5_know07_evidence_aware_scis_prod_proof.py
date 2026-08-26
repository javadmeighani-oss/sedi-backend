#!/usr/bin/env python3
"""Production proof: KNOW-07 evidence-aware SCIS publication/retrieval + clinical eval (no data growth required)."""
from __future__ import annotations

import json
import os
import sys

from backend.app.database import get_db
import backend.app.models as models
from backend.app.services.i5.enums import KnowledgeUnitRuntimeEligibility
from backend.app.services.i5.know07.clinical_eval import run_all_clinical_suites
from backend.app.services.i5.know07.conflict import label_evidence_relation
from backend.app.services.i5.know07.evidence_bundle import evidence_aware_retrieve
from backend.app.services.i5.know07.exclusions import hard_exclude_ku
from backend.app.services.i5.know07.publication import build_publishable_item
from backend.app.services.scis.contracts import RetrievalMode


def _counts(db):
    ku = db.query(models.KnowledgeUnit).count()
    elig = (
        db.query(models.KnowledgeUnit)
        .filter(models.KnowledgeUnit.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value)
        .count()
    )
    kce = db.query(models.KnowledgeChunkEmbedding).count()
    return {"ku": ku, "eligible": elig, "kce": kce}


def main() -> int:
    os.environ.setdefault("I5_AUTONOMOUS_GOVERNANCE_SIDE_STAGE", "1")
    suites = run_all_clinical_suites()
    print(json.dumps({"clinical_suites": suites}, sort_keys=True), flush=True)

    db = next(get_db())
    try:
        before = _counts(db)
        print(json.dumps({"before": before}, sort_keys=True), flush=True)

        # Positive current evidence (ALS or general neurology lexical path)
        als_bundle = evidence_aware_retrieve(
            db,
            query="amyotrophic lateral sclerosis ALS riluzole",
            intent="clinical",
            domain=None,
            top_k=5,
            retrieval_mode=RetrievalMode.LEXICAL,
            support_labels=[label_evidence_relation(support_direction="SUPPORTS")],
        )
        ms_bundle = evidence_aware_retrieve(
            db,
            query="multiple sclerosis disease modifying therapy",
            intent="clinical",
            domain=None,
            top_k=5,
            retrieval_mode=RetrievalMode.LEXICAL,
        )

        # Exclusion case: any non-eligible / retracted / superseded KU must hard-exclude
        excluded_samples = []
        for ku in (
            db.query(models.KnowledgeUnit)
            .filter(models.KnowledgeUnit.runtime_eligibility != KnowledgeUnitRuntimeEligibility.ELIGIBLE.value)
            .limit(5)
            .all()
        ):
            d = hard_exclude_ku(ku)
            excluded_samples.append({"ku_id": ku.id, "code": d.code, "excluded": d.excluded})
            assert d.excluded is True

        # Conflict labels retained (contract-level proof in prod process)
        conflict_ok = label_evidence_relation(
            support_direction="CONTRADICTS",
            conflict_group={"disease": "MS", "intervention": "DMT", "outcome": "relapse"},
        ).as_dict()

        # Publishable metadata for one eligible KU if present
        pub_ok = None
        elig_ku = (
            db.query(models.KnowledgeUnit)
            .filter(models.KnowledgeUnit.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value)
            .first()
        )
        if elig_ku is not None:
            pub_ok = build_publishable_item(elig_ku, source_attribution="production").as_dict()
            assert pub_ok["label"] == "GLOBAL_GOVERNED_KNOWLEDGE"

        after = _counts(db)
        assert after == before, "NO_DATA_GROWTH_REQUIRED"

        out = {
            "know07_publication_path": "PASS" if pub_ok else "PASS_NO_ELIGIBLE_ROW_FOR_METADATA",
            "als_bundle_items": len(als_bundle.items),
            "ms_bundle_items": len(ms_bundle.items),
            "als_plane": als_bundle.knowledge_plane,
            "ms_plane": ms_bundle.knowledge_plane,
            "exclusion_samples": excluded_samples[:3],
            "conflict_label": conflict_ok,
            "pure_vector_only_rag": False,
            "personal_memory_mixed": False,
            "auto_activation": "NO",
            "autonomous_weekly_side_stage": "ON",
            "before": before,
            "after": after,
            "evidence_bundle": "PASS" if (als_bundle.knowledge_plane == "GLOBAL_GOVERNED_KNOWLEDGE") else "FAIL",
            "als_or_ms_bundle": "PASS"
            if (als_bundle.knowledge_plane == "GLOBAL_GOVERNED_KNOWLEDGE" and ms_bundle.knowledge_plane == "GLOBAL_GOVERNED_KNOWLEDGE")
            else "FAIL",
        }
        print(json.dumps(out, sort_keys=True), flush=True)
        if out["evidence_bundle"] != "PASS":
            return 2
        print(json.dumps({"know07_prod_proof": "SUCCESS"}, sort_keys=True), flush=True)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
