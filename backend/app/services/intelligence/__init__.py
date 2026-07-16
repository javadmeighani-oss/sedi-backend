"""Section 15 connected intelligence package (I1–I4)."""

from backend.app.services.intelligence.contracts import (
    CONTRACT_VERSION,
    OrchestrationError,
    OrchestrationResult,
)
from backend.app.services.intelligence.feature_flags import (
    intelligence_orchestrator_v1_enabled,
)
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.app.services.intelligence.assembler import AuthorizedContextAssembler
from backend.app.services.intelligence.context_types import ContextBudgets

__all__ = [
    "CONTRACT_VERSION",
    "AuthorizedContextAssembler",
    "ContextBudgets",
    "IntelligenceOrchestrator",
    "OrchestrationError",
    "OrchestrationResult",
    "intelligence_orchestrator_v1_enabled",
]
