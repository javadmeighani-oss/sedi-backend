# app/services/memory/memory_contract.py
"""
Memory Contract - Defines allowed domains and keys for UserMemoryFact storage.

This contract ensures consistency and prevents invalid data from being stored.
"""

from typing import Any, Dict, List, Optional

# Allowed domains for memory facts
ALLOWED_DOMAINS = {
    "lifestyle": "Lifestyle patterns (sleep, hydration, activity, etc.)",
    "medical": "Medical information (conditions, medications, allergies)",
    "preferences": "User preferences (communication style, interests)",
    "routines": "Daily and weekly routines",
    "goals": "Health and fitness goals",
    "vitals": "Vital signs data from devices (heart_rate_bpm, etc.)",
    # Stage 06 / B1: user-stated body-function status that tailors plans (non-diagnostic, I6-canonical).
    "function": "User-stated body-function status (swallowing, mobility, breathing, ...)",
    # Stage 06 / B1.5-a: friendly plan-intake answers (goal, allergies, preferences, budget, time).
    "intake": "User-stated plan-intake answers (goal, allergies, food/exercise preferences, budget, time)",
    # CR-01 longitudinal user-understanding domains (non-medical; I6-canonical).
    "work": "Work context (occupation, schedule, stressors)",
    "education": "Education background (level, field of study)",
    "social": "Social context (household, support, relationships, activity preference)",
    "values": "Personal values and life priorities",
    "barriers": "Practical barriers (time, financial, environmental, motivation)",
}

# Allowed keys per domain
ALLOWED_KEYS: Dict[str, List[str]] = {
    "lifestyle": [
        "sleep_duration_hours",
        "sleep_quality",
        "hydration_ml",
        "activity_level",
        "steps_count",
        "exercise_minutes",
        "mood",
        "stress_level",
        "food_habits",
        "diet_notes",
    ],
    "medical": [
        "conditions",
        "medications",
        "allergies",
        "health_concerns",
        # R-014: user-stated family health history (never inferred; only what the user said).
        "family_history",
    ],
    "preferences": [
        "communication_style",
        "notification_preferences",
        "language_preference",
        "interests",
        "timezone",
        "quiet_hours",
        # CR-01 interaction preferences (non-diagnostic).
        "response_length",
        "interaction_style",
        "follow_up_preference",
        "listen_before_advice",
        "proactive_checkin_preference",
    ],
    "intake": [
        "goal",
        "allergies",
        "food_preferences",
        "budget",
        "cooking_time",
        "meal_times",
        "exercise_preferences",
        "exercise_time",
        "equipment",
    ],
    "function": [
        "swallowing",
        "mobility",
        "breathing",
        "balance",
        "cognition",
        "senses",
        "pain_fatigue",
        "digestion",
        "glucose",
        "appetite",
        "general",
    ],
    "routines": [
        "wake_time",
        "bedtime",
        "meal_times",
        "exercise_schedule",
    ],
    "goals": [
        "health_goals",
        "fitness_goals",
        "lifestyle_goals",
    ],
    "vitals": [
        "heart_rate_bpm",
        "blood_pressure_sys",
        "blood_pressure_dia",
        "glucose_mg_dl",
        "temperature_c",
    ],
    "work": [
        "occupation",
        "work_schedule",
        "work_stressors",
    ],
    "education": [
        "education_level",
        "field_of_study",
    ],
    "social": [
        "household_context",
        "support_network",
        "important_relationships",
        "social_activity_preference",
    ],
    "values": [
        "important_values",
        "life_priorities",
    ],
    "barriers": [
        "time_constraints",
        "financial_constraints",
        "environmental_constraints",
        "motivation_barriers",
    ],
}


# v636 ownership classes. I6 may store a key only when it is CANONICAL_I6 or
# explicitly LEGACY_COMPATIBILITY (non-authoritative). Stronger owners win.
CANONICAL_I6 = "CANONICAL_I6"
CANONICAL_PROFILE = "CANONICAL_PROFILE"
CANONICAL_HEALTH = "CANONICAL_HEALTH"
CANONICAL_MEDICATION = "CANONICAL_MEDICATION"
CANONICAL_GOALS_OR_LIFESTYLE = "CANONICAL_GOALS_OR_LIFESTYLE"
CANONICAL_VITALS_I9 = "CANONICAL_VITALS_I9"
LEGACY_COMPATIBILITY = "LEGACY_COMPATIBILITY"

# Read-only aliases: never persist the left-hand key as a second truth.
LEGACY_KEY_ALIASES: Dict[tuple, tuple] = {
    ("preferences", "language"): ("preferences", "language_preference"),
}

# Keys that must not be written as independent I6 truth (stronger owner exists).
I6_WRITE_BLOCKED_OWNERS = frozenset({
    CANONICAL_PROFILE,
    CANONICAL_HEALTH,
    CANONICAL_MEDICATION,
    CANONICAL_VITALS_I9,
})

KEY_OWNERSHIP_OVERRIDES: Dict[tuple, str] = {
    ("preferences", "timezone"): CANONICAL_PROFILE,  # UserProfileCore.timezone
    ("preferences", "quiet_hours"): CANONICAL_PROFILE,  # NotificationPrefs + UserProfileCore quiet window
    ("medical", "conditions"): CANONICAL_HEALTH,  # UserCondition
    ("medical", "medications"): CANONICAL_MEDICATION,  # UserMedication
    ("medical", "allergies"): LEGACY_COMPATIBILITY,  # UserProfileFact.allergy is structured owner; no dedicated table
    ("medical", "health_concerns"): CANONICAL_I6,
    ("medical", "family_history"): CANONICAL_I6,
}

