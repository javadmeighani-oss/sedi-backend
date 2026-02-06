# Release D: deterministic rule evaluation
from dataclasses import dataclass
from typing import Any, Dict, List, Callable
from .models import Decision


@dataclass(frozen=True)
class Rule:
    rule_id: str
    match: Callable[[Dict[str, Any]], bool]
    build: Callable[[Dict[str, Any]], Decision]


def evaluate_rules(event: Dict[str, Any], rules: List[Rule]) -> Decision:
    for r in rules:
        if r.match(event):
            d = r.build(event)
            if d.reason == "no_rule_matched":
                d = Decision(
                    decision=d.decision,
                    reason=r.rule_id,
                    severity=d.severity,
                    source_event_id=d.source_event_id,
                    meta=d.meta,
                )
            return d
    return Decision()


def default_rules() -> List[Rule]:
    def match_hr_high_rest(e: Dict[str, Any]) -> bool:
        return (
            e.get("event_type") == "heart_rate"
            and isinstance(e.get("bpm"), (int, float))
            and e.get("bpm") > 110
            and e.get("context") == "rest"
        )

    def build_hr_high_rest(e: Dict[str, Any]) -> Decision:
        return Decision(
            decision="notify",
            reason="HR_HIGH_REST",
            severity="medium",
            source_event_id=e.get("id"),
            meta={"bpm": e.get("bpm"), "context": e.get("context")},
        )

    return [
        Rule(rule_id="HR_HIGH_REST", match=match_hr_high_rest, build=build_hr_high_rest)
    ]
