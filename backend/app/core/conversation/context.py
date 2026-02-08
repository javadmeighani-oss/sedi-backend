# app/core/conversation/context.py
"""
Conversation Context Builder - Health Care Assistant

RESPONSIBILITY:
- Builds conversation context by combining:
  - Memory (short-term, medium-term, long-term)
  - Current stage
  - Recent messages
  - Health data (vital signs from devices)
  - Lifestyle patterns
- Provides comprehensive context for health care assistant
- NO decisions
- NO text generation
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from backend.app.core.conversation.memory import ConversationMemory
from backend.app.core.conversation.stages import ConversationStage
from backend.app.models import Memory, HealthData


class ConversationContext:
    """Builds conversation context for brain and prompts"""
    
    def __init__(
        self,
        user_id: int,
        stage: ConversationStage,
        memory: ConversationMemory,
        user_message: Optional[str] = None,
        user_name: Optional[str] = None  # User's name from frontend (stored locally)
    ):
        self.user_id = user_id
        self.stage = stage
        self.memory = memory
        self.user_message = user_message
        self.user_name = user_name  # Name from frontend
    
    def build(self) -> Dict[str, any]:
        """
        Build complete conversation context for health care assistant.
        
        Includes:
        - SHORT-TERM memory: Recent conversations
        - MEDIUM-TERM memory: Patterns and lifestyle habits
        - LONG-TERM memory: Deep understanding of user's health profile
        - Health data: Vital signs from connected devices
        - Lifestyle patterns: Work, exercise, sleep, diet patterns
        
        Returns:
            Dict with:
            - user_id: User ID
            - stage: Current conversation stage
            - user_name: User's name
            - memory_facts: Extracted memory facts (lifestyle, health patterns)
            - recent_messages: Recent conversation history (SHORT-TERM)
            - conversation_count: Total conversation exchanges
            - time_since_last: Time since last interaction
            - user_message: Current user message (if any)
            - health_data: Recent vital signs data (if available)
            - lifestyle_patterns: Extracted lifestyle patterns (MEDIUM-TERM)
        """
        # EXPERIENCE STABILITY: Load structured memory domains (RAG-ready)
        # STEP 4: Memory is OPTIONAL - handle failures gracefully
        try:
            memory_facts = self.memory.extract_memory_facts(self.user_id)
            recent_messages = self.memory.get_recent_messages(self.user_id, limit=10)  # More for health context
            conversation_count = self.memory.get_conversation_count(self.user_id)
            time_since_last = self.memory.get_time_since_last_interaction(self.user_id)
        except Exception as memory_error:
            # STEP 4: Memory failure is non-critical - use defaults
            print(f"[CONTEXT WARNING] ⚠️ Memory load failed (non-critical): {memory_error}")
            print(f"[CONTEXT WARNING] Using empty defaults - chat will work without memory")
            memory_facts = {}
            recent_messages = []
            conversation_count = 0
            time_since_last = None
        
        # Format recent messages for context (SHORT-TERM memory)
        recent_history = []
        for msg in reversed(recent_messages):  # Oldest first
            recent_history.append({
                "user": msg.user_message,
                "sedi": msg.sedi_response,
                "timestamp": msg.created_at.isoformat()
            })
        
        # Get recent health data (vital signs from devices)
        health_data = self._get_recent_health_data()
        
        # Extract lifestyle patterns from conversation history (MEDIUM-TERM memory)
        lifestyle_patterns = self._extract_lifestyle_patterns(recent_messages)
        
        # EXPERIENCE STABILITY: Build context with structured memory domains
        # This prevents repetition by providing organized, RAG-ready facts
        # Priority: frontend name > extracted name from memory > None
        extracted_name = memory_facts.get("profile", {}).get("name")
        final_user_name = self.user_name or extracted_name  # Use frontend name if available, otherwise extracted
        
        return {
            "user_id": self.user_id,
            "stage": self.stage.value,
            "user_name": final_user_name,  # From frontend (priority) or extracted from memory
            "memory_facts": memory_facts,  # Structured domains (profile, medical, vitals, etc.)
            "recent_messages": recent_history,  # SHORT-TERM: Recent conversation context
            "conversation_count": conversation_count,
            "time_since_last": str(time_since_last) if time_since_last else None,
            "user_message": self.user_message,
            "health_data": health_data,  # Vital signs data
            "lifestyle_patterns": lifestyle_patterns,  # MEDIUM-TERM patterns
            # EXPERIENCE STABILITY: Structured domains for RAG
            "profile": memory_facts.get("profile", {}),
            "medical": memory_facts.get("medical", {}),
            "vitals": memory_facts.get("vitals", {}),
            "lifestyle": memory_facts.get("lifestyle", {}),
            "preferences": memory_facts.get("preferences", {}),
            "routines": memory_facts.get("routines", {}),
            "goals": memory_facts.get("goals", {}),
            "conversation_state": memory_facts.get("conversation_state", {})
        }
    
    def _get_recent_health_data(self) -> Optional[Dict[str, any]]:
        """
        Get recent health data (vital signs) from connected devices.
        
        Returns recent health metrics if available, None otherwise.
        """
        try:
            # Get recent health data (last 24 hours)
            from backend.app.models import HealthData
            from datetime import datetime, timedelta
            
            recent_health = (
                self.memory.db.query(HealthData)
                .filter(HealthData.user_id == self.user_id)
                .filter(HealthData.created_at >= datetime.utcnow() - timedelta(days=1))
                .order_by(HealthData.created_at.desc())
                .limit(10)
                .all()
            )
            
            if not recent_health:
                return None
            
            # Calculate averages for context
            heart_rates = [float(h.heart_rate) for h in recent_health if h.heart_rate]
            temperatures = [float(h.temperature) for h in recent_health if h.temperature]
            spo2_values = [float(h.spo2) for h in recent_health if h.spo2]
            
            health_summary = {}
            if heart_rates:
                health_summary["avg_heart_rate"] = sum(heart_rates) / len(heart_rates)
                health_summary["heart_rate_trend"] = "increasing" if heart_rates[0] > heart_rates[-1] else "decreasing" if len(heart_rates) > 1 else "stable"
            if temperatures:
                health_summary["avg_temperature"] = sum(temperatures) / len(temperatures)
            if spo2_values:
                health_summary["avg_spo2"] = sum(spo2_values) / len(spo2_values)
            
            health_summary["data_points"] = len(recent_health)
            health_summary["latest_timestamp"] = recent_health[0].created_at.isoformat() if recent_health else None
            
            return health_summary if health_summary else None
            
        except Exception as e:
            print(f"[CONTEXT ERROR] Failed to get health data: {e}")
            return None
    
    def _extract_lifestyle_patterns(self, recent_messages: List[Memory]) -> Dict[str, any]:
        """
        Extract lifestyle patterns from conversation history (MEDIUM-TERM memory).
        
        Analyzes recent conversations to identify:
        - Work patterns (schedule, stress levels)
        - Exercise habits
        - Sleep patterns
        - Diet preferences
        - Health concerns mentioned
        """
        if not recent_messages or len(recent_messages) < 3:
            return {}
        
        # Simple pattern extraction - in future, can be enhanced with NLP
        patterns = {
            "work_mentioned": False,
            "exercise_mentioned": False,
            "sleep_mentioned": False,
            "diet_mentioned": False,
            "health_concern_mentioned": False,
        }
        
        # Check recent messages for lifestyle keywords
        lifestyle_keywords = {
            "work": ["work", "job", "office", "meeting", "project", "کار", "شغل", "مكتب", "عمل"],
            "exercise": ["exercise", "workout", "gym", "run", "sport", "تمرين", "ورزش", "جيم", "رياضة"],
            "sleep": ["sleep", "tired", "rest", "bed", "خواب", "خسته", "استراحت", "نوم", "راحة"],
            "diet": ["food", "eat", "diet", "meal", "hungry", "غذا", "خوردن", "رژيم", "طعام", "أكل"],
            "health": ["health", "pain", "ache", "sick", "doctor", "سلامت", "درد", "بيمار", "صحة", "ألم"],
        }
        
        all_text = " ".join([msg.user_message.lower() + " " + msg.sedi_response.lower() for msg in recent_messages])
        
        for pattern_key, keywords in lifestyle_keywords.items():
            if any(keyword in all_text for keyword in keywords):
                if pattern_key == "work":
                    patterns["work_mentioned"] = True
                elif pattern_key == "exercise":
                    patterns["exercise_mentioned"] = True
                elif pattern_key == "sleep":
                    patterns["sleep_mentioned"] = True
                elif pattern_key == "diet":
                    patterns["diet_mentioned"] = True
                elif pattern_key == "health":
                    patterns["health_concern_mentioned"] = True
        
        return patterns
    
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

