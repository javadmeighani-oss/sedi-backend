"""Gate 3 knowledge retrieval with trust/freshness/citation rules."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.gate3.constants import MIN_TRUST_BY_RISK, PROVIDER_CATEGORIES, RANKING_STRIP_PHRASES, TRUST_ORDER


def _reframe_provider_query(query: str) -> Tuple[str, bool]:
    """Strip unsupported ranking language; search continues with reframed terms."""
    q = (query or "").strip().lower()
    reframed = False
    for phrase in RANKING_STRIP_PHRASES:
        if phrase in q:
            reframed = True
            q = q.replace(phrase, " ")
    q = re.sub(r"\s+", " ", q).strip()
    return q, reframed


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_fresh(source: models.KnowledgeSource) -> bool:
    if source.ingestion_status == "deprecated":
        return False
    if not source.last_checked_at:
        return False
    days = source.freshness_policy_days or 180
    checked = _as_utc(source.last_checked_at)
    return (_utc_now() - checked) <= timedelta(days=days)


def _trust_ok(source: models.KnowledgeSource, risk_level: str) -> bool:
    min_trust = MIN_TRUST_BY_RISK.get(risk_level or "low")
    if min_trust is None:
        return False
    return TRUST_ORDER.get(source.trust_level, 0) >= TRUST_ORDER.get(min_trust, 0)


def search_knowledge(
    db: Session,
    query: str,
    *,
    category: Optional[str] = None,
    locale: Optional[str] = None,
    limit: int = 5,
    risk_level: str = "low",
) -> Dict[str, Any]:
    if risk_level == "emergency":
        return {"chunks": [], "stale_excluded": 0, "message": "kb_blocked_emergency"}

    q, ranking_reframed = _reframe_provider_query(query or "")
    if not q:
        return {"chunks": [], "stale_excluded": 0}

    rows = (
        db.query(models.KnowledgeChunk, models.KnowledgeDocument, models.KnowledgeSource)
        .join(models.KnowledgeDocument, models.KnowledgeDocument.id == models.KnowledgeChunk.document_id)
        .join(models.KnowledgeSource, models.KnowledgeSource.id == models.KnowledgeDocument.source_id)
        .filter(models.KnowledgeDocument.status == "active")
        .filter(models.KnowledgeSource.ingestion_status == "active")
        .all()
    )

    scored: List[tuple] = []
    stale_excluded = 0
    for chunk, doc, src in rows:
        if category and doc.category != category:
            continue
        if locale and doc.locale != locale:
            continue
        if not _trust_ok(src, risk_level):
            continue
        fresh = _is_fresh(src)
        if not fresh:
            stale_excluded += 1
            continue
        hay = f"{doc.title} {doc.summary or ''} {chunk.content}".lower()
        if q not in hay and not any(tok in hay for tok in q.split() if len(tok) > 2):
            continue
        score = sum(1 for tok in q.split() if tok in hay)
        if doc.category in PROVIDER_CATEGORIES:
            score += 0.5
        scored.append((score, chunk, doc, src))

    scored.sort(key=lambda x: x[0], reverse=True)
    # Prefer multiple provider options
    if category in PROVIDER_CATEGORIES or any(
        s[2].category in PROVIDER_CATEGORIES for s in scored[: limit * 2]
    ):
        limit = max(limit, 2)

    out = []
    seen_docs = set()
    for _, chunk, doc, src in scored:
        if doc.id in seen_docs and doc.category in PROVIDER_CATEGORIES:
            continue
        seen_docs.add(doc.id)
        out.append({
            "chunk_id": chunk.id,
            "content": chunk.content[:600],
            "citation": {
                "label": chunk.citation_label,
                "source_id": src.id,
                "source_name": src.name,
                "document_id": doc.id,
                "document_title": doc.title,
                "category": doc.category,
                "trust_level": src.trust_level,
                "last_checked_at": src.last_checked_at.isoformat() + "Z" if src.last_checked_at else None,
                "region": doc.region,
                "city": doc.city,
                "specialty": doc.specialty,
            },
            "stale": False,
        })
        if len(out) >= limit:
            break

    result: Dict[str, Any] = {
        "chunks": out,
        "stale_excluded": stale_excluded,
        "disclaimer": "based on registered curated sources" if out else None,
    }
    if ranking_reframed:
        result["ranking_language_reframed"] = True
        result["ranking_notice"] = (
            "Unsupported 'best' ranking was removed. Options are from registered curated sources only."
        )
    return result
