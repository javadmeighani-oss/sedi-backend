"""Frozen I8 operational constants (PD-I8-01 / ARCH-02 / PD-I8-04A)."""

from __future__ import annotations

PRESENTATION_JSON_MAX_BYTES = 8192
CLEANUP_GRACE_HOURS = 36
SUMMARY_TEXT_MAX_LEN = 512

PLAN_STATUSES = frozenset({"ACTIVE", "COMPLETED", "SUPERSEDED", "EXPIRED", "CANCELLED"})
ACTION_STATUSES = frozenset({"ACTIVE", "COMPLETED", "SUPERSEDED", "EXPIRED", "CANCELLED", "FAILED"})
REPLAYABLE_PLAN_STATUSES = frozenset({"ACTIVE"})
REPLAYABLE_ACTION_STATUSES = frozenset({"ACTIVE", "COMPLETED"})
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

# KNOW-06 governed person-specific disease applicability — not runtime-ready.
GOVERNED_DISEASE_APPLICABILITY_AVAILABLE = False

OPERATIONAL_SUMMARY_LABELS: dict[str, str] = {
    "nutrition": "Governed nutrition action",
    "exercise": "Governed activity action",
    "routine": "Governed routine action",
    "lifestyle": "Governed lifestyle action",
    "wellbeing": "Governed wellbeing action",
    "cross_domain": "Governed cross-domain action",
}

# PD-I8-04A proactive evaluation ledger (frozen DCR vocabulary)
TRIGGER_FAMILIES = frozenset({"event", "schedule", "future_i9"})
EVALUATION_LIFECYCLE_STATUSES = frozenset(
    {"IN_PROGRESS", "COMPLETED", "FAILED_RETRYABLE", "FAILED_TERMINAL"}
)
EVALUATION_OUTCOMES = frozenset({"ACTION_CREATED", "NO_ACTION"})

PROACTIVE_NO_ACTION_STATUSES = frozenset(
    {
        "MISSING_GROUNDED_ACTION_CONTENT",
        "MISSING_ELIGIBLE_KNOWLEDGE",
    }
)

PROACTIVE_TERMINAL_STATUSES = frozenset(
    {
        "UNSUPPORTED_CLINICAL_APPLICABILITY",
        "UNSAFE_REQUEST_BLOCKED",
        "THERAPEUTIC_FAIL_CLOSED",
        "ALLERGY_HARD_CONSTRAINT",
        "RESTRICTION_BLOCKED",
        "AUTH_IDENTITY_MISMATCH",
    }
)

PROACTIVE_RETRYABLE_STATUSES = frozenset(
    {
        "CONSENT_REQUIRED",
        "TIMEZONE_REQUIRED",
        "TIMEZONE_INVALID",
        "UNVERIFIED_ALLERGY_SIGNAL",
        "PRESENTATION_TOO_LARGE",
    }
)

SEMANTIC_ENVELOPE_FORBIDDEN_KEYS = frozenset(
    {
        "notification_title",
        "notification_body",
        "title",
        "body",
        "channel",
        "send_at",
        "send_time",
        "fatigue",
        "bundle",
        "bundling",
        "delivery",
        "delivery_retry",
        "push",
        "lock_screen",
        "copywriting",
        "ux",
        "normalized_statement",
        "raw_i5_statement",
        "diagnosis",
        "prescription",
    }
)
