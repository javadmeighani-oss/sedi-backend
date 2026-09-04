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

# CAP-OPEN-17 personalization bounds (relevance only; never clinical authority).
MAX_PERSONALIZATION_TERMS_PER_CATEGORY = 8
MAX_PERSONALIZATION_TERM_LEN = 48
MAX_PERSONALIZATION_TOTAL_TOKENS = 64
MAX_PERSONALIZATION_SCORE = 999

_EVIDENCE_RANK: dict[str, int] = {
    EvidenceStrength.HIGH.value: 3,
    EvidenceStrength.MODERATE.value: 2,
    EvidenceStrength.LOW.value: 1,
}

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)
_ALLOWED_REASON_TAGS = frozenset(
    {
        "goal_relevance",
        "preference_relevance",
        "lifestyle_relevance",
        "restriction_relevance",
        "routine_relevance",
        "domain_hint_match",
        "language_match",
    }
)


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


@dataclass(frozen=True)
class RetrievalPersonalizationContext:
    """Bounded safe user-context relevance features for CAP-OPEN-17.

    Never authoritative for clinical truth. Never persists onto KU/Memory rows.
    """

    language: Optional[str] = None
    goal_terms: tuple[str, ...] = ()
    preference_terms: tuple[str, ...] = ()
    lifestyle_terms: tuple[str, ...] = ()
    restriction_terms: tuple[str, ...] = ()
    routine_terms: tuple[str, ...] = ()
    domain_hints: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not (
            self.language
            or self.goal_terms
            or self.preference_terms
            or self.lifestyle_terms
            or self.restriction_terms
            or self.routine_terms
            or self.domain_hints
        )

    def to_audit_dict(self) -> dict[str, Any]:
        """Category sizes only — no raw user term values."""
        return {
            "language_set": bool(self.language),
            "goal_term_count": len(self.goal_terms),
            "preference_term_count": len(self.preference_terms),
            "lifestyle_term_count": len(self.lifestyle_terms),
            "restriction_term_count": len(self.restriction_terms),
            "routine_term_count": len(self.routine_terms),
            "domain_hint_count": len(self.domain_hints),
        }


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
    personalization_score: int = 0
    personalization_reasons: list[str] = field(default_factory=list)

    def as_care_snippet(self) -> dict[str, Any]:
        """CARE_CONTEXT-compatible snippet; citation rendering owned by W4-P02."""
        retrieval_mode = "scis_lexical" if str(self.memory_item_id).startswith("SCIS_KCE:") else "memory"
        chunk_id = None
        if retrieval_mode == "scis_lexical":
            try:
                chunk_id = int(str(self.memory_item_id).split(":", 1)[1])
            except (IndexError, ValueError, TypeError):
                chunk_id = None
        return {
            "content": self.normalized_statement,
            "knowledge_unit_id": self.knowledge_unit_id,
            "canonical_unit_id": self.canonical_unit_id,
            "immutable_version_id": self.immutable_version_id,
            "memory_item_id": self.memory_item_id,
            "provenance_id": self.provenance_id,
            "source_profile_id": self.source_profile_id,
            "raw_evidence_id": self.raw_evidence_id,
            "language": self.language,
            "domain": self.domain,
            "retrieval_mode": retrieval_mode,
            "chunk_id": chunk_id,
            "rank_score": self.rank_score,
            "citation": {
                "label": f"KU:{self.canonical_unit_id}:{self.immutable_version_id}",
                "handoff": "W4-P02",
                "chunk_id": chunk_id,
                "source_profile_id": self.source_profile_id,
            },
            "evidence_strength": self.evidence_strength,
            "inclusion_reasons": list(self.inclusion_reasons),
            "personalization_score": int(self.personalization_score),
            "personalization_reasons": list(self.personalization_reasons),
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
    personalization_applied: bool = False
    personalization_audit: dict[str, Any] = field(default_factory=dict)
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
            "personalization_applied": self.personalization_applied,
            "personalization_audit": dict(self.personalization_audit),
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
                    "personalization_score": int(i.personalization_score),
                    "personalization_reasons": list(i.personalization_reasons),
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


def _rank_score(
    evidence_strength: str,
    overlap: int,
    personalization_score: int = 0,
) -> int:
    """Deterministic ranking: evidence > query overlap > personalization.

    Personalization never exceeds the query-overlap bucket (max 999).
    """
    strength = _EVIDENCE_RANK.get(str(evidence_strength), 0)
    pers = max(0, min(int(personalization_score), MAX_PERSONALIZATION_SCORE))
    return strength * 1_000_000 + overlap * 1_000 + pers


def _normalize_term_token(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if not isinstance(raw, (str, int, float)):
        return None
    try:
        text = str(raw)
    except Exception:
        return None
    if not text or not text.strip():
        return None
    nq = normalize_query(text)
    if not nq.normalized_query:
        return None
    # Prefer first meaningful token for bounded term lists.
    token = nq.tokens[0] if nq.tokens else nq.normalized_query
    if len(token) > MAX_PERSONALIZATION_TERM_LEN:
        token = token[:MAX_PERSONALIZATION_TERM_LEN]
    return token or None


def _expand_raw_to_terms(raw: Any) -> tuple[str, ...]:
    """Expand a title/phrase into normalized tokens (bounded later by caller)."""
    if raw is None:
        return ()
    if not isinstance(raw, (str, int, float)):
        return ()
    nq = normalize_query(str(raw))
    out: list[str] = []
    for tok in nq.tokens:
        if len(tok) > MAX_PERSONALIZATION_TERM_LEN:
            tok = tok[:MAX_PERSONALIZATION_TERM_LEN]
        if tok:
            out.append(tok)
    return tuple(out)


def _bounded_unique_terms(values: Sequence[Any], *, limit: int) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for tok in _expand_raw_to_terms(raw):
            if not tok or tok in seen:
                continue
            seen.add(tok)
            out.append(tok)
            if len(out) >= limit:
                return tuple(out)
    return tuple(out)


def normalize_personalization_context(
    personalization: Optional[RetrievalPersonalizationContext | Mapping[str, Any]],
) -> Optional[RetrievalPersonalizationContext]:
    """Deterministic bounded normalization; malformed optional context → None."""
    if personalization is None:
        return None
    try:
        if isinstance(personalization, RetrievalPersonalizationContext):
            src = personalization
            language = src.language
            goal_terms = src.goal_terms
            preference_terms = src.preference_terms
            lifestyle_terms = src.lifestyle_terms
            restriction_terms = src.restriction_terms
            routine_terms = src.routine_terms
            domain_hints = src.domain_hints
        elif isinstance(personalization, Mapping):
            language = personalization.get("language")
            goal_terms = personalization.get("goal_terms") or ()
            preference_terms = personalization.get("preference_terms") or ()
            lifestyle_terms = personalization.get("lifestyle_terms") or ()
            restriction_terms = personalization.get("restriction_terms") or ()
            routine_terms = personalization.get("routine_terms") or ()
            domain_hints = personalization.get("domain_hints") or ()
        else:
            return None

        lang = None
        if language is not None and str(language).strip():
            lang = str(language).strip().casefold()[:16]

        ctx = RetrievalPersonalizationContext(
            language=lang,
            goal_terms=_bounded_unique_terms(
                list(goal_terms), limit=MAX_PERSONALIZATION_TERMS_PER_CATEGORY
            ),
            preference_terms=_bounded_unique_terms(
                list(preference_terms), limit=MAX_PERSONALIZATION_TERMS_PER_CATEGORY
            ),
            lifestyle_terms=_bounded_unique_terms(
                list(lifestyle_terms), limit=MAX_PERSONALIZATION_TERMS_PER_CATEGORY
            ),
            restriction_terms=_bounded_unique_terms(
                list(restriction_terms), limit=MAX_PERSONALIZATION_TERMS_PER_CATEGORY
            ),
            routine_terms=_bounded_unique_terms(
                list(routine_terms), limit=MAX_PERSONALIZATION_TERMS_PER_CATEGORY
            ),
            domain_hints=_bounded_unique_terms(
                list(domain_hints), limit=MAX_PERSONALIZATION_TERMS_PER_CATEGORY
            ),
        )
        total = (
            len(ctx.goal_terms)
            + len(ctx.preference_terms)
            + len(ctx.lifestyle_terms)
            + len(ctx.restriction_terms)
            + len(ctx.routine_terms)
            + len(ctx.domain_hints)
            + (1 if ctx.language else 0)
        )
        if total > MAX_PERSONALIZATION_TOTAL_TOKENS:
            # Cap by truncating softer categories first while remaining deterministic.
            ctx = RetrievalPersonalizationContext(
                language=ctx.language,
                goal_terms=ctx.goal_terms[:4],
                preference_terms=ctx.preference_terms[:4],
                lifestyle_terms=ctx.lifestyle_terms[:4],
                restriction_terms=ctx.restriction_terms[:4],
                routine_terms=ctx.routine_terms[:4],
                domain_hints=ctx.domain_hints[:4],
            )
        if ctx.is_empty():
            return None
        return ctx
    except Exception:
        return None


def build_personalization_context_from_memory(
    memory_context: Optional[Mapping[str, Any]],
    *,
    language: Optional[str] = None,
) -> Optional[RetrievalPersonalizationContext]:
    """Derive minimal safe personalization features from CARE memory context.

    Excludes medications, conditions, doctor phones, and other high-risk PHI.
    """
    if not isinstance(memory_context, Mapping):
        memory_context = {}
    try:
        goals = memory_context.get("goals") or []
        habits = memory_context.get("habits") or []
        restrictions = memory_context.get("restrictions") or []
        memory_facts = memory_context.get("memory_facts") or {}
        lifestyle_summary = memory_context.get("lifestyle_summary")
        profile = memory_context.get("profile_core") or {}

        goal_raw: list[Any] = []
        for g in goals if isinstance(goals, list) else []:
            if isinstance(g, Mapping):
                goal_raw.append(g.get("title") or g.get("category"))
            else:
                goal_raw.append(g)

        habit_raw: list[Any] = []
        for h in habits if isinstance(habits, list) else []:
            if isinstance(h, Mapping):
                habit_raw.append(h.get("name"))
            else:
                habit_raw.append(h)

        restriction_raw: list[Any] = []
        for r in restrictions if isinstance(restrictions, list) else []:
            if isinstance(r, Mapping):
                restriction_raw.append(r.get("title") or r.get("restriction_type"))
            else:
                restriction_raw.append(r)

        pref_raw: list[Any] = []
        lifestyle_raw: list[Any] = []
        routine_raw: list[Any] = []
        if isinstance(memory_facts, Mapping):
            for item in memory_facts.get("preferences") or []:
                if isinstance(item, Mapping):
                    pref_raw.append(item.get("key"))
            for item in memory_facts.get("lifestyle") or []:
                if isinstance(item, Mapping):
                    lifestyle_raw.append(item.get("key"))
            for item in memory_facts.get("routines") or []:
                if isinstance(item, Mapping):
                    routine_raw.append(item.get("key"))
            for item in memory_facts.get("goals") or []:
                if isinstance(item, Mapping):
                    goal_raw.append(item.get("key"))

        if lifestyle_summary:
            lifestyle_raw.extend(normalize_query(str(lifestyle_summary)).tokens[:8])

        lang = language or (profile.get("language") if isinstance(profile, Mapping) else None)
        return normalize_personalization_context(
            {
                "language": lang,
                "goal_terms": goal_raw,
                "preference_terms": pref_raw,
                "lifestyle_terms": lifestyle_raw + habit_raw,
                "restriction_terms": restriction_raw,
                "routine_terms": routine_raw,
                "domain_hints": [],
            }
        )
    except Exception:
        return None


def _personalization_relevance(
    *,
    ku_language: str,
    ku_domain: str,
    haystack: str,
    ctx: Optional[RetrievalPersonalizationContext],
) -> tuple[int, list[str]]:
    """Compute bounded personalization score + non-sensitive reason tags."""
    if ctx is None or ctx.is_empty():
        return 0, []
    score = 0
    reasons: list[str] = []
    hay_tokens = set(normalize_query(haystack).tokens)

    def _add_category(terms: Sequence[str], tag: str, weight: int) -> None:
        nonlocal score
        if not terms:
            return
        hits = sum(1 for t in terms if t in hay_tokens)
        if hits:
            score += hits * weight
            if tag in _ALLOWED_REASON_TAGS and tag not in reasons:
                reasons.append(tag)

    _add_category(ctx.goal_terms, "goal_relevance", 12)
    _add_category(ctx.preference_terms, "preference_relevance", 8)
    _add_category(ctx.lifestyle_terms, "lifestyle_relevance", 8)
    _add_category(ctx.restriction_terms, "restriction_relevance", 6)
    _add_category(ctx.routine_terms, "routine_relevance", 6)
    _add_category(ctx.domain_hints, "domain_hint_match", 10)

    if ctx.language and str(ku_language).casefold() == ctx.language:
        score += 10
        reasons.append("language_match")
    if ctx.domain_hints and str(ku_domain).casefold() in set(ctx.domain_hints):
        if "domain_hint_match" not in reasons:
            reasons.append("domain_hint_match")
        score += 8

    score = max(0, min(score, MAX_PERSONALIZATION_SCORE))
    reasons = [r for r in reasons if r in _ALLOWED_REASON_TAGS]
    return score, reasons


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
    enqueue_gap_on_empty: bool = False,
    require_query_tokens: bool = False,
    personalization: Optional[RetrievalPersonalizationContext | Mapping[str, Any]] = None,
) -> RetrievalResult:
    """Knowledge-DB-first retrieval with fail-closed eligibility filters.

    K04: prefer governed SCIS lexical evidence (no KnowledgeMemoryItem required).
    Memory plane is fallback only when SCIS returns nothing — paths are not merged.
    Personalization (CAP-OPEN-17) is post-eligibility ranking only.
    Default enqueue_gap_on_empty=False — normal serving is side-effect free.
    """
    from backend.app import models
    from backend.app.services.scis.governed_runtime_adapter import (
        retrieve_scis_lexical_runtime_items,
    )

    nq = normalize_query(query)
    lim = clamp_limit(limit)
    serving_lim = min(lim, 5)
    trace_id = str(uuid.uuid4())
    query_id = _sha256_hex(f"{trace_id}|{nq.normalized_query}")[:32]
    pers_ctx = normalize_personalization_context(personalization)

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
        personalization_applied=False,
        personalization_audit=pers_ctx.to_audit_dict() if pers_ctx else {},
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

    # K04 primary path: governed SCIS lexical (works with knowledge_memory_items=0).
    try:
        scis_items = retrieve_scis_lexical_runtime_items(
            db,
            nq.original_query,
            language=result.language_filter,
            domain=result.domain_filter,
            limit=serving_lim,
        )
    except Exception:  # noqa: BLE001 — SCIS unavailable → memory fallback
        scis_items = []

    if scis_items:
        ranked: list[RetrievedKnowledgeItem] = []
        for item in scis_items:
            pers_score, pers_reasons = _personalization_relevance(
                ku_language=item.language,
                ku_domain=item.domain,
                haystack=item.normalized_statement,
                ctx=pers_ctx,
            )
            if pers_score:
                result.personalization_applied = True
            ranked.append(
                RetrievedKnowledgeItem(
                    knowledge_unit_id=item.knowledge_unit_id,
                    canonical_unit_id=item.canonical_unit_id,
                    immutable_version_id=item.immutable_version_id,
                    memory_item_id=item.memory_item_id,
                    memory_row_id=item.memory_row_id,
                    source_profile_id=item.source_profile_id,
                    provenance_id=item.provenance_id,
                    raw_evidence_id=item.raw_evidence_id,
                    domain=item.domain,
                    language=item.language,
                    topic_taxonomy=item.topic_taxonomy,
                    normalized_statement=item.normalized_statement,
                    evidence_strength=item.evidence_strength,
                    freshness_state=item.freshness_state,
                    conflict_state=item.conflict_state,
                    medical_safety_state=item.medical_safety_state,
                    runtime_eligibility=item.runtime_eligibility,
                    rank_score=item.rank_score + pers_score,
                    inclusion_reasons=list(item.inclusion_reasons)
                    + ([f"PERSONALIZATION_SCORE:{pers_score}"] if pers_score else []),
                    personalization_score=pers_score,
                    personalization_reasons=list(pers_reasons),
                )
            )
        ranked.sort(key=lambda i: (-i.rank_score, i.canonical_unit_id, i.knowledge_unit_id))
        result.items = ranked[:serving_lim]
        result.safe_user_facing_intent = (
            "Governed SCIS lexical knowledge matched this query after eligibility filters."
        )
        return result

    # Fallback: CURRENT KnowledgeMemoryItem plane (historical path; not required for K04).
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
        # Query relevance floor: personalization cannot admit zero-overlap matches.
        if nq.tokens and overlap < 1:
            _exclude(
                result.exclusions,
                result.exclusion_counts,
                ku_id=ku.id,
                canonical_unit_id=canon,
                reason="QUERY_NO_MATCH",
            )
            continue

        haystack = " ".join(
            [
                str(ku.normalized_statement or ""),
                str(ku.topic_taxonomy or ""),
                str(ku.domain or ""),
            ]
        )
        pers_score, pers_reasons = _personalization_relevance(
            ku_language=str(ku.language),
            ku_domain=str(ku.domain),
            haystack=haystack,
            ctx=pers_ctx,
        )
        score = _rank_score(str(ku.evidence_strength), overlap, pers_score)
        inclusion = [
            "CURRENT_MEMORY",
            "KU_ELIGIBLE_MATRIX",
            "MEMORY_ELIGIBLE",
            "PROVENANCE_COMPLETE",
            "PROVENANCE_ROW_PRESENT",
            f"TOKEN_OVERLAP:{overlap}",
        ]
        if pers_score:
            inclusion.append(f"PERSONALIZATION_SCORE:{pers_score}")
            result.personalization_applied = True
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
                inclusion_reasons=inclusion,
                personalization_score=pers_score,
                personalization_reasons=list(pers_reasons),
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

    result.items = deduped[:serving_lim]
    for dropped in deduped[serving_lim:]:
        _exclude(
            result.exclusions,
            result.exclusion_counts,
            ku_id=dropped.knowledge_unit_id,
            canonical_unit_id=dropped.canonical_unit_id,
            reason="LIMIT_TRUNCATED",
        )

    if not result.items:
        result.status = status_override or STATUS_NO_ELIGIBLE_KNOWLEDGE
        lang = (result.language_filter or "").lower()
        if lang.startswith("fa") or lang.startswith("ar"):
            result.safe_user_facing_intent = (
                "LANGUAGE_GAP: no governed evidence in the requested language after "
                "eligibility filters; do not silently translate or invent medical content."
            )
            result.exclusion_counts["LANGUAGE_GAP"] = (
                result.exclusion_counts.get("LANGUAGE_GAP", 0) + 1
            )
        else:
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
