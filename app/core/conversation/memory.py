# app/core/conversation/memory.py
"""
Conversation Memory - Read/Write Only

RESPONSIBILITY:
- Reads/writes conversation memory
- Extracts: name, interests, dislikes, lifestyle hints, identification phrase
- NO decisions
- NO text generation
"""

from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from app.models import User, Memory
from datetime import datetime, timedelta


class ConversationMemory:
    """Handles conversation memory read/write operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_name(self, user_id: int) -> Optional[str]:
        """Get user's name from User model"""
        user = self.db.query(User).filter(User.id == user_id).first()
        return user.name if user else None
    
    def get_recent_messages(self, user_id: int, limit: int = 10) -> List[Memory]:
        """Get recent conversation messages"""
        return (
            self.db.query(Memory)
            .filter(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc())
            .limit(limit)
            .all()
        )
    
    def extract_memory_facts(self, user_id: int) -> Dict[str, any]:
        """
        Extract structured facts from conversation memory.
        
        Returns:
            Dict with:
            - name: User's name (if mentioned)
            - interests: List of mentioned interests
            - dislikes: List of mentioned dislikes
            - lifestyle_hints: List of lifestyle information
            - identification_phrase: Unique phrase user uses
        """
        memories = self.get_recent_messages(user_id, limit=50)
        
        facts = {
            "name": None,
            "interests": [],
            "dislikes": [],
            "lifestyle_hints": [],
            "identification_phrase": None,
        }
        
        # Extract name from User model
        facts["name"] = self.get_user_name(user_id)
        
        # For now, we'll rely on the brain to extract facts from messages
        # In future phases, this can be enhanced with NLP extraction
        
        return facts
    
    def save_conversation(
        self,
        user_id: int,
        user_message: str,
        sedi_response: str,
        language: str = "en"
    ) -> Memory:
        """Save a conversation exchange to memory"""
        memory = Memory(
            user_id=user_id,
            user_message=user_message,
            sedi_response=sedi_response,
            language=language,
            created_at=datetime.utcnow()
        )
        self.db.add(memory)
        self.db.commit()
        self.db.refresh(memory)
        return memory
    
    def get_conversation_count(self, user_id: int) -> int:
        """Get total number of conversation exchanges"""
        return self.db.query(Memory).filter(Memory.user_id == user_id).count()
    
    def get_last_interaction_time(self, user_id: int) -> Optional[datetime]:
        """Get timestamp of last interaction"""
        last_memory = (
            self.db.query(Memory)
            .filter(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc())
            .first()
        )
        return last_memory.created_at if last_memory else None
    
    def get_time_since_last_interaction(self, user_id: int) -> Optional[timedelta]:
        """Get time elapsed since last interaction"""
        last_time = self.get_last_interaction_time(user_id)
        if last_time:
            return datetime.utcnow() - last_time
        return None

