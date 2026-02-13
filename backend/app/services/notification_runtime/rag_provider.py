# backend.app.services.notification_runtime.rag_provider
"""
RAG Provider (Stage 16.6, Stage 23 Step 5)

Clean interface for RAG integration. V1: facts-anchored RagContextPack summary
for companion_* templates only; fail-open. No RAG for health_alert or high-risk.
"""

from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session


class RAGProvider:
    """
    Retrieves context for notification enhancement.
    Stage 23 Step 5: For companion_* uses RagContextPack summary; fail-open.
    """

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def retrieve_notification_context(
        self,
        user_id: int,
        notification_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        query_hint: str = "",
    ) -> Optional[str]:
        """
        Retrieve context for notification (e.g. companion templates).
        V1: Only for companion/connection_ping; uses RagContextPack summary.
        Returns None on failure or for non-companion / high-risk.
        """
        try:
            from backend.app.services.rag_context import (
                build_rag_context_pack,
                rag_allowed,
                serialize_rag_pack_for_context,
            )
        except ImportError:
            try:
                from app.services.rag_context import (
                    build_rag_context_pack,
                    rag_allowed,
                    serialize_rag_pack_for_context,
                )
            except ImportError:
                return None
        if not self.db or not notification_type or str(notification_type).strip().lower() not in (
            "connection_ping",
            "companion",
        ):
            return None
        if query_hint and not rag_allowed(query_hint, "en"):
            return None
        try:
            pack = build_rag_context_pack(self.db, user_id, fallback_language="en")
            return serialize_rag_pack_for_context(pack, max_chars=600)
        except Exception:
            return None

    def retrieve_condition_context(
        self,
        condition_name: str,
        user_conditions: Optional[List[Any]] = None,
    ) -> Optional[str]:
        """
        Retrieve care context for a medical condition.
        Returns None for now. Future: RAG over condition knowledge base.
        """
        return None
