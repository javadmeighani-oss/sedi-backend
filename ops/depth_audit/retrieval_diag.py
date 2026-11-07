"""R-074 step 6 - READ-ONLY retrieval diagnostics (runs inside the backend container via stdin; rollback only, no writes).

For a few knowledge-type questions it prints WHERE the evidence is lost: how many chunks the text index holds for the key word,
what the lexical branch returns for the planned query, what the full governed retrieval returns, and its exclusion counts.
Output lines start with `DIAG|`. No user data, no model call.
"""
from __future__ import annotations

import json

from sqlalchemy import text

QUERIES = [
    ("en", "caring for a family member with dementia", "dementia"),
    ("fa", "مراقبت از بیمار مبتلا به زوال عقل در خانه", "dementia"),
    ("en", "meal plan for type 2 diabetes", "diabetes"),
    ("en", "how to understand blood test results cholesterol hemoglobin", "cholesterol"),
    ("en", "low back pain causes self care and exercises", "pain"),
    ("en", "how to treat insomnia and improve sleep", "insomnia"),
]


def main() -> None:
    from backend.app.database import get_db
    from backend.app.services.i5.runtime_knowledge_retrieval import retrieve_knowledge_context
    from backend.app.services.scis.lexical import lexical_search

    db = next(get_db())
    try:
        for lang, q, key in QUERIES:
            row = {"lang": lang, "q": q[:60]}
            try:
                row["chunks_with_keyword"] = db.execute(
                    text("SELECT COUNT(*) FROM knowledge_chunk_embeddings WHERE search_tsv @@ plainto_tsquery('simple', :k)"),
                    {"k": key},
                ).scalar()
                row["chunks_total"] = db.execute(text("SELECT COUNT(*) FROM knowledge_chunk_embeddings")).scalar()
            except Exception as e:  # noqa: BLE001
                db.rollback()
                row["sql_error"] = type(e).__name__
            try:
                cands, meta = lexical_search(db, q, language=lang, top_k=10)
                qp = meta.get("query_plan", {})
                row["lexical"] = {
                    "raw_count": meta.get("raw_count"),
                    "primary": qp.get("primary_query"),
                    "fallback": qp.get("fallback_query"),
                    "used": qp.get("used"),
                    "error": meta.get("error"),
                }
            except Exception as e:  # noqa: BLE001
                db.rollback()
                row["lexical_error"] = type(e).__name__
            try:
                res = retrieve_knowledge_context(db, q, language=lang, limit=10, enqueue_gap_on_empty=False)
                row["retrieval"] = {
                    "status": res.status,
                    "items": len(res.items),
                    "domains": sorted({i.domain for i in res.items}),
                    "exclusions": res.exclusion_counts,
                    "sufficiency": {k: res.sufficiency_audit.get(k) for k in list(res.sufficiency_audit)[:8]},
                    "obs": {k: res.observability.get(k) for k in list(res.observability)[:14]},
                }
            except Exception as e:  # noqa: BLE001
                db.rollback()
                row["retrieval_error"] = type(e).__name__
            db.rollback()
            print("DIAG|" + json.dumps(row, ensure_ascii=False, default=str)[:3800])
        print("DIAG|done|PASS")
    finally:
        db.rollback()
        db.close()


main()
