"""R-074 step 6b: link ELIGIBLE knowledge units to their catalog concept by URL (idempotent, additive).

`link_knowledge_unit_semantics` links a unit only while the governed crawl visits it. Units crawled before their concept had a
catalog needle (step 5 pages) stay unlinked until the next weekly run; concept-restricted retrieval then serves only the few
linked units. This runs the SAME deterministic rule (catalog URL needle -> concept) over the units already in the library.
No classifier, no model call, no new concept: a link row is written only when a governed needle matches the unit's own
canonical URL. Dry run by default; `--apply` commits. Output lines start with `RELINK|`.
"""
from __future__ import annotations

import sys
from typing import Any

from backend.app import models
from backend.app.services.i5.know02.concept_catalog import concept_key_for_url
from backend.app.services.i5.know02.taxonomy import link_ku_concept


def relink_catalog_concepts(db: Any, *, apply: bool = False) -> dict[str, Any]:
    rows = (
        db.query(models.KnowledgeUnit.id, models.I5RawEvidence.canonical_url)
        .join(models.KnowledgeProvenance, models.KnowledgeProvenance.knowledge_unit_id == models.KnowledgeUnit.id)
        .join(models.I5RawEvidence, models.I5RawEvidence.id == models.KnowledgeProvenance.raw_evidence_id)
        .filter(models.KnowledgeUnit.runtime_eligibility == "ELIGIBLE")
        .all()
    )
    concepts = {c.concept_key: int(c.id) for c in db.query(models.I5ClinicalConcept).all()}
    existing = {
        (int(k), int(c)) for k, c in db.query(models.I5KnowledgeUnitConcept.knowledge_unit_id, models.I5KnowledgeUnitConcept.concept_id).all()
    }
    seen = would = 0
    per_concept: dict[str, int] = {}
    for ku_id, url in rows:
        seen += 1
        key = concept_key_for_url(url)
        cid = concepts.get(key) if key else None
        if cid is None or (int(ku_id), cid) in existing:
            continue
        would += 1
        per_concept[key] = per_concept.get(key, 0) + 1
        if apply:
            link_ku_concept(db, knowledge_unit_id=int(ku_id), concept_id=cid)
    if apply:
        db.commit()
    else:
        db.rollback()
    return {"eligible_units_seen": seen, "new_links": would, "per_concept": per_concept, "applied": bool(apply)}


def main(argv: list[str]) -> int:
    from backend.app.database import get_db

    apply = "--apply" in argv
    db = next(get_db())
    try:
        out = relink_catalog_concepts(db, apply=apply)
        print("RELINK|result|" + str(out))
        print("RELINK|done|PASS")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print("RELINK|error|" + type(exc).__name__)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
