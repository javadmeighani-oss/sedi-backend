"""I9 VitalObservationContext — nonnumeric observation context foundation (G11).

Transient/internal contract only. No schema. No clinical interpretation.
Never invents activity/altitude/temp-method/quality/confirmation values.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.absolute_vital_observation import CanonicalVitalObservation

# Bounded symptom window relative to observation time (existing report timestamps only).
_SYMPTOM_LOOKBACK = timedelta(hours=24)
_SYMPTOM_LOOKAHEAD = timedelta(minutes=15)


class AuthorityState(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class ContextualField:
    """One context slot with explicit authority state — never invents values."""

    state: AuthorityState
    value: Any = None
    source: Optional[str] = None

    @property
    def is_known(self) -> bool:
        return self.state == AuthorityState.KNOWN


def _unknown(source: Optional[str] = None, value: Any = None) -> ContextualField:
    return ContextualField(state=AuthorityState.UNKNOWN, value=value, source=source)


def _known(value: Any, source: str) -> ContextualField:
    return ContextualField(state=AuthorityState.KNOWN, value=value, source=source)


@dataclass(frozen=True)
class VitalObservationContext:
    """Canonical I9 observation-context contract (structural / authority-tagged)."""

    activity_state: ContextualField
    symptom_refs: ContextualField
    altitude: ContextualField
    temperature_method: ContextualField
    quality_state: ContextualField
    confirmation_state: ContextualField
    medication_context: ContextualField
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _self_subject_matches_account(
    db: Session,
    *,
    health_subject_id: Optional[int],
    account_user_id: Optional[int],
) -> bool:
    """Symptoms are account-scoped; only attach when observation is SELF for that account."""
    if health_subject_id is None or account_user_id is None:
        return False
    row = (
        db.query(models.HealthSubject)
        .filter(
            models.HealthSubject.id == int(health_subject_id),
            models.HealthSubject.linked_user_id == int(account_user_id),
            models.HealthSubject.subject_kind == "self",
            models.HealthSubject.status == "active",
        )
        .first()
    )
    return row is not None


def _resolve_symptom_refs(
    db: Session,
    *,
    account_user_id: Optional[int],
    health_subject_id: Optional[int],
    measured_at: Optional[datetime],
) -> ContextualField:
    if not _self_subject_matches_account(
        db, health_subject_id=health_subject_id, account_user_id=account_user_id
    ):
        return _unknown(source="symptom_subject_boundary")
    if measured_at is None or account_user_id is None:
        return _unknown(source="symptom_time_or_account_missing")

    when = _as_utc(measured_at)
    assert when is not None
    start = when - _SYMPTOM_LOOKBACK
    end = when + _SYMPTOM_LOOKAHEAD

    rows = (
        db.query(models.HealthSymptomReport)
        .filter(
            models.HealthSymptomReport.user_id == int(account_user_id),
            models.HealthSymptomReport.status == "active",
        )
        .order_by(models.HealthSymptomReport.reported_at.desc())
        .all()
    )
    refs: list[dict[str, Any]] = []
    for row in rows:
        reported = _as_utc(row.reported_at)
        if reported is None:
            continue
        if reported < start or reported > end:
            continue
        refs.append(
            {
                "id": int(row.id),
                "symptom_label": row.symptom_label,
                "symptom_code": row.symptom_code,
                "reported_at": reported.isoformat(),
                "status": row.status,
            }
        )
    if not refs:
        return _unknown(source="health_symptom_reports_none_in_window")
    return _known(refs, source="health_symptom_reports")


def _resolve_medication_context(
    db: Session,
    *,
    account_user_id: Optional[int],
) -> ContextualField:
    """Optional inventory only — does NOT infer physiological medication effect."""
    if account_user_id is None:
        return _unknown(source="medication_account_missing")
    rows = (
        db.query(models.UserMedication)
        .filter(models.UserMedication.user_id == int(account_user_id))
        .all()
    )
    if not rows:
        return _unknown(source="user_medications_none")
    refs = [{"user_medication_id": int(r.id), "medication_id": int(r.medication_id)} for r in rows]
    # PARTIAL: inventory known; effect / observation-linkage unknown (never inferred).
    return ContextualField(
        state=AuthorityState.KNOWN,
        value={
            "inventory_refs": refs,
            "effect": "UNKNOWN",
            "observation_linked": False,
            "authority": "OPTIONAL_PARTIAL",
        },
        source="user_medications_inventory_only",
    )


def resolve_vital_observation_context(
    db: Session,
    observation: CanonicalVitalObservation,
) -> VitalObservationContext:
    """Build context for one observation from existing authorities only."""
    symptoms = _resolve_symptom_refs(
        db,
        account_user_id=observation.account_user_id,
        health_subject_id=observation.health_subject_id,
        measured_at=observation.measured_at,
    )
    medication = _resolve_medication_context(db, account_user_id=observation.account_user_id)

    # No authoritative sources today — remain UNKNOWN (do not copy PM quality onto HealthData).
    quality = _unknown(source="healthdata_quality_absent")
    if observation.quality_state not in (None, ""):
        # Only accept quality already attached on the observation from its own authority path.
        quality = _known(observation.quality_state, source="observation.quality_state")

    return VitalObservationContext(
        activity_state=_unknown(source="no_vital_activity_authority"),
        symptom_refs=symptoms,
        altitude=_unknown(source="no_altitude_authority"),
        temperature_method=_unknown(source="no_temperature_method_authority"),
        quality_state=quality,
        confirmation_state=_unknown(
            source="no_vital_confirmation_authority",
            value="UNCONFIRMED",
        ),
        medication_context=medication,
        diagnostics={
            "schema_required_for": [
                "activity_state",
                "altitude",
                "temperature_method",
                "healthdata_quality",
                "vital_confirmation",
            ],
            "clinical_inference": False,
            "repeat_inference": False,
            "medication_effect_inferred": False,
        },
    )


def attach_context_to_observations(
    db: Session,
    observations: Sequence[CanonicalVitalObservation],
) -> list[CanonicalVitalObservation]:
    """Return observations with provenance.context_contract populated (transient)."""
    out: list[CanonicalVitalObservation] = []
    for obs in observations:
        ctx = resolve_vital_observation_context(db, obs)
        prov = dict(obs.provenance or {})
        prov["vital_observation_context"] = {
            "activity_state": ctx.activity_state.state.value,
            "symptom_refs": ctx.symptom_refs.state.value,
            "altitude": ctx.altitude.state.value,
            "temperature_method": ctx.temperature_method.state.value,
            "quality_state": ctx.quality_state.state.value,
            "confirmation_state": ctx.confirmation_state.state.value,
            "medication_context": ctx.medication_context.state.value,
            "medication_authority": (ctx.medication_context.value or {}).get("authority")
            if isinstance(ctx.medication_context.value, dict)
            else None,
            "symptom_ref_ids": [r["id"] for r in (ctx.symptom_refs.value or [])]
            if ctx.symptom_refs.is_known and isinstance(ctx.symptom_refs.value, list)
            else [],
            "diagnostics": ctx.diagnostics,
        }
        # Keep object for eligibility without inventing clinical meaning.
        prov["context_object"] = ctx
        out.append(replace(obs, provenance=prov))
    return out
