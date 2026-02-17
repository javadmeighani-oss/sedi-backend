# Release D: service wrapper for decision engine (single import path for isinstance)
from typing import Dict, Any, List

from backend.app.decision_engine.models import Decision, EventDto, CreateHealthAlertAction, Action
from .rules import evaluate_rules, default_rules
from backend.app.services.vitals.rule_alerts import compute_alert_actions


def decide_from_event(event: Dict[str, Any]) -> Decision:
    """Used by POST /decision/evaluate (rule-based, e.g. HR_HIGH_REST with context)."""
    rules = default_rules()
    return evaluate_rules(event, rules)


def evaluate_event(event: EventDto) -> List[Action]:
    """
    Single entry point for device events: compute actions (e.g. health alerts) from event.
    No persistence; caller runs action executor to persist notifications.
    """
    return compute_alert_actions(
        user_id=event.user_id,
        event_type=event.event_type,
        normalized_payload=event.payload,
    )
