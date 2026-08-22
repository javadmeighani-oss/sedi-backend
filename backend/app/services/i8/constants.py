"""Frozen I8 operational constants (PD-I8-01 / ARCH-02)."""

from __future__ import annotations

PRESENTATION_JSON_MAX_BYTES = 8192
CLEANUP_GRACE_HOURS = 36
SUMMARY_TEXT_MAX_LEN = 512

PLAN_STATUSES = frozenset({"ACTIVE", "COMPLETED", "SUPERSEDED", "EXPIRED", "CANCELLED"})
ACTION_STATUSES = frozenset({"ACTIVE", "COMPLETED", "SUPERSEDED", "EXPIRED", "CANCELLED", "FAILED"})
GENERATION_MODES = frozenset({"reactive", "proactive"})
ACTION_DOMAINS = frozenset(
    {"nutrition", "exercise", "routine", "lifestyle", "wellbeing", "cross_domain"}
)
SAFETY_STATES = frozenset({"SAFE", "BLOCKED", "CLARIFY"})

THERAPEUTIC_TOKENS = (
    "prescribe",
    "prescription",
    "change my medication",
    "stop taking",
    "increase dose",
    "decrease dose",
    "adjust dose",
    "start medication",
    "replace treatment",
)

UNSAFE_DIAGNOSIS_TOKENS = ("diagnose", "diagnosis")

DISEASE_AWARE_HINTS = (
    "diabetes",
    "hypertension",
    "cancer",
    "kidney disease",
    "heart failure",
    "copd",
    "asthma",
)

MAX_KNOWLEDGE_REFS = 8
