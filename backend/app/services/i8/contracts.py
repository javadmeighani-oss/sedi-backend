"""I8 unified reactive core contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class I8ActionSuggestion:
    label: str
    detail: str


@dataclass
class I8OperationalActionResult:
    status: str
    domain: str
    action_mode: str = "reactive"
    summary: str = ""
    suggestions: list[I8ActionSuggestion] = field(default_factory=list)
    rationale: str = ""
    safety_state: str = "SAFE"
    clarification_required: bool = False
    missing_information: list[str] = field(default_factory=list)
    knowledge_refs: list[dict[str, Any]] = field(default_factory=list)
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    plan_id: Optional[int] = None
    action_id: Optional[int] = None
    persisted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "domain": self.domain,
            "action_mode": self.action_mode,
            "summary": self.summary,
            "suggestions": [{"label": s.label, "detail": s.detail} for s in self.suggestions],
            "rationale": self.rationale,
            "safety_state": self.safety_state,
            "clarification_required": self.clarification_required,
            "missing_information": list(self.missing_information),
            "knowledge_refs": list(self.knowledge_refs),
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "plan_id": self.plan_id,
            "action_id": self.action_id,
            "persisted": self.persisted,
        }
