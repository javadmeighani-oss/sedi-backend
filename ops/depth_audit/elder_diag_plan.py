"""R-074 step 4c - READ-ONLY: WHERE is an elder-care question lost (query plan, lexical hits, governed retrieval)?

Runs inside the backend container via stdin (rollback only, no writes, no model call, no user data). Lines start with `DIAG|`.
"""
from __future__ import annotations

import json

QUERIES = [
    ("en", "how can I look after my elderly mother at home"),
    ("en", "caring for an elderly parent at home"),
    ("en", "caring for older adults at home"),
    ("en", "looking after my elderly father"),
    ("en", "my grandmother is old and falls a lot"),
    ("en", "fall prevention for older people at home"),
    ("en", "senior care tips"),
    ("en", "older adults falls"),
    ("fa", "مراقبت از مادر سالمندم در خانه"),
    ("fa", "پدرم سالمند است و زیاد زمین می‌خورد"),
    ("ar", "كيف أعتني بأمي المسنة في المنزل"),
]


def main() -> None:
    from backend.app.database import get_db
    from backend.app.services.i5.runtime_knowledge_retrieval import retrieve_knowledge_context
    from backend.app.services.scis.lexical import lexical_search

    db = next(get_db())
    try:
        for lang, q in QUERIES:
            row = {"lang": lang, "q": q}
            try:
                _c, meta = lexical_search(db, q, language=lang, top_k=10)
                qp = meta.get("query_plan", {})
                row["lex"] = {
                    "raw": meta.get("raw_count"),
                    "primary": qp.get("primary_query"),
                    "fallback": qp.get("fallback_query"),
                    "used": qp.get("used"),
                }
            except Exception as e:  # noqa: BLE001
                db.rollback()
                row["lex_error"] = type(e).__name__
            try:
                res = retrieve_knowledge_context(db, q, language=lang, limit=10, enqueue_gap_on_empty=False)
                row["status"] = res.status
                row["n"] = len(res.items)
                row["topics"] = sorted({str(i.topic_taxonomy) for i in res.items})[:6]
                row["excl"] = res.exclusion_counts
                row["suff"] = {k: res.sufficiency_audit.get(k) for k in list(res.sufficiency_audit)[:6]}
                row["obs"] = {k: res.observability.get(k) for k in list(res.observability)[:10]}
            except Exception as e:  # noqa: BLE001
                db.rollback()
                row["retr_error"] = type(e).__name__
            db.rollback()
            print("DIAG|q|" + json.dumps(row, ensure_ascii=False, default=str)[:1700])
        print("DIAG|done|PASS")
    finally:
        db.rollback()
        db.close()


main()
