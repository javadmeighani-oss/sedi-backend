"""Section 15-I2 — typed authorized context items (extends I1 contracts)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Sequence

ConsentState = Literal["explicit", "legacy_scope", "unknown", "denied"]
FreshnessState = Literal["fresh", "stale", "unknown", "not_applicable"]
SensitivityClass = Literal["low", "medium", "high", "critical"]
ContextSectionName = Literal[
    "profile",
    "lifestyle",
    "health",
    "memory",
    "notification",
]

# Label for non-evidence-backed numeric budgets (not medical policy; not tokens).
BUDGET_CLASSIFICATION_TECHNICAL_DEFAULT = (
    "I2 conservative technical safety defaults pending evaluation"
)
MEMORY_TURNS_PROVENANCE = (
    "evidence_backed:ConversationBrain.process_message "
    "get_recent_messages(user_id, limit=10)"
)


class ContextSource(str, Enum):
    PROFILE = "profile"
    LIFESTYLE = "lifestyle"
    HEALTH = "health"
    MEMORY = "memory"
    NOTIFICATION = "notification"


# Deterministic assembly / projection order only.
# NOT conflict-authority: unsupported supersession must not use these ranks.
ADAPTER_ORDER: tuple[ContextSource, ...] = (
    ContextSource.PROFILE,
    ContextSource.LIFESTYLE,
    ContextSource.HEALTH,
    ContextSource.MEMORY,
    ContextSource.NOTIFICATION,
)

SOURCE_SORT_RANK: dict[ContextSource, int] = {
    ContextSource.PROFILE: 10,
    ContextSource.LIFESTYLE: 20,
    ContextSource.HEALTH: 30,
    ContextSource.MEMORY: 40,
    ContextSource.NOTIFICATION: 50,
}

# Backward-compatible alias used only as a sort rank (never authority).
SOURCE_PRECEDENCE = SOURCE_SORT_RANK


@dataclass(frozen=True)
class ContextBudgets:
    """Central I2 budget configuration (request-overrideable; no global mutation)."""

    max_items_per_section: int = 10
    max_total_context_items: int = 40
    max_compatibility_projection_chars: int = 3500
    max_memory_turns: int = 10
    classification: str = BUDGET_CLASSIFICATION_TECHNICAL_DEFAULT
    memory_turns_provenance: str = MEMORY_TURNS_PROVENANCE

    def __post_init__(self) -> None:
        if self.max_items_per_section < 1 or self.max_total_context_items < 1:
            raise ValueError("invalid_budget")
        if self.max_compatibility_projection_chars < 64:
            raise ValueError("invalid_projection_budget")
        if self.max_memory_turns < 1:
            raise ValueError("invalid_memory_turns")


DEFAULT_CONTEXT_BUDGETS = ContextBudgets()

# Module-level mirrors of defaults for adapters that only need memory turns.
MAX_ITEMS_PER_SECTION = DEFAULT_CONTEXT_BUDGETS.max_items_per_section
MAX_TOTAL_CONTEXT_ITEMS = DEFAULT_CONTEXT_BUDGETS.max_total_context_items
MAX_COMPATIBILITY_PROJECTION_CHARS = (
    DEFAULT_CONTEXT_BUDGETS.max_compatibility_projection_chars
)
MAX_MEMORY_TURNS = DEFAULT_CONTEXT_BUDGETS.max_memory_turns


@dataclass(frozen=True)
class ContextProvenance:
    source: ContextSource
    owner_user_id: int
    query_label: str
    record_hint: Optional[str] = None  # never a raw DB id in projection/logs


@dataclass
class ContextItem:
    canonical_key: str
    section: ContextSectionName
    source: ContextSource
    structured_value: Any
    display_text: str
    provenance: ContextProvenance
    observed_at: Optional[datetime]
    freshness: FreshnessState
    sensitivity: SensitivityClass
    consent: ConsentState
    may_send_to_llm: bool
    sort_rank: int
    active: bool = True
    conflicted: bool = False
    truncated: bool = False
    coalesced_provenance: list[ContextProvenance] = field(default_factory=list)

    @property
    def precedence(self) -> int:
        """Deprecated alias for sort_rank (ordering only; not authority)."""
        return self.sort_rank


@dataclass
class ContextSection:
    name: ContextSectionName
    items: list[ContextItem] = field(default_factory=list)
    empty_reason: Optional[str] = None


@dataclass
class ContextSnapshot:
    """Request-scoped assembled authorized context (internal only)."""

    request_id: str
    owner_user_id: int
    sections: dict[str, ContextSection]
    items: list[ContextItem]
    preferred_name: Optional[str]
    conflict_count: int
    truncated_count: int
    reason_codes: tuple[str, ...]
    adapter_order: tuple[str, ...]
    budget_classification: str = BUDGET_CLASSIFICATION_TECHNICAL_DEFAULT


@dataclass(frozen=True)
class CompatibilityProjection:
    """Deterministic LLM-eligible text projection from a snapshot."""

    text: str
    item_count: int
    char_count: int
    truncated: bool
    excluded_conflict_count: int
    preferred_name: Optional[str]


def safe_item_sort_key(item: ContextItem) -> tuple:
    return (
        item.sort_rank,
        item.section,
        item.canonical_key,
        item.source.value,
        item.display_text,
    )


def assert_no_sensitive_in_reason_codes(codes: Sequence[str]) -> None:
    for code in codes:
        if not code or not code.replace("_", "").isalnum():
            raise AssertionError("unsafe_reason_code")
