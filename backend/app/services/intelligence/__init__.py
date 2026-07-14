"""Section 15 connected intelligence package (I1 foundation)."""

from backend.app.services.intelligence.contracts import (
    CONTRACT_VERSION,
    OrchestrationError,
    OrchestrationResult,
)
from backend.app.services.intelligence.feature_flags import (
    intelligence_orchestrator_v1_enabled,
)
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator

__all__ = [
    "CONTRACT_VERSION",
    "IntelligenceOrchestrator",
    "OrchestrationError",
    "OrchestrationResult",
    "intelligence_orchestrator_v1_enabled",
]
