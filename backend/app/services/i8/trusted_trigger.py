"""TrustedTrigger_V1 contract for in-process I8 proactive producers (PD-I8-04B)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping

from backend.app.services.i8.schedule_rules import is_allowed_schedule_rule

TRUSTED_PRODUCER_I8_SCHEDULE_SCAN_V1 = "i8_schedule_scan_v1"

TRUSTED_SCHEDULE_PRODUCERS = frozenset(
    {
        TRUSTED_PRODUCER_I8_SCHEDULE_SCAN_V1,
    }
)

ALLOWED_METADATA_KEYS = frozenset(
    {
        "timezone_snapshot",
        "scan_batch_id",
        "job_id",
    }
)

_MAX_METADATA_VALUE_LEN = 128


class TrustedTriggerValidationError(ValueError):
    """Rejected untrusted or incomplete trigger contract."""


@dataclass(frozen=True)
class TrustedTriggerV1:
    """Minimum SCHEDULE-capable trusted trigger (Gate2/I9 families deferred)."""

    producer_id: str
    user_id: int
    trigger_family: str
    schedule_rule_id: str
    user_local_date: date
    producer_attempt_id: str
    bounded_metadata: Mapping[str, str] = field(default_factory=dict)

    def canonical_identity_parts(self) -> tuple[str, int, str, str]:
        return (
            "schedule",
            int(self.user_id),
            self.schedule_rule_id.strip(),
            self.user_local_date.isoformat(),
        )


def validate_trusted_schedule_trigger(trigger: TrustedTriggerV1) -> TrustedTriggerV1:
    producer = (trigger.producer_id or "").strip()
    if producer not in TRUSTED_SCHEDULE_PRODUCERS:
        raise TrustedTriggerValidationError("UNTRUSTED_PRODUCER")

    if int(trigger.user_id) <= 0:
        raise TrustedTriggerValidationError("INVALID_USER_ID")

    family = (trigger.trigger_family or "").strip().casefold()
    if family != "schedule":
        raise TrustedTriggerValidationError("UNSUPPORTED_TRIGGER_FAMILY_FOR_ADAPTER")

    rule = (trigger.schedule_rule_id or "").strip()
    if not is_allowed_schedule_rule(rule):
        raise TrustedTriggerValidationError("SCHEDULE_RULE_NOT_ALLOWLISTED")

    if trigger.user_local_date is None:
        raise TrustedTriggerValidationError("USER_LOCAL_DATE_REQUIRED")

    attempt = (trigger.producer_attempt_id or "").strip()
    if not attempt or len(attempt) > 128:
        raise TrustedTriggerValidationError("INVALID_PRODUCER_ATTEMPT_ID")

    cleaned: dict[str, str] = {}
    for key, value in dict(trigger.bounded_metadata or {}).items():
        if key not in ALLOWED_METADATA_KEYS:
            raise TrustedTriggerValidationError("METADATA_KEY_NOT_ALLOWED")
        text = str(value)
        if len(text) > _MAX_METADATA_VALUE_LEN:
            raise TrustedTriggerValidationError("METADATA_VALUE_TOO_LONG")
        cleaned[key] = text

    return TrustedTriggerV1(
        producer_id=producer,
        user_id=int(trigger.user_id),
        trigger_family="schedule",
        schedule_rule_id=rule,
        user_local_date=trigger.user_local_date,
        producer_attempt_id=attempt,
        bounded_metadata=cleaned,
    )


def trusted_trigger_to_log_fields(trigger: TrustedTriggerV1) -> dict[str, Any]:
    """Safe observability fields (no raw health / notification content)."""
    return {
        "producer_id": trigger.producer_id,
        "user_id": trigger.user_id,
        "trigger_family": trigger.trigger_family,
        "schedule_rule_id": trigger.schedule_rule_id,
        "user_local_date": trigger.user_local_date.isoformat(),
        "producer_attempt_id": trigger.producer_attempt_id,
        "metadata_keys": sorted(trigger.bounded_metadata.keys()),
    }
