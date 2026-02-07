# Release D: internal tests for rule evaluation (no DB, no external services)
from app.decision_engine.models import EventDto, CreateHealthAlertAction
from app.decision_engine.service import decide_from_event, evaluate_event


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


# evaluate_event: unified path (vitals thresholds from rule_alerts)
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
    assert a.alert_code == "high_heart_rate"
    assert a.priority == "critical"
    assert "high" in (a.alert_reason or "").lower() or "very high" in (a.alert_reason or "").lower()


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
