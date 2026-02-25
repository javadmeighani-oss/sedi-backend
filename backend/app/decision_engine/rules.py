# Release D: deterministic rule evaluation
from dataclasses import dataclass
from typing import Any, Dict, List, Callable, Optional

from .models import Decision, EventDto, CreateHealthAlertAction, Action


@dataclass(frozen=True)
class Rule:
    rule_id: str
    match: Callable[[Dict[str, Any]], bool]
    build: Callable[[Dict[str, Any]], Decision]


CANONICAL_ALERT_CODE_BY_REASON: Dict[str, str] = {
    "HR_HIGH_REST": "heart_rate_high",
    "HR_HIGH": "heart_rate_high",
    "HR_LOW": "heart_rate_low",
    "BP_HIGH": "blood_pressure_high",
    "GLUCOSE_HIGH": "glucose_high",
    "GLUCOSE_LOW": "glucose_low",
    "TEMP_HIGH": "temperature_high",
    # Backward aliases
    "high_heart_rate": "heart_rate_high",
    "low_heart_rate": "heart_rate_low",
    "high_blood_pressure": "blood_pressure_high",
    "high_glucose": "glucose_high",
    "low_glucose": "glucose_low",
    "high_temperature": "temperature_high",
}


def canonical_alert_code_from_reason(reason: str) -> str:
    if not reason:
        return ""
    return CANONICAL_ALERT_CODE_BY_REASON.get(reason, reason)


def ensure_canonical_decision(decision: Decision, fallback_rule_id: str = "") -> Decision:
    rule_id = decision.rule_id or fallback_rule_id or (decision.reason if decision.reason != "no_rule_matched" else "")
    alert_code = decision.alert_code or canonical_alert_code_from_reason(rule_id or decision.reason)
    priority = decision.priority if isinstance(decision.priority, int) else 0
    # Health-alert decisions in V1 should be high severity.
    severity = "high" if decision.decision == "notify" and alert_code else decision.severity
    return Decision(
        decision=decision.decision,
        reason=rule_id or decision.reason,
        severity=severity,  # type: ignore[arg-type]
        alert_code=alert_code,
        priority=priority if priority else (1 if decision.decision == "notify" and alert_code else 0),
        rule_id=rule_id,
        source_event_id=decision.source_event_id,
        meta=decision.meta,
    )


def evaluate_rules(event: Dict[str, Any], rules: List[Rule]) -> Decision:
    for r in rules:
        if r.match(event):
            return ensure_canonical_decision(r.build(event), fallback_rule_id=r.rule_id)
    return Decision()


def default_rules() -> List[Rule]:
    def match_hr_high_rest(e: Dict[str, Any]) -> bool:
        return (
            e.get("event_type") == "heart_rate"
            and isinstance(e.get("bpm"), (int, float))
            and e.get("bpm") >= 120
            and e.get("context") == "rest"
        )

    def build_hr_high_rest(e: Dict[str, Any]) -> Decision:
        return Decision(
            decision="notify",
            reason="HR_HIGH_REST",
            severity="high",
            alert_code="heart_rate_high",
            priority=1,
            rule_id="HR_HIGH_REST",
            source_event_id=e.get("id"),
            meta={"bpm": e.get("bpm"), "context": e.get("context")},
        )

    return [
        Rule(rule_id="HR_HIGH_REST", match=match_hr_high_rest, build=build_hr_high_rest)
    ]


# ---------- D1: minimal HIGH-severity rules (device_events -> notifications) ----------
# Thresholds (single source of truth):
# - heart_rate >=120 with context=rest (HR_HIGH_REST), otherwise >=130
# - heart_rate <= 50
# - blood_pressure sys>=160 or dia>=110
# - glucose >= 240 or <= 60
# - temperature >= 39.0
# Titles/bodies: plain Persian (hardcoded), short and safe.

@dataclass(frozen=True)
class CanonicalRuleMatch:
    rule_id: str
    alert_code: str
    severity: str
    priority: int
    meta: Dict[str, Any]


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_event_dto(event_raw: Dict[str, Any]) -> EventDto:
    payload = event_raw.get("payload") if isinstance(event_raw.get("payload"), dict) else {}
    merged = dict(payload)
    for key in ("bpm", "context", "sys", "dia", "systolic", "diastolic", "glucose_mg_dl", "glucose", "temperature_c", "temperature"):
        if key in event_raw and key not in merged:
            merged[key] = event_raw[key]
    return EventDto(
        user_id=int(event_raw.get("user_id") or 0),
        device_id=event_raw.get("device_id"),
        event_type=str(event_raw.get("event_type") or ""),
        payload=merged,
        event_id=event_raw.get("id") or event_raw.get("event_id"),
    )


