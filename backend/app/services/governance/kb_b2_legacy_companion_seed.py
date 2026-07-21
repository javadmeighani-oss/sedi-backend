"""I5-B2-P1-L1 — controlled legacy companion seed (dry-run-first; fail-closed).

Planning performs zero writes. Apply requires explicit authorization inputs and is
never invoked by this Gate package. Reuses P1 persistence; does not duplicate it.

No network, fetch, publication, scheduler, or startup side effects.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app.models import GovernedSourceProfile, KnowledgeSource
from backend.app.services.governance.contracts import SourceOperationalStatus
from backend.app.services.governance.kb_b2_source_profile_persistence import (
    SourceProfilePersistenceError,
    append_profile_version,
    coerce_governance_evidence,
    compute_snapshot_fingerprint,
    create_or_get_profile,
    get_current_profile_version,
    normalize_canonical_key,
    normalize_locator,
)

SEED_PACKAGE_ID = "i5b2_p1_l1"
SEED_SCHEMA_VERSION = "i5b2_p1_l1_v1"
DEFAULT_OPERATIONAL_STATUS = SourceOperationalStatus.DISABLED.value
OPERATOR_CONFIRM_TOKEN = "CONFIRM_P1_L1_APPLY"

# Gate3h catalog source_key inventory (static extract; evidence never invented).
GATE3H_CATALOG_SOURCE_KEYS: tuple[str, ...] = (
    "who_global_health_topics",
    "medlineplus_consumer_health",
    "nhs_uk_live_well",
    "cdc_health_lifestyle",
    "nice_org_uk_public",
    "who_mental_health",
    "nimh_nih_mental_health",
    "apa_psychology_help",
    "nhs_mental_health",
    "medlineplus_mental_health",
    "irimc_member_search",
    "paziresh24_com",
    "doctoreto_com",
    "nobat_ir",
    "doctor_yab_ir",
    "drdr_ir",
)

_FORBIDDEN_IMPORT_MARKERS: tuple[str, ...] = (
    "urllib.request",
    "httpx",
    "requests",
    "aiohttp",
    "apscheduler",
    "BackgroundScheduler",
)


class EligibilityClass(str, Enum):
    ELIGIBLE_WITH_EXISTING_EVIDENCE = "ELIGIBLE_WITH_EXISTING_EVIDENCE"
    ELIGIBLE_ONLY_WITH_EXPLICIT_MAPPING = "ELIGIBLE_ONLY_WITH_EXPLICIT_MAPPING"
    INELIGIBLE_MISSING_EVIDENCE = "INELIGIBLE_MISSING_EVIDENCE"
    BLOCKED_REQUIRES_PRODUCT_OR_LEGAL_DECISION = "BLOCKED_REQUIRES_PRODUCT_OR_LEGAL_DECISION"
    OUT_OF_SCOPE_NON_SOURCE_OBJECT = "OUT_OF_SCOPE_NON_SOURCE_OBJECT"


class SeedDecision(str, Enum):
    WOULD_CREATE = "would_create"
    WOULD_APPEND = "would_append"
    ALREADY_PRESENT = "already_present"
    INELIGIBLE = "ineligible"
    CONFLICTED = "conflicted"
    BLOCKED = "blocked"
    ERROR = "error"


class SeedActionKind(str, Enum):
    CREATE_PROFILE = "create_profile"
    APPEND_VERSION = "append_version"
    NO_OP = "no_op"
    NONE = "none"


class LegacyCompanionSeedError(Exception):
    """Typed fail-closed seed orchestration error."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class LegacyCompanionSeedCandidate:
    """One legacy companion seed candidate (explicit evidence required for eligibility)."""

    source_key: str
    display_name: str
    locator: Optional[str] = None
    locator_kind: Optional[str] = None
    legacy_knowledge_source_id: Optional[int] = None
    governance_evidence: Optional[Mapping[str, Any]] = None
    product_legal_hold: bool = False


@dataclass(frozen=True)
class LegacyCompanionSeedAction:
    kind: SeedActionKind
    detail: str = ""


