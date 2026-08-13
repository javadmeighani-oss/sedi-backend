"""DCR-04 legacy fact-stack write freeze. Reads remain. No table drops."""

from __future__ import annotations

import os

FROZEN_STACKS = ("user_facts", "kc_user_facts", "user_profile_facts")
CANONICAL_OWNER = "user_memory_facts"


class LegacyFactStackFrozen(PermissionError):
    def __init__(self, stack: str):
        self.stack = stack
        super().__init__("LEGACY_FACT_STACK_FROZEN")


def legacy_fact_writes_frozen() -> bool:
    """Frozen by default. Tests/ops may set SEDI_LEGACY_FACT_WRITES_ENABLED=true."""
    return os.getenv("SEDI_LEGACY_FACT_WRITES_ENABLED", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }


def assert_legacy_write_allowed(stack: str) -> None:
    if stack not in FROZEN_STACKS:
        return
    if legacy_fact_writes_frozen():
        raise LegacyFactStackFrozen(stack)
