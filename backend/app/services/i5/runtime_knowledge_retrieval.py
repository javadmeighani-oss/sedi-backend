"""I5-IMPL-W4-P01 — Knowledge-Database-First runtime retrieval (activation-neutral).

Owns safe KU/Memory retrieval + structured context envelope for CARE_CONTEXT.
Reuses W2-P02 eligibility / W2-P01 memory eligibility. Synthesis / reference
rendering belong to W4-P02. No live network, no migration, no base-model
medical fallback.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from backend.app.services.i5.enums import (
    EvidenceStrength,
    KnowledgeGapPriority,
    KnowledgeGapSeverity,
    KnowledgeGapStatus,
    KnowledgeGapType,
    KnowledgeGapUrgency,
    KnowledgeUnitRuntimeEligibility,
    SupersessionState,
)
from backend.app.services.i5.knowledge_memory_service import evaluate_memory_eligibility
from backend.app.services.i5.runtime_eligibility_gate import (
    evaluate_knowledge_unit_eligibility,
)

PACKAGE_ID = "I5-IMPL-W4-P01"
MANAGEMENT_ALIAS = "P08"
SERVICE_NAME = "runtime_knowledge_retrieval"
DEFAULT_LIMIT = 3
MAX_LIMIT = 10

# Frozen retrieval statuses (W4-P01 design freeze; not W4-P02 answer literals).
STATUS_OK = "OK"
STATUS_NO_ELIGIBLE_KNOWLEDGE = "NO_ELIGIBLE_KNOWLEDGE"
STATUS_MULTIPLE_CURRENT_FAIL_CLOSED = "MULTIPLE_CURRENT_FAIL_CLOSED"
STATUS_BROKEN_VERSION_CHAIN = "BROKEN_VERSION_CHAIN"
STATUS_INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"

NO_BASE_MODEL_FALLBACK = True

_EVIDENCE_RANK: dict[str, int] = {
    EvidenceStrength.HIGH.value: 3,
    EvidenceStrength.MODERATE.value: 2,
    EvidenceStrength.LOW.value: 1,
}

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


class RuntimeKnowledgeRetrievalError(ValueError):
    """Fail-closed retrieval error."""


@dataclass(frozen=True)
class NormalizedQuery:
    original_query: str
    normalized_query: str
    tokens: tuple[str, ...]


@dataclass
class ExclusionRecord:
    knowledge_unit_id: Optional[int]
    canonical_unit_id: Optional[str]
    reason: str


@dataclass
class RetrievedKnowledgeItem:
    knowledge_unit_id: int
    canonical_unit_id: str
    immutable_version_id: str
    memory_item_id: str
    memory_row_id: int
    source_profile_id: Optional[int]
    provenance_id: Optional[int]
    raw_evidence_id: Optional[int]
    domain: str
    language: str
    topic_taxonomy: Optional[str]
    normalized_statement: str
    evidence_strength: str
    freshness_state: str
    conflict_state: str
    medical_safety_state: str
    runtime_eligibility: str
    rank_score: int
    inclusion_reasons: list[str] = field(default_factory=list)

    def as_care_snippet(self) -> dict[str, Any]:
        """CARE_CONTEXT-compatible snippet; citation rendering owned by W4-P02."""
        return {
            "content": self.normalized_statement,
            "knowledge_unit_id": self.knowledge_unit_id,
            "canonical_unit_id": self.canonical_unit_id,
            "immutable_version_id": self.immutable_version_id,
            "memory_item_id": self.memory_item_id,
            "provenance_id": self.provenance_id,
            "source_profile_id": self.source_profile_id,
            "citation": {
                "label": f"KU:{self.canonical_unit_id}:{self.immutable_version_id}",
                "handoff": "W4-P02",
            },
            "evidence_strength": self.evidence_strength,
            "inclusion_reasons": list(self.inclusion_reasons),
        }

    def w4p02_handoff(self) -> dict[str, Any]:
        return {
            "knowledge_unit_id": self.knowledge_unit_id,
            "canonical_unit_id": self.canonical_unit_id,
            "immutable_version_id": self.immutable_version_id,
            "memory_item_id": self.memory_item_id,
            "provenance_id": self.provenance_id,
            "source_profile_id": self.source_profile_id,
            "raw_evidence_id": self.raw_evidence_id,
            "normalized_statement": self.normalized_statement,
            "evidence_strength": self.evidence_strength,
            "render_owned_by": "I5-IMPL-W4-P02",
        }


@dataclass
class RetrievalResult:
    package_id: str = PACKAGE_ID
    status: str = STATUS_OK
    query_id: str = ""
    trace_id: str = ""
    original_query: str = ""
    normalized_query: str = ""
    user_id_scope: Optional[int] = None
    language_filter: Optional[str] = None
    domain_filter: Optional[str] = None
    items: list[RetrievedKnowledgeItem] = field(default_factory=list)
    exclusions: list[ExclusionRecord] = field(default_factory=list)
    exclusion_counts: dict[str, int] = field(default_factory=dict)
    gap_id: Optional[int] = None
    no_base_model_fallback: bool = NO_BASE_MODEL_FALLBACK
    clarification_required: bool = False
    escalation_required: bool = False
    safe_user_facing_intent: str = (
        "No safe governed knowledge is available for this query; "
        "do not invent medical content."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "status": self.status,
            "query_id": self.query_id,
            "trace_id": self.trace_id,
            "original_query": self.original_query,
            "normalized_query": self.normalized_query,
            "user_id_scope": self.user_id_scope,
            "language_filter": self.language_filter,
            "domain_filter": self.domain_filter,
            "retrieved_count": len(self.items),
            "items": [
                {
                    "knowledge_unit_id": i.knowledge_unit_id,
                    "canonical_unit_id": i.canonical_unit_id,
                    "immutable_version_id": i.immutable_version_id,
                    "memory_item_id": i.memory_item_id,
                    "memory_row_id": i.memory_row_id,
                    "source_profile_id": i.source_profile_id,
                    "provenance_id": i.provenance_id,
                    "raw_evidence_id": i.raw_evidence_id,
                    "domain": i.domain,
                    "language": i.language,
                    "topic_taxonomy": i.topic_taxonomy,
                    "normalized_statement": i.normalized_statement,
                    "evidence_strength": i.evidence_strength,
                    "freshness_state": i.freshness_state,
                    "conflict_state": i.conflict_state,
                    "medical_safety_state": i.medical_safety_state,
                    "runtime_eligibility": i.runtime_eligibility,
                    "rank_score": i.rank_score,
                    "inclusion_reasons": list(i.inclusion_reasons),
                    "w4p02_handoff": i.w4p02_handoff(),
                }
                for i in self.items
            ],
            "exclusions": [
                {
                    "knowledge_unit_id": e.knowledge_unit_id,
                    "canonical_unit_id": e.canonical_unit_id,
                    "reason": e.reason,
                }
                for e in self.exclusions
            ],
            "exclusion_counts": dict(self.exclusion_counts),
            "gap_id": self.gap_id,
            "no_base_model_fallback": self.no_base_model_fallback,
            "clarification_required": self.clarification_required,
            "escalation_required": self.escalation_required,
            "safe_user_facing_intent": self.safe_user_facing_intent,
            "knowledge_snippets": [i.as_care_snippet() for i in self.items],
        }


def _sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_query(original_query: str) -> NormalizedQuery:
    """Deterministic normalization; original preserved for audit."""
    if original_query is None:
        raise RuntimeKnowledgeRetrievalError("QUERY_REQUIRED")
    original = str(original_query)
    nf = unicodedata.normalize("NFKC", original)
    lowered = nf.casefold()
    stripped_punct = _PUNCT_RE.sub(" ", lowered)
    collapsed = _WS_RE.sub(" ", stripped_punct).strip()
    tokens = tuple(t for t in collapsed.split(" ") if t)
    return NormalizedQuery(
        original_query=original,
        normalized_query=collapsed,
        tokens=tokens,
    )


def clamp_limit(limit: Optional[int]) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise RuntimeKnowledgeRetrievalError("LIMIT_INVALID") from exc
    if value < 1:
        raise RuntimeKnowledgeRetrievalError("LIMIT_INVALID")
    return min(value, MAX_LIMIT)


def _token_overlap_score(tokens: Sequence[str], text: str) -> int:
    if not tokens:
        return 0
    hay = normalize_query(text or "").normalized_query
    hay_tokens = set(hay.split(" ")) if hay else set()
    return sum(1 for t in tokens if t in hay_tokens)


def _rank_score(evidence_strength: str, overlap: int, knowledge_unit_id: int) -> int:
    """Deterministic ranking key component (higher better). Tie-break by -id later."""
    strength = _EVIDENCE_RANK.get(str(evidence_strength), 0)
    # Pack into single int: strength dominates, then overlap, then inverse id via sort
    return strength * 1_000_000 + overlap * 1_000


def _bump(counts: dict[str, int], reason: str) -> None:
    counts[reason] = counts.get(reason, 0) + 1


def _exclude(
    exclusions: list[ExclusionRecord],
    counts: dict[str, int],
    *,
    ku_id: Optional[int],
    canonical_unit_id: Optional[str],
    reason: str,
) -> None:
    exclusions.append(
        ExclusionRecord(
            knowledge_unit_id=ku_id,
            canonical_unit_id=canonical_unit_id,
            reason=reason,
        )
    )
    _bump(counts, reason)


def resolve_current_version_candidates(
    memory_rows: Sequence[Any],
    units_by_id: Mapping[int, Any],
) -> tuple[list[Any], list[ExclusionRecord], dict[str, int], Optional[str]]:
    """Keep CURRENT memory rows; fail-closed on multi-current or broken chains."""
    exclusions: list[ExclusionRecord] = []
    counts: dict[str, int] = {}
    by_canon: dict[str, list[Any]] = {}
    status_override: Optional[str] = None

    for mem in memory_rows:
        ku = units_by_id.get(getattr(mem, "knowledge_unit_id", None))
        if ku is None:
            _exclude(
                exclusions,
                counts,
                ku_id=getattr(mem, "knowledge_unit_id", None),
                canonical_unit_id=None,
                reason="MISSING_KNOWLEDGE_UNIT",
            )
            continue
        if str(getattr(mem, "supersession_state", "")) != SupersessionState.CURRENT.value:
            _exclude(
                exclusions,
                counts,
                ku_id=ku.id,
                canonical_unit_id=ku.canonical_unit_id,
                reason="NOT_CURRENT_MEMORY",
            )
            continue
        parent_id = getattr(ku, "supersedes_unit_id", None)
        if parent_id is not None and parent_id not in units_by_id:
            # Parent may be outside loaded set — load check deferred by caller via
            # units_by_id completeness; treat missing parent as broken chain.
            _exclude(
                exclusions,
                counts,
                ku_id=ku.id,
                canonical_unit_id=ku.canonical_unit_id,
                reason="BROKEN_VERSION_CHAIN",
            )
            status_override = STATUS_BROKEN_VERSION_CHAIN
            continue
        by_canon.setdefault(str(ku.canonical_unit_id), []).append(mem)

    survivors: list[Any] = []
    for canon, group in by_canon.items():
        if len(group) > 1:
            for mem in group:
                ku = units_by_id[mem.knowledge_unit_id]
                _exclude(
                    exclusions,
                    counts,
                    ku_id=ku.id,
                    canonical_unit_id=canon,
                    reason="MULTIPLE_CURRENT_CANDIDATES",
                )
            status_override = STATUS_MULTIPLE_CURRENT_FAIL_CLOSED
            continue
        survivors.extend(group)
    return survivors, exclusions, counts, status_override


def enqueue_runtime_retrieval_gap(
    db: Any,
    *,
    original_query: str,
    normalized_query: str,
    domain: str,
    trace_id: str,
    status: str,
) -> Any:
    """Create KnowledgeGap for runtime retrieval failure (TESTS_TO_AUTHOR fallback+gap)."""
    from backend.app import models

    key_material = f"w4p01|{domain}|{normalized_query}|{status}|{trace_id}"
    row = models.KnowledgeGap(
        canonical_gap_key=_sha256_hex(key_material),
        canonicalization_version="v1",
        hash_algorithm="SHA-256",
        domain=domain or "unknown",
        gap_type=KnowledgeGapType.RUNTIME_RETRIEVAL_FAILURE.value,
        title=f"W4-P01 runtime retrieval: {status}",
        description=(
            f"No safe governed knowledge returned. status={status} "
            f"trace_id={trace_id}"
        ),
        evidence_of_gap=original_query[:2000],
        current_knowledge_state="NO_ELIGIBLE_RETRIEVED",
        required_knowledge_state="ELIGIBLE_CURRENT_CLEARED_WITH_PROVENANCE",
        priority=KnowledgeGapPriority.P2.value,
        severity=KnowledgeGapSeverity.MEDIUM.value,
        urgency=KnowledgeGapUrgency.NORMAL.value,
        status=KnowledgeGapStatus.OPEN.value,
        target_package_id=PACKAGE_ID,
        discovered_by=SERVICE_NAME,
        next_action="Author or clear governed KU/Memory for this query family",
        capability_id="CAP-OPEN-15",
    )
    db.add(row)
    db.flush()
    return row


def retrieve_knowledge_context(
    db: Any,
    query: str,
    *,
    user_id: Optional[int] = None,
    language: Optional[str] = None,
    domain: Optional[str] = None,
    limit: Optional[int] = None,
    enqueue_gap_on_empty: bool = True,
    require_query_tokens: bool = False,
) -> RetrievalResult:
    """Knowledge-DB-first retrieval with fail-closed eligibility filters.

    Personalization boundary: language + domain filters only. user_id is audit
    scope only and must not override eligibility or leak cross-user PHI into KU.
    """
    from backend.app import models

    nq = normalize_query(query)
    lim = clamp_limit(limit)
    trace_id = str(uuid.uuid4())
    query_id = _sha256_hex(f"{trace_id}|{nq.normalized_query}")[:32]

    result = RetrievalResult(
        status=STATUS_OK,
        query_id=query_id,
        trace_id=trace_id,
        original_query=nq.original_query,
        normalized_query=nq.normalized_query,
        user_id_scope=user_id,
        language_filter=(language.strip() if language else None),
        domain_filter=(domain.strip() if domain else None),
        no_base_model_fallback=NO_BASE_MODEL_FALLBACK,
    )

    if require_query_tokens and not nq.tokens:
        result.status = STATUS_INSUFFICIENT_CONTEXT
        result.clarification_required = True
        result.safe_user_facing_intent = (
            "Query is empty after normalization; clarification required."
        )
        if enqueue_gap_on_empty:
            gap = enqueue_runtime_retrieval_gap(
                db,
                original_query=nq.original_query,
                normalized_query=nq.normalized_query or "",
                domain=result.domain_filter or "unknown",
                trace_id=trace_id,
                status=result.status,
            )
            result.gap_id = gap.id
        return result

    # Load CURRENT memory candidates (version resolution entry point).
    q = db.query(models.KnowledgeMemoryItem).filter(
        models.KnowledgeMemoryItem.supersession_state == SupersessionState.CURRENT.value
    )
    memory_rows = q.all()

    ku_ids = {m.knowledge_unit_id for m in memory_rows}
    # Also load supersession parents for chain integrity.
    units = (
        db.query(models.KnowledgeUnit)
        .filter(models.KnowledgeUnit.id.in_(ku_ids))
        .all()
        if ku_ids
        else []
    )
    units_by_id: dict[int, Any] = {u.id: u for u in units}
    parent_ids = {
        u.supersedes_unit_id
        for u in units
        if getattr(u, "supersedes_unit_id", None) is not None
    }
    missing_parents = parent_ids - set(units_by_id)
    if missing_parents:
        parents = (
            db.query(models.KnowledgeUnit)
            .filter(models.KnowledgeUnit.id.in_(missing_parents))
            .all()
        )
        for p in parents:
            units_by_id[p.id] = p
        # Remaining missing parents stay absent → broken chain in resolver.

    survivors, excl, counts, status_override = resolve_current_version_candidates(
        memory_rows, units_by_id
    )
    result.exclusions.extend(excl)
    for k, v in counts.items():
        result.exclusion_counts[k] = result.exclusion_counts.get(k, 0) + v

    # Provenance rows
    survivor_ku_ids = [m.knowledge_unit_id for m in survivors]
    prov_rows = (
        db.query(models.KnowledgeProvenance)
        .filter(models.KnowledgeProvenance.knowledge_unit_id.in_(survivor_ku_ids))
        .all()
        if survivor_ku_ids
        else []
    )
    prov_by_ku = {p.knowledge_unit_id: p for p in prov_rows}

    candidates: list[RetrievedKnowledgeItem] = []
    for mem in survivors:
        ku = units_by_id[mem.knowledge_unit_id]
        canon = str(ku.canonical_unit_id)

        # Domain / language filters (owned personalization / taxonomy boundary)
        if result.domain_filter and str(ku.domain) != result.domain_filter:
            _exclude(
                result.exclusions,
                result.exclusion_counts,
                ku_id=ku.id,
                canonical_unit_id=canon,
                reason="DOMAIN_FILTER",
            )
            continue
        if result.language_filter and str(ku.language) != result.language_filter:
            _exclude(
                result.exclusions,
                result.exclusion_counts,
                ku_id=ku.id,
                canonical_unit_id=canon,
                reason="LANGUAGE_FILTER",
            )
            continue

        mem_elig = evaluate_memory_eligibility(mem)
        if mem_elig != KnowledgeUnitRuntimeEligibility.ELIGIBLE:
            _exclude(
                result.exclusions,
                result.exclusion_counts,
                ku_id=ku.id,
                canonical_unit_id=canon,
                reason=f"MEMORY_NOT_ELIGIBLE:{mem_elig.value}",
            )
            continue

        ku_elig = evaluate_knowledge_unit_eligibility(ku)
        if ku_elig != KnowledgeUnitRuntimeEligibility.ELIGIBLE:
            _exclude(
                result.exclusions,
                result.exclusion_counts,
                ku_id=ku.id,
                canonical_unit_id=canon,
                reason=f"KU_NOT_ELIGIBLE:{ku_elig.value}",
            )
            continue

        # Stored runtime_eligibility must already be ELIGIBLE (matrix + column).
        if str(ku.runtime_eligibility) != KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
            _exclude(
                result.exclusions,
                result.exclusion_counts,
                ku_id=ku.id,
                canonical_unit_id=canon,
                reason="RUNTIME_ELIGIBILITY_COLUMN_NOT_ELIGIBLE",
            )
            continue

        if not bool(ku.provenance_complete):
            _exclude(
                result.exclusions,
                result.exclusion_counts,
                ku_id=ku.id,
                canonical_unit_id=canon,
                reason="PROVENANCE_INCOMPLETE_FLAG",
            )
            continue

        prov = prov_by_ku.get(ku.id)
        if prov is None:
            _exclude(
                result.exclusions,
                result.exclusion_counts,
                ku_id=ku.id,
                canonical_unit_id=canon,
                reason="MISSING_PROVENANCE_ROW",
            )
            continue

        if getattr(ku, "retraction_reason", None):
            _exclude(
                result.exclusions,
                result.exclusion_counts,
                ku_id=ku.id,
                canonical_unit_id=canon,
                reason="RETRACTED",
            )
            continue

        pub = str(getattr(ku, "publication_state", "") or "")
        if pub in {"SUPERSEDED", "WITHDRAWN"}:
            _exclude(
                result.exclusions,
                result.exclusion_counts,
                ku_id=ku.id,
                canonical_unit_id=canon,
                reason=f"PUBLICATION_{pub}",
            )
            continue

        overlap = _token_overlap_score(
            nq.tokens,
            " ".join(
                [
                    str(ku.normalized_statement or ""),
                    str(ku.topic_taxonomy or ""),
                    str(ku.disease_or_health_condition or ""),
                    str(ku.domain or ""),
                ]
            ),
        )
        # Empty query tokens: allow eligible CURRENT items (browse/filter mode).
        if nq.tokens and overlap < 1:
            _exclude(
                result.exclusions,
                result.exclusion_counts,
                ku_id=ku.id,
                canonical_unit_id=canon,
                reason="QUERY_NO_MATCH",
            )
            continue

        score = _rank_score(str(ku.evidence_strength), overlap, ku.id)
        candidates.append(
            RetrievedKnowledgeItem(
                knowledge_unit_id=ku.id,
                canonical_unit_id=canon,
                immutable_version_id=str(ku.immutable_version_id),
                memory_item_id=str(mem.memory_item_id),
                memory_row_id=int(mem.id),
                source_profile_id=getattr(prov, "source_profile_id", None),
                provenance_id=int(prov.id),
                raw_evidence_id=getattr(prov, "raw_evidence_id", None),
                domain=str(ku.domain),
                language=str(ku.language),
                topic_taxonomy=getattr(ku, "topic_taxonomy", None),
                normalized_statement=str(ku.normalized_statement),
                evidence_strength=str(ku.evidence_strength),
                freshness_state=str(ku.freshness_state),
                conflict_state=str(ku.conflict_state),
                medical_safety_state=str(ku.medical_safety_state),
                runtime_eligibility=str(ku.runtime_eligibility),
                rank_score=score,
                inclusion_reasons=[
                    "CURRENT_MEMORY",
                    "KU_ELIGIBLE_MATRIX",
                    "MEMORY_ELIGIBLE",
                    "PROVENANCE_COMPLETE",
                    "PROVENANCE_ROW_PRESENT",
                    f"TOKEN_OVERLAP:{overlap}",
                ],
            )
        )

    # Deterministic sort: rank_score desc, canonical_unit_id asc, knowledge_unit_id asc
    candidates.sort(
        key=lambda i: (-i.rank_score, i.canonical_unit_id, i.knowledge_unit_id)
    )

    # Dedupe by canonical_unit_id (keep highest ranked)
    seen_canon: set[str] = set()
    deduped: list[RetrievedKnowledgeItem] = []
    for item in candidates:
        if item.canonical_unit_id in seen_canon:
            _exclude(
                result.exclusions,
                result.exclusion_counts,
                ku_id=item.knowledge_unit_id,
                canonical_unit_id=item.canonical_unit_id,
                reason="DEDUPE_CANONICAL_UNIT",
            )
            continue
        seen_canon.add(item.canonical_unit_id)
        deduped.append(item)

    result.items = deduped[:lim]
    for dropped in deduped[lim:]:
        _exclude(
            result.exclusions,
            result.exclusion_counts,
            ku_id=dropped.knowledge_unit_id,
            canonical_unit_id=dropped.canonical_unit_id,
            reason="LIMIT_TRUNCATED",
        )

    if not result.items:
        result.status = status_override or STATUS_NO_ELIGIBLE_KNOWLEDGE
        result.safe_user_facing_intent = (
            "No safe governed knowledge matched this query after eligibility "
            "and version filters; do not invent medical content."
        )
        if enqueue_gap_on_empty:
            gap = enqueue_runtime_retrieval_gap(
                db,
                original_query=nq.original_query,
                normalized_query=nq.normalized_query,
                domain=result.domain_filter or "unknown",
                trace_id=trace_id,
                status=result.status,
            )
            result.gap_id = gap.id
    elif status_override and status_override != STATUS_OK:
        # Partial success with structural warnings already excluded — keep OK if items exist
        pass

    return result


def assert_no_base_model_medical_fallback(result: RetrievalResult) -> None:
    if not result.no_base_model_fallback:
        raise RuntimeKnowledgeRetrievalError("BASE_MODEL_FALLBACK_MARKER_MISSING")
    if result.status != STATUS_OK and result.items:
        raise RuntimeKnowledgeRetrievalError("INCONSISTENT_NO_SAFE_RESULT")
