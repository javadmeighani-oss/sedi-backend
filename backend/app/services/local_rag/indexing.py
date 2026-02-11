# backend.app.services.local_rag.indexing (Stage 17.6, 17.8)
"""
Background indexing for RAG embeddings.
Stage 17.8: Daily summaries only. Manual/admin-triggered.
"""

import hashlib
import os
from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app import models

RAG_VECTOR_REBUILD = os.environ.get("RAG_VECTOR_REBUILD", "false").lower() in ("true", "1", "yes")
RAG_VECTOR_BATCH_SIZE = int(os.environ.get("RAG_VECTOR_BATCH_SIZE", "200") or "200")
RAG_VECTOR_DIM = int(os.environ.get("RAG_VECTOR_DIM", "1536") or "1536")


def _content_hash(text_val: str) -> str:
    return hashlib.sha256((text_val or "").encode("utf-8")).hexdigest()


def index_daily_summaries_for_user(
    db: Session,
    user_id: int,
    days: int = 30,
) -> Dict[str, Any]:
    """
    Index DailyMemorySummary rows for last N days into rag_embeddings.
    Skips unchanged when RAG_VECTOR_REBUILD=false.
    Returns {indexed, skipped, failed}.
    """
    result = {"indexed": 0, "skipped": 0, "failed": 0}
    cutoff = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(models.DailyMemorySummary)
        .filter(
            models.DailyMemorySummary.user_id == user_id,
            models.DailyMemorySummary.created_at >= cutoff,
        )
        .order_by(models.DailyMemorySummary.created_at.desc())
        .limit(100)
        .all()
    )

    to_embed: list = []
    for r in rows:
        if not r.summary or not r.summary.strip():
            continue
        text_val = r.summary.strip()[:500]
        h = _content_hash(text_val)
        if not RAG_VECTOR_REBUILD:
            existing = db.execute(
                text(
                    "SELECT 1 FROM rag_embeddings WHERE user_id=:uid AND source_type='daily_summary' AND source_id=:sid AND content_hash=:h"
                ),
                {"uid": user_id, "sid": str(r.id), "h": h},
            ).fetchone()
            if existing:
                result["skipped"] += 1
                continue
        label = f"day_{r.created_at.strftime('%Y-%m-%d')}" if r.created_at else f"id_{r.id}"
        to_embed.append({
            "source_id": str(r.id),
            "label": label,
            "text": text_val,
            "content_hash": h,
            "created_at": r.created_at,
        })

    if not to_embed:
        return result

    try:
        from backend.app.services.local_rag.embedding_client import embed_texts, _vector_to_pg_str
    except Exception as e:
        result["failed"] = len(to_embed)
        raise RuntimeError(f"Embedding client unavailable: {e}") from e

    texts = [x["text"] for x in to_embed]
    try:
        embeddings = embed_texts(texts)
    except Exception:
        result["failed"] = len(to_embed)
        raise

    if len(embeddings) != len(to_embed):
        result["failed"] = len(to_embed)
        return result

    for item, emb in zip(to_embed, embeddings):
        try:
            vec_str = _vector_to_pg_str(emb)
            db.execute(
                text("""
                    INSERT INTO rag_embeddings (user_id, source_type, source_id, content_hash, embedding)
                    VALUES (:uid, 'daily_summary', :sid, :h, :vec::vector)
                    ON CONFLICT (user_id, source_type, source_id)
                    DO UPDATE SET content_hash = EXCLUDED.content_hash, embedding = EXCLUDED.embedding
                """),
                {"uid": user_id, "sid": item["source_id"], "h": item["content_hash"], "vec": vec_str},
            )
            db.commit()
            result["indexed"] += 1
        except Exception:
            db.rollback()
            result["failed"] += 1
    return result


def index_embeddings_for_user(db: Session, user_id: int) -> Dict[str, Any]:
    """
    Legacy wrapper; delegates to index_daily_summaries_for_user.
    Only runs if RAG_VECTOR_REBUILD=true.
    """
    result = {"indexed": 0, "skipped": 0, "errors": 0}
    if not RAG_VECTOR_REBUILD:
        return result
    try:
        r = index_daily_summaries_for_user(db, user_id, days=30)
        result["indexed"] = r["indexed"]
        result["skipped"] = r["skipped"]
        result["errors"] = r["failed"]
    except Exception:
        result["errors"] += 1
        raise
    return result


def index_daily_summaries_all(
    db: Session,
    days: int = 30,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Index daily summaries for a batch of users (for controlled rollout).
    Returns {indexed, skipped, failed, users_processed, next_offset}.
    """
    user_ids = [
        row[0]
        for row in db.execute(
            text("SELECT DISTINCT user_id FROM daily_memory_summaries ORDER BY user_id LIMIT :lim OFFSET :off"),
            {"lim": limit, "off": offset},
        ).fetchall()
    ]
    total_indexed = 0
    total_skipped = 0
    total_failed = 0
    for uid in user_ids:
        r = index_daily_summaries_for_user(db, uid, days=days)
        total_indexed += r["indexed"]
        total_skipped += r["skipped"]
        total_failed += r["failed"]
    next_offset = offset + len(user_ids) if user_ids else offset
    return {
        "indexed": total_indexed,
        "skipped": total_skipped,
        "failed": total_failed,
        "users_processed": len(user_ids),
        "next_offset": next_offset,
    }
