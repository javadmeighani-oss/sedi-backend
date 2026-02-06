# Release D: service wrapper for decision engine
from typing import Dict, Any
from .rules import evaluate_rules, default_rules
from .models import Decision


def decide_from_event(event: Dict[str, Any]) -> Decision:
    rules = default_rules()
    return evaluate_rules(event, rules)
