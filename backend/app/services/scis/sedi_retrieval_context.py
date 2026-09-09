"""SediRetrievalContext — bounded authorized retrieval scope (not authority).

SMART_RAG_RETRIEVES_EVIDENCE=YES
SMART_RAG_OWNS_SEDI_TRUTH=NO

Carries scope/refs only. Forbidden: raw I7 memory, raw device/ECG, raw RAG
chunks-as-authority, raw clinical traces-as-authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class SubjectMode(str, Enum):
    SELF = "SELF"
    MANAGED = "MANAGED"


# Forbidden raw payload keys — fail closed if attempted on the boundary.
FORBIDDEN_RAW_CONTEXT_KEYS = frozenset(
    {
        "raw_i7_memory",
        "raw_device_measurements",
        "raw_ecg",
        "raw_rag_chunks",
        "raw_clinical_traces",
        "RAW_I7_MEMORY",
        "RAW_DEVICE_MEASUREMENTS",
        "RAW_ECG",
        "RAW_RAG_CHUNKS_AS_AUTHORITY",
        "RAW_CLINICAL_TRACES_AS_AUTHORITY",
    }
)

DEFAULT_ALLOWED_KNOWLEDGE_CLASSES: Tuple[str, ...] = ("GLOBAL_GOVERNED_KNOWLEDGE",)


@dataclass(frozen=True)
class BoundedContextRef:
    """Opaque cross-I reference — never embeds raw authority payloads."""

    ref_type: str
    authority: str
    ref_id: Optional[int] = None
    label: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref_type": self.ref_type,
            "authority": self.authority,
            "ref_id": self.ref_id,
            "label": self.label,
        }


@dataclass(frozen=True)
class SediRetrievalContext:
    """Authorized retrieval scope for Smart-RAG / SCIS.

    Maps into ScisRetrievalRequest.user_authorization_context (boundary only).
    Does not mint I4/I5/I6/I7/I8/I9/I10 authority.
    """

    requester_account_id: int
    target_health_subject_id: int
    subject_mode: SubjectMode
    relationship: str
    authorization_scope: Tuple[str, ...]
    purpose: str
    language: str
    intent: Optional[str] = None
    domain: Optional[str] = None
    safety_classification: Optional[str] = None
    allowed_knowledge_classes: Tuple[str, ...] = DEFAULT_ALLOWED_KNOWLEDGE_CLASSES
    personal_context_ref: Optional[BoundedContextRef] = None
    governed_action_ref: Optional[BoundedContextRef] = None
    device_status_ref: Optional[BoundedContextRef] = None
    trace_id: Optional[str] = None
    access_role: Optional[str] = None
    linked_user_id: Optional[int] = None

    def __post_init__(self) -> None:
        if self.subject_mode == SubjectMode.MANAGED and self.linked_user_id is not None:
            # Mother MANAGED ALS contract: linked_user_id must remain NULL.
            # Do not invent / substitute a mother account.
            raise ValueError("NO_FAKE_MOTHER_ACCOUNT:MANAGED_LINKED_USER_ID_MUST_BE_NULL")
        if self.subject_mode == SubjectMode.SELF and self.requester_account_id != (
            self.linked_user_id if self.linked_user_id is not None else self.requester_account_id
        ):
            # SELF subject's linked_user_id must equal requester when present.
            if self.linked_user_id is not None and int(self.linked_user_id) != int(
                self.requester_account_id
            ):
                raise ValueError("NO_HEALTHSUBJECT_SUBSTITUTION:SELF_LINKED_USER_MISMATCH")

    def to_authorization_boundary(self) -> Dict[str, Any]:
        """Serialize for ScisRetrievalRequest.user_authorization_context.

        Refs and scope only — never raw cross-I payloads.
        """
        payload: Dict[str, Any] = {
            "requester_account_id": int(self.requester_account_id),
            "target_health_subject_id": int(self.target_health_subject_id),
            "subject_mode": self.subject_mode.value,
            "relationship": self.relationship,
            "authorization_scope": list(self.authorization_scope),
            "purpose": self.purpose,
            "language": self.language,
            "intent": self.intent,
            "domain": self.domain,
            "safety_classification": self.safety_classification,
            "allowed_knowledge_classes": list(self.allowed_knowledge_classes),
            "access_role": self.access_role,
            "linked_user_id": self.linked_user_id,
            "trace_id": self.trace_id,
            "personal_context_ref": (
                self.personal_context_ref.to_dict() if self.personal_context_ref else None
            ),
            "governed_action_ref": (
                self.governed_action_ref.to_dict() if self.governed_action_ref else None
            ),
            "device_status_ref": (
                self.device_status_ref.to_dict() if self.device_status_ref else None
            ),
            "smart_rag_owns_sedi_truth": False,
            "smart_rag_retrieves_evidence": True,
        }
        reject_forbidden_raw_keys(payload)
        return payload


def reject_forbidden_raw_keys(payload: Dict[str, Any]) -> None:
    keys = {str(k) for k in payload.keys()}
    hit = keys & FORBIDDEN_RAW_CONTEXT_KEYS
    if hit:
        raise ValueError(f"RAW_CROSS_I_DATA_FORBIDDEN:{sorted(hit)}")
