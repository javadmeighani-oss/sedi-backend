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
        if user and user.name:
            return user.name
        return None
    
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
        Extract structured facts from conversation memory - EXPERIENCE STABILITY LAYER.
        
        Returns structured memory domains for RAG-ready storage:
        - profile: Basic user information
        - medical: Health conditions, medications, allergies
        - vitals: Vital signs data (from HealthData)
        - lifestyle: Work, exercise, sleep, diet patterns
        - preferences: Communication style, interests
        - routines: Daily/weekly patterns
        - goals: Health, fitness, lifestyle goals
        - conversation_state: Current stage and flags
        
        This structure is RAG-ready and prevents repetition by storing facts
        in organized domains rather than raw chat.
        """
        # Get memories for different time periods
        short_term = self.get_recent_messages(user_id, limit=10)  # Last 10 exchanges
        medium_term = self.get_recent_messages(user_id, limit=50)  # Last 50 exchanges (days/weeks)
        long_term = self.get_recent_messages(user_id, limit=200)  # All significant history
        
        # Get user info (name no longer stored in database)
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = None  # Name no longer stored in database
        
        # EXPERIENCE STABILITY: Structured memory domains
        facts = {
            "profile": {
                "name": self._extract_name(medium_term, user_name),
                "age": self._extract_age(medium_term),
                "language": user.preferred_language if user else "en",
                "created_at": user.created_at.isoformat() if user and user.created_at else None
            },
            "medical": {
                "conditions": self._extract_medical_conditions(medium_term),
                "medications": self._extract_medications(medium_term),
                "allergies": self._extract_allergies(medium_term),
                "health_concerns": self._extract_health_concerns(medium_term)
            },
            "vitals": self._extract_vitals(user_id),
            "lifestyle": {
                "work_patterns": self._extract_work_patterns(medium_term),
                "exercise_patterns": self._extract_exercise_patterns(medium_term),
                "sleep_patterns": self._extract_sleep_patterns(medium_term),
                "diet_patterns": self._extract_diet_patterns(medium_term)
            },
            "preferences": {
                "communication_style": self._extract_preferences(medium_term).get("communication_style", "conversational"),
                "health_goals": self._extract_health_goals(long_term),
                "interests": self._extract_interests(medium_term)
            },
            "routines": {
                "daily_routine": self._extract_daily_routine(medium_term),
                "weekly_patterns": self._extract_weekly_patterns(medium_term)
            },
            "goals": {
                "health_goals": self._extract_health_goals(long_term),
                "fitness_goals": self._extract_fitness_goals(long_term),
                "lifestyle_goals": self._extract_lifestyle_goals(long_term)
            },
            "conversation_state": {
                "stage": None,  # Will be set by brain.py
                "last_stage_transition": None,  # Will be tracked by brain.py
                "flags": {
                    "name_learned": self._is_name_learned(medium_term, user_name),
                    "basic_info_learned": len(medium_term) > 3
                }
            }
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

    # EXPERIENCE STABILITY: Structured extraction methods for RAG-ready domains
    def _extract_name(self, memories: List[Memory], user_name: Optional[str]) -> Optional[str]:
        """Extract user's name from conversations or use stored name"""
        if user_name and not user_name.startswith("anonymous_"):
            return user_name
        
        # Try to extract name from conversations
        name_keywords = ["my name is", "i'm", "i am", "اسم من", "من", "اسمم", "اسم"]
        for m in memories:
            msg_lower = m.user_message.lower()
            for kw in name_keywords:
                if kw in msg_lower:
                    # Extract name after keyword (simplified)
                    parts = m.user_message.split(kw, 1)
                    if len(parts) > 1:
                        name = parts[1].strip().split()[0] if parts[1].strip() else None
                        if name and len(name) > 1:
                            return name
        return user_name if user_name else None
    
    def _extract_age(self, memories: List[Memory]) -> Optional[int]:
        """Extract user's age from conversations"""
        age_keywords = ["years old", "age", "سن", "عمر"]
        for m in memories:
            msg_lower = m.user_message.lower()
            for kw in age_keywords:
                if kw in msg_lower:
                    # Try to extract number before/after keyword
                    import re
                    numbers = re.findall(r'\d+', m.user_message)
                    if numbers:
                        age = int(numbers[0])
                        if 1 <= age <= 120:  # Reasonable age range
                            return age
        return None
    
    def _extract_medical_conditions(self, memories: List[Memory]) -> List[str]:
        """Extract medical conditions mentioned"""
        condition_keywords = ["diabetes", "hypertension", "asthma", "condition", "بیماری", "مرض", "حالة"]
        conditions = []
        for m in memories:
            msg_lower = m.user_message.lower()
            if any(kw in msg_lower for kw in condition_keywords):
                # Extract relevant phrase (simplified)
                conditions.append(m.user_message[:100])
        return conditions[:5]
    
    def _extract_medications(self, memories: List[Memory]) -> List[str]:
        """Extract medications mentioned"""
        med_keywords = ["medication", "medicine", "pill", "drug", "دارو", "دواء"]
        medications = []
        for m in memories:
            msg_lower = m.user_message.lower()
            if any(kw in msg_lower for kw in med_keywords):
                medications.append(m.user_message[:100])
        return medications[:5]
    
    def _extract_allergies(self, memories: List[Memory]) -> List[str]:
        """Extract allergies mentioned"""
        allergy_keywords = ["allergy", "allergic", "حساسیت", "حساسية"]
        allergies = []
        for m in memories:
            msg_lower = m.user_message.lower()
            if any(kw in msg_lower for kw in allergy_keywords):
                allergies.append(m.user_message[:100])
        return allergies[:5]
    
    def _extract_health_concerns(self, memories: List[Memory]) -> List[str]:
        """Extract health concerns mentioned"""
        concern_keywords = ["pain", "ache", "sick", "unwell", "درد", "بیمار", "ألم", "مريض"]
        concerns = []
        for m in memories:
            msg_lower = m.user_message.lower()
            if any(kw in msg_lower for kw in concern_keywords):
                concerns.append(m.user_message[:100])
        return concerns[:5]
    
    def _extract_vitals(self, user_id: int) -> Dict[str, any]:
        """Extract vital signs data from HealthData"""
        try:
            from app.models import HealthData
            recent_health = (
                self.db.query(HealthData)
                .filter(HealthData.user_id == user_id)
                .order_by(HealthData.created_at.desc())
                .limit(10)
                .all()
            )
            
            if not recent_health:
                return {
                    "heart_rate_avg": None,
                    "temperature_avg": None,
                    "spo2_avg": None,
                    "last_reading": None
                }
            
            heart_rates = [float(h.heart_rate) for h in recent_health if h.heart_rate]
            temperatures = [float(h.temperature) for h in recent_health if h.temperature]
            spo2_values = [float(h.spo2) for h in recent_health if h.spo2]
            
            return {
                "heart_rate_avg": sum(heart_rates) / len(heart_rates) if heart_rates else None,
                "temperature_avg": sum(temperatures) / len(temperatures) if temperatures else None,
                "spo2_avg": sum(spo2_values) / len(spo2_values) if spo2_values else None,
                "last_reading": recent_health[0].created_at.isoformat() if recent_health else None
            }
        except Exception as e:
            print(f"[MEMORY ERROR] Failed to extract vitals: {e}")
            return {
                "heart_rate_avg": None,
                "temperature_avg": None,
                "spo2_avg": None,
                "last_reading": None
            }
    
    def _extract_interests(self, memories: List[Memory]) -> List[str]:
        """Extract user interests mentioned"""
        interest_keywords = ["like", "enjoy", "love", "interest", "علاقه", "دوست دارم", "اهتمام"]
        interests = []
        for m in memories:
            msg_lower = m.user_message.lower()
            if any(kw in msg_lower for kw in interest_keywords):
                interests.append(m.user_message[:100])
        return interests[:5]
    
    def _extract_daily_routine(self, memories: List[Memory]) -> List[str]:
        """Extract daily routine patterns"""
        routine_keywords = ["morning", "evening", "routine", "usually", "روزانه", "معمولاً", "روتين"]
        routines = []
        for m in memories:
            msg_lower = m.user_message.lower()
            if any(kw in msg_lower for kw in routine_keywords):
                routines.append(m.user_message[:100])
        return routines[:5]
    
    def _extract_weekly_patterns(self, memories: List[Memory]) -> Dict[str, any]:
        """Extract weekly patterns"""
        return {
            "work_days": None,  # Can be enhanced
            "exercise_days": None,
            "patterns_mentioned": len([m for m in memories if "week" in m.user_message.lower() or "هفته" in m.user_message.lower()]) > 0
        }
    
    def _extract_fitness_goals(self, memories: List[Memory]) -> List[str]:
        """Extract fitness goals"""
        fitness_keywords = ["fitness", "exercise", "workout", "gym", "ورزش", "تمرين", "لياقة"]
        goals = []
        for m in memories:
            msg_lower = m.user_message.lower()
            if any(kw in msg_lower for kw in fitness_keywords):
                if "goal" in msg_lower or "want" in msg_lower or "هدف" in msg_lower:
                    goals.append(m.user_message[:100])
        return goals[:5]
    
    def _extract_lifestyle_goals(self, memories: List[Memory]) -> List[str]:
        """Extract lifestyle goals"""
        lifestyle_keywords = ["lifestyle", "life", "change", "improve", "سبک زندگی", "تحسين"]
        goals = []
        for m in memories:
            msg_lower = m.user_message.lower()
            if any(kw in msg_lower for kw in lifestyle_keywords):
                if "goal" in msg_lower or "want" in msg_lower or "هدف" in msg_lower:
                    goals.append(m.user_message[:100])
        return goals[:5]
    
    def _is_name_learned(self, memories: List[Memory], user_name: Optional[str]) -> bool:
        """Check if user's name has been learned"""
        if user_name and not user_name.startswith("anonymous_"):
            return True
        return self._extract_name(memories, user_name) is not None

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
    
    def upsert_extracted_facts(
        self,
        user_id: int,
        facts: Dict[str, any],
        source: str = "chat"
    ) -> None:
        """
        OPTIONAL method to upsert extracted facts into UserMemoryFact.
        
        This does NOT change the main chat flow unless called explicitly.
        Keeps current keyword extraction logic.
        
        Args:
            user_id: User ID
            facts: Dictionary of facts to extract (from extract_memory_facts output)
            source: Source of facts ("chat" | "device" | "manual")
        """
        try:
            from app.services.memory import MemoryRepository
            
            repo = MemoryRepository(self.db)
            
            # Extract lifestyle facts
            lifestyle = facts.get("lifestyle", {})
            if lifestyle:
                # Sleep patterns
                sleep_patterns = lifestyle.get("sleep_patterns", {})
                if sleep_patterns.get("mentioned"):
                    # Try to extract sleep duration from recent message
                    recent = sleep_patterns.get("recent", "")
                    if recent:
                        # Simple extraction (can be enhanced)
                        import re
                        hours_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)', recent.lower())
                        if hours_match:
                            try:
                                hours = float(hours_match.group(1))
                                if 0 <= hours <= 24:
                                    repo.upsert_fact(
                                        user_id=user_id,
                                        domain="lifestyle",
                                        key="sleep_duration_hours",
                                        value=hours,
                                        confidence=0.6,
                                        source=source
                                    )
                            except (ValueError, TypeError):
                                pass
            
            # Extract preferences
            preferences = facts.get("preferences", {})
            if preferences:
                comm_style = preferences.get("communication_style")
                if comm_style:
                    repo.upsert_fact(
                        user_id=user_id,
                        domain="preferences",
                        key="communication_style",
                        value=comm_style,
                        confidence=0.7,
                        source=source
                    )
        except Exception as e:
            # Fail silently - this is optional functionality
            print(f"[Memory] Optional fact extraction failed: {e}")

