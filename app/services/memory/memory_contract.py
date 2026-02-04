# app/services/memory/memory_contract.py
"""
Memory Contract - Defines allowed domains and keys for UserMemoryFact storage.

This contract ensures consistency and prevents invalid data from being stored.
"""

from typing import Dict, List, Optional

# Allowed domains for memory facts
ALLOWED_DOMAINS = {
    "lifestyle": "Lifestyle patterns (sleep, hydration, activity, etc.)",
    "medical": "Medical information (conditions, medications, allergies)",
    "preferences": "User preferences (communication style, interests)",
    "routines": "Daily and weekly routines",
    "goals": "Health and fitness goals",
    "vitals": "Vital signs data from devices (heart_rate_bpm, etc.)",
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
    ],
    "medical": [
        "conditions",
        "medications",
        "allergies",
        "health_concerns",
    ],
    "preferences": [
        "communication_style",
        "notification_preferences",
        "language_preference",
        "interests",
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
    ],
}


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
    def validate_fact(domain: str, key: str) -> tuple:
        """
        Validate a memory fact.
        
        Returns:
            (is_valid, error_message)
        """
        if not MemoryContract.is_valid_domain(domain):
            return False, f"Invalid domain: {domain}. Allowed: {list(ALLOWED_DOMAINS.keys())}"
        
        if not MemoryContract.is_valid_key(domain, key):
            return False, f"Invalid key '{key}' for domain '{domain}'. Allowed: {ALLOWED_KEYS.get(domain, [])}"
        
        return True, None
    
    @staticmethod
    def get_allowed_keys_for_domain(domain: str) -> List[str]:
        """Get all allowed keys for a domain"""
        return ALLOWED_KEYS.get(domain, [])
