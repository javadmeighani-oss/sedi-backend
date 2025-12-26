# app/core/conversation/__init__.py
"""
Conversation Brain v1 - Human-Like Conversation Foundation

This module implements the conversation brain architecture for Sedi.
All conversation logic, state management, and text generation happens here.

Architecture:
- brain.py: Central decision engine (COMMANDER)
- stages.py: Conversation & relationship state machine
- prompts.py: Language & text generation (Sedi's voice)
- memory.py: Conversation memory (read/write only)
- context.py: Builds conversation context
"""

from .brain import ConversationBrain
from .stages import ConversationStage, get_stage, transition_stage

__all__ = [
    'ConversationBrain',
    'ConversationStage',
    'get_stage',
    'transition_stage',
]

