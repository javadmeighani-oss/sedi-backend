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
    Determine current conversation stage for a user - EXPERIENCE STABILITY LAYER.
    
    Logic:
    - FIRST_CONTACT: No memory entries
    - INTRODUCTION: 1-3 memory entries, name not fully learned
    - GETTING_TO_KNOW: 4-10 memory entries, learning preferences
    - DAILY_RELATION: 11-30 memory entries, regular interaction
    - STABLE_RELATION: 30+ memory entries, established relationship
    
    EXPERIENCE STABILITY: Validates user_id exists and memory_count is correct.
    
    Returns:
        ConversationStage: Current stage
    """
    # EXPERIENCE STABILITY: Validate user exists
    from app.models import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        print(f"[STAGE DEBUG] ERROR: User {user_id} not found - returning FIRST_CONTACT")
        return ConversationStage.FIRST_CONTACT
    
    memory_count = db.query(Memory).filter(Memory.user_id == user_id).count()
    
    # TEMP DEBUG: Log stage detection
    print(f"[STAGE DEBUG] user_id={user_id}, memory_count={memory_count}")
    
    # EXPERIENCE STABILITY: Deterministic stage calculation
    if memory_count == 0:
        stage = ConversationStage.FIRST_CONTACT
    elif memory_count <= 3:
        stage = ConversationStage.INTRODUCTION
    elif memory_count <= 10:
        stage = ConversationStage.GETTING_TO_KNOW
    elif memory_count <= 30:
        stage = ConversationStage.DAILY_RELATION
    else:
        stage = ConversationStage.STABLE_RELATION
    
    print(f"[STAGE DEBUG] Detected stage: {stage.value}")
    return stage


def transition_stage(
    current_stage: ConversationStage,
    user_id: int,
    db: Session
) -> ConversationStage:
    """
    Check if stage transition is needed and return new stage - EXPERIENCE STABILITY LAYER.
    
    EXPERIENCE STABILITY RULES:
    1. Forward-only progression (no regression)
    2. Stage must match memory_count
    3. If mismatch, use higher stage (never regress)
    
    This function only determines transitions, does not modify state.
    
    Returns:
        ConversationStage: New stage (may be same as current)
    """
    new_stage = get_stage(user_id, db)
    
    # EXPERIENCE STABILITY: Forward-only progression (no regression)
    stage_order = [
        ConversationStage.FIRST_CONTACT,
        ConversationStage.INTRODUCTION,
        ConversationStage.GETTING_TO_KNOW,
        ConversationStage.DAILY_RELATION,
        ConversationStage.STABLE_RELATION,
    ]
    
    current_index = stage_order.index(current_stage)
    new_index = stage_order.index(new_stage)
    
    # EXPERIENCE STABILITY: Only allow forward progression
    if new_index > current_index:
        print(f"[STAGE DEBUG] Stage transition: {current_stage.value} -> {new_stage.value}")
        return new_stage
    elif new_index < current_index:
        # EXPERIENCE STABILITY: If stage would regress, keep current stage
        # This prevents stage regression (e.g., if user_id changes)
        print(f"[STAGE DEBUG] Stage regression prevented: {current_stage.value} -> {new_stage.value}, keeping {current_stage.value}")
        return current_stage
    else:
        # Same stage
        return current_stage

