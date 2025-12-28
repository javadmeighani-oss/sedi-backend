# app/core/conversation/memory.py
"""
Conversation Memory - Health Care Assistant

RESPONSIBILITY:
- Reads/writes conversation memory
- Manages three types of memory:
  * SHORT-TERM: Recent conversations (last few exchanges)
  * MEDIUM-TERM: Lifestyle patterns, habits, preferences (days/weeks)
  * LONG-TERM: Deep understanding of user's health profile, goals, relationship history
- Extracts: name, lifestyle patterns, health habits, work patterns, exercise, sleep, diet
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
        memories = (
            self.db.query(Memory)
            .filter(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc())
            .limit(limit)
            .all()
        )
        # TEMP DEBUG: Log memory load
        print(f"[MEMORY DEBUG] Loaded {len(memories)} recent messages for user_id={user_id}")
        return memories
    
    def extract_memory_facts(self, user_id: int) -> Dict[str, any]:
        """
        Extract structured facts from conversation memory for health care assistant.
        
        Combines SHORT-TERM, MEDIUM-TERM, and LONG-TERM memory:
        - SHORT-TERM: Recent conversation context
        - MEDIUM-TERM: Lifestyle patterns learned over days/weeks
        - LONG-TERM: Deep understanding of user's health profile
        
        Returns:
            Dict with:
            - name: User's name
            - lifestyle_patterns: Work, exercise, sleep, diet patterns
            - health_habits: Health-related habits mentioned
            - health_goals: Health goals mentioned
            - personal_info: Personal life information
            - work_info: Work-related information
            - preferences: User preferences learned
        """
        # Get memories for different time periods
        short_term = self.get_recent_messages(user_id, limit=10)  # Last 10 exchanges
        medium_term = self.get_recent_messages(user_id, limit=50)  # Last 50 exchanges (days/weeks)
        long_term = self.get_recent_messages(user_id, limit=200)  # All significant history
        
        facts = {
            "name": self.get_user_name(user_id),
            "lifestyle_patterns": {
                "work": self._extract_work_patterns(medium_term),
                "exercise": self._extract_exercise_patterns(medium_term),
                "sleep": self._extract_sleep_patterns(medium_term),
                "diet": self._extract_diet_patterns(medium_term),
            },
            "health_habits": self._extract_health_habits(medium_term),
            "health_goals": self._extract_health_goals(long_term),
            "personal_info": self._extract_personal_info(medium_term),
            "work_info": self._extract_work_info(medium_term),
            "preferences": self._extract_preferences(medium_term),
        }
        
        return facts
    
    def _extract_work_patterns(self, memories: List[Memory]) -> Dict[str, any]:
        """Extract work-related patterns from conversations"""
        work_keywords = ["work", "job", "office", "meeting", "project", "deadline", "کار", "شغل", "مكتب", "عمل"]
        work_mentions = [m for m in memories if any(kw in m.user_message.lower() for kw in work_keywords)]
        return {
            "mentioned": len(work_mentions) > 0,
            "frequency": len(work_mentions),
            "recent": work_mentions[-1].user_message if work_mentions else None
        }
    
    def _extract_exercise_patterns(self, memories: List[Memory]) -> Dict[str, any]:
        """Extract exercise-related patterns from conversations"""
        exercise_keywords = ["exercise", "workout", "gym", "run", "sport", "تمرين", "ورزش", "جيم", "رياضة"]
        exercise_mentions = [m for m in memories if any(kw in m.user_message.lower() for kw in exercise_keywords)]
        return {
            "mentioned": len(exercise_mentions) > 0,
            "frequency": len(exercise_mentions),
            "recent": exercise_mentions[-1].user_message if exercise_mentions else None
        }
    
    def _extract_sleep_patterns(self, memories: List[Memory]) -> Dict[str, any]:
        """Extract sleep-related patterns from conversations"""
        sleep_keywords = ["sleep", "tired", "rest", "bed", "خواب", "خسته", "استراحت", "نوم", "راحة"]
        sleep_mentions = [m for m in memories if any(kw in m.user_message.lower() for kw in sleep_keywords)]
        return {
            "mentioned": len(sleep_mentions) > 0,
            "frequency": len(sleep_mentions),
            "recent": sleep_mentions[-1].user_message if sleep_mentions else None
        }
    
    def _extract_diet_patterns(self, memories: List[Memory]) -> Dict[str, any]:
        """Extract diet-related patterns from conversations"""
        diet_keywords = ["food", "eat", "diet", "meal", "hungry", "غذا", "خوردن", "رژيم", "طعام", "أكل"]
        diet_mentions = [m for m in memories if any(kw in m.user_message.lower() for kw in diet_keywords)]
        return {
            "mentioned": len(diet_mentions) > 0,
            "frequency": len(diet_mentions),
            "recent": diet_mentions[-1].user_message if diet_mentions else None
        }
    
    def _extract_health_habits(self, memories: List[Memory]) -> List[str]:
        """Extract health-related habits mentioned"""
        health_keywords = ["health", "exercise", "meditation", "yoga", "walk", "سلامت", "تمرين", "يوغا", "مشي", "صحة"]
        health_mentions = []
        for m in memories:
            if any(kw in m.user_message.lower() for kw in health_keywords):
                # Extract relevant phrases (simplified - can be enhanced with NLP)
                health_mentions.append(m.user_message[:100])  # First 100 chars
        return health_mentions[:5]  # Top 5 mentions
    
    def _extract_health_goals(self, memories: List[Memory]) -> List[str]:
        """Extract health goals mentioned"""
        goal_keywords = ["goal", "want", "plan", "target", "هدف", "ميخواهم", "برنامه", "هدف", "خطة"]
        goals = []
        for m in memories:
            if any(kw in m.user_message.lower() for kw in goal_keywords):
                goals.append(m.user_message[:100])
        return goals[:5]
    
    def _extract_personal_info(self, memories: List[Memory]) -> Dict[str, any]:
        """Extract personal life information"""
        return {
            "mentioned": len([m for m in memories if "family" in m.user_message.lower() or "خانواده" in m.user_message.lower()]) > 0,
            "frequency": len([m for m in memories if "family" in m.user_message.lower() or "خانواده" in m.user_message.lower()])
        }
    
    def _extract_work_info(self, memories: List[Memory]) -> Dict[str, any]:
        """Extract work information"""
        work_keywords = ["work", "job", "office", "کار", "شغل", "مكتب"]
        work_mentions = [m for m in memories if any(kw in m.user_message.lower() for kw in work_keywords)]
        return {
            "mentioned": len(work_mentions) > 0,
            "frequency": len(work_mentions),
            "stress_mentioned": len([m for m in work_mentions if "stress" in m.user_message.lower() or "استرس" in m.user_message.lower()]) > 0
        }
    
    def _extract_preferences(self, memories: List[Memory]) -> Dict[str, any]:
        """Extract user preferences"""
        return {
            "language": memories[0].language if memories else "en",
            "communication_style": "conversational"  # Can be enhanced with analysis
        }
    
    def save_conversation(
        self,
        user_id: int,
        user_message: str,
        sedi_response: str,
        language: str = "en"
    ) -> Memory:
        """Save a conversation exchange to memory"""
        # TEMP DEBUG: Log before save
        memory_count_before = self.get_conversation_count(user_id)
        print(f"[MEMORY DEBUG] Saving conversation - user_id={user_id}, count_before={memory_count_before}")
        print(f"[MEMORY DEBUG] Message snippet: {user_message[:50]}...")
        
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
        
        # TEMP DEBUG: Log after save
        memory_count_after = self.get_conversation_count(user_id)
        print(f"[MEMORY DEBUG] Memory saved - user_id={user_id}, count_after={memory_count_after}, memory_id={memory.id}")
        
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

