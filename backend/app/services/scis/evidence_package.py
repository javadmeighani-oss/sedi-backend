"""SediEvidencePackage — thin semantic wrapper over existing SCIS evidence contracts.

EVIDENCE_PACKAGE != ANSWER | ACTION | DIAGNOSIS | DEVICE_STATUS | NOTIFICATION_SEMANTIC
Reuses ScisRetrievalResponse / ScisEvidenceItem. No parallel retrieval architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.services.scis.contracts import ScisEvidenceItem, ScisRetrievalResponse
from backend.app.services.scis.sedi_retrieval_context import SediRetrievalContext


class EvidenceSemanticEscalationError(ValueError):
    """Raised when evidence is illegally promoted to action/diagnosis/status/notify."""


@dataclass
class SediEvidencePackage:
    """Governed retrieval evidence package for downstream Sedi authorities."""

    response: ScisRetrievalResponse
    context_scope: Dict[str, Any] = field(default_factory=dict)
    knowledge_authority_label: str = "GOVERNED"
    routes: tuple = ()

    # Explicit semantic locks (never flipped by ranking).
    is_answer: bool = False
    is_action: bool = False
    is_diagnosis: bool = False
    is_device_status: bool = False
    is_notification_semantic: bool = False

    @classmethod
    def from_scis_response(
        cls,
        response: ScisRetrievalResponse,
        *,
        ctx: Optional[SediRetrievalContext] = None,
        routes: tuple = (),
        knowledge_authority_label: str = "GOVERNED",
    ) -> "SediEvidencePackage":
        scope: Dict[str, Any] = {}
        if ctx is not None:
            scope = {
                "requester_account_id": ctx.requester_account_id,
                "target_health_subject_id": ctx.target_health_subject_id,
                "subject_mode": ctx.subject_mode.value,
                "purpose": ctx.purpose,
                "language": ctx.language,
                "domain": ctx.domain,
                "trace_id": ctx.trace_id,
                "allowed_knowledge_classes": list(ctx.allowed_knowledge_classes),
                "authorization_scope": list(ctx.authorization_scope),
            }
        return cls(
            response=response,
            context_scope=scope,
            knowledge_authority_label=knowledge_authority_label,
            routes=routes,
        )

    @property
    def evidence(self) -> List[ScisEvidenceItem]:
        return list(self.response.evidence)

    @property
    def trace_id(self) -> Optional[str]:
        return self.response.request_trace_id or self.context_scope.get("trace_id")

    @property
    def fallback_state(self) -> Any:
        return self.response.fallback_state

    def provenance_summary(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for item in self.evidence:
            prov = item.provenance
            out.append(
                {
                    "chunk_id": item.chunk_id,
                    "knowledge_unit_id": item.knowledge_unit_id,
                    "immutable_version_id": item.immutable_version_id,
                    "label": item.label,
                    "language": item.language,
                    "retrieval_branch": item.retrieval_branch,
                    "lexical_rank": item.lexical_rank,
                    "vector_rank": item.vector_rank,
                    "fusion_rank": item.fusion_rank,
                    "runtime_eligibility": item.runtime_eligibility,
                    "embedding_model": item.embedding_model,
                    "source_profile_id": getattr(prov, "source_profile_id", None),
                    "raw_evidence_id": getattr(prov, "raw_evidence_id", None),
                }
            )
        return out

    def as_i8_evidence_input(self) -> Dict[str, Any]:
        """Evidence-only payload for I8. Does not create action/plan/DONE."""
        return {
            "kind": "SEDI_EVIDENCE_PACKAGE",
            "authority_label": self.knowledge_authority_label,
            "trace_id": self.trace_id,
            "evidence_count": len(self.evidence),
            "provenance": self.provenance_summary(),
            "context_scope": dict(self.context_scope),
            "fallback_state": getattr(self.fallback_state, "value", str(self.fallback_state)),
            "embedding_model": self.response.embedding_model,
            "mode": self.response.mode,
            "mints_i8_action": False,
            "mints_i9_status": False,
            "mints_i10_semantic": False,
            "is_diagnosis": False,
        }

    def refuse_mint_i8_action(self) -> None:
        raise EvidenceSemanticEscalationError("RAG_EVIDENCE_CANNOT_MINT_I8_ACTION")

    def refuse_mint_i9_status(self) -> None:
        raise EvidenceSemanticEscalationError("SMART_RAG_CANNOT_MINT_I9_STATUS")

    def refuse_mint_i10_semantic(self) -> None:
        raise EvidenceSemanticEscalationError("SMART_RAG_CANNOT_MINT_I10_SEMANTIC")

    def refuse_diagnosis(self) -> None:
        raise EvidenceSemanticEscalationError("SMART_RAG_CANNOT_DIAGNOSE")

    def refuse_care_action_from_status(self) -> None:
        raise EvidenceSemanticEscalationError(
            "I9_STATUS_CONTEXT_CANNOT_MINT_ACTION_SAFETY_OR_DIAGNOSIS"
        )

    def assert_no_semantic_escalation(self) -> None:
        if any(
            (
                self.is_answer,
                self.is_action,
                self.is_diagnosis,
                self.is_device_status,
                self.is_notification_semantic,
            )
        ):
            raise EvidenceSemanticEscalationError("NO_EVIDENCE_SEMANTIC_ESCALATION")
