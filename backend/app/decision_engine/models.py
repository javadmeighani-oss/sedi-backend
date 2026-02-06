# Release D: minimal Decision schema
from pydantic import BaseModel
from typing import Literal, Optional, Dict, Any

DecisionType = Literal["none", "notify", "store_only"]
Severity = Literal["low", "medium", "high"]


class Decision(BaseModel):
    decision: DecisionType = "none"
    reason: str = "no_rule_matched"
    severity: Severity = "low"
    source_event_id: Optional[int] = None
    meta: Dict[str, Any] = {}
