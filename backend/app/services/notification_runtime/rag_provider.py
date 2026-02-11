# backend.app.services.notification_runtime.rag_provider
"""
RAG Provider Placeholder (Stage 16.6)

Clean interface for future RAG integration. NOT wired yet.
Notification text generation does NOT call RAG. This module provides a placeholder
for when vitals/rules/decision engine needs condition-specific care guidance.
"""

from typing import Optional, List, Dict, Any


class RAGProvider:
    """
    Placeholder for future RAG retrieval.
    Use this to fetch condition-specific care tips or personalized content.
    """

    def retrieve_notification_context(
        self,
        user_id: int,
        notification_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Retrieve context for notification enhancement (e.g. condition-specific tips).
        
        Returns None for now. Future: call RAG service for user conditions,
        medications, recent vitals, etc.
        """
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
