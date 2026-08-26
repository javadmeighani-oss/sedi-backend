"""I5-KNOW-07 — evidence-aware SCIS publication + clinical eval (global governed knowledge).

Reuses SCIS lexical/hybrid substrate, runtime eligibility gate, and KCE invalidation.
No personal-memory plane. No RAG redesign / ANN / dense auto-embedding.
"""

from __future__ import annotations

PACKAGE_ID = "I5-KNOW-07"
AUTHORITY_DOCS = (
    "docs/architecture/i5-final-knowledge-architecture-freeze-01/08_EVIDENCE_AWARE_RAG_SCIS_CONTRACT.md",
    "docs/architecture/i5-final-knowledge-architecture-freeze-01/09_REMAINING_SCOPE_IMPLEMENTATION_WAVES.md",
)

GLOBAL_GOVERNED_KNOWLEDGE_LABEL = "GLOBAL_GOVERNED_KNOWLEDGE"
PURE_VECTOR_ONLY_RAG_ALLOWED = False
KNOW06_APPLICABILITY_RUNTIME_IN_SCOPE = False

SUPPORT_DIRECTIONS = frozenset({"SUPPORTS", "CONTRADICTS", "REFUTES", "INCONCLUSIVE"})

CONFLICT_GROUPING_KEYS = (
    "disease",
    "population",
    "intervention",
    "comparator",
    "outcome",
    "time_horizon",
)

LIVING_KNOWLEDGE_EVENTS = frozenset(
    {
        "NEW_PUBLICATION",
        "GUIDELINE_EDITION",
        "CORRECTION",
        "EXPRESSION_OF_CONCERN",
        "RETRACTION",
        "DRUG_APPROVAL_SAFETY_CHANGE",
        "TRIAL_STATUS_CHANGE",
        "GUIDELINE_SUPERSESSION",
    }
)
