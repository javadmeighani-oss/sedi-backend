# backend.app.services.lifestyle.summary_service (Stage 17.1, 17.3, 17.5)
"""
Lifestyle summary generator. RAG-ready (local-only for v1).
Uses UserProfileKnowledge, UserMemoryFact, DailyMemorySummary.
Stage 17.3: Optional sources per section for explainability.
Stage 17.5: Optional Local RAG enrichment when RAG_LOCAL_ENABLED=true.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.memory import MemoryRepository

LIFESTYLE_AI_SUMMARY = os.environ.get("LIFESTYLE_AI_SUMMARY", "false").lower() in ("true", "1", "yes")
RAG_LOCAL_ENABLED = os.environ.get("RAG_LOCAL_ENABLED", "false").lower() in ("true", "1", "yes")

# Source anchor: type, id, label, ts? (Stage 17.3)
SourceAnchor = Dict[str, Any]


def generate_summary(db: Session, user_id: int, language: str = "en") -> Dict[str, Any]:
    """
    Generate lifestyle summary. Fast (<200ms typical).
    Returns: {generated_at, language, sections: [{title, body, items?, sources?}], sources_used: {facts_count, memory_days_covered}}
    sections[].sources is optional (Stage 17.3) for backward compatibility.
    """
    lang = language if language in ("en", "fa", "ar") else "en"
    now = datetime.utcnow()

    # 1) What I know (stable facts)
    facts_items, facts_count, facts_sources = _gather_stable_facts(db, user_id, lang)

    # 2) Recent patterns (last 7 days memory summaries)
    recent_items, memory_days, recent_sources = _gather_recent_patterns(db, user_id, lang)

    # 3) Next suggested check-in (safe question)
    check_in_body = _check_in_prompt(lang)
    check_in_sources = facts_sources[:2] if facts_sources else []

    # Stage 17.5/17.6: Optional Local RAG enrichment (gated; never breaks when disabled)
    rag_sources: List[SourceAnchor] = []
    if RAG_LOCAL_ENABLED:
        try:
            from backend.app.services.local_rag.provider_router import retrieve as rag_retrieve

            result = rag_retrieve(db, user_id, "lifestyle summary", lang)
            if result.combined_text and result.sources:
                rag_sources = result.sources
                if recent_items and len(result.combined_text) > 20:
                    recent_items = list(recent_items)
                    recent_items.insert(0, result.combined_text[:200].strip())
                elif not recent_items and len(result.combined_text) > 20:
                    recent_items = [result.combined_text[:200].strip()]
        except Exception:
            pass

    if rag_sources:
        seen = {(s.get("type"), s.get("id")) for s in recent_sources}
        merged = list(recent_sources)
        for s in rag_sources:
            k = (s.get("type"), s.get("id"))
            if k not in seen:
                merged.append(s)
                seen.add(k)
        recent_sources = merged[:15]  # contribute from facts

    sections = [
        {"title": _t("What I know", "آنچه می‌دانم", "ما أعرفه", lang), "body": "", "items": facts_items, "sources": facts_sources},
        {"title": _t("Recent patterns", "الگوهای اخیر", "الأنماط الأخيرة", lang), "body": "", "items": recent_items, "sources": recent_sources},
        {"title": _t("Next suggested check-in", "پیشنهاد بررسی بعدی", "التحقق المقترح التالي", lang), "body": check_in_body, "items": None, "sources": check_in_sources if check_in_sources else None},
    ]

    if LIFESTYLE_AI_SUMMARY and (facts_items or recent_items):
        sections = _ai_polish_sections(sections, lang)
        # Re-attach sources after polish (AI may have stripped them)
        sections[0]["sources"] = facts_sources
        sections[1]["sources"] = recent_sources
        sections[2]["sources"] = check_in_sources if check_in_sources else None

    return {
        "generated_at": now.isoformat(),
        "language": lang,
        "sections": sections,
        "sources_used": {
            "facts_count": facts_count,
            "memory_days_covered": memory_days,
        },
    }


def _t(en: str, fa: str, ar: str, lang: str) -> str:
    if lang == "fa":
        return fa
    if lang == "ar":
        return ar
    return en


def _gather_stable_facts(db: Session, user_id: int, lang: str) -> Tuple[List[str], int, List[SourceAnchor]]:
    """From UserProfileKnowledge + UserMemoryFact + UserFact. Returns (items, count, sources)."""
    items: List[str] = []
    sources: List[SourceAnchor] = []
    repo = MemoryRepository(db)

    # UserProfileKnowledge
    profile = db.query(models.UserProfileKnowledge).filter(
        models.UserProfileKnowledge.user_id == user_id
    ).first()
    if profile:
        if profile.baseline_summary and profile.baseline_summary.strip():
            items.append(_t("Baseline", "خط پایه", "الخط الأساسي", lang) + ": " + profile.baseline_summary.strip()[:200])
            sources.append({"type": "user_profile_knowledge", "id": str(profile.id), "label": "baseline", "ts": profile.updated_at.isoformat() if profile.updated_at else None})
        if profile.goals_json and profile.goals_json.strip():
            items.append(_t("Goals", "اهداف", "الأهداف", lang) + ": " + profile.goals_json.strip()[:150])
            sources.append({"type": "user_profile_knowledge", "id": str(profile.id), "label": "goals", "ts": profile.updated_at.isoformat() if profile.updated_at else None})
        if profile.preferences_json and profile.preferences_json.strip():
            items.append(_t("Preferences", "ترجیحات", "التفضيلات", lang) + ": " + profile.preferences_json.strip()[:150])
            sources.append({"type": "user_profile_knowledge", "id": str(profile.id), "label": "preferences", "ts": profile.updated_at.isoformat() if profile.updated_at else None})

    # UserMemoryFact lifestyle
    for domain in ("lifestyle", "routines", "goals"):
        facts = repo.get_facts_by_domain(user_id, domain)
        for f in facts:
            try:
                val = json.loads(f.value_json or "null")
                if val is not None:
                    items.append(f"{f.key}: {str(val)[:80]}")
                    sources.append({"type": "user_memory_fact", "id": str(f.id), "label": f"{domain}/{f.key}", "ts": (f.updated_at or f.created_at).isoformat() if (f.updated_at or f.created_at) else None})
            except json.JSONDecodeError:
                pass

    # UserFact (stable facts)
    uf_rows = db.query(models.UserFact).filter(models.UserFact.user_id == user_id).order_by(models.UserFact.updated_at.desc()).limit(10).all()
    for uf in uf_rows:
        if uf.value_json:
            try:
                val = json.loads(uf.value_json)
                items.append(f"{uf.key}: {str(val)[:80]}")
                sources.append({"type": "user_fact", "id": str(uf.id), "label": uf.key, "ts": uf.updated_at.isoformat() if uf.updated_at else None})
            except json.JSONDecodeError:
                pass

    facts_count = len(items)
    return items[:10], facts_count, sources[:15]


def _gather_recent_patterns(db: Session, user_id: int, lang: str) -> Tuple[List[str], int, List[SourceAnchor]]:
    """From DailyMemorySummary last 7 days. Returns (items, count, sources)."""
    cutoff = datetime.utcnow() - timedelta(days=7)
    rows = (
        db.query(models.DailyMemorySummary)
        .filter(
            models.DailyMemorySummary.user_id == user_id,
            models.DailyMemorySummary.created_at >= cutoff,
        )
        .order_by(models.DailyMemorySummary.created_at.desc())
        .limit(7)
        .all()
    )
    items: List[str] = []
    sources: List[SourceAnchor] = []
    for r in rows:
        if r.summary and r.summary.strip():
            items.append(r.summary.strip()[:120])
            sources.append({"type": "daily_summary", "id": str(r.id), "label": f"day_{r.created_at.strftime('%Y-%m-%d')}" if r.created_at else f"id_{r.id}", "ts": r.created_at.isoformat() if r.created_at else None})
    return items[:7], len(rows), sources[:10]


def _check_in_prompt(lang: str) -> str:
    if lang == "fa":
        return "چطور بوده روزت؟ چند ساعت خوابیدی؟"
    if lang == "ar":
        return "كيف كان يومك؟ كم ساعة نمت؟"
    return "How has your day been? How many hours did you sleep?"


def _ai_polish_sections(sections: List[Dict], lang: str) -> List[Dict]:
    """Optional AI wording polish; does not add new facts."""
    try:
        from openai import OpenAI
        client = OpenAI()
        text = json.dumps(sections, ensure_ascii=False)[:800]
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": f"Rewrite these section items in a friendly tone. Do NOT add new facts. Keep same structure. Language: {lang}. Output valid JSON array of sections with title, body, items."
            }, {"role": "user", "content": text}],
            max_tokens=400,
        )
        content = (r.choices[0].message.content or "").strip()
        parsed = json.loads(content)
        if isinstance(parsed, list) and len(parsed) >= 2:
            return parsed
    except Exception:
        pass
    return sections
