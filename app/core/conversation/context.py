# app/core/conversation/context.py
"""
Conversation Context Builder

RESPONSIBILITY:
- Builds conversation context by combining:
  - Memory
  - Current stage
  - Recent messages
- Provides clean input to brain and prompts
- NO decisions
- NO text generation
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from app.core.conversation.memory import ConversationMemory
from app.core.conversation.stages import ConversationStage
from app.models import Memory


class ConversationContext:
    """Builds conversation context for brain and prompts"""
    
    def __init__(
        self,
        user_id: int,
        stage: ConversationStage,
        memory: ConversationMemory,
        user_message: Optional[str] = None
    ):
        self.user_id = user_id
        self.stage = stage
        self.memory = memory
        self.user_message = user_message
    
    def build(self) -> Dict[str, any]:
        """
        Build complete conversation context.
        
        Returns:
            Dict with:
            - user_id: User ID
            - stage: Current conversation stage
            - user_name: User's name
            - memory_facts: Extracted memory facts
            - recent_messages: Recent conversation history
            - conversation_count: Total conversation exchanges
            - time_since_last: Time since last interaction
            - user_message: Current user message (if any)
        """
        memory_facts = self.memory.extract_memory_facts(self.user_id)
        recent_messages = self.memory.get_recent_messages(self.user_id, limit=5)
        conversation_count = self.memory.get_conversation_count(self.user_id)
        time_since_last = self.memory.get_time_since_last_interaction(self.user_id)
        
        # Format recent messages for context
        recent_history = []
        for msg in reversed(recent_messages):  # Oldest first
            recent_history.append({
                "user": msg.user_message,
                "sedi": msg.sedi_response,
                "timestamp": msg.created_at.isoformat()
            })
        
        return {
            "user_id": self.user_id,
            "stage": self.stage.value,
            "user_name": memory_facts.get("name"),
            "memory_facts": memory_facts,
            "recent_messages": recent_history,
            "conversation_count": conversation_count,
            "time_since_last": str(time_since_last) if time_since_last else None,
            "user_message": self.user_message,
        }
    
    def get_stage_description(self) -> str:
        """Get human-readable stage description"""
        descriptions = {
            ConversationStage.FIRST_CONTACT: "First contact - user just started",
            ConversationStage.INTRODUCTION: "Introduction - learning basic info",
            ConversationStage.GETTING_TO_KNOW: "Getting to know - learning preferences",
            ConversationStage.DAILY_RELATION: "Daily relation - established relationship",
            ConversationStage.STABLE_RELATION: "Stable relation - long-term companion",
        }
        return descriptions.get(self.stage, "Unknown stage")

