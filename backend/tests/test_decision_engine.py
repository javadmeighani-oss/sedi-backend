# Release D: internal tests for rule evaluation (no DB, no external services)
from backend.app.decision_engine.models import EventDto, CreateHealthAlertAction
from backend.app.decision_engine.service import decide_from_event, evaluate_event


def test_no_match_returns_none():
    d = decide_from_event({"id": 1, "event_type": "heart_rate", "bpm": 80, "context": "rest"})
    assert d.decision in ("none", "store_only")
    assert d.reason in ("no_rule_matched",)


def test_hr_high_rest_triggers_notify():
    d = decide_from_event({"id": 2, "event_type": "heart_rate", "bpm": 130, "context": "rest"})
    assert d.decision == "notify"
    assert d.reason == "HR_HIGH_REST"
    assert d.severity == "high"
    assert d.alert_code == "heart_rate_high"
    assert d.priority == 1
    assert d.rule_id == "HR_HIGH_REST"
    assert d.source_event_id == 2


# evaluate_event: unified path (D1 evaluate_high_rules; alert_code set from rule_id for dedupe/analytics)
def test_evaluate_event_bpm_180_returns_high_heart_rate_action():
    event = EventDto(
        user_id=1,
        device_id="Sedi001",
        event_type="heart_rate",
        payload={"bpm": 180},
        event_id=42,
    )
    actions = evaluate_event(event)
    assert len(actions) == 1
    a = actions[0]
    assert isinstance(a, CreateHealthAlertAction)
    assert a.user_id == 1
    # V1: evaluate_high_rules sets alert_code from rule_id (heart_rate_high)
    assert a.alert_code == "heart_rate_high"
    assert a.priority == "high"


def test_evaluate_event_normal_bpm_returns_no_action():
    event = EventDto(
        user_id=1,
        event_type="heart_rate",
        payload={"bpm": 75},
    )
    actions = evaluate_event(event)
    assert len(actions) == 0


def test_evaluate_event_unknown_type_returns_no_action():
    event = EventDto(
        user_id=1,
        event_type="unknown_type",
        payload={"x": 1},
    )
    actions = evaluate_event(event)
    assert len(actions) == 0
