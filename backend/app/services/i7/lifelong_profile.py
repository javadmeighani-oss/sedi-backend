"""Derived lifelong profile builder. Not SoT. Not diagnosis."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i6.consent_service import PERM_READ, require_permission
from backend.app.services.i6.memory_writes import list_facts
from backend.app.services.i7.period_summaries import period_bounds

GENERATOR_VERSION = "i7-v1-lifelong-profile"
UNSUPPORTED = ("diagnosis", "dose", "prescription", "treatment_plan")


class LifelongProfileError(ValueError):
    pass


def rebuild_lifelong_profile(
    db: Session, user_id: int, *, commit: bool = True
) -> models.UserLifelongProfile:
    require_permission(db, user_id, PERM_READ)
    facts = list_facts(db, user_id)
    for fact in facts:
        blob = f"{fact.domain}.{fact.key}".lower()
        if any(tok in blob for tok in UNSUPPORTED):
            raise LifelongProfileError("UNSUPPORTED_MEDICAL_INFERENCE")
    start, end = period_bounds("YEARLY")
    keys = sorted(f"{f.domain}.{f.key}" for f in facts)
    payload = {
        "authority": "I6_FACTS_ARE_SOT",
        "profile_is_derived_only": True,
        "not_diagnosis": True,
        "generator_version": GENERATOR_VERSION,
        "fact_count": len(facts),
        "keys": keys,
        "habits": [k for k in keys if k.startswith("lifestyle.")],
        "preferences": [k for k in keys if "prefer" in k or k.startswith("preferences.")],
        "goals": [k for k in keys if k.startswith("goals.")],
    }
    structured = json.dumps(payload, sort_keys=True)
    source_ids = json.dumps([f.id for f in facts], sort_keys=True)
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
        narrative_compact=f"Derived compact profile of {len(facts)} I6 facts; not source of truth.",
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
