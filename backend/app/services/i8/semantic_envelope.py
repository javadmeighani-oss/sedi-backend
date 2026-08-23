"""Bounded sanitized I8 semantic action envelope (PD-I8-04A DCR-B).

I8 owns decision meaning, not Smart Notification interruption/copy/delivery.
"""

from __future__ import annotations

import json
from typing import Any

from backend.app.services.i8.constants import (
    PRESENTATION_JSON_MAX_BYTES,
    SEMANTIC_ENVELOPE_FORBIDDEN_KEYS,
)


ALLOWED_ENVELOPE_KEYS = frozenset(
    {
        "schema",
        "action_id",
        "plan_id",
        "user_id",
        "evaluation_identity_key",
        "domain",
        "semantic_intent_type",
        "action_type",
        "sanitized_presentation_meaning",
        "advisory_importance",
        "safety_state",
        "applicability_state",
        "valid_from",
        "valid_until",
        "lifecycle_status",
        "knowledge_refs",
        "grounding",
    }
)


class SemanticEnvelopeError(ValueError):
    pass


def build_semantic_action_envelope(
    *,
    user_id: int,
    domain: str,
    action_type: str,
    sanitized_presentation_meaning: str,
    safety_state: str,
    knowledge_refs: list[dict[str, Any]],
    valid_from: str | None = None,
    valid_until: str | None = None,
    lifecycle_status: str | None = None,
    plan_id: int | None = None,
    action_id: int | None = None,
    evaluation_identity_key: str | None = None,
    advisory_importance: str | None = None,
    applicability_state: str | None = None,
) -> dict[str, Any]:
    """Build the minimum I8-owned sanitized semantic envelope."""
    envelope: dict[str, Any] = {
        "schema": "i8.semantic_action.v1",
        "user_id": user_id,
        "domain": domain,
        "semantic_intent_type": action_type,
        "action_type": action_type,
        "sanitized_presentation_meaning": sanitized_presentation_meaning,
        "safety_state": safety_state,
        "grounding": "governed_i5_reference",
        "knowledge_refs": list(knowledge_refs),
    }
    if plan_id is not None:
        envelope["plan_id"] = plan_id
    if action_id is not None:
        envelope["action_id"] = action_id
    if evaluation_identity_key is not None:
        envelope["evaluation_identity_key"] = evaluation_identity_key
    if advisory_importance is not None:
        envelope["advisory_importance"] = advisory_importance
    if applicability_state is not None:
        envelope["applicability_state"] = applicability_state
    if valid_from is not None:
        envelope["valid_from"] = valid_from
    if valid_until is not None:
        envelope["valid_until"] = valid_until
    if lifecycle_status is not None:
        envelope["lifecycle_status"] = lifecycle_status
    validate_semantic_envelope(envelope)
    return envelope


def validate_semantic_envelope(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise SemanticEnvelopeError("SEMANTIC_ENVELOPE_NOT_OBJECT")
    keys = set(payload.keys())
    forbidden = keys & SEMANTIC_ENVELOPE_FORBIDDEN_KEYS
    if forbidden:
        raise SemanticEnvelopeError(f"SEMANTIC_ENVELOPE_FORBIDDEN_KEYS:{sorted(forbidden)}")
    unknown = keys - ALLOWED_ENVELOPE_KEYS
    if unknown:
        raise SemanticEnvelopeError(f"SEMANTIC_ENVELOPE_UNKNOWN_KEYS:{sorted(unknown)}")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > PRESENTATION_JSON_MAX_BYTES:
        raise SemanticEnvelopeError("SEMANTIC_ENVELOPE_TOO_LARGE")
    meaning = payload.get("sanitized_presentation_meaning")
    if meaning is not None and not isinstance(meaning, str):
        raise SemanticEnvelopeError("SEMANTIC_ENVELOPE_MEANING_TYPE")
    # Fail closed on raw I5 statement markers inside meaning.
    if isinstance(meaning, str):
        lowered = meaning.casefold()
        for banned in ("normalized_statement", "raw i5", "diagnosis:", "prescription:"):
            if banned in lowered:
                raise SemanticEnvelopeError("SEMANTIC_ENVELOPE_UNSAFE_MEANING")


def envelope_to_presentation_json(envelope: dict[str, Any]) -> str:
    validate_semantic_envelope(envelope)
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
