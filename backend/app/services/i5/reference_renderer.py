"""I5-IMPL-W4-P02 — grounded synthesis + reference / citation / disclosure renderer.

Consumes W4-P01 RetrievalResult (Knowledge-DB-first). Deterministic synthesis only:
no live LLM / network. Personalization may adapt language/tone/format but must not
alter medical facts. local_rag is out of scope and must remain untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Union

from backend.app.schemas.i5_references import (
    DisclosureView,
    GroundedAnswerView,
    PersonalizationView,
    ReferenceItemView,
    SupportedClaimView,
)

PACKAGE_ID = "I5-IMPL-W4-P02"
MANAGEMENT_ALIAS = "P09"
SERVICE_NAME = "reference_renderer"

STATUS_OK = "OK"
STATUS_NO_SAFE_KNOWLEDGE = "NO_SAFE_KNOWLEDGE"
STATUS_CONFLICT_DISCLOSURE = "CONFLICT_DISCLOSURE"
STATUS_SAFETY_DISCLOSURE = "SAFETY_DISCLOSURE"
STATUS_INSUFFICIENT = "INSUFFICIENT"

NO_BASE_MODEL_MEDICAL_FALLBACK = True

TRIGGER_USER_REQUEST_SOURCES = "USER_REQUEST_SOURCES"
TRIGGER_CONFLICT = "CONFLICT"
TRIGGER_SAFETY = "SAFETY"
TRIGGER_STALE = "STALE"
TRIGGER_UNCERTAINTY = "UNCERTAINTY"
TRIGGER_NO_SAFE_KNOWLEDGE = "NO_SAFE_KNOWLEDGE"
TRIGGER_JURISDICTION = "JURISDICTION"

CLAIM_KIND_SUPPORTED_MEDICAL = "SUPPORTED_MEDICAL"
CLAIM_KIND_PERSONALIZED_WRAPPER = "PERSONALIZED_NON_MEDICAL_WRAPPER"
CLAIM_KIND_DISCLOSURE = "SAFETY_LIMITATION_DISCLOSURE"


@dataclass(frozen=True)
class EvidenceHandoff:
    knowledge_unit_id: int
    canonical_unit_id: str
    immutable_version_id: str
    memory_item_id: Optional[str]
    provenance_id: Optional[int]
    source_profile_id: Optional[int]
    raw_evidence_id: Optional[int]
    normalized_statement: str
    evidence_strength: str
    freshness_state: str = "CURRENT"
    conflict_state: str = "NONE"
    medical_safety_state: str = "CLEARED"
    domain: str = ""
    language: str = ""

    @property
    def label(self) -> str:
        return f"KU:{self.canonical_unit_id}:{self.immutable_version_id}"


def _as_mapping(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, Mapping):
        return dict(obj)
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return dict(obj.to_dict())
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return {}


def extract_handoffs_from_retrieval(
    retrieval: Union[Mapping[str, Any], Any],
) -> list[EvidenceHandoff]:
    """Normalize W4-P01 RetrievalResult / care envelope into evidence handoffs."""
    data = _as_mapping(retrieval)
    items = data.get("items") or []
    # CARE envelope may only expose knowledge_snippets.
    if not items and data.get("knowledge_snippets"):
        items = data.get("knowledge_snippets") or []
    out: list[EvidenceHandoff] = []
    for raw in items:
        item = _as_mapping(raw)
        # Prefer explicit w4p02_handoff payload when present.
        if callable(getattr(raw, "w4p02_handoff", None)):
            item = dict(raw.w4p02_handoff())
            # Preserve states from object when available.
            for key in (
                "freshness_state",
                "conflict_state",
                "medical_safety_state",
                "domain",
                "language",
            ):
                if hasattr(raw, key):
                    item[key] = getattr(raw, key)
        statement = (
            item.get("normalized_statement")
            or item.get("content")
            or item.get("statement_excerpt")
            or ""
        )
        ku_id = item.get("knowledge_unit_id")
        canon = item.get("canonical_unit_id") or ""
        version = item.get("immutable_version_id") or ""
        if ku_id is None or not str(statement).strip():
            continue
        cit = _as_mapping(item.get("citation"))
        label = cit.get("label") or f"KU:{canon}:{version}"
        if not version and ":" in str(label):
            parts = str(label).split(":")
            if len(parts) >= 3:
                canon = canon or parts[1]
                version = version or parts[2]
        out.append(
            EvidenceHandoff(
                knowledge_unit_id=int(ku_id),
                canonical_unit_id=str(canon or f"ku-{ku_id}"),
                immutable_version_id=str(version or "unknown"),
                memory_item_id=item.get("memory_item_id"),
                provenance_id=item.get("provenance_id"),
                source_profile_id=item.get("source_profile_id"),
                raw_evidence_id=item.get("raw_evidence_id"),
                normalized_statement=str(statement).strip(),
                evidence_strength=str(item.get("evidence_strength") or "UNKNOWN"),
                freshness_state=str(item.get("freshness_state") or "CURRENT"),
                conflict_state=str(item.get("conflict_state") or "NONE"),
                medical_safety_state=str(item.get("medical_safety_state") or "CLEARED"),
                domain=str(item.get("domain") or ""),
                language=str(item.get("language") or ""),
            )
        )
    return out


def reject_unsupported_medical_claim(
    claim_text: str,
    evidence: Sequence[EvidenceHandoff],
) -> Optional[str]:
    """Return rejection reason if claim is not grounded in eligible evidence statements."""
    text = (claim_text or "").strip().lower()
    if not text:
        return "EMPTY_CLAIM"
    for ev in evidence:
        stmt = ev.normalized_statement.strip().lower()
        if text == stmt or text in stmt or stmt in text:
            return None
    return "UNSUPPORTED_MEDICAL_CLAIM"


def build_references(evidence: Sequence[EvidenceHandoff]) -> list[ReferenceItemView]:
    refs: list[ReferenceItemView] = []
    for ev in evidence:
        refs.append(
            ReferenceItemView(
                knowledge_unit_id=ev.knowledge_unit_id,
                canonical_unit_id=ev.canonical_unit_id,
                immutable_version_id=ev.immutable_version_id,
                memory_item_id=ev.memory_item_id,
                provenance_id=ev.provenance_id,
                source_profile_id=ev.source_profile_id,
                raw_evidence_id=ev.raw_evidence_id,
                label=ev.label,
                evidence_strength=ev.evidence_strength,
                statement_excerpt=ev.normalized_statement[:500],
            )
        )
    # Deterministic order: label then ku id.
    return sorted(refs, key=lambda r: (r.label, r.knowledge_unit_id))


def build_disclosures(
    *,
    retrieval_status: str,
    exclusions: Sequence[Mapping[str, Any] | Any],
    evidence: Sequence[EvidenceHandoff],
    user_requested_sources: bool,
) -> list[DisclosureView]:
    disclosures: list[DisclosureView] = []
    exclusion_reasons = []
    for ex in exclusions:
        m = _as_mapping(ex)
        reason = str(m.get("reason") or "")
        if reason:
            exclusion_reasons.append(reason)

    if user_requested_sources:
        disclosures.append(
            DisclosureView(
                trigger=TRIGGER_USER_REQUEST_SOURCES,
                message="SHOW SOURCES requested; references listed from eligible governed knowledge only.",
            )
        )

    if any("CONFLICT" in r or "KU_NOT_ELIGIBLE:REVIEW_REQUIRED" in r for r in exclusion_reasons):
        disclosures.append(
            DisclosureView(
                trigger=TRIGGER_CONFLICT,
                message=(
                    "Material conflict or review-required evidence was excluded; "
                    "Sedi will not collapse conflicting medical claims into one fabricated truth."
                ),
            )
        )

    if any(
        ("SAFETY" in r)
        or ("RESTRICTED" in r)
        or ("BLOCKED" in r)
        or ("PENDING_REVIEW" in r)
        or any(x in r for x in ("RESTRICTED", "BLOCKED", "PENDING_REVIEW"))
        for r in exclusion_reasons
    ) or any(
        e.medical_safety_state in {"RESTRICTED", "BLOCKED", "PENDING_REVIEW"} for e in evidence
    ):
        disclosures.append(
            DisclosureView(
                trigger=TRIGGER_SAFETY,
                message=(
                    "Safety-gated knowledge was excluded or limited; "
                    "do not treat pending/restricted/blocked evidence as cleared medical guidance."
                ),
            )
        )

    if any("STALE" in r or "freshness" in r.lower() for r in exclusion_reasons) or any(
        e.freshness_state == "STALE" for e in evidence
    ):
        disclosures.append(
            DisclosureView(
                trigger=TRIGGER_STALE,
                message="Stale knowledge was excluded from grounded synthesis.",
            )
        )

    if retrieval_status in {STATUS_NO_SAFE_KNOWLEDGE, "NO_ELIGIBLE_KNOWLEDGE"} or not evidence:
        disclosures.append(
            DisclosureView(
                trigger=TRIGGER_NO_SAFE_KNOWLEDGE,
                message=(
                    "No safe governed knowledge is available for this query; "
                    "Sedi will not invent medical content (NO_BASE_MODEL_MEDICAL_FALLBACK)."
                ),
            )
        )
        disclosures.append(
            DisclosureView(
                trigger=TRIGGER_UNCERTAINTY,
                message="Confidence is limited because eligible evidence is absent.",
            )
        )

    # Deduplicate by trigger, preserve order.
    seen: set[str] = set()
    unique: list[DisclosureView] = []
    for d in disclosures:
        if d.trigger in seen:
            continue
        seen.add(d.trigger)
        unique.append(d)
    return unique


def synthesize_grounded_text(
    evidence: Sequence[EvidenceHandoff],
    *,
    language: Optional[str] = None,
) -> tuple[str, list[SupportedClaimView]]:
    """Deterministic grounded synthesis from eligible statements only (no LLM)."""
    if not evidence:
        return (
            "No safe governed knowledge is available. Do not invent medical content.",
            [],
        )
    ordered = sorted(evidence, key=lambda e: (e.label, e.knowledge_unit_id))
    claims: list[SupportedClaimView] = []
    lines: list[str] = []
    wrapper = "Educational summary from governed knowledge sources:"
    if language and language.lower().startswith("fa"):
        wrapper = "خلاصه آموزشی بر اساس دانش حکومتی/حاکمیتی موجود:"
    lines.append(wrapper)
    claims.append(
        SupportedClaimView(
            claim_id="claim-wrapper-0",
            claim_text=wrapper,
            claim_kind=CLAIM_KIND_PERSONALIZED_WRAPPER,
            evidence_knowledge_unit_ids=[],
            evidence_labels=[],
        )
    )
    for idx, ev in enumerate(ordered, start=1):
        line = f"{idx}. {ev.normalized_statement} [{ev.label}]"
        lines.append(line)
        claims.append(
            SupportedClaimView(
                claim_id=f"claim-{idx}",
                claim_text=ev.normalized_statement,
                claim_kind=CLAIM_KIND_SUPPORTED_MEDICAL,
                evidence_knowledge_unit_ids=[ev.knowledge_unit_id],
                evidence_labels=[ev.label],
            )
        )
    lines.append(
        "This is educational information from governed sources, not a diagnosis or treatment order."
    )
    claims.append(
        SupportedClaimView(
            claim_id="claim-disclosure-footer",
            claim_text=lines[-1],
            claim_kind=CLAIM_KIND_DISCLOSURE,
            evidence_knowledge_unit_ids=[],
            evidence_labels=[],
        )
    )
    return "\n".join(lines), claims


def resolve_status(
    *,
    retrieval_status: str,
    evidence: Sequence[EvidenceHandoff],
    exclusions: Sequence[Any],
) -> str:
    if evidence:
        reasons = [str(_as_mapping(ex).get("reason") or "") for ex in exclusions]
        if any("CONFLICT" in r for r in reasons):
            return STATUS_CONFLICT_DISCLOSURE
        if any(e.medical_safety_state in {"RESTRICTED", "BLOCKED", "PENDING_REVIEW"} for e in evidence):
            return STATUS_SAFETY_DISCLOSURE
        return STATUS_OK
    if retrieval_status in {"NO_ELIGIBLE_KNOWLEDGE", STATUS_NO_SAFE_KNOWLEDGE}:
        return STATUS_NO_SAFE_KNOWLEDGE
    if retrieval_status and retrieval_status != "OK":
        return STATUS_INSUFFICIENT
    return STATUS_NO_SAFE_KNOWLEDGE


def render_grounded_answer(
    retrieval: Union[Mapping[str, Any], Any],
    *,
    language: Optional[str] = None,
    user_requested_sources: bool = True,
    proposed_unsupported_claims: Optional[Sequence[str]] = None,
) -> GroundedAnswerView:
    """Primary W4-P02 entry: grounded synthesis + SHOW SOURCES / WHY SEDI SAID THIS."""
    data = _as_mapping(retrieval)
    # Nested CARE envelope.
    if "i5_knowledge_retrieval" in data and isinstance(data["i5_knowledge_retrieval"], Mapping):
        nested = dict(data["i5_knowledge_retrieval"])
        if not nested.get("items") and data.get("knowledge_snippets"):
            nested["items"] = data.get("knowledge_snippets")
        data = nested

    retrieval_status = str(data.get("status") or data.get("i5_retrieval_status") or "OK")
    exclusions = list(data.get("exclusions") or [])
    evidence = extract_handoffs_from_retrieval(data)

    rejected: list[str] = []
    for claim in proposed_unsupported_claims or []:
        reason = reject_unsupported_medical_claim(claim, evidence)
        if reason:
            rejected.append(f"{reason}:{claim}")

    status = resolve_status(
        retrieval_status=retrieval_status,
        evidence=evidence,
        exclusions=exclusions,
    )
    synthesized, claims = synthesize_grounded_text(evidence, language=language)
    refs = build_references(evidence)
    disclosures = build_disclosures(
        retrieval_status=status if status != STATUS_OK else retrieval_status,
        exclusions=exclusions,
        evidence=evidence,
        user_requested_sources=user_requested_sources,
    )

    show_sources = [f"{r.label} — {r.statement_excerpt}" for r in refs]
    why = [
        f"Sedi used eligible governed knowledge unit {r.label} (strength={r.evidence_strength})."
        for r in refs
    ]
    if not why:
        why = [
            "Sedi did not synthesize medical facts because no eligible governed knowledge was available."
        ]

    personalization = PersonalizationView(
        language=language,
        tone="neutral_educational",
        format_hint="show_sources_block",
        medical_facts_altered=False,
    )

    chat_metadata = {
        "package_id": PACKAGE_ID,
        "management_alias": MANAGEMENT_ALIAS,
        "show_sources": show_sources,
        "why_sedi_said_this": why,
        "disclosure_triggers": [d.trigger for d in disclosures],
        "no_base_model_fallback": NO_BASE_MODEL_MEDICAL_FALLBACK,
        "reference_count": len(refs),
        "status": status,
    }

    return GroundedAnswerView(
        package_id=PACKAGE_ID,
        management_alias=MANAGEMENT_ALIAS,
        status=status,
        query_id=data.get("query_id"),
        trace_id=data.get("trace_id"),
        synthesized_text=synthesized,
        claims=claims,
        unsupported_claims_rejected=rejected,
        references=refs,
        show_sources=show_sources,
        why_sedi_said_this=why,
        disclosures=disclosures,
        personalization=personalization,
        no_base_model_fallback=NO_BASE_MODEL_MEDICAL_FALLBACK,
        chat_metadata=chat_metadata,
    )


def format_care_context_block(answer: GroundedAnswerView, *, max_chars: int = 1200) -> str:
    """Compact CARE_CONTEXT / brain system block from a grounded answer."""
    lines = [
        "[CARE_CONTEXT] W4-P02 grounded synthesis + references (educational use only):",
        f"Status: {answer.status}",
        "NO_BASE_MODEL_MEDICAL_FALLBACK=1",
    ]
    if answer.synthesized_text:
        lines.append("Grounded summary:")
        lines.append(answer.synthesized_text[:600])
    if answer.show_sources:
        lines.append("SHOW SOURCES:")
        for src in answer.show_sources[:5]:
            lines.append(f"- {src[:180]}")
    if answer.why_sedi_said_this:
        lines.append("WHY SEDI SAID THIS:")
        for why in answer.why_sedi_said_this[:5]:
            lines.append(f"- {why[:180]}")
    if answer.disclosures:
        lines.append("Disclosures:")
        for d in answer.disclosures[:4]:
            lines.append(f"- [{d.trigger}] {d.message[:160]}")
    return "\n".join(lines)[:max_chars]


def render_from_care_context(
    care_context: Mapping[str, Any],
    *,
    language: Optional[str] = None,
    user_requested_sources: bool = True,
) -> GroundedAnswerView:
    lang = language or care_context.get("language")
    return render_grounded_answer(
        care_context,
        language=lang if isinstance(lang, str) else language,
        user_requested_sources=user_requested_sources,
    )
