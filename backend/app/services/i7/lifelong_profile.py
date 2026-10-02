"""Derived lifelong profile builder. Not SoT. Not diagnosis.

CR-04C adds an additive deterministic semantic_profile v1 while preserving
existing top-level habits/preferences/goals semantics for I8.
I6 remains source of truth. No runtime activation in this module's callers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i6.consent_service import PERM_READ, require_permission
from backend.app.services.i6.memory_writes import list_facts
from backend.app.services.i7.period_summaries import period_bounds
from backend.app.services.memory.memory_contract import (
    CANONICAL_I6,
    LEGACY_COMPATIBILITY,
    MemoryContract,
)

GENERATOR_VERSION = "i7-v1-lifelong-profile"
SEMANTIC_PROFILE_VERSION = "v1"
UNSUPPORTED = ("diagnosis", "dose", "prescription", "treatment_plan")
_VALUE_COMPACT_MAX = 120
_NARRATIVE_MAX = 500

_HIGH_SENSITIVITY_DOMAINS = frozenset({"social", "values", "barriers"})

# Domain → semantic group for projectable I6 facts (excluding high-sensitivity).
_DOMAIN_GROUP: dict[str, str] = {
    "routines": "routines",
    "preferences": "interaction_preferences",
    "lifestyle": "lifestyle_context",
    "work": "work_context",
    "education": "education_context",
}

_SEMANTIC_GROUP_ORDER: tuple[str, ...] = (
    "routines",
    "interaction_preferences",
    "lifestyle_context",
    "work_context",
    "education_context",
    "high_sensitivity_context_refs",
)


class LifelongProfileError(ValueError):
    pass


def _sorted_facts(facts: list[models.UserMemoryFact]) -> list[models.UserMemoryFact]:
    return sorted(facts, key=lambda f: (f.domain or "", f.key or "", int(f.id)))


def _compact_scalar(value: Any) -> Optional[str]:
    """Deterministic scalar/bounded compact value. No raw dict/list dump."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        text = str(value).strip()
        return text[:_VALUE_COMPACT_MAX] if text else None
    if isinstance(value, str):
        text = value.strip()
        return text[:_VALUE_COMPACT_MAX] if text else None
    if isinstance(value, dict):
        for key in ("value", "label", "name", "target", "amount"):
            if value.get(key) is not None:
                return _compact_scalar(value.get(key))
        for v in value.values():
            if isinstance(v, (str, int, float, bool)):
                return _compact_scalar(v)
        return None
    if isinstance(value, list):
        if not value:
            return None
        return _compact_scalar(value[0])
    text = str(value).strip()
    return text[:_VALUE_COMPACT_MAX] if text else None


def _value_compact_from_fact(fact: models.UserMemoryFact) -> Optional[str]:
    raw = fact.value_json
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        text = str(raw).strip()
        return text[:_VALUE_COMPACT_MAX] if text else None
    return _compact_scalar(parsed)


def _change_state(fact: models.UserMemoryFact) -> str:
    if getattr(fact, "supersedes_fact_id", None) is not None:
        return "corrected"
    return "current"


def _normalized_sensitivity_class(fact: models.UserMemoryFact) -> str:
    raw = getattr(fact, "sensitivity_class", None)
    if raw is None:
        return ""
    return str(raw).strip().casefold()


def _effective_high(fact: models.UserMemoryFact) -> bool:
    """Fail-closed high sensitivity: domain-high OR row sensitivity_class=high."""
    domain, _key = MemoryContract.canonicalize_key(fact.domain, fact.key)
    if domain in _HIGH_SENSITIVITY_DOMAINS:
        return True
    return _normalized_sensitivity_class(fact) == "high"


def _provenance_class(fact: models.UserMemoryFact) -> str:
    """Preserve known provenance; never fabricate USER_STATED/USER_CONFIRMED."""
    raw = getattr(fact, "provenance_class", None)
    if raw is None:
        return "UNKNOWN"
    text = str(raw).strip()
    if not text:
        return "UNKNOWN"
    return text


def _base_entry(fact: models.UserMemoryFact, *, sensitivity: str) -> dict[str, Any]:
    return {
        "canonical_key": f"{fact.domain}.{fact.key}",
        "source_fact_id": int(fact.id),
        "provenance_class": _provenance_class(fact),
        "source": fact.source or "manual",
        "sensitivity": sensitivity,
        "change_state": _change_state(fact),
        "supersedes_fact_id": (
            int(fact.supersedes_fact_id)
            if getattr(fact, "supersedes_fact_id", None) is not None
            else None
        ),
    }


def _eligible_for_semantic(fact: models.UserMemoryFact) -> bool:
    """Semantic entries only from I6-owned, context-projectable domains/keys."""
    domain, key = MemoryContract.canonicalize_key(fact.domain, fact.key)
    if not MemoryContract.is_i6_context_projectable(domain, key):
        return False
    owner = MemoryContract.classify_ownership(domain, key)
    return owner in {CANONICAL_I6, LEGACY_COMPATIBILITY}


