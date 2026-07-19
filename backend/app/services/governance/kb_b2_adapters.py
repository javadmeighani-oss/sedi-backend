"""Section 15-I5-B2-A1 — pure boundary adapters for legacy → typed I5-B1 contracts.

No ORM, I/O, env, HTTP, scheduler, or runtime wiring. Deterministic and fail-closed.
Fix2: raw-only converters; category-name-only checkpoint evidence; no typed passthrough.
Fix3: reject all collections.abc.Mapping top-level category containers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Iterable, Optional, Tuple
import json
import math
import unicodedata

from backend.app.services.governance.contracts import (
    GovernanceAction,
    PublicationState,
    ReviewStatus,
    SourceOperationalStatus,
)
from backend.app.services.governance.kb_lifecycle_mapping import (
    PolicyCheckpoint,
    checkpoint_evidence_requirements_satisfied,
    map_legacy_publication_state,
    map_legacy_review_status,
    map_legacy_source_operational_status,
    policy_checkpoint_spec,
)

__all__ = (
    "LegacyToTypedConversionError",
    "convert_source_operational_status",
    "convert_review_status",
    "convert_publication_state",
    "convert_automation_inputs",
    "build_prefetch_evidence_categories",
    "build_prepublish_evidence_categories",
    "build_scheduled_authorization_request",
    "derive_policy_decision_idempotency_key",
    "derive_fetch_run_idempotency_key",
    "derive_source_version_composition_key",
    "derive_provenance_evidence_fingerprint",
    "derive_document_version_dedup_key",
    "derive_publication_release_evidence_fingerprint",
    "assert_checkpoint_evidence_or_raise",
)

_CANONICAL_NULL: str = "__CANONICAL_NULL__"
_SHA256_HEX_LEN: int = 64
_MISSING: object = object()

# B1 result shapes (authoritative; not re-defined as competing contracts).
SourceOperationalMappingResult = Tuple[
    SourceOperationalStatus, Tuple[str, ...], bool, bool
]
ReviewStatusMappingResult = Tuple[ReviewStatus, Tuple[str, ...], bool, bool, bool]
PublicationStateMappingResult = Tuple[PublicationState, Tuple[str, ...], bool, bool]


class LegacyToTypedConversionError(ValueError):
    """Raised when a legacy/external value cannot be converted to a typed contract."""


@dataclass(frozen=True)
class ScheduledAuthorizationInputs:
    """Internal six-operand inputs for B1 scheduled-authorization evaluation."""

    i5_schedule_flag_enabled: bool
    legacy_kb_schedule_flag_enabled: bool
    global_scheduler_enabled: bool
    source_fetch_enabled: bool
    governed_profile_automation_permitted: bool
    source_operational_status: SourceOperationalStatus


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _require_bool(field: str, value: Any) -> bool:
    if value is _MISSING:
        raise LegacyToTypedConversionError(f"{field}_required")
    if type(value) is not bool:
        raise LegacyToTypedConversionError(f"{field}_must_be_bool")
    return value


def _normalize_legacy_status_transport(field: str, value: Any) -> Optional[str]:
    """Transport normalization only; does not decide governed meaning."""
    if value is None:
        return None
    if isinstance(value, bool) or (
        isinstance(value, int) and not isinstance(value, bool)
    ):
        raise LegacyToTypedConversionError(f"{field}_invalid_type")
    if not isinstance(value, str):
        raise LegacyToTypedConversionError(f"{field}_must_be_str")
    return _nfc(value.strip()) if value.strip() else ""


def _normalize_category_name(value: Any) -> str:
    if type(value) is not str:
        raise LegacyToTypedConversionError("checkpoint_evidence_category_invalid_type")
    normalized = _nfc(value).strip()
    if not normalized:
        raise LegacyToTypedConversionError("checkpoint_evidence_category_empty")
    return normalized


def _normalize_provided_categories(
    provided_evidence_categories: Any,
) -> Tuple[str, ...]:
    """Normalize category-name inputs; reject bare strings and non-iterables."""
    if provided_evidence_categories is None:
        raise LegacyToTypedConversionError("provided_evidence_categories_required")
    if type(provided_evidence_categories) is str:
        raise LegacyToTypedConversionError(
            "provided_evidence_categories_must_be_iterable_of_str"
        )
    if type(provided_evidence_categories) is bytes:
        raise LegacyToTypedConversionError(
            "provided_evidence_categories_must_be_iterable_of_str"
        )
    # Mappings are iterable by keys; reject every Mapping as a category container.
    if isinstance(provided_evidence_categories, Mapping):
        raise LegacyToTypedConversionError(
            "invalid_checkpoint_evidence_categories_container"
        )
    try:
        iterator = iter(provided_evidence_categories)
    except TypeError as exc:
        raise LegacyToTypedConversionError(
            "provided_evidence_categories_must_be_iterable_of_str"
        ) from exc

    seen: set[str] = set()
    ordered_unique: list[str] = []
    for item in iterator:
        name = _normalize_category_name(item)
        if name not in seen:
            seen.add(name)
            ordered_unique.append(name)
    return tuple(ordered_unique)


def _build_checkpoint_categories(
    checkpoint: PolicyCheckpoint,
    provided_evidence_categories: Any,
) -> Tuple[str, ...]:
    """Validate category names against B1 spec; return official-order subset."""
    spec = policy_checkpoint_spec(checkpoint)
    required = spec.required_evidence_categories
    required_set = frozenset(required)
    provided = _normalize_provided_categories(provided_evidence_categories)
    for name in provided:
        if name not in required_set:
            raise LegacyToTypedConversionError("unknown_checkpoint_evidence_category")
    present = tuple(category for category in required if category in frozenset(provided))
    if not checkpoint_evidence_requirements_satisfied(checkpoint, present):
        raise LegacyToTypedConversionError("checkpoint_evidence_categories_incomplete")
    return present


def convert_source_operational_status(
    legacy_ingestion_status: Any = None,
    *,
    source_fetch_enabled: Any = _MISSING,
    governed_profile_present: Any = _MISSING,
    governed_profile_verified: Any = _MISSING,
) -> SourceOperationalMappingResult:
    """Delegate raw legacy source status to B1. Typed enums are rejected."""
    if isinstance(legacy_ingestion_status, SourceOperationalStatus):
        raise LegacyToTypedConversionError(
            "typed_source_operational_status_not_accepted"
        )

    fetch_enabled = _require_bool("source_fetch_enabled", source_fetch_enabled)
    profile_present = _require_bool(
        "governed_profile_present", governed_profile_present
    )
    profile_verified = _require_bool(
        "governed_profile_verified", governed_profile_verified
    )

    transport = _normalize_legacy_status_transport(
        "legacy_ingestion_status", legacy_ingestion_status
    )
    status_for_b1: Optional[str] = None if transport == "" else transport
    return map_legacy_source_operational_status(
        legacy_ingestion_status=status_for_b1,
        source_fetch_enabled=fetch_enabled,
        governed_profile_present=profile_present,
        governed_profile_verified=profile_verified,
    )


def convert_review_status(
    legacy_review_status: Any = None,
) -> ReviewStatusMappingResult:
    """Delegate raw legacy review status to B1. Typed enums are rejected."""
    if isinstance(legacy_review_status, ReviewStatus):
        raise LegacyToTypedConversionError("typed_review_status_not_accepted")

    transport = _normalize_legacy_status_transport(
        "legacy_review_status", legacy_review_status
    )
    status_for_b1: Optional[str] = None if transport == "" else transport
    return map_legacy_review_status(status_for_b1)


def convert_publication_state(
    document_status: Any = None,
    *,
    published_at_present: Any = _MISSING,
) -> PublicationStateMappingResult:
    """Delegate raw legacy publication state to B1. Typed enums are rejected."""
    if isinstance(document_status, PublicationState):
        raise LegacyToTypedConversionError("typed_publication_state_not_accepted")

    published = _require_bool("published_at_present", published_at_present)

    transport = _normalize_legacy_status_transport("document_status", document_status)
    status_for_b1: Optional[str] = None if transport == "" else transport
    return map_legacy_publication_state(
        document_status=status_for_b1,
        published_at_present=published,
    )


def convert_automation_inputs(
    *,
    i5_schedule_flag_enabled: Any = _MISSING,
    legacy_kb_schedule_flag_enabled: Any = _MISSING,
    global_scheduler_enabled: Any = _MISSING,
    source_fetch_enabled: Any = _MISSING,
    governed_profile_automation_permitted: Any = _MISSING,
    source_operational_status: Any = _MISSING,
    governed_profile_present: Any = _MISSING,
    governed_profile_verified: Any = _MISSING,
) -> ScheduledAuthorizationInputs:
    """Validate six scheduled-fetch operands; raw status via B1, typed status direct."""
    if source_operational_status is _MISSING:
        raise LegacyToTypedConversionError("source_operational_status_required")

    fetch_enabled = _require_bool("source_fetch_enabled", source_fetch_enabled)

    if isinstance(source_operational_status, SourceOperationalStatus):
        # Typed governed status enters the DTO directly; do not invent mapper metadata
        # and do not route through the raw-only converter.
        status = source_operational_status
    else:
        status, _reasons, _manual, _fail_closed = convert_source_operational_status(
            source_operational_status,
            source_fetch_enabled=fetch_enabled,
            governed_profile_present=governed_profile_present,
            governed_profile_verified=governed_profile_verified,
        )

    return ScheduledAuthorizationInputs(
        i5_schedule_flag_enabled=_require_bool(
            "i5_schedule_flag_enabled", i5_schedule_flag_enabled
        ),
        legacy_kb_schedule_flag_enabled=_require_bool(
            "legacy_kb_schedule_flag_enabled", legacy_kb_schedule_flag_enabled
        ),
        global_scheduler_enabled=_require_bool(
            "global_scheduler_enabled", global_scheduler_enabled
        ),
        source_fetch_enabled=fetch_enabled,
        governed_profile_automation_permitted=_require_bool(
            "governed_profile_automation_permitted",
            governed_profile_automation_permitted,
        ),
        source_operational_status=status,
    )


def build_prefetch_evidence_categories(
    provided_evidence_categories: Iterable[str],
) -> Tuple[str, ...]:
    """Validate PRE_FETCH category names; return official B1-ordered complete set."""
    return _build_checkpoint_categories(
        PolicyCheckpoint.PRE_FETCH, provided_evidence_categories
    )


def build_prepublish_evidence_categories(
    provided_evidence_categories: Iterable[str],
) -> Tuple[str, ...]:
    """Validate PRE_PUBLISH category names; return official B1-ordered complete set."""
    return _build_checkpoint_categories(
        PolicyCheckpoint.PRE_PUBLISH, provided_evidence_categories
    )


def build_scheduled_authorization_request(
    *,
    i5_schedule_flag_enabled: Any = _MISSING,
    legacy_kb_schedule_flag_enabled: Any = _MISSING,
    global_scheduler_enabled: Any = _MISSING,
    source_fetch_enabled: Any = _MISSING,
    governed_profile_automation_permitted: Any = _MISSING,
    source_operational_status: Any = _MISSING,
    governed_profile_present: Any = _MISSING,
    governed_profile_verified: Any = _MISSING,
) -> ScheduledAuthorizationInputs:
    """Construct typed scheduled-authorization inputs for B1 (does not evaluate)."""
    return convert_automation_inputs(
        i5_schedule_flag_enabled=i5_schedule_flag_enabled,
        legacy_kb_schedule_flag_enabled=legacy_kb_schedule_flag_enabled,
        global_scheduler_enabled=global_scheduler_enabled,
        source_fetch_enabled=source_fetch_enabled,
        governed_profile_automation_permitted=governed_profile_automation_permitted,
        source_operational_status=source_operational_status,
        governed_profile_present=governed_profile_present,
        governed_profile_verified=governed_profile_verified,
    )


def assert_checkpoint_evidence_or_raise(
    checkpoint: Any,
    provided_evidence_categories: Tuple[str, ...],
) -> None:
    """Delegate to B1 checkpoint evidence validation; fail closed on incomplete evidence."""
    if not isinstance(checkpoint, PolicyCheckpoint):
        raise ValueError("unsupported_policy_checkpoint")
    try:
        ok = checkpoint_evidence_requirements_satisfied(
            checkpoint, provided_evidence_categories
        )
    except TypeError as exc:
        raise ValueError(f"checkpoint_evidence_invalid:{checkpoint.value}") from exc
    except ValueError as exc:
        raise ValueError(f"checkpoint_evidence_invalid:{checkpoint.value}") from exc
    if not ok:
        raise ValueError(f"checkpoint_evidence_incomplete:{checkpoint.value}")


def _normalize_identity_value(field: str, value: Any, *, allow_null: bool = False) -> Any:
    if value is None:
        if allow_null:
            return _CANONICAL_NULL
        raise ValueError(f"{field}_required")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError(f"{field}_naive_datetime_forbidden")
        utc = value.astimezone(timezone.utc)
        text = utc.isoformat().replace("+00:00", "Z")
        if text.endswith("+00:00"):
            text = text[:-6] + "Z"
        return text
    if type(value) is bool:
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field}_non_finite_float_forbidden")
        return value
    if isinstance(value, str):
        normalized = _nfc(value)
        if not allow_null and not normalized.strip():
            raise ValueError(f"{field}_empty")
        return normalized
    raise ValueError(f"{field}_unsupported_type")


def _canonical_identity_payload(
    ordered_fields: Tuple[Tuple[str, Any, bool], ...],
) -> str:
    """Build deterministic JSON array of [name, value] pairs (fixed order)."""
    pairs = []
    for name, raw, allow_null in ordered_fields:
        pairs.append([name, _normalize_identity_value(name, raw, allow_null=allow_null)])
    return json.dumps(pairs, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _derive_canonical_sha256(payload: str) -> str:
    digest = sha256(payload.encode("utf-8")).hexdigest()
    if len(digest) != _SHA256_HEX_LEN:
        raise ValueError("sha256_length_invalid")
    return digest


def derive_policy_decision_idempotency_key(
    *,
    ingestion_run_id: Any,
    action: Any,
    request_fingerprint: Any,
    policy_version: Any,
) -> str:
    """SHA-256 of (ingestion_run_id, action, request_fingerprint, policy_version)."""
    if isinstance(action, GovernanceAction):
        action_value: Any = action
    elif isinstance(action, str):
        try:
            action_value = GovernanceAction(action.strip())
        except ValueError as exc:
            raise ValueError("action_unsupported") from exc
    else:
        raise ValueError("action_invalid_type")
    payload = _canonical_identity_payload(
        (
            ("ingestion_run_id", ingestion_run_id, False),
            ("action", action_value, False),
            ("request_fingerprint", request_fingerprint, False),
            ("policy_version", policy_version, False),
        )
    )
    return _derive_canonical_sha256(payload)


def derive_fetch_run_idempotency_key(
    *,
    source_profile_id: Any,
    source_profile_version_id: Any,
    trigger_type: Any,
    trigger_identity: Any,
    canonical_url: Any,
    policy_version: Any,
) -> str:
    """Stable logical fetch-run key; attempt_number must not participate."""
    if not isinstance(canonical_url, str) or not canonical_url.strip():
        raise ValueError("canonical_url_empty")
    payload = _canonical_identity_payload(
        (
            ("source_profile_id", source_profile_id, False),
            ("source_profile_version_id", source_profile_version_id, False),
            ("trigger_type", trigger_type, False),
            ("trigger_identity", trigger_identity, False),
            ("canonical_url", canonical_url, False),
            ("policy_version", policy_version, False),
        )
    )
    return _derive_canonical_sha256(payload)


def derive_source_version_composition_key(
    *,
    source_profile_version_reference: Any,
    raw_object_reference: Any,
) -> str:
    """Composition key for B1 governed_source_version authority fields only."""
    payload = _canonical_identity_payload(
        (
            ("source_profile_version_reference", source_profile_version_reference, False),
            ("raw_object_reference", raw_object_reference, False),
        )
    )
    return _derive_canonical_sha256(payload)


def derive_provenance_evidence_fingerprint(
    *,
    governed_document_id: Any,
    governed_source_version_id: Any,
    raw_content_id: Any,
    source_acquisition_id: Any,
    document_content_hash: Any,
    parser_version: Any,
    normalizer_version: Any,
    chunker_version: Any,
    producer_service_version: Any,
    normalization_config_fingerprint: Any,
    chunking_config_fingerprint: Any,
) -> str:
    """Acquisition-specific provenance evidence fingerprint."""
    payload = _canonical_identity_payload(
        (
            ("governed_document_id", governed_document_id, False),
            ("governed_source_version_id", governed_source_version_id, False),
            ("raw_content_id", raw_content_id, False),
            ("source_acquisition_id", source_acquisition_id, False),
            ("document_content_hash", document_content_hash, False),
            ("parser_version", parser_version, False),
            ("normalizer_version", normalizer_version, False),
            ("chunker_version", chunker_version, False),
            ("producer_service_version", producer_service_version, False),
            ("normalization_config_fingerprint", normalization_config_fingerprint, False),
            ("chunking_config_fingerprint", chunking_config_fingerprint, False),
        )
    )
    return _derive_canonical_sha256(payload)


def derive_document_version_dedup_key(
    *,
    governed_document_id: Any,
    document_content_hash: Any,
    parser_version: Any,
    normalizer_version: Any,
    chunker_version: Any,
    normalization_config_fingerprint: Any,
    chunking_config_fingerprint: Any,
) -> str:
    """Acquisition-insensitive semantic document-version identity (NO_CHANGE signal)."""
    payload = _canonical_identity_payload(
        (
            ("governed_document_id", governed_document_id, False),
            ("document_content_hash", document_content_hash, False),
            ("parser_version", parser_version, False),
            ("normalizer_version", normalizer_version, False),
            ("chunker_version", chunker_version, False),
            ("normalization_config_fingerprint", normalization_config_fingerprint, False),
            ("chunking_config_fingerprint", chunking_config_fingerprint, False),
        )
    )
    return _derive_canonical_sha256(payload)


def derive_publication_release_evidence_fingerprint(
    *,
    document_version_id: Any,
    human_approval_record_id: Any,
    human_approval_projection_version_counter: Any,
    release_channel: Any,
    release_target: Any,
    visibility: Any,
    release_configuration_fingerprint: Any,
    jurisdiction_snapshot_reference: Any,
    license_evidence_reference: Any,
    intended_effective_time: Any,
    rollback_target_document_version_id: Any = None,
) -> str:
    """Pre-policy publication-release evidence fingerprint for PRE_PUBLISH."""
    if not isinstance(intended_effective_time, datetime):
        raise ValueError("intended_effective_time_must_be_datetime")
    payload = _canonical_identity_payload(
        (
            ("document_version_id", document_version_id, False),
            ("human_approval_record_id", human_approval_record_id, False),
            (
                "human_approval_projection_version_counter",
                human_approval_projection_version_counter,
                False,
            ),
            ("release_channel", release_channel, False),
            ("release_target", release_target, False),
            ("visibility", visibility, False),
            ("release_configuration_fingerprint", release_configuration_fingerprint, False),
            ("jurisdiction_snapshot_reference", jurisdiction_snapshot_reference, False),
            ("license_evidence_reference", license_evidence_reference, False),
            ("intended_effective_time", intended_effective_time, False),
            (
                "rollback_target_document_version_id",
                rollback_target_document_version_id,
                True,
            ),
        )
    )
    return _derive_canonical_sha256(payload)
