"""Section 10 environment-driven feature flags (default OFF)."""

from __future__ import annotations

import os

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _env_flag_enabled(name: str) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in _TRUE_VALUES


# Caregiver delivery
def caregiver_delivery_enabled() -> bool:
    return _env_flag_enabled("SEDI_CAREGIVER_DELIVERY_ENABLED")


def caregiver_daily_report_enabled() -> bool:
    return _env_flag_enabled("SEDI_CAREGIVER_DAILY_REPORT_ENABLED")


def caregiver_vital_alert_enabled() -> bool:
    return _env_flag_enabled("SEDI_CAREGIVER_VITAL_ALERT_ENABLED")


def caregiver_care_summary_enabled() -> bool:
    return _env_flag_enabled("SEDI_CAREGIVER_CARE_SUMMARY_ENABLED")


def i10_care_network_delivery_enabled() -> bool:
    return _env_flag_enabled("SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED")


# Emergency escalation
def emergency_escalation_enabled() -> bool:
    return _env_flag_enabled("SEDI_EMERGENCY_ESCALATION_ENABLED")


def voice_call_requests_enabled() -> bool:
    return _env_flag_enabled("SEDI_VOICE_CALL_REQUESTS_ENABLED")


def voice_call_provider_enabled() -> bool:
    return _env_flag_enabled("SEDI_VOICE_CALL_PROVIDER_ENABLED")


# Medication stock
def medication_stock_notifications_enabled() -> bool:
    return _env_flag_enabled("SEDI_MEDICATION_STOCK_NOTIFICATIONS_ENABLED")


# Event / lifestyle schedulers
def event_reminder_scheduler_enabled() -> bool:
    return _env_flag_enabled("SEDI_EVENT_REMINDER_SCHEDULER_ENABLED")


def lifestyle_reminder_scheduler_enabled() -> bool:
    return _env_flag_enabled("SEDI_LIFESTYLE_REMINDER_SCHEDULER_ENABLED")


# Proactive interaction
def proactive_interaction_enabled() -> bool:
    return _env_flag_enabled("SEDI_PROACTIVE_INTERACTION_ENABLED")


def proactive_followup_enabled() -> bool:
    return _env_flag_enabled("SEDI_PROACTIVE_FOLLOWUP_ENABLED")


def contextual_followup_enabled() -> bool:
    return _env_flag_enabled("SEDI_I10_CONTEXTUAL_FOLLOWUP_ENABLED")


def coaching_followup_enabled() -> bool:
    return _env_flag_enabled("SEDI_I10_COACHING_FOLLOWUP_ENABLED")


def i10_care_digest_producer_enabled() -> bool:
    return _env_flag_enabled("SEDI_I10_CARE_DIGEST_PRODUCER_ENABLED")


def i10_care_action_producer_enabled() -> bool:
    return _env_flag_enabled("SEDI_I10_CARE_ACTION_PRODUCER_ENABLED")


def inactivity_policy_enabled() -> bool:
    return _env_flag_enabled("SEDI_INACTIVITY_POLICY_ENABLED")


# KB embeddings / hybrid retrieval
def kb_embeddings_enabled() -> bool:
    return _env_flag_enabled("SEDI_KB_EMBEDDINGS_ENABLED")


def kb_vector_retrieval_enabled() -> bool:
    return _env_flag_enabled("SEDI_KB_VECTOR_RETRIEVAL_ENABLED")


def kb_hybrid_retrieval_enabled() -> bool:
    return _env_flag_enabled("SEDI_KB_HYBRID_RETRIEVAL_ENABLED")