def _build_semantic_profile(
    facts: list[models.UserMemoryFact],
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {name: [] for name in _SEMANTIC_GROUP_ORDER}
    for fact in _sorted_facts(facts):
        if not _eligible_for_semantic(fact):
            continue
        domain, _key = MemoryContract.canonicalize_key(fact.domain, fact.key)
        if _effective_high(fact):
            entry = _base_entry(fact, sensitivity="high")
            # Metadata/ref only — never copy raw value into semantic profile.
            groups["high_sensitivity_context_refs"].append(entry)
            continue
        group = _DOMAIN_GROUP.get(domain)
        if group is None:
            continue
        entry = _base_entry(fact, sensitivity="medium")
        compact = _value_compact_from_fact(fact)
        if compact is not None:
            entry["value_compact"] = compact
        groups[group].append(entry)
    return groups


def _build_narrative(semantic_groups: dict[str, list[dict[str, Any]]]) -> str:
    """Deterministic bounded narrative from safe medium facts only."""
    parts: list[str] = ["Derived compact profile"]
    for group_name in _SEMANTIC_GROUP_ORDER:
        if group_name == "high_sensitivity_context_refs":
            continue
        for entry in semantic_groups.get(group_name, []):
            compact = entry.get("value_compact")
            if not compact:
                continue
            parts.append(f"{entry['canonical_key']}={compact}")
    parts.append("not diagnosis; I6 remains SoT")
    text = "; ".join(parts)
    return text[:_NARRATIVE_MAX]


def _assert_no_unsupported_inference(facts: list[models.UserMemoryFact]) -> None:
    for fact in facts:
        blob = f"{fact.domain}.{fact.key}".lower()
        if any(tok in blob for tok in UNSUPPORTED):
            raise LifelongProfileError("UNSUPPORTED_MEDICAL_INFERENCE")


def rebuild_lifelong_profile(
    db: Session, user_id: int, *, commit: bool = True
) -> models.UserLifelongProfile:
    require_permission(db, user_id, PERM_READ)
    facts = list_facts(db, user_id)
    _assert_no_unsupported_inference(facts)
    ordered = _sorted_facts(facts)
    start, end = period_bounds("YEARLY")
    keys = sorted(f"{f.domain}.{f.key}" for f in ordered)
    semantic_groups = _build_semantic_profile(ordered)
    payload = {
        "authority": "I6_FACTS_ARE_SOT",
        "profile_is_derived_only": True,
        "not_diagnosis": True,
        "generator_version": GENERATOR_VERSION,
        "fact_count": len(ordered),
        "keys": keys,
        # I8 reads these key lists — preserve existing semantics (domain.key strings).
        "habits": [k for k in keys if k.startswith("lifestyle.")],
        "preferences": [k for k in keys if "prefer" in k or k.startswith("preferences.")],
        "goals": [k for k in keys if k.startswith("goals.")],
        # CR-04C additive semantic longitudinal profile (derived only).
        "semantic_profile": {
            "version": SEMANTIC_PROFILE_VERSION,
            **semantic_groups,
        },
    }
    structured = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    source_ids = json.dumps(sorted(int(f.id) for f in ordered))
    narrative = _build_narrative(semantic_groups)

    prior_active = (
        db.query(models.UserLifelongProfile)
        .filter(
            models.UserLifelongProfile.user_id == user_id,
            models.UserLifelongProfile.status == "active",
        )
        .order_by(models.UserLifelongProfile.version.desc())
        .first()
    )
    if prior_active is not None and prior_active.structured_profile_json == structured:
        return prior_active

    latest_any = (
        db.query(models.UserLifelongProfile)
        .filter(models.UserLifelongProfile.user_id == user_id)
        .order_by(models.UserLifelongProfile.version.desc())
        .first()
    )
    version = 1 if latest_any is None else int(latest_any.version) + 1
    if prior_active is not None:
        prior_active.status = "superseded"
        prior_active.superseded_at = datetime.now(timezone.utc)
    consent = (
        db.query(models.UserConsent)
        .filter(
            models.UserConsent.subject_user_id == user_id,
            models.UserConsent.status == "active",
        )
        .first()
    )
    row = models.UserLifelongProfile(
        user_id=user_id,
        version=version,
        status="active",
        structured_profile_json=structured,
        narrative_compact=narrative,
        source_fact_ids_json=source_ids,
        source_event_refs_json="[]",
        consent_id=consent.id if consent is not None else None,
        generator_version=GENERATOR_VERSION,
        built_from_period_start=start,
        built_from_period_end=end,
    )
    db.add(row)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(row)
    return row
