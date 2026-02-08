# Release D: internal endpoint for decision testing
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict

from backend.app.decision_engine.service import decide_from_event

router = APIRouter(prefix="/decision", tags=["decision"])


class DecisionTestRequest(BaseModel):
    event: Dict[str, Any]


@router.post("/evaluate")
def evaluate_decision(req: DecisionTestRequest):
    d = decide_from_event(req.event)
    return {"ok": True, "decision": d.model_dump()}