def evaluate_v1_rule_matches(event: EventDto) -> List[CanonicalRuleMatch]:
    matches: List[CanonicalRuleMatch] = []
    payload = event.payload or {}
    event_type = event.event_type

    if event_type == "heart_rate":
        bpm = _as_float(payload.get("bpm"))
        if bpm is None:
            return matches
        context = str(payload.get("context") or "").strip().lower()
        if context == "rest" and bpm >= 120:
            matches.append(
                CanonicalRuleMatch(
                    rule_id="HR_HIGH_REST",
                    alert_code="heart_rate_high",
                    severity="high",
                    priority=1,
                    meta={"bpm": bpm, "context": "rest"},
                )
            )
        elif bpm >= 130:
            matches.append(
                CanonicalRuleMatch(
                    rule_id="HR_HIGH",
                    alert_code="heart_rate_high",
                    severity="high",
                    priority=1,
                    meta={"bpm": bpm},
                )
            )
        elif bpm <= 50:
            matches.append(
                CanonicalRuleMatch(
                    rule_id="HR_LOW",
                    alert_code="heart_rate_low",
                    severity="high",
                    priority=1,
                    meta={"bpm": bpm},
                )
            )

    elif event_type == "blood_pressure":
        sys_v = _as_float(payload.get("sys", payload.get("systolic")))
        dia_v = _as_float(payload.get("dia", payload.get("diastolic")))
        if sys_v is None or dia_v is None:
            return matches
        if sys_v >= 160 or dia_v >= 110:
            matches.append(
                CanonicalRuleMatch(
                    rule_id="BP_HIGH",
                    alert_code="blood_pressure_high",
                    severity="high",
                    priority=1,
                    meta={"sys": sys_v, "dia": dia_v},
                )
            )

    elif event_type == "glucose":
        mg_dl = _as_float(payload.get("glucose_mg_dl", payload.get("glucose")))
        if mg_dl is None:
            return matches
        if mg_dl >= 240:
            matches.append(
                CanonicalRuleMatch(
                    rule_id="GLUCOSE_HIGH",
                    alert_code="glucose_high",
                    severity="high",
                    priority=1,
                    meta={"mg_dl": mg_dl},
                )
            )
        elif mg_dl <= 60:
            matches.append(
                CanonicalRuleMatch(
                    rule_id="GLUCOSE_LOW",
                    alert_code="glucose_low",
                    severity="high",
                    priority=1,
                    meta={"mg_dl": mg_dl},
                )
            )

    elif event_type == "temperature":
        c = _as_float(payload.get("temperature_c", payload.get("temperature")))
        if c is None:
            return matches
        if c >= 39.0:
            matches.append(
                CanonicalRuleMatch(
                    rule_id="TEMP_HIGH",
                    alert_code="temperature_high",
                    severity="high",
                    priority=1,
                    meta={"temperature_c": c},
                )
            )

    return matches


def decide_from_event_v1(event_raw: Dict[str, Any]) -> Decision:
    event = _extract_event_dto(event_raw)
    matches = evaluate_v1_rule_matches(event)
    if not matches:
        return Decision()
    m = matches[0]
    return ensure_canonical_decision(
        Decision(
            decision="notify",
            reason=m.rule_id,
            severity="high",
            alert_code=m.alert_code,
            priority=m.priority,
            rule_id=m.rule_id,
            source_event_id=event.event_id,
            meta=m.meta,
        ),
        fallback_rule_id=m.rule_id,
    )


def evaluate_high_rules(event: EventDto) -> List[Action]:
    out: List[Action] = []
    for m in evaluate_v1_rule_matches(event):
        if m.alert_code == "heart_rate_high":
            out.append(
                CreateHealthAlertAction(
                    user_id=event.user_id,
                    channel="health_alert",
                    title="هشدار ضربان قلب",
                    body="ضربان قلبت بالاست. اگر حالت بد است یا علائم داری، با پزشک تماس بگیر.",
                    severity="high",
                    rule_id=m.alert_code,
                    alert_code=m.alert_code,
                    meta=m.meta,
                    priority="high",
                )
            )
        elif m.alert_code == "heart_rate_low":
            out.append(
                CreateHealthAlertAction(
                    user_id=event.user_id,
                    channel="health_alert",
                    title="هشدار ضربان قلب",
                    body="ضربان قلبت پایینه. اگر حالت بد است یا علائم داری، با پزشک تماس بگیر.",
                    severity="high",
                    rule_id=m.alert_code,
                    alert_code=m.alert_code,
                    meta=m.meta,
                    priority="high",
                )
            )
        elif m.alert_code == "blood_pressure_high":
            out.append(
                CreateHealthAlertAction(
                    user_id=event.user_id,
                    channel="health_alert",
                    title="هشدار فشار خون",
                    body="فشارخون بالاست. آرام باش و در صورت تداوم یا علائم، با پزشک تماس بگیر.",
                    severity="high",
                    rule_id=m.alert_code,
                    alert_code=m.alert_code,
                    meta=m.meta,
                    priority="high",
                )
            )
        elif m.alert_code == "glucose_high":
            out.append(
                CreateHealthAlertAction(
                    user_id=event.user_id,
                    channel="health_alert",
                    title="هشدار قند خون",
                    body="قند خون بالاست. در صورت تداوم یا علائم، با پزشک تماس بگیر.",
                    severity="high",
                    rule_id=m.alert_code,
                    alert_code=m.alert_code,
                    meta=m.meta,
                    priority="high",
                )
            )
        elif m.alert_code == "glucose_low":
            out.append(
                CreateHealthAlertAction(
                    user_id=event.user_id,
                    channel="health_alert",
                    title="هشدار قند خون",
                    body="قند خون پایینه. اگر حالت بد است یا علائم داری، با پزشک تماس بگیر.",
                    severity="high",
                    rule_id=m.alert_code,
                    alert_code=m.alert_code,
                    meta=m.meta,
                    priority="high",
                )
            )
        elif m.alert_code == "temperature_high":
            out.append(
                CreateHealthAlertAction(
                    user_id=event.user_id,
                    channel="health_alert",
                    title="هشدار تب",
                    body="دمای بدنت بالاست. استراحت کن، آب بخور و در صورت تداوم با پزشک تماس بگیر.",
                    severity="high",
                    rule_id=m.alert_code,
                    alert_code=m.alert_code,
                    meta=m.meta,
                    priority="high",
                )
            )
    return out