# R-014 "second memory": user-STATED health facts that Sedi may use when answering (consent-gated reads).
# The generic I6 projection still excludes the medical domain (conditions/medications come from their own
# owners); these two keys are projected through HealthContextAdapter only.
I6_USER_STATED_HEALTH_KEYS = (
    ("medical", "health_concerns"),
    ("medical", "family_history"),
)

DOMAIN_OWNERSHIP_DEFAULT: Dict[str, str] = {
    "lifestyle": CANONICAL_I6,
    "routines": CANONICAL_I6,
    "preferences": CANONICAL_I6,
    "work": CANONICAL_I6,
    "education": CANONICAL_I6,
    "social": CANONICAL_I6,
    "values": CANONICAL_I6,
    "barriers": CANONICAL_I6,
    "goals": CANONICAL_GOALS_OR_LIFESTYLE,  # UserGoal is product owner; I6 goals are compatibility-only
    "medical": CANONICAL_HEALTH,
    "vitals": CANONICAL_VITALS_I9,
}

# I6 facts that may be projected into Sedi/LLM context as I6 memory (not as a competing owner).
I6_CONTEXT_EXCLUDED_KEYS = frozenset({
    ("preferences", "timezone"),
    ("preferences", "quiet_hours"),
    ("preferences", "language_preference"),
})
I6_CONTEXT_EXCLUDED_DOMAINS = frozenset({"medical", "vitals", "goals"})


def render_stated_value(raw: Any) -> str:
    """JSON memory value -> short readable text («دیابت، فشار خون»)."""
    import json as _json

    if raw is None:
        return ""
    try:
        data = _json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        data = raw
    if isinstance(data, (list, tuple)):
        return "، ".join(str(x).strip() for x in data if str(x).strip())
    if isinstance(data, dict) and "value" in data:
        return str(data["value"]).strip()
    return str(data).strip()


class MemoryContract:
    """Validates memory fact domains and keys"""
    
    @staticmethod
    def is_valid_domain(domain: str) -> bool:
        """Check if domain is allowed"""
        return domain in ALLOWED_DOMAINS
    
    @staticmethod
    def is_valid_key(domain: str, key: str) -> bool:
        """Check if key is allowed for the given domain"""
        if domain not in ALLOWED_KEYS:
            return False
        return key in ALLOWED_KEYS[domain]

    @staticmethod
    def canonicalize_key(domain: str, key: str) -> tuple:
        """Map a legacy reader/writer key onto the single canonical vocabulary pair."""
        return LEGACY_KEY_ALIASES.get((domain, key), (domain, key))

    @staticmethod
    def classify_ownership(domain: str, key: str) -> str:
        canonical_domain, canonical_key = MemoryContract.canonicalize_key(domain, key)
        override = KEY_OWNERSHIP_OVERRIDES.get((canonical_domain, canonical_key))
        if override:
            return override
        return DOMAIN_OWNERSHIP_DEFAULT.get(canonical_domain, CANONICAL_I6)

    @staticmethod
    def i6_write_permitted(domain: str, key: str) -> tuple:
        """
        Whether I6 may persist this key as a writable fact.

        Compatibility/cache keys with a stronger owner are rejected so I6 cannot
        become a second canonical truth store.
        """
        owner = MemoryContract.classify_ownership(domain, key)
        if owner in I6_WRITE_BLOCKED_OWNERS:
            return False, (
                f"NON_I6_CANONICAL_OWNER:{owner} for {domain}/{key}. "
                "I6 cannot store a competing truth for this concept."
            )
        return True, None

    @staticmethod
    def is_i6_context_projectable(domain: str, key: str) -> bool:
        canonical_domain, canonical_key = MemoryContract.canonicalize_key(domain, key)
        if canonical_domain in I6_CONTEXT_EXCLUDED_DOMAINS:
            return False
        if (canonical_domain, canonical_key) in I6_CONTEXT_EXCLUDED_KEYS:
            return False
        return MemoryContract.classify_ownership(canonical_domain, canonical_key) in {
            CANONICAL_I6,
            LEGACY_COMPATIBILITY,
        }
    
    @staticmethod
    def validate_fact(domain: str, key: str) -> tuple:
        """
        Validate a memory fact.
        
        Returns:
            (is_valid, error_message)
        """
        domain, key = MemoryContract.canonicalize_key(domain, key)
        if not MemoryContract.is_valid_domain(domain):
            return False, f"Invalid domain: {domain}. Allowed: {list(ALLOWED_DOMAINS.keys())}"
        
        if not MemoryContract.is_valid_key(domain, key):
            return False, f"Invalid key '{key}' for domain '{domain}'. Allowed: {ALLOWED_KEYS.get(domain, [])}"

        permitted, owner_err = MemoryContract.i6_write_permitted(domain, key)
        if not permitted:
            return False, owner_err
        
        return True, None
    
    @staticmethod
    def get_allowed_keys_for_domain(domain: str) -> List[str]:
        """Get all allowed keys for a domain"""
        return ALLOWED_KEYS.get(domain, [])
