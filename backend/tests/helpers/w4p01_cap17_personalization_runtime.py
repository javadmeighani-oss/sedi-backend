"""CAP-OPEN-17 personalization runtime selectors + evidence helpers."""
from __future__ import annotations

_CAP17_TEST = "backend/tests/test_section30_i5_w4_cap17_personalization.py"

CAP17_RUNTIME_SELECTORS: tuple[str, ...] = (
    f"{_CAP17_TEST}::test_P17_T00_malformed_personalization_degrades",
    f"{_CAP17_TEST}::test_P17_T01_baseline_empty_personalization",
    f"{_CAP17_TEST}::test_P17_T02_goal_relevance_ranking",
    f"{_CAP17_TEST}::test_P17_T03_query_relevance_precedes_personalization",
    f"{_CAP17_TEST}::test_P17_T04_safety_precedence_not_eligible",
    f"{_CAP17_TEST}::test_P17_T05_provenance_precedence",
    f"{_CAP17_TEST}::test_P17_T06_superseded_not_selected",
    f"{_CAP17_TEST}::test_P17_T07_language_personalization_soft_boost",
    f"{_CAP17_TEST}::test_P17_T08_restriction_relevance_metadata",
    f"{_CAP17_TEST}::test_P17_T09_cross_user_isolation",
    f"{_CAP17_TEST}::test_P17_T10_no_user_phi_on_shared_knowledge",
    f"{_CAP17_TEST}::test_P17_T11_no_base_model_fallback",
    f"{_CAP17_TEST}::test_P17_T12_care_context_personalization_wiring",
    f"{_CAP17_TEST}::test_P17_T13_w4p02_handoff_compatibility",
    f"{_CAP17_TEST}::test_P17_T14_determinism",
)

CAP17_EXPECTED_RUNTIME_NODE_IDS: frozenset[str] = frozenset(CAP17_RUNTIME_SELECTORS)
EXPECTED_CAP17_NODE_COUNT = 15
EXPECTED_CAP17_SELECTOR_COUNT = 15