@dataclass(frozen=True)
class LegacyCompanionSeedDecision:
    legacy_identifier: str
    canonical_key: str
    normalized_locator: Optional[str]
    eligibility: EligibilityClass
    decision: SeedDecision
    reason: str
    missing_evidence: tuple[str, ...]
    conflicts: tuple[str, ...]
    proposed_operational_status: str
    proposed_fingerprint: Optional[str]
    proposed_actions: tuple[LegacyCompanionSeedAction, ...]
    seed_operation_key: str


@dataclass(frozen=True)
class LegacyCompanionSeedPlan:
    schema_version: str
    dry_run: bool
    plan_digest: str
    decisions: tuple[LegacyCompanionSeedDecision, ...]
    total_scanned: int
    eligible: int
    already_present: int
    would_create: int
    would_append: int
    ineligible: int
    conflicted: int
    blocked: int
    errors: int


@dataclass(frozen=True)
class LegacyCompanionSeedReport:
    plan_digest: str
    applied: bool
    environment: Optional[str]
    committed: tuple[str, ...]
    failed: tuple[str, ...]
    decisions: tuple[LegacyCompanionSeedDecision, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)


_GOVERNANCE_REQUIRED_FIELDS: tuple[str, ...] = (
    "publisher_authority_identity",
    "source_class",
    "authority_evidence_tier",
    "jurisdiction_scope",
    "primary_language",
    "specialty_domain",
    "license_status",
    "permitted_use_restriction",
    "storage_permission",
    "transformation_permission",
    "display_redistribution_permission",
    "automation_status",
    "verification_method",
    "freshness_policy_days",
    "freshness_status",
    "fetch_policy",
    "iran_first_applicable",
    "policy_version_reference",
    "configuration_version_reference",
    "effective_at",
)


def catalog_inventory_candidates() -> tuple[LegacyCompanionSeedCandidate, ...]:
    """Static Gate3h catalog inventory without inventing governance evidence."""
    return tuple(
        LegacyCompanionSeedCandidate(
            source_key=key,
            display_name=key,
            governance_evidence=None,
            product_legal_hold=key
            in {
                "nice_org_uk_public",
                "irimc_member_search",
                "paziresh24_com",
                "doctoreto_com",
                "nobat_ir",
                "doctor_yab_ir",
                "drdr_ir",
            },
        )
        for key in GATE3H_CATALOG_SOURCE_KEYS
    )


def deterministic_canonical_key(source_key: str) -> str:
    if not isinstance(source_key, str) or not source_key.strip():
        raise LegacyCompanionSeedError("source_key_empty")
    return normalize_canonical_key(f"{SEED_PACKAGE_ID}:{source_key.strip()}")


