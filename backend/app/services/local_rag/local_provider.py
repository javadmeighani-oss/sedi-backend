# backend.app.services.local_rag.local_provider (Stage 17.5)
"""
Local RAG provider. Retrieves only from Sedi internal stores.
Gated by RAG_LOCAL_ENABLED. No external retrieval.
"""

import os
import re
import json
from datetime import datetime, timedelta
from typing import List, Tuple

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.memory import MemoryRepository
from backend.app.services.local_rag.contracts import (
    RetrievedChunk,
    RetrievalResult,
    SourceAnchor,
)

RAG_LOCAL_ENABLED = os.environ.get("RAG_LOCAL_ENABLED", "false").lower() in ("true", "1", "yes")
RAG_LOCAL_TOP_K = int(os.environ.get("RAG_LOCAL_TOP_K", "6") or "6")
RAG_LOCAL_MAX_CHARS = int(os.environ.get("RAG_LOCAL_MAX_CHARS", "1200") or "1200")
RAG_CHUNK_MAX_CHARS = 250


def _normalize_tokens(text: str) -> List[str]:
    """Basic tokenization: split on non-alphanumeric, lowercase."""
    if not text or not isinstance(text, str):
        return []
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return [t for t in cleaned.split() if len(t) >= 2]


def _score_chunk(chunk_text: str, query_tokens: List[str]) -> int:
    """Score by number of query tokens appearing in chunk (simple overlap)."""
    if not query_tokens:
        return 1
    chunk_tokens = set(_normalize_tokens(chunk_text))
    return sum(1 for t in query_tokens if t in chunk_tokens)


def _make_source(t: str, row_id: int, label: str, ts=None) -> SourceAnchor:
    return {
        "type": t,
        "id": str(row_id),
        "label": label,
        "ts": ts.isoformat() if hasattr(ts, "isoformat") and ts else (str(ts) if ts else None),
    }


class LocalRAGProvider:
    """
    Local RAG provider. Retrieves from internal DB only.
    No embeddings; simple keyword overlap scoring.
    """

    def __init__(self, db: Session):
        self.db = db

    def retrieve(
        self,
        user_id: int,
        query_text: str,
        language: str = "en",
    ) -> RetrievalResult:
        """
        Retrieve relevant chunks from internal stores.
        Returns RetrievalResult with combined_text and sources.
        """
        chunks: List[Tuple[str, SourceAnchor]] = []
        query_tokens = _normalize_tokens(query_text or "lifestyle summary")

        # 1) UserFact
        for uf in (
            self.db.query(models.UserFact)
            .filter(models.UserFact.user_id == user_id)
            .order_by(models.UserFact.updated_at.desc())
            .limit(15)
            .all()
        ):
            if not uf.value_json:
                continue
            try:
                val = json.loads(uf.value_json)
                text = f"{uf.key}: {str(val)[:120]}"
            except json.JSONDecodeError:
                text = f"{uf.key}: (value)"
            src = _make_source("user_fact", uf.id, uf.key or "fact", uf.updated_at)
            chunks.append((text, src))
        # 2) UserMemoryFact (lifestyle, preferences)
        repo = MemoryRepository(self.db)
        from backend.app.services.memory.memory_contract import MemoryContract

        for domain in ("lifestyle", "routines", "preferences"):
            facts = repo.get_facts_by_domain(user_id, domain)
            for f in facts[:10]:
                if not MemoryContract.is_i6_context_projectable(f.domain, f.key):
                    continue
                try:
                    val = json.loads(f.value_json or "null")
                    text = f"{f.key}: {str(val)[:120]}"
                except json.JSONDecodeError:
                    text = f"{f.key}: (value)"
                ts = f.updated_at or f.created_at
                src = _make_source("user_memory_fact", f.id, f"{domain}/{f.key}", ts)
                chunks.append((text, src))
        # 3) DailyMemorySummary (last 7 days)
        cutoff = datetime.utcnow() - timedelta(days=7)
        for r in (
            self.db.query(models.DailyMemorySummary)
            .filter(
                models.DailyMemorySummary.user_id == user_id,
                models.DailyMemorySummary.created_at >= cutoff,
            )
            .order_by(models.DailyMemorySummary.created_at.desc())
            .limit(7)
            .all()
        ):
            if r.summary and r.summary.strip():
                text = r.summary.strip()[:200]
                label = f"day_{r.created_at.strftime('%Y-%m-%d')}" if r.created_at else f"id_{r.id}"
                src = _make_source("daily_summary", r.id, label, r.created_at)
                chunks.append((text, src))
        # 4) Memory turns (last 10, user messages only)
        for m in (
            self.db.query(models.Memory)
            .filter(models.Memory.user_id == user_id)
            .order_by(models.Memory.created_at.desc())
            .limit(10)
            .all()
        ):
            if m.user_message and m.user_message.strip():
                text = m.user_message.strip()[:180]
                src = _make_source("memory_turn", m.id, "turn", m.created_at)
                chunks.append((text, src))
        # 5) UserProfileKnowledge
        profile = (
            self.db.query(models.UserProfileKnowledge)
            .filter(models.UserProfileKnowledge.user_id == user_id)
            .first()
        )
        if profile:
            for field, label in [
                ("baseline_summary", "baseline"),
                ("goals_json", "goals"),
                ("preferences_json", "preferences"),
            ]:
                val = getattr(profile, field, None)
                if val and str(val).strip():
                    s = str(val).strip()[:180]
                    src = _make_source("user_profile_knowledge", profile.id, label, profile.updated_at)
                    chunks.append((s, src))
        # 6) Accepted candidates (optional)
        for c in (
            self.db.query(models.UserFactCandidate)
            .filter(
                models.UserFactCandidate.user_id == user_id,
                models.UserFactCandidate.status == "accepted",
            )
            .order_by(models.UserFactCandidate.created_at.desc())
            .limit(5)
            .all()
        ):
            if c.value_json:
                try:
                    val = json.loads(c.value_json)
                    text = f"{c.domain}/{c.key}: {str(val)[:120]}"
                except json.JSONDecodeError:
                    text = f"{c.domain}/{c.key}: (value)"
                src = _make_source("candidate_fact", c.id, f"{c.domain}/{c.key}", c.created_at)
                chunks.append((text, src))

        # Score and rank
        scored = [
            (_score_chunk(text, query_tokens), text, src)
            for text, src in chunks
        ]
        scored.sort(key=lambda x: (-x[0], x[1][:50]))
        top = scored[: RAG_LOCAL_TOP_K]

        # Truncate each chunk and build result
        result_chunks: List[RetrievedChunk] = []
        combined_parts: List[str] = []
        seen_sources: List[SourceAnchor] = []
        budget = RAG_LOCAL_MAX_CHARS
        for _score, text, src in top:
            snippet = text[:RAG_CHUNK_MAX_CHARS] if len(text) > RAG_CHUNK_MAX_CHARS else text
            if not snippet.strip():
                continue
            result_chunks.append(RetrievedChunk(snippet, src))
            if budget > 0:
                part = snippet[:budget]
                combined_parts.append(part)
                budget -= len(part) + 2
            if src not in seen_sources:
                seen_sources.append(src)

        combined_text = "\n\n".join(combined_parts)[:RAG_LOCAL_MAX_CHARS].strip()
        return RetrievalResult(
            chunks=result_chunks,
            combined_text=combined_text,
            sources=seen_sources,
        )
