"""R-074 step 4b - READ-ONLY diagnostics: did the new elder-care / musculoskeletal pages reach the library and the chat?

Runs inside the backend container via stdin (rollback only, no writes, no model call, no user data). Output lines start with `DIAG|`.
For each reviewed page: raw-evidence rows, knowledge units, their eligibility/review/publication states. For elder-care questions:
which units and source pages the governed retrieval actually returns.
"""
from __future__ import annotations

import json

from sqlalchemy import text

MP = "https://medlineplus.gov/"
SLUGS = (
    "seniorshealth", "balanceproblems", "caregivers", "exerciseforseniors",  # new in step 4b
    "mobilityaids", "alzheimerscaregivers", "falls", "homecareservices", "nursinghomes", "pressuresores", "elderabuse",  # earlier
    "backinjuries", "fibromyalgia", "gout", "jointdisorders", "rheumatoidarthritis", "rotatorcuffinjuries", "sportsinjuries",
)
QUERIES = [
    ("en", "fall prevention for older people at home"),
    ("en", "how can I look after my elderly mother at home"),
    ("en", "balance problems in older adults"),
    ("en", "exercise for seniors"),
    ("fa", "پیشگیری از زمین‌خوردن سالمند در خانه"),
    ("fa", "مراقبت از مادر سالمندم در خانه"),
    ("fa", "ورزش مناسب برای سالمندان"),
    ("en", "gout diet and attacks"),
]


def main() -> None:
    from backend.app.database import get_db
    from backend.app.services.i5.runtime_knowledge_retrieval import retrieve_knowledge_context

    db = next(get_db())
    try:
        for slug in SLUGS:
            url = f"{MP}{slug}.html"
            row = {"slug": slug}
            try:
                row["raw_evidence"] = db.execute(
                    text("SELECT COUNT(*) FROM i5_raw_evidence WHERE canonical_url = :u"), {"u": url}
                ).scalar()
                states = db.execute(
                    text(
                        "SELECT ku.runtime_eligibility, ku.review_state, ku.publication_state, ku.domain, COUNT(*) "
                        "FROM knowledge_units ku JOIN knowledge_provenance kp ON kp.knowledge_unit_id = ku.id "
                        "JOIN i5_raw_evidence re ON re.id = kp.raw_evidence_id WHERE re.canonical_url = :u "
                        "GROUP BY 1,2,3,4"
                    ),
                    {"u": url},
                ).fetchall()
                row["units"] = [list(map(str, s)) for s in states]
            except Exception as e:  # noqa: BLE001
                db.rollback()
                row["error"] = type(e).__name__
            print("DIAG|page|" + json.dumps(row, ensure_ascii=False)[:900])
        for lang, q in QUERIES:
            row = {"lang": lang, "q": q}
            try:
                res = retrieve_knowledge_context(db, q, language=lang, limit=10, enqueue_gap_on_empty=False)
                items = []
                for it in res.items:
                    urls = db.execute(
                        text(
                            "SELECT re.canonical_url FROM knowledge_provenance kp JOIN i5_raw_evidence re ON re.id = kp.raw_evidence_id "
                            "WHERE kp.knowledge_unit_id = :k LIMIT 1"
                        ),
                        {"k": it.knowledge_unit_id},
                    ).scalar()
                    items.append({"ku": it.knowledge_unit_id, "domain": it.domain, "topic": it.topic_taxonomy, "url": (urls or "")[-48:]})
                row["status"] = res.status
                row["n"] = len(items)
                row["items"] = items
                row["exclusions"] = res.exclusion_counts
            except Exception as e:  # noqa: BLE001
                db.rollback()
                row["error"] = type(e).__name__
            db.rollback()
            print("DIAG|query|" + json.dumps(row, ensure_ascii=False, default=str)[:2400])
        print("DIAG|done|PASS")
    finally:
        db.rollback()
        db.close()


main()
