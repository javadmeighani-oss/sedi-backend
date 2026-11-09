"""R-083 / Javad 2026-11-09 - READ-ONLY probe: does the knowledge REACH the chat for a back-pain conversation?

Runs inside the backend container via stdin. For a fixed list of generic utterances (no user data) it asks the SAME
retrieval + renderer the chat uses and prints what the model would receive: status, number of units, domains, and the first
words of each distinct unit, plus whether a domain answer-guide is attached. Never writes (rollback only). Lines: `CHAT|`.
"""
from __future__ import annotations

import json

QUERIES = [
    ("fa", "کمرم کمی درد میکنه"),
    ("fa", "نه روی مهره های پایین کمرم است بیشتر شاید بخاطر رانندگی طولانی باشد"),
    ("fa", "درد کمر بعد از رانندگی طولانی چه تمرین‌هایی کمک می‌کند"),
    ("en", "my lower back hurts a little"),
    ("en", "lower back pain after long driving what exercises help"),
]


def main() -> None:
    from backend.app.core.conversation.domain_guides import answer_guide_block
    from backend.app.database import get_db
    from backend.app.services.i5.reference_renderer import format_care_context_block, render_grounded_answer
    from backend.app.services.i5.runtime_knowledge_retrieval import retrieve_knowledge_context

    db = next(get_db())
    try:
        for lang, q in QUERIES:
            row = {"lang": lang, "q": q}
            try:
                res = retrieve_knowledge_context(db, q, language=lang, limit=10, enqueue_gap_on_empty=False)
                d = res.to_dict() if hasattr(res, "to_dict") else {}
                grounded = render_grounded_answer(d, language=lang, user_requested_sources=True)
                block = str(format_care_context_block(grounded, max_chars=8200) or "")
                items = list(getattr(res, "items", []) or [])
                row.update(
                    status=getattr(res, "status", None),
                    items=len(items),
                    distinct_canon=len({str(getattr(i, "canonical_unit_id", ""))[:40] for i in items}),
                    domains=sorted({str(getattr(i, "domain", "")) for i in items}),
                    block_chars=len(block),
                    guide=bool(answer_guide_block(q)) if grounded is not None else False,
                    heads=[str(getattr(i, "statement", getattr(i, "normalized_statement", "")))[:90].replace("\n", " ") for i in items[:6]],
                    sufficiency=(getattr(res, "sufficiency_audit", {}) or {}).get("reason"),
                )
            except Exception as exc:  # noqa: BLE001
                row["error"] = type(exc).__name__
                try:
                    db.rollback()
                except Exception:  # noqa: BLE001
                    pass
            print("CHAT|" + json.dumps(row, ensure_ascii=False, sort_keys=True))
            db.rollback()
    finally:
        db.rollback()
        db.close()


main()
