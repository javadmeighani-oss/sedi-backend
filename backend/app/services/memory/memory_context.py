# app/services/memory/memory_context.py
"""
Memory Context - Builds compact memory context for DecisionEngine.

Extracts relevant lifestyle facts and builds a structured context object.
"""

from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
import json

from backend.app.services.memory.memory_repository import MemoryRepository


class MemoryContext:
    """Compact memory context for DecisionEngine"""
    
    def __init__(self):
        self.sleep_duration_hours: Optional[float] = None
        self.sleep_quality: Optional[str] = None
        self.hydration_ml: Optional[float] = None
        self.activity_level: Optional[str] = None
        self.steps_count: Optional[int] = None
        self.exercise_minutes: Optional[int] = None
        self.mood: Optional[str] = None
        self.stress_level: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "sleep_duration_hours": self.sleep_duration_hours,
            "sleep_quality": self.sleep_quality,
            "hydration_ml": self.hydration_ml,
            "activity_level": self.activity_level,
            "steps_count": self.steps_count,
            "exercise_minutes": self.exercise_minutes,
            "mood": self.mood,
            "stress_level": self.stress_level,
        }
    
    def has_sleep_data(self) -> bool:
        """Check if sleep data is available"""
        return self.sleep_duration_hours is not None
    
    def has_hydration_data(self) -> bool:
        """Check if hydration data is available"""
        return self.hydration_ml is not None
    
    def has_activity_data(self) -> bool:
        """Check if activity data is available"""
        return self.activity_level is not None or self.steps_count is not None


def build_memory_context(db: Session, user_id: int) -> MemoryContext:
    """
    Build a MemoryContext from UserMemoryFact for a user.
    
    Args:
        db: Database session
        user_id: User ID
    
    Returns:
        MemoryContext object
    """
    repo = MemoryRepository(db)
    context = MemoryContext()
    
    # Get lifestyle facts
    lifestyle_facts = repo.get_facts_by_domain(user_id, "lifestyle")
    
    for fact in lifestyle_facts:
        try:
            value = json.loads(fact.value_json)
            
            # Map keys to context attributes
            if fact.key == "sleep_duration_hours":
                context.sleep_duration_hours = float(value) if isinstance(value, (int, float, str)) else None
            elif fact.key == "sleep_quality":
                context.sleep_quality = str(value) if value else None
            elif fact.key == "hydration_ml":
                context.hydration_ml = float(value) if isinstance(value, (int, float, str)) else None
            elif fact.key == "activity_level":
                context.activity_level = str(value) if value else None
            elif fact.key == "steps_count":
                context.steps_count = int(value) if isinstance(value, (int, float, str)) else None
            elif fact.key == "exercise_minutes":
                context.exercise_minutes = int(value) if isinstance(value, (int, float, str)) else None
            elif fact.key == "mood":
                context.mood = str(value) if value else None
            elif fact.key == "stress_level":
                context.stress_level = str(value) if value else None
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"[MemoryContext] Error parsing fact {fact.key}: {e}")
            continue
    
    return context
