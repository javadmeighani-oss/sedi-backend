"""Bounded unified interaction context builder — labeled layers, no merge."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.core.conversation.memory import ConversationMemory

CONTEXT_BUDGETS = {
    "current_user_message": 4000,
    "recent_turns": 6000,
    "same_day_summary": 1500,
    "long_term_memory": 2000,
    "user_profile": 1200,
    "lifestyle_context": 1500,
    "health_care_context": 2000,
    "device_vital_context": 1500,
    "notification_context": 2000,
    "curated_knowledge": 2500,
}

TRUNCATION_PRIORITY = [
    "safety",
    "current_user_message",
    "recent_turns",
    "health_care_context",
    "notification_context",
    "user_profile",
    "long_term_memory",
    "curated_knowledge",
    "same_day_summary",
    "lifestyle_context",
    "device_vital_context",
]


@dataclass
class InteractionContextPack:
    layers: Dict[str, str] = field(default_factory=dict)
    truncated_layers: List[str] = field(default_factory=list)
    total_chars: int = 0


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[: max_chars - 3] + "...", True


def build_unified_context(
    db: Session,
    user_id: int,
    *,
    current_message: str,
    language: str = "fa",
    notification_context: Optional[Dict[str, Any]] = None,
    health_context: Optional[Dict[str, Any]] = None,
    device_context: Optional[Dict[str, Any]] = None,
    curated_knowledge: Optional[List[str]] = None,
    profile_snippet: Optional[str] = None,
    long_term_facts: Optional[List[str]] = None,
    max_recent_turns: int = 10,
) -> InteractionContextPack:
    pack = InteractionContextPack()
    memory = ConversationMemory(db)

    msg, trunc = _truncate(current_message, CONTEXT_BUDGETS["current_user_message"])
    pack.layers["current_user_message"] = msg
    if trunc:
        pack.truncated_layers.append("current_user_message")

    turns = memory.get_recent_messages(user_id, limit=max_recent_turns)
    turn_lines = []
    for t in reversed(turns):
        if getattr(t, "user_message", None):
            turn_lines.append(f"user: {str(t.user_message)[:500]}")
        if getattr(t, "sedi_response", None):
            turn_lines.append(f"assistant: {str(t.sedi_response)[:500]}")
    turns_text = "\n".join(turn_lines)
    turns_text, trunc = _truncate(turns_text, CONTEXT_BUDGETS["recent_turns"])
    pack.layers["recent_turns"] = turns_text
    if trunc:
        pack.truncated_layers.append("recent_turns")

    try:
        from backend.app.services.i7.hierarchy import get_canonical_daily

        ups = get_canonical_daily(db, user_id)
        summary = ups.narrative_summary if ups and ups.narrative_summary else ""
    except Exception:
        summary = ""
    if summary:
        summary, trunc = _truncate(summary, CONTEXT_BUDGETS["same_day_summary"])
        pack.layers["same_day_summary"] = summary
        if trunc:
            pack.truncated_layers.append("same_day_summary")

    if profile_snippet:
        prof, trunc = _truncate(profile_snippet, CONTEXT_BUDGETS["user_profile"])
        pack.layers["user_profile"] = prof
        if trunc:
            pack.truncated_layers.append("user_profile")

    if long_term_facts:
        lt = "\n".join(f"- {f}" for f in long_term_facts[:20])
        lt, trunc = _truncate(lt, CONTEXT_BUDGETS["long_term_memory"])
        pack.layers["long_term_memory"] = lt
        if trunc:
            pack.truncated_layers.append("long_term_memory")

    if health_context:
        hc = str(health_context)[:CONTEXT_BUDGETS["health_care_context"]]
        pack.layers["health_care_context"] = hc

    if device_context:
        dc = str(device_context)[:CONTEXT_BUDGETS["device_vital_context"]]
        pack.layers["device_vital_context"] = dc

    if notification_context:
        nc = str(notification_context)[:CONTEXT_BUDGETS["notification_context"]]
        pack.layers["notification_context"] = nc

    if curated_knowledge:
        kb = "\n".join(curated_knowledge[:8])
        kb, trunc = _truncate(kb, CONTEXT_BUDGETS["curated_knowledge"])
        pack.layers["curated_knowledge"] = kb
        if trunc:
            pack.truncated_layers.append("curated_knowledge")

    pack.layers["user_language"] = language
    pack.total_chars = sum(len(v) for v in pack.layers.values())
    return pack


def format_labeled_blocks(pack: InteractionContextPack) -> str:
    lines = []
    for layer_name in TRUNCATION_PRIORITY:
        if layer_name == "safety":
            continue
        content = pack.layers.get(layer_name)
        if content:
            label = layer_name.upper().replace("_", " ")
            lines.append(f"[{label}]\n{content}")
    return "\n\n".join(lines)
