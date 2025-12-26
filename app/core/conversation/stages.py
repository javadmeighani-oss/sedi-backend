# app/core/conversation/stages.py
"""
Conversation Stages - Relationship State Machine

RESPONSIBILITY:
- Defines relationship and conversation stages
- Handles stage transitions only
- NO text generation
- NO database access
"""

from enum import Enum
from typing import Optional
from sqlalchemy.orm import Session
from app.models import User, Memory


class ConversationStage(Enum):
    """Relationship and conversation stages"""
    FIRST_CONTACT = "first_contact"  # User just started, no memory
    INTRODUCTION = "introduction"  # Learning name, basic info
    GETTING_TO_KNOW = "getting_to_know"  # Learning interests, preferences
    DAILY_RELATION = "daily_relation"  # Established relationship, regular check-ins
    STABLE_RELATION = "stable_relation"  # Long-term companion, deep understanding


def get_stage(user_id: int, db: Session) -> ConversationStage:
    """
    Determine current conversation stage for a user.
    
    Logic:
    - FIRST_CONTACT: No memory entries
    - INTRODUCTION: 1-3 memory entries, name not fully learned
    - GETTING_TO_KNOW: 4-10 memory entries, learning preferences
    - DAILY_RELATION: 11-30 memory entries, regular interaction
    - STABLE_RELATION: 30+ memory entries, established relationship
    
    Returns:
        ConversationStage: Current stage
    """
    memory_count = db.query(Memory).filter(Memory.user_id == user_id).count()
    
    if memory_count == 0:
        return ConversationStage.FIRST_CONTACT
    elif memory_count <= 3:
        return ConversationStage.INTRODUCTION
    elif memory_count <= 10:
        return ConversationStage.GETTING_TO_KNOW
    elif memory_count <= 30:
        return ConversationStage.DAILY_RELATION
    else:
        return ConversationStage.STABLE_RELATION


def transition_stage(
    current_stage: ConversationStage,
    user_id: int,
    db: Session
) -> ConversationStage:
    """
    Check if stage transition is needed and return new stage.
    
    This function only determines transitions, does not modify state.
    
    Returns:
        ConversationStage: New stage (may be same as current)
    """
    new_stage = get_stage(user_id, db)
    
    # Only allow forward progression (no regression)
    stage_order = [
        ConversationStage.FIRST_CONTACT,
        ConversationStage.INTRODUCTION,
        ConversationStage.GETTING_TO_KNOW,
        ConversationStage.DAILY_RELATION,
        ConversationStage.STABLE_RELATION,
    ]
    
    current_index = stage_order.index(current_stage)
    new_index = stage_order.index(new_stage)
    
    if new_index > current_index:
        return new_stage
    else:
        return current_stage

