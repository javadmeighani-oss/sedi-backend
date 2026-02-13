# backend.app.services.rag_context
"""
Stage 23 Step 5: Controlled RAG V1 (facts-anchored).
RagContextPack, builder, medical risk gate.
"""

from backend.app.services.rag_context.rag_context_pack import RagContextPack
from backend.app.services.rag_context.rag_context_builder import (
    build_rag_context_pack,
    serialize_rag_pack_for_context,
)
from backend.app.services.rag_context.medical_risk_gate_v1 import (
    is_high_risk_medical,
    rag_allowed,
)

__all__ = [
    "RagContextPack",
    "build_rag_context_pack",
    "serialize_rag_pack_for_context",
    "is_high_risk_medical",
    "rag_allowed",
]
