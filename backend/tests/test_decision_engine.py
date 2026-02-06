# Release D: internal tests for rule evaluation (no DB, no external services)
from app.decision_engine.service import decide_from_event


def test_no_match_returns_none():
    d = decide_from_event({"id": 1, "event_type": "heart_rate", "bpm": 80, "context": "rest"})
    assert d.decision in ("none", "store_only")
    assert d.reason in ("no_rule_matched",)


def test_hr_high_rest_triggers_notify():
    d = decide_from_event({"id": 2, "event_type": "heart_rate", "bpm": 130, "context": "rest"})
    assert d.decision == "notify"
    assert d.reason == "HR_HIGH_REST"
    assert d.severity == "medium"
    assert d.source_event_id == 2
