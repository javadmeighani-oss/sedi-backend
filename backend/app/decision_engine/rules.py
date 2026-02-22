# Release D: deterministic rule evaluation
from dataclasses import dataclass
from typing import Any, Dict, List, Callable
from .models import Decision, EventDto, CreateHealthAlertAction, Action


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


# ---------- D1: minimal HIGH-severity rules (device_events -> notifications) ----------
# Thresholds: heart_rate >= 130 or <= 50; blood_pressure sys>=160 or dia>=110;
# glucose >= 240 or <= 60; temperature >= 39.0
# Titles/bodies: plain Persian (hardcoded), short and safe.

def evaluate_high_rules(event: EventDto) -> List[Action]:
    """
    Evaluate event against minimal HIGH-severity rules; returns list of CreateHealthAlertAction.
    No persistence; caller builds dedupe_key and persists notifications.
    """
    out: List[Action] = []
    payload = event.payload or {}
    user_id = event.user_id

    if event.event_type == "heart_rate":
        try:
            bpm = float(payload.get("bpm"))
        except (TypeError, ValueError):
            return out
        if bpm >= 130:
            out.append(CreateHealthAlertAction(
                user_id=user_id,
                channel="health_alert",
                title="هشدار ضربان قلب",
                body="ضربان قلبت بالاست. اگر حالت بد است یا علائم داری، با پزشک تماس بگیر.",
                severity="high",
                rule_id="heart_rate_high",
                alert_code="heart_rate_high",
                meta={"bpm": bpm},
                priority="high",
            ))
        elif bpm <= 50:
            out.append(CreateHealthAlertAction(
                user_id=user_id,
                channel="health_alert",
                title="هشدار ضربان قلب",
                body="ضربان قلبت پایینه. اگر حالت بد است یا علائم داری، با پزشک تماس بگیر.",
                severity="high",
                rule_id="heart_rate_low",
                alert_code="heart_rate_low",
                meta={"bpm": bpm},
                priority="high",
            ))

    elif event.event_type == "blood_pressure":
        try:
            sys_v = float(payload.get("sys"))
            dia_v = float(payload.get("dia"))
        except (TypeError, ValueError):
            return out
        if sys_v >= 160 or dia_v >= 110:
            out.append(CreateHealthAlertAction(
                user_id=user_id,
                channel="health_alert",
                title="هشدار فشار خون",
                body="فشارخون بالاست. آرام باش و در صورت تداوم یا علائم، با پزشک تماس بگیر.",
                severity="high",
                rule_id="blood_pressure_high",
                alert_code="blood_pressure_high",
                meta={"sys": sys_v, "dia": dia_v},
                priority="high",
            ))

    elif event.event_type == "glucose":
        try:
            mg_dl = float(payload.get("glucose_mg_dl"))
        except (TypeError, ValueError):
            return out
        if mg_dl >= 240:
            out.append(CreateHealthAlertAction(
                user_id=user_id,
                channel="health_alert",
                title="هشدار قند خون",
                body="قند خون بالاست. در صورت تداوم یا علائم، با پزشک تماس بگیر.",
                severity="high",
                rule_id="glucose_high",
                alert_code="glucose_high",
                meta={"mg_dl": mg_dl},
                priority="high",
            ))
        elif mg_dl <= 60:
            out.append(CreateHealthAlertAction(
                user_id=user_id,
                channel="health_alert",
                title="هشدار قند خون",
                body="قند خون پایینه. اگر حالت بد است یا علائم داری، با پزشک تماس بگیر.",
                severity="high",
                rule_id="glucose_low",
                alert_code="glucose_low",
                meta={"mg_dl": mg_dl},
                priority="high",
            ))

    elif event.event_type == "temperature":
        try:
            c = float(payload.get("temperature_c"))
        except (TypeError, ValueError):
            return out
        if c >= 39.0:
            out.append(CreateHealthAlertAction(
                user_id=user_id,
                channel="health_alert",
                title="هشدار تب",
                body="دمای بدنت بالاست. استراحت کن، آب بخور و در صورت تداوم با پزشک تماس بگیر.",
                severity="high",
                rule_id="temperature_high",
                alert_code="temperature_high",
                meta={"temperature_c": c},
                priority="high",
            ))

    return out
