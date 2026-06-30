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
        self.food_habits: Optional[str] = None
        self.diet_notes: Optional[str] = None
        self.routines: Dict[str, Any] = {}
        self.preferences: Dict[str, Any] = {}
        self.goals_summary: List[str] = []
        self.habits_summary: List[str] = []
        self.upcoming_events_summary: List[str] = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        base = {
            "sleep_duration_hours": self.sleep_duration_hours,
            "sleep_quality": self.sleep_quality,
            "hydration_ml": self.hydration_ml,
            "activity_level": self.activity_level,
            "steps_count": self.steps_count,
            "exercise_minutes": self.exercise_minutes,
            "mood": self.mood,
            "stress_level": self.stress_level,
            "food_habits": self.food_habits,
            "diet_notes": self.diet_notes,
        }
        base["routines"] = self.routines or {}
        base["preferences"] = self.preferences or {}
        base["goals_summary"] = self.goals_summary or []
        base["habits_summary"] = self.habits_summary or []
        base["upcoming_events_summary"] = self.upcoming_events_summary or []
        return base
    
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
    Gate 2: also attaches routines, preferences, goals/habits summaries, near-term events on the object.
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
            elif fact.key == "food_habits":
                context.food_habits = str(value) if value else None
            elif fact.key == "diet_notes":
                context.diet_notes = str(value) if value else None
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"[MemoryContext] Error parsing fact {fact.key}: {e}")
            continue

    # Gate 2 extended domains on context object
    context.routines = {}
    for fact in repo.get_facts_by_domain(user_id, "routines"):
        try:
            context.routines[fact.key] = json.loads(fact.value_json)
        except Exception:
            context.routines[fact.key] = fact.value_json

    context.preferences = {}
    for fact in repo.get_facts_by_domain(user_id, "preferences"):
        try:
            context.preferences[fact.key] = json.loads(fact.value_json)
        except Exception:
            context.preferences[fact.key] = fact.value_json

    try:
        from backend.app.services.gate2_data_service import list_goals, list_habits, list_events

        context.goals_summary = [g["title"] for g in list_goals(db, user_id)[:5]]
        context.habits_summary = [h["name"] for h in list_habits(db, user_id)[:5]]
        context.upcoming_events_summary = [
            f"{e['title']} ({e['starts_at']})" for e in list_events(db, user_id, upcoming_only=True)[:3]
        ]
    except Exception:
        context.goals_summary = []
        context.habits_summary = []
        context.upcoming_events_summary = []

    return context
