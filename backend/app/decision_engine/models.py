# Release D: minimal Decision schema + Event/Actions for unified path
from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any, List, Union

DecisionType = Literal["none", "notify", "store_only"]
Severity = Literal["low", "medium", "high"]


class Decision(BaseModel):
    decision: DecisionType = "none"
    reason: str = "no_rule_matched"
    severity: Severity = "low"
    alert_code: str = ""
    priority: int = 0
    rule_id: str = ""
    source_event_id: Optional[int] = None
    meta: Dict[str, Any] = {}


# Canonical event DTO for Decision Engine (device_ingestion -> evaluate_event)
class EventDto(BaseModel):
    user_id: int
    device_id: Optional[str] = None
    event_type: str
    payload: Dict[str, Any]
    recorded_at: Optional[datetime] = None
    received_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the server received the event; defaults to now if omitted (backward-compatible for tests).",
    )
    event_id: Optional[int] = None


# Actions returned by evaluate_event; executor persists them (e.g. via notification_engine)
# D1: supports ready title/body + rule_id for dedupe_key building; legacy alert_code/priority kept for backward compat
@dataclass(frozen=True)
class CreateHealthAlertAction:
    user_id: int
    channel: str = "health_alert"
    title: str = ""
    body: str = ""
    severity: Literal["low", "medium", "high"] = "high"
    rule_id: str = ""
    meta: Optional[Dict[str, Any]] = None
    # Legacy fields (used by notification_engine.create_health_alert when title/body empty)
    alert_code: str = ""
    alert_reason: Optional[str] = None
    priority: Literal["low", "normal", "high", "critical"] = "high"


# Union of all action types for type hints
Action = Union[CreateHealthAlertAction]
