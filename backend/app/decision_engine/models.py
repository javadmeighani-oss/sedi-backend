# Release D: minimal Decision schema + Event/Actions for unified path
from dataclasses import dataclass
from datetime import datetime
from pydantic import BaseModel
from typing import Literal, Optional, Dict, Any, List, Union

DecisionType = Literal["none", "notify", "store_only"]
Severity = Literal["low", "medium", "high"]


class Decision(BaseModel):
    decision: DecisionType = "none"
    reason: str = "no_rule_matched"
    severity: Severity = "low"
    source_event_id: Optional[int] = None
    meta: Dict[str, Any] = {}


# Canonical event DTO for Decision Engine (device_ingestion -> evaluate_event)
class EventDto(BaseModel):
    user_id: int
    device_id: Optional[str] = None
    event_type: str
    payload: Dict[str, Any]
    recorded_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    event_id: Optional[int] = None


# Actions returned by evaluate_event; executor persists them (e.g. via notification_engine)
@dataclass(frozen=True)
class CreateHealthAlertAction:
    user_id: int
    alert_code: str
    alert_reason: Optional[str] = None
    priority: Literal["low", "normal", "high", "critical"] = "high"


# Union of all action types for type hints
Action = Union[CreateHealthAlertAction]
