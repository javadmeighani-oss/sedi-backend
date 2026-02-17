# backend/app/behavior/__init__.py
"""Behavior Layer V1: controlled, human-care, female persona for Chat and Notifications."""
from backend.app.behavior.policy import BehaviorPolicy
from backend.app.behavior.service import (
    apply_behavior_to_question,
    try_create_companion_ping_notification,
)

__all__ = [
    "BehaviorPolicy",
    "apply_behavior_to_question",
    "try_create_companion_ping_notification",
]