def deterministic_seed_operation_key(
    *,
    canonical_key: str,
    legacy_knowledge_source_id: Optional[int],
    fingerprint: Optional[str],
) -> str:
    payload = {
        "package": SEED_PACKAGE_ID,
        "canonical_key": canonical_key,
        "legacy_knowledge_source_id": legacy_knowledge_source_id,
        "fingerprint": fingerprint,
        "schema": SEED_SCHEMA_VERSION,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _missing_evidence_fields(evidence: Optional[Mapping[str, Any]]) -> tuple[str, ...]:
    if evidence is None:
        return _GOVERNANCE_REQUIRED_FIELDS
    if not isinstance(evidence, Mapping):
        return ("governance_evidence_must_be_mapping",)
    missing: list[str] = []
    for name in _GOVERNANCE_REQUIRED_FIELDS:
        if name not in evidence:
            missing.append(name)
    return tuple(missing)


def _classify_eligibility(
    candidate: LegacyCompanionSeedCandidate,
    missing: Sequence[str],
) -> EligibilityClass:
    if candidate.product_legal_hold:
        return EligibilityClass.BLOCKED_REQUIRES_PRODUCT_OR_LEGAL_DECISION
    if missing:
        if candidate.governance_evidence is None:
            return EligibilityClass.ELIGIBLE_ONLY_WITH_EXPLICIT_MAPPING
        return EligibilityClass.INELIGIBLE_MISSING_EVIDENCE
    return EligibilityClass.ELIGIBLE_WITH_EXISTING_EVIDENCE


def _stable_sort_key(candidate: LegacyCompanionSeedCandidate) -> tuple[str, str, str]:
    return (
        normalize_canonical_key(candidate.source_key)
        if candidate.source_key.strip()
        else "",
        candidate.source_key,
        candidate.display_name or "",
    )


def _decision_digest_row(decision: LegacyCompanionSeedDecision) -> dict[str, Any]:
    return {
        "legacy_identifier": decision.legacy_identifier,
        "canonical_key": decision.canonical_key,
        "normalized_locator": decision.normalized_locator,
        "eligibility": decision.eligibility.value,
        "decision": decision.decision.value,
        "reason": decision.reason,
        "missing_evidence": list(decision.missing_evidence),
        "conflicts": list(decision.conflicts),
        "proposed_operational_status": decision.proposed_operational_status,
        "proposed_fingerprint": decision.proposed_fingerprint,
        "proposed_actions": [a.kind.value for a in decision.proposed_actions],
        "seed_operation_key": decision.seed_operation_key,
    }


def compute_plan_digest(decisions: Sequence[LegacyCompanionSeedDecision]) -> str:
    """Digest is independent of input order (rows sorted by canonical_key)."""
    rows = [_decision_digest_row(d) for d in decisions]
    rows.sort(key=lambda r: (r["canonical_key"], r["legacy_identifier"]))
    payload = {
        "schema_version": SEED_SCHEMA_VERSION,
        "package": SEED_PACKAGE_ID,
        "decisions": rows,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _summarize(decisions: Sequence[LegacyCompanionSeedDecision]) -> dict[str, int]:
    counts = {
        "eligible": 0,
        "already_present": 0,
        "would_create": 0,
        "would_append": 0,
        "ineligible": 0,
        "conflicted": 0,
        "blocked": 0,
        "errors": 0,
    }
    for d in decisions:
        if d.decision == SeedDecision.ALREADY_PRESENT:
            counts["already_present"] += 1
            counts["eligible"] += 1
        elif d.decision == SeedDecision.WOULD_CREATE:
            counts["would_create"] += 1
            counts["eligible"] += 1
        elif d.decision == SeedDecision.WOULD_APPEND:
            counts["would_append"] += 1
            counts["eligible"] += 1
        elif d.decision == SeedDecision.INELIGIBLE:
            counts["ineligible"] += 1
        elif d.decision == SeedDecision.CONFLICTED:
            counts["conflicted"] += 1
        elif d.decision == SeedDecision.BLOCKED:
            counts["blocked"] += 1
        elif d.decision == SeedDecision.ERROR:
            counts["errors"] += 1
    return counts


def evaluate_candidate(
    session: Optional[Session],
    candidate: LegacyCompanionSeedCandidate,
) -> LegacyCompanionSeedDecision:
    """Evaluate one candidate. Session may be None for pure static planning."""
    missing = _missing_evidence_fields(candidate.governance_evidence)
    eligibility = _classify_eligibility(candidate, missing)
    try:
        canonical_key = deterministic_canonical_key(candidate.source_key)
    except LegacyCompanionSeedError as exc:
        return LegacyCompanionSeedDecision(
            legacy_identifier=candidate.source_key,
            canonical_key="",
            normalized_locator=None,
            eligibility=EligibilityClass.INELIGIBLE_MISSING_EVIDENCE,
            decision=SeedDecision.ERROR,
            reason=exc.reason,
            missing_evidence=missing,
            conflicts=(),
            proposed_operational_status=DEFAULT_OPERATIONAL_STATUS,
            proposed_fingerprint=None,
            proposed_actions=(LegacyCompanionSeedAction(SeedActionKind.NONE),),
            seed_operation_key="",
        )

    locator_kind = candidate.locator_kind
    locator = candidate.locator
    normalized_locator: Optional[str] = None
    conflicts: list[str] = []
    fingerprint: Optional[str] = None

    if eligibility == EligibilityClass.BLOCKED_REQUIRES_PRODUCT_OR_LEGAL_DECISION:
        op_key = deterministic_seed_operation_key(
            canonical_key=canonical_key,
            legacy_knowledge_source_id=candidate.legacy_knowledge_source_id,
            fingerprint=None,
        )
        return LegacyCompanionSeedDecision(
            legacy_identifier=candidate.source_key,
            canonical_key=canonical_key,
            normalized_locator=None,
            eligibility=eligibility,
            decision=SeedDecision.BLOCKED,
            reason="blocked_requires_product_or_legal_decision",
            missing_evidence=missing,
            conflicts=(),
            proposed_operational_status=DEFAULT_OPERATIONAL_STATUS,
            proposed_fingerprint=None,
            proposed_actions=(LegacyCompanionSeedAction(SeedActionKind.NONE),),
            seed_operation_key=op_key,
        )

    if missing:
        op_key = deterministic_seed_operation_key(
            canonical_key=canonical_key,
            legacy_knowledge_source_id=candidate.legacy_knowledge_source_id,
            fingerprint=None,
        )
        reason = (
            "eligible_only_with_explicit_mapping"
            if eligibility == EligibilityClass.ELIGIBLE_ONLY_WITH_EXPLICIT_MAPPING
            else "ineligible_missing_evidence"
        )
        return LegacyCompanionSeedDecision(
            legacy_identifier=candidate.source_key,
            canonical_key=canonical_key,
            normalized_locator=None,
            eligibility=eligibility,
            decision=SeedDecision.INELIGIBLE,
            reason=reason,
            missing_evidence=missing,
            conflicts=(),
            proposed_operational_status=DEFAULT_OPERATIONAL_STATUS,
            proposed_fingerprint=None,
            proposed_actions=(LegacyCompanionSeedAction(SeedActionKind.NONE),),
            seed_operation_key=op_key,
        )

    try:
        kind, loc = normalize_locator(locator_kind, locator)
        normalized_locator = loc
        evidence = coerce_governance_evidence(candidate.governance_evidence or {})
        fingerprint = compute_snapshot_fingerprint(evidence)
    except SourceProfilePersistenceError as exc:
        op_key = deterministic_seed_operation_key(
            canonical_key=canonical_key,
            legacy_knowledge_source_id=candidate.legacy_knowledge_source_id,
            fingerprint=None,
        )
        return LegacyCompanionSeedDecision(
            legacy_identifier=candidate.source_key,
            canonical_key=canonical_key,
            normalized_locator=None,
            eligibility=EligibilityClass.INELIGIBLE_MISSING_EVIDENCE,
            decision=SeedDecision.ERROR,
            reason=exc.reason,
            missing_evidence=missing,
            conflicts=(),
            proposed_operational_status=DEFAULT_OPERATIONAL_STATUS,
            proposed_fingerprint=None,
            proposed_actions=(LegacyCompanionSeedAction(SeedActionKind.NONE),),
            seed_operation_key=op_key,
        )

    op_key = deterministic_seed_operation_key(
        canonical_key=canonical_key,
        legacy_knowledge_source_id=candidate.legacy_knowledge_source_id,
        fingerprint=fingerprint,
    )

    if session is None:
        return LegacyCompanionSeedDecision(
            legacy_identifier=candidate.source_key,
            canonical_key=canonical_key,
            normalized_locator=normalized_locator,
            eligibility=eligibility,
            decision=SeedDecision.WOULD_CREATE,
            reason="would_create_profile_and_version",
            missing_evidence=(),
            conflicts=(),
            proposed_operational_status=DEFAULT_OPERATIONAL_STATUS,
            proposed_fingerprint=fingerprint,
            proposed_actions=(
                LegacyCompanionSeedAction(SeedActionKind.CREATE_PROFILE),
                LegacyCompanionSeedAction(SeedActionKind.APPEND_VERSION),
            ),
            seed_operation_key=op_key,
        )

    # Session-backed conflict and presence checks (read-only).
    try:
        existing = (
            session.query(GovernedSourceProfile)
            .filter(GovernedSourceProfile.canonical_key == canonical_key)
            .one_or_none()
        )
        if existing is not None:
            if (
                existing.locator_kind != kind
                or existing.normalized_locator != loc
                or existing.legacy_knowledge_source_id
                != candidate.legacy_knowledge_source_id
            ):
                conflicts.append("canonical_key_identity_conflict")
            else:
                current = None
                if existing.current_profile_version_id is not None:
                    current = get_current_profile_version(session, profile_id=existing.id)
                if current is not None and current.snapshot_fingerprint == fingerprint:
                    return LegacyCompanionSeedDecision(
                        legacy_identifier=candidate.source_key,
                        canonical_key=canonical_key,
                        normalized_locator=normalized_locator,
                        eligibility=eligibility,
                        decision=SeedDecision.ALREADY_PRESENT,
                        reason="already_present_identical_fingerprint",
                        missing_evidence=(),
                        conflicts=(),
                        proposed_operational_status=existing.operational_status,
                        proposed_fingerprint=fingerprint,
                        proposed_actions=(
                            LegacyCompanionSeedAction(SeedActionKind.NO_OP),
                        ),
                        seed_operation_key=op_key,
                    )
                if current is not None and current.snapshot_fingerprint != fingerprint:
                    return LegacyCompanionSeedDecision(
                        legacy_identifier=candidate.source_key,
                        canonical_key=canonical_key,
                        normalized_locator=normalized_locator,
                        eligibility=eligibility,
                        decision=SeedDecision.BLOCKED,
                        reason="block_requires_separate_approval",
                        missing_evidence=(),
                        conflicts=("changed_governed_evidence",),
                        proposed_operational_status=existing.operational_status,
                        proposed_fingerprint=fingerprint,
                        proposed_actions=(
                            LegacyCompanionSeedAction(SeedActionKind.NONE),
                        ),
                        seed_operation_key=op_key,
                    )
                # Profile exists without current version — would append initial.
                return LegacyCompanionSeedDecision(
                    legacy_identifier=candidate.source_key,
                    canonical_key=canonical_key,
                    normalized_locator=normalized_locator,
                    eligibility=eligibility,
                    decision=SeedDecision.WOULD_APPEND,
                    reason="would_append_initial_version",
                    missing_evidence=(),
                    conflicts=(),
                    proposed_operational_status=DEFAULT_OPERATIONAL_STATUS,
                    proposed_fingerprint=fingerprint,
                    proposed_actions=(
                        LegacyCompanionSeedAction(SeedActionKind.APPEND_VERSION),
                    ),
                    seed_operation_key=op_key,
                )

        if kind is not None and loc is not None:
            locator_hit = (
                session.query(GovernedSourceProfile)
                .filter(
                    GovernedSourceProfile.locator_kind == kind,
                    GovernedSourceProfile.normalized_locator == loc,
                )
                .one_or_none()
            )
            if locator_hit is not None:
                conflicts.append("locator_identity_conflict")

        if candidate.legacy_knowledge_source_id is not None:
            legacy_hit = (
                session.query(GovernedSourceProfile)
                .filter(
                    GovernedSourceProfile.legacy_knowledge_source_id
                    == candidate.legacy_knowledge_source_id
                )
                .one_or_none()
            )
            if legacy_hit is not None:
                conflicts.append("legacy_knowledge_source_conflict")
            ks = session.get(KnowledgeSource, candidate.legacy_knowledge_source_id)
            if ks is None:
                conflicts.append("legacy_knowledge_source_missing")

        if conflicts:
            return LegacyCompanionSeedDecision(
                legacy_identifier=candidate.source_key,
                canonical_key=canonical_key,
                normalized_locator=normalized_locator,
                eligibility=eligibility,
                decision=SeedDecision.CONFLICTED,
                reason="identity_conflict",
                missing_evidence=(),
                conflicts=tuple(conflicts),
                proposed_operational_status=DEFAULT_OPERATIONAL_STATUS,
                proposed_fingerprint=fingerprint,
                proposed_actions=(LegacyCompanionSeedAction(SeedActionKind.NONE),),
                seed_operation_key=op_key,
            )

        return LegacyCompanionSeedDecision(
            legacy_identifier=candidate.source_key,
            canonical_key=canonical_key,
            normalized_locator=normalized_locator,
            eligibility=eligibility,
            decision=SeedDecision.WOULD_CREATE,
            reason="would_create_profile_and_version",
            missing_evidence=(),
            conflicts=(),
            proposed_operational_status=DEFAULT_OPERATIONAL_STATUS,
            proposed_fingerprint=fingerprint,
            proposed_actions=(
                LegacyCompanionSeedAction(SeedActionKind.CREATE_PROFILE),
                LegacyCompanionSeedAction(SeedActionKind.APPEND_VERSION),
            ),
            seed_operation_key=op_key,
        )
    except SourceProfilePersistenceError as exc:
        return LegacyCompanionSeedDecision(
            legacy_identifier=candidate.source_key,
            canonical_key=canonical_key,
            normalized_locator=normalized_locator,
            eligibility=eligibility,
            decision=SeedDecision.ERROR,
            reason=exc.reason,
            missing_evidence=(),
            conflicts=tuple(conflicts),
            proposed_operational_status=DEFAULT_OPERATIONAL_STATUS,
            proposed_fingerprint=fingerprint,
            proposed_actions=(LegacyCompanionSeedAction(SeedActionKind.NONE),),
            seed_operation_key=op_key,
        )


def build_plan(
    session: Optional[Session],
    candidates: Sequence[LegacyCompanionSeedCandidate],
    *,
    dry_run: bool = True,
) -> LegacyCompanionSeedPlan:
    """Build a deterministic plan. Never writes."""
    ordered = sorted(candidates, key=_stable_sort_key)
    decisions = tuple(evaluate_candidate(session, c) for c in ordered)
    # Re-sort decisions by canonical_key for digest stability if keys collide on empty.
    decisions_sorted = tuple(
        sorted(decisions, key=lambda d: (d.canonical_key, d.legacy_identifier))
    )
    digest = compute_plan_digest(decisions_sorted)
    summary = _summarize(decisions_sorted)
    return LegacyCompanionSeedPlan(
        schema_version=SEED_SCHEMA_VERSION,
        dry_run=dry_run,
        plan_digest=digest,
        decisions=decisions_sorted,
        total_scanned=len(decisions_sorted),
        eligible=summary["eligible"],
        already_present=summary["already_present"],
        would_create=summary["would_create"],
        would_append=summary["would_append"],
        ineligible=summary["ineligible"],
        conflicted=summary["conflicted"],
        blocked=summary["blocked"],
        errors=summary["errors"],
    )


def _require_apply_authorization(
    *,
    dry_run: bool,
    target_environment: Optional[str],
    candidate_allowlist: Optional[Sequence[str]],
    expected_plan_digest: Optional[str],
    operator_confirmation: Optional[str],
    plan: LegacyCompanionSeedPlan,
) -> None:
    if dry_run:
        raise LegacyCompanionSeedError("apply_requires_dry_run_false")
    if not target_environment or not str(target_environment).strip():
        raise LegacyCompanionSeedError("apply_requires_target_environment")
    if candidate_allowlist is None or len(tuple(candidate_allowlist)) == 0:
        raise LegacyCompanionSeedError("apply_requires_candidate_allowlist")
    if not expected_plan_digest or not str(expected_plan_digest).strip():
        raise LegacyCompanionSeedError("apply_requires_expected_plan_digest")
    if expected_plan_digest != plan.plan_digest:
        raise LegacyCompanionSeedError("apply_plan_digest_mismatch")
    if operator_confirmation != OPERATOR_CONFIRM_TOKEN:
        raise LegacyCompanionSeedError("apply_requires_operator_confirmation")


def apply_plan(
    session: Session,
    candidates: Sequence[LegacyCompanionSeedCandidate],
    *,
    dry_run: bool = True,
    target_environment: Optional[str] = None,
    candidate_allowlist: Optional[Sequence[str]] = None,
    expected_plan_digest: Optional[str] = None,
    operator_confirmation: Optional[str] = None,
) -> LegacyCompanionSeedReport:
    """Apply an authorized plan. Default dry_run=True refuses writes."""
    plan = build_plan(session, candidates, dry_run=dry_run)
    if dry_run:
        return LegacyCompanionSeedReport(
            plan_digest=plan.plan_digest,
            applied=False,
            environment=target_environment,
            committed=(),
            failed=(),
            decisions=plan.decisions,
            notes=("dry_run_zero_writes",),
        )

    _require_apply_authorization(
        dry_run=dry_run,
        target_environment=target_environment,
        candidate_allowlist=candidate_allowlist,
        expected_plan_digest=expected_plan_digest,
        operator_confirmation=operator_confirmation,
        plan=plan,
    )
    allow_raw = {str(k) for k in (candidate_allowlist or ())}
    committed: list[str] = []
    failed: list[str] = []
    by_key = {c.source_key: c for c in candidates}

    for decision in plan.decisions:
        if decision.legacy_identifier not in allow_raw:
            continue
        if decision.decision not in (
            SeedDecision.WOULD_CREATE,
            SeedDecision.WOULD_APPEND,
            SeedDecision.ALREADY_PRESENT,
        ):
            continue
        if decision.decision == SeedDecision.ALREADY_PRESENT:
            committed.append(decision.legacy_identifier)
            continue
        candidate = by_key.get(decision.legacy_identifier)
        if candidate is None:
            failed.append(decision.legacy_identifier)
            continue
        try:
            with session.begin_nested():
                profile = (
                    session.query(GovernedSourceProfile)
                    .filter(GovernedSourceProfile.canonical_key == decision.canonical_key)
                    .with_for_update()
                    .one_or_none()
                )
                if profile is None:
                    profile = create_or_get_profile(
                        session,
                        canonical_key=decision.canonical_key,
                        locator_kind=candidate.locator_kind,
                        locator=candidate.locator,
                        legacy_knowledge_source_id=candidate.legacy_knowledge_source_id,
                    )
                if profile.operational_status != DEFAULT_OPERATIONAL_STATUS:
                    raise LegacyCompanionSeedError("operational_status_must_remain_disabled")
                version = append_profile_version(
                    session,
                    profile_id=profile.id,
                    governance_evidence=dict(candidate.governance_evidence or {}),
                )
                session.refresh(profile)
                if profile.operational_status != DEFAULT_OPERATIONAL_STATUS:
                    raise LegacyCompanionSeedError("operational_status_must_remain_disabled")
                if profile.current_profile_version_id != version.id:
                    raise LegacyCompanionSeedError("current_pointer_integrity_conflict")
            committed.append(decision.legacy_identifier)
        except (SourceProfilePersistenceError, LegacyCompanionSeedError) as exc:
            failed.append(f"{decision.legacy_identifier}:{getattr(exc, 'reason', str(exc))}")

    return LegacyCompanionSeedReport(
        plan_digest=plan.plan_digest,
        applied=True,
        environment=target_environment,
        committed=tuple(committed),
        failed=tuple(failed),
        decisions=plan.decisions,
        notes=("apply_completed",),
    )


def assert_module_security_boundaries(source_text: str) -> None:
    """Static helper for tests: reject network/scheduler markers in this module."""
    for marker in _FORBIDDEN_IMPORT_MARKERS:
        if marker in source_text:
            raise LegacyCompanionSeedError(f"forbidden_marker_present:{marker}")
    for forbidden in (
        "create_publication",
        "PublicationRelease",
        "run_scheduled",
        "KnowledgeSourceFetcher",
        "fetch_source(",
    ):
        if forbidden in source_text:
            raise LegacyCompanionSeedError(f"forbidden_side_effect:{forbidden}")
