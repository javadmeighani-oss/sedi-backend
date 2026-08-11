"""I5-KNOW-04 — official scientific connectors + change intelligence.

Does NOT activate Production crawler/RAG/scheduler.
Does NOT perform mass world ingestion.
"""

from backend.app.services.i5.know04.change_intelligence import (
    apply_artifact_change,
    reassess_claim_runtime_support,
    record_change_event,
)
from backend.app.services.i5.know04.contract import ConnectorCapabilities, ConnectorRecord, ScientificConnector
from backend.app.services.i5.know04.observability import finish_run, start_run
from backend.app.services.i5.know04.rights_gate import evaluate_connector_rights, require_processing_allowed
from backend.app.services.i5.know04.seed_profiles import seed_know04_connector_profiles

__all__ = [
    "ConnectorCapabilities",
    "ConnectorRecord",
    "ScientificConnector",
    "apply_artifact_change",
    "evaluate_connector_rights",
    "finish_run",
    "reassess_claim_runtime_support",
    "record_change_event",
    "require_processing_allowed",
    "seed_know04_connector_profiles",
    "start_run",
]
