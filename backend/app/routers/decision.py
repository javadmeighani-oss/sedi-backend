# Release D: internal endpoint for decision testing
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict

from backend.app.decision_engine.service import decide_from_event

router = APIRouter(prefix="/decision", tags=["decision"])


class DecisionTestRequest(BaseModel):
    event: Dict[str, Any]


def _normalize_event_for_rules(event: Dict[str, Any]) -> Dict[str, Any]:
    """Lift payload.bpm and payload.context to top-level so default_rules() can match (backward compatible)."""
    out = dict(event)
    payload = out.get("payload")
    if isinstance(payload, dict):
        if "bpm" not in out and "bpm" in payload:
            out["bpm"] = payload["bpm"]
        if "context" not in out and "context" in payload:
            out["context"] = payload["context"]
    return out


@router.post("/evaluate")
def evaluate_decision(req: DecisionTestRequest):
    event = _normalize_event_for_rules(req.event)
    d = decide_from_event(event)
    return {"ok": True, "decision": d.model_dump()}
