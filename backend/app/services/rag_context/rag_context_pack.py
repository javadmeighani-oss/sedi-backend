# backend.app.services.rag_context.rag_context_pack
"""
Stage 23 Step 5: Facts-anchored RAG context pack.
Stable facts, lifestyle/daily summary, goals, medical conditions (when safe).
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RagContextPack(BaseModel):
    """Facts-anchored context for RAG: verified/structured sources only."""

    user_id: int
    language: str = "en"
    preferred_name: Optional[str] = None
    stable_facts: Dict[str, Any] = Field(default_factory=dict)
    lifestyle_summary: Optional[str] = None
    daily_summary: Optional[str] = None
    medical_conditions: List[str] = Field(default_factory=list)
    goals: List[str] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
