"""Phase2-B CASE09 — authority-safe bounded deterministic coreference.

Consumes only caller-provided structured referents. Never invents access,
HealthSubject links, medications, or results. No LLM.
PERSONAL != GOVERNED. SELF != MANAGED.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from backend.app.services.scis.normalize import normalize_for_language

STATE_RESOLVED = "RESOLVED"
STATE_AMBIGUOUS = "AMBIGUOUS"
STATE_UNRESOLVED = "UNRESOLVED"
STATE_NOT_APPLICABLE = "NOT_APPLICABLE"

TYPE_HEALTH_SUBJECT = "HEALTH_SUBJECT"
TYPE_MEDICATION = "MEDICATION"
TYPE_RESULT = "RESULT"
TYPE_TOPIC = "TOPIC"

SCOPE_SELF = "SELF"
SCOPE_MANAGED = "MANAGED"
SCOPE_CARE_CONTEXT = "CARE_CONTEXT"
SCOPE_UNKNOWN = "UNKNOWN"

AUTHORITY_PERSONAL = "PERSONAL"
AUTHORITY_GOVERNED = "GOVERNED"

# Bounded follow-up surface forms (deterministic; no synonym inference).
_CUE_MEDICATION = {
    "en": ("that medicine", "the medicine", "that medication", "the medication"),
    "fa": ("همان دارو", "اون دارو", "آن دارو", "دارو چطور"),
    "ar": ("ذلك الدواء", "هذا الدواء", "الدواء"),
}
_CUE_RESULT = {
    "en": ("last result", "the last result", "previous result", "that result"),
    "fa": ("نتیجه قبلی", "آخرین نتیجه", "همان نتیجه", "نتیجه قبل"),
    "ar": ("النتيجة السابقة", "اخر نتيجة", "تلك النتيجة"),
}
_CUE_HEALTH_SUBJECT_MOTHER = {
    "en": ("my mother", "mother", "how was she", "how is she", "about her"),
    "fa": ("مادرم", "مادر من", "چطور بود", "حالش چطور", "او چطور"),
    "ar": ("امي", "والدتي", "كيف كانت", "كيف حالها"),
}
_CUE_HEALTH_SUBJECT_SELF = {
    "en": ("myself", "about me", "for me", "my own"),
    "fa": ("خودم", "درباره من", "برای من"),
    "ar": ("انا نفسي", "عني", "بالنسبة لي"),
}
_CUE_GENERIC = {
    "en": ("what about it", "about it", "and that", "what about that"),
    "fa": ("در مورد آن", "درباره آن", "آن چطور", "در موردش"),
    "ar": ("ماذا عن ذلك", "بخصوص ذلك", "وماذا عن"),
}


@dataclass(frozen=True)
class StructuredReferent:
    """Caller-provided authorized referent candidate (no discovery)."""

    referent_type: str
    referent_key: str
    authority_label: str
    source_scope: str = SCOPE_UNKNOWN
    authorized: bool = True
    retrieval_hint: Optional[str] = None  # bounded non-PHI hint only


@dataclass(frozen=True)
class CoreferenceResolution:
    state: str
    referent_type: Optional[str] = None
    referent_key: Optional[str] = None
    source_scope: Optional[str] = None
    authority_label: Optional[str] = None
    clarification_required: bool = False
    retrieval_hint: Optional[str] = None
    cue_kind: Optional[str] = None

    def to_audit_dict(self) -> dict:
        """Sanitized observability — no raw medical/chat text."""
        return {
            "coreference_state": self.state,
            "coreference_referent_type": self.referent_type,
            "coreference_source_scope": self.source_scope,
            "coreference_authority_label": self.authority_label,
            "clarification_required": self.clarification_required,
            "cue_kind": self.cue_kind,
            "has_retrieval_hint": bool(self.retrieval_hint),
            # Opaque key only when already structured/safe from caller.
            "referent_key_present": bool(self.referent_key),
        }


def _lang_root(language: Optional[str]) -> str:
    lang = (language or "en").strip().lower()
    if lang.startswith("fa") or lang in {"persian", "farsi"}:
        return "fa"
    if lang.startswith("ar") or lang in {"arabic"}:
        return "ar"
    return "en"


def _contains_any(hay: str, needles: Tuple[str, ...]) -> Optional[str]:
    for n in needles:
        if n and n in hay:
            return n
    return None


def _detect_cue(query: str, *, language: Optional[str]) -> Optional[str]:
    root = _lang_root(language)
    norm = normalize_for_language(query or "", language)
    lower = (query or "").casefold()
    hay = f"{norm} {lower}"
    if _contains_any(hay, _CUE_MEDICATION[root]):
        return TYPE_MEDICATION
    if _contains_any(hay, _CUE_RESULT[root]):
        return TYPE_RESULT
    if _contains_any(hay, _CUE_HEALTH_SUBJECT_MOTHER[root]):
        return TYPE_HEALTH_SUBJECT
    if _contains_any(hay, _CUE_HEALTH_SUBJECT_SELF[root]):
        return "HEALTH_SUBJECT_SELF"
    if _contains_any(hay, _CUE_GENERIC[root]):
        return "GENERIC"
    return None


def _normalize_referents(
    referents: Optional[Sequence[StructuredReferent | Mapping]],
) -> Tuple[StructuredReferent, ...]:
    out: list[StructuredReferent] = []
    for raw in referents or ():
        try:
            if isinstance(raw, StructuredReferent):
                ref = raw
            elif isinstance(raw, Mapping):
                key = str(raw.get("referent_key") or "").strip()
                rtype = str(raw.get("referent_type") or "").strip().upper()
                if not key or not rtype:
                    continue
                auth = str(raw.get("authority_label") or AUTHORITY_PERSONAL).strip().upper()
                if auth not in {AUTHORITY_PERSONAL, AUTHORITY_GOVERNED}:
                    continue
                scope = str(raw.get("source_scope") or SCOPE_UNKNOWN).strip().upper()
                hint = raw.get("retrieval_hint")
                hint_s = str(hint).strip()[:64] if hint else None
                ref = StructuredReferent(
                    referent_type=rtype,
                    referent_key=key[:64],
                    authority_label=auth,
                    source_scope=scope or SCOPE_UNKNOWN,
                    authorized=bool(raw.get("authorized", True)),
                    retrieval_hint=hint_s,
                )
            else:
                continue
            if not ref.authorized:
                continue
            if not ref.referent_key or not ref.referent_type:
                continue
            out.append(ref)
        except Exception:
            continue
    return tuple(out)


def _pick_unique(cands: Sequence[StructuredReferent], *, cue_kind: str) -> CoreferenceResolution:
    if len(cands) == 0:
        return CoreferenceResolution(
            state=STATE_UNRESOLVED,
            clarification_required=True,
            cue_kind=cue_kind,
        )
    if len(cands) > 1:
        return CoreferenceResolution(
            state=STATE_AMBIGUOUS,
            clarification_required=True,
            cue_kind=cue_kind,
            referent_type=cands[0].referent_type,
        )
    one = cands[0]
    return CoreferenceResolution(
        state=STATE_RESOLVED,
        referent_type=one.referent_type,
        referent_key=one.referent_key,
        source_scope=one.source_scope,
        authority_label=one.authority_label,
        clarification_required=False,
        retrieval_hint=one.retrieval_hint or one.referent_key,
        cue_kind=cue_kind,
    )


def resolve_coreference(
    query: str,
    *,
    language: Optional[str] = "en",
    referents: Optional[Sequence[StructuredReferent | Mapping]] = None,
) -> CoreferenceResolution:
    """Deterministic authority-safe coreference. Never invents referents."""
    cue = _detect_cue(query, language=language)
    if cue is None:
        return CoreferenceResolution(state=STATE_NOT_APPLICABLE, clarification_required=False)

    pool = _normalize_referents(referents)

    if cue == TYPE_MEDICATION:
        return _pick_unique(
            [r for r in pool if r.referent_type == TYPE_MEDICATION],
            cue_kind=cue,
        )
    if cue == TYPE_RESULT:
        return _pick_unique(
            [r for r in pool if r.referent_type == TYPE_RESULT],
            cue_kind=cue,
        )
    if cue == TYPE_HEALTH_SUBJECT:
        # Mother/she cues: prefer MANAGED; SELF+MANAGED → ambiguous; SELF-only → unresolved
        # (never substitute Son SELF for Mother MANAGED).
        hs = [r for r in pool if r.referent_type == TYPE_HEALTH_SUBJECT]
        managed = [r for r in hs if r.source_scope == SCOPE_MANAGED]
        self_hs = [r for r in hs if r.source_scope == SCOPE_SELF]
        if managed and self_hs:
            return CoreferenceResolution(
                state=STATE_AMBIGUOUS,
                clarification_required=True,
                cue_kind=cue,
                referent_type=TYPE_HEALTH_SUBJECT,
            )
        if managed:
            return _pick_unique(managed, cue_kind=cue)
        # Mother/she cue without MANAGED referent → do not bind SELF.
        return CoreferenceResolution(
            state=STATE_UNRESOLVED,
            clarification_required=True,
            cue_kind=cue,
            referent_type=TYPE_HEALTH_SUBJECT,
        )

    if cue == "HEALTH_SUBJECT_SELF":
        # Explicit self cue: bind only SCOPE_SELF; never MANAGED.
        self_hs = [
            r
            for r in pool
            if r.referent_type == TYPE_HEALTH_SUBJECT and r.source_scope == SCOPE_SELF
        ]
        return _pick_unique(self_hs, cue_kind=cue)

    # GENERIC "it/that": only resolve when exactly one authorized referent of any type.
    return _pick_unique(pool, cue_kind="GENERIC")
