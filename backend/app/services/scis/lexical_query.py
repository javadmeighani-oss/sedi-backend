"""Deterministic lexical query formulation for SCIS FTS (token-efficient).

Reduces natural-language function words so plainto_tsquery('simple', ...) does
not AND every conversational token. Generic across diseases/topics — no
domain-specific branches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from backend.app.services.scis.normalize import normalize_for_language

# Hard function/stop words only (not medical synonym expansion).
_EN_FUNCTION_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "to",
        "with",
        "without",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "are",
        "be",
        "been",
        "being",
        "before",
        "below",
        "between",
        "both",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "during",
        "each",
        "few",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "him",
        "his",
        "how",
        "i",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "only",
        "other",
        "our",
        "ours",
        "out",
        "over",
        "own",
        "same",
        "shall",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "theirs",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "would",
        "you",
        "your",
        "yours",
    }
)

# Soft drop for FALLBACK only — conversational care scaffolding, not disease terms.
_EN_SOFT_FALLBACK_DROP = frozenset(
    {
        "monitored",
        "monitoring",
        "monitor",
        "daily",
        "person",
        "people",
        "someone",
        "something",
        "things",
        "thing",
        "cases",
        "case",
        "items",
        "item",
        "aspects",
        "aspect",
        "regarding",
        "concerning",
        "care",
        "support",
        "supportive",
        "management",
        "question",
        "need",
        "needs",
        "needed",
    }
)

# Bounded FA/AR function words (no synonym / translation dictionary).
_FA_AR_FUNCTION_WORDS = frozenset(
    {
        "چه",
        "چی",
        "برای",
        "از",
        "به",
        "با",
        "در",
        "که",
        "را",
        "و",
        "یا",
        "این",
        "آن",
        "یک",
        "ها",
        "های",
        "مورد",
        "موارد",
        "باید",
        "تحت",
        "نظر",
        "باشد",
        "هستند",
        "است",
        "بود",
        "فرد",
        "افراد",
        "روزانه",
        "مبتلا",
        "مراقبت",
        "کدام",
        "چگونه",
        "آیا",
        "من",
        "ما",
        "او",
        "آنها",
        "على",
        "في",
        "من",
        "إلى",
        "عن",
        "مع",
        "هذا",
        "هذه",
        "ما",
        "هل",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]+", re.UNICODE)

_MAX_PRIMARY_TOKENS = 8
_MAX_FALLBACK_TOKENS = 4
_MIN_TOKEN_LEN = 2

# Phase2-A CASE_02 — bounded adjacent phrase preservation (metadata complement).
MAX_PHRASE_TOKENS = 3
MAX_PHRASES_PER_QUERY = 6

# CASE04 — bounded explicit negation markers (no NLI / synonym expansion).
# plainto_tsquery cannot faithfully preserve polarity; lexical FTS fail-closes.
NEGATION_POLICY_NONE = "NONE"
NEGATION_POLICY_FAIL_CLOSED = "FAIL_CLOSED_LEXICAL_FTS_CANNOT_PRESERVE_POLARITY"
NEGATION_SUPPORT = "BOUNDED_EXPLICIT_MARKER_SEMANTICS"

_EXPLICIT_NEGATION_MARKERS_EN = frozenset({"not", "no", "nor", "without"})
_EXPLICIT_NEGATION_MARKERS_FA = frozenset({"نه", "نیست", "نیستند", "بدون"})
_EXPLICIT_NEGATION_MARKERS_AR = frozenset({"لا", "ليس", "ليست", "بدون"})


@dataclass(frozen=True)
class LexicalQueryPlan:
    """At most PRIMARY + one FALLBACK formulation.

    phrases: adjacent multi-token content phrases (≤3 tokens each, ≤6 total).
    alias_hints: non-authoritative curated expansions (≤4); never clinical truth.
    negation_*: runtime-only polarity safety metadata (never persisted).
    """

    original_query: str
    language: str
    normalized_original: str
    primary_query: str
    fallback_query: Optional[str]
    original_tokens: Tuple[str, ...]
    primary_tokens: Tuple[str, ...]
    fallback_tokens: Tuple[str, ...]
    phrases: Tuple[str, ...] = ()
    alias_hints: Tuple[str, ...] = ()
    negation_present: bool = False
    negation_markers: Tuple[str, ...] = ()
    negation_policy: str = NEGATION_POLICY_NONE

    @property
    def original_token_count(self) -> int:
        return len(self.original_tokens)

    @property
    def primary_token_count(self) -> int:
        return len(self.primary_tokens)

    @property
    def fallback_token_count(self) -> int:
        return len(self.fallback_tokens)

    @property
    def phrase_count(self) -> int:
        return len(self.phrases)


def _is_fa_ar(language: str | None) -> bool:
    lang = (language or "en").lower()
    return lang.startswith("fa") or lang.startswith("ar") or lang in {"persian", "arabic", "farsi"}


def _tokenize(normalized: str) -> Tuple[str, ...]:
    if not normalized:
        return ()
    return tuple(t for t in _TOKEN_RE.findall(normalized) if len(t) >= _MIN_TOKEN_LEN)


def _function_words(language: str | None) -> frozenset[str]:
    if _is_fa_ar(language):
        return _FA_AR_FUNCTION_WORDS | _EN_FUNCTION_WORDS
    return _EN_FUNCTION_WORDS


def _negation_marker_set(language: str | None) -> frozenset[str]:
    """Bounded explicit markers for the active language (plus shared بدون).

    Includes language-normalized forms so Arabic yeh → Persian yeh rewrites
    (normalize_for_language) still match deterministically.
    """
    lang = (language or "en").lower()
    if lang.startswith("fa") or lang in {"persian", "farsi"}:
        raw = _EXPLICIT_NEGATION_MARKERS_FA | _EXPLICIT_NEGATION_MARKERS_EN
    elif lang.startswith("ar") or lang in {"arabic"}:
        raw = _EXPLICIT_NEGATION_MARKERS_AR | _EXPLICIT_NEGATION_MARKERS_EN
    else:
        raw = _EXPLICIT_NEGATION_MARKERS_EN
    out: set[str] = set()
    for m in raw:
        out.add(m)
        nm = normalize_for_language(m, language)
        if nm:
            out.add(nm)
            out.update(_tokenize(nm))
    return frozenset(out)


def detect_explicit_negation(
    tokens: Sequence[str],
    *,
    language: str | None = "en",
) -> Tuple[bool, Tuple[str, ...]]:
    """Detect bounded explicit negation markers in already-tokenized text.

    Does not perform NLI, synonym expansion, or grammar understanding.
    """
    markers = _negation_marker_set(language)
    found: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t in markers and t not in seen:
            seen.add(t)
            found.append(t)
    return bool(found), tuple(found)


def _content_tokens(tokens: Sequence[str], language: str | None) -> Tuple[str, ...]:
    stops = _function_words(language)
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t in stops or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= _MAX_PRIMARY_TOKENS:
            break
    return tuple(out)


def _fallback_value(token: str) -> int:
    """Higher = keep sooner. Prefer short acronyms and long content terms."""
    if token in _EN_SOFT_FALLBACK_DROP:
        return -1
    if token.isalpha() and 2 <= len(token) <= 5:
        return 200 - len(token)  # short acronym-style tokens
    return len(token)


def _select_fallback_tokens(primary: Sequence[str]) -> Tuple[str, ...]:
    ranked = sorted(
        (( _fallback_value(t), i, t) for i, t in enumerate(primary)),
        key=lambda x: (-x[0], x[1]),
    )
    chosen: list[str] = []
    for score, _i, tok in ranked:
        if score < 0:
            continue
        chosen.append(tok)
        if len(chosen) >= _MAX_FALLBACK_TOKENS:
            break
    if not chosen:
        return ()
    # Preserve original relative order among selected tokens.
    selected = set(chosen)
    return tuple(t for t in primary if t in selected)


def extract_important_phrases(
    tokens: Sequence[str],
    *,
    language: str | None = "en",
    max_phrase_tokens: int = MAX_PHRASE_TOKENS,
    max_phrases: int = MAX_PHRASES_PER_QUERY,
) -> Tuple[str, ...]:
    """Preserve adjacent multi-token content phrases (deterministic, bounded).

    Does not create clinical authority, synonyms, or translations.
    Unigrams are not phrases. Max phrase length ≤3; max phrases ≤6.
    """
    if max_phrase_tokens < 2 or max_phrases < 1:
        return ()
    max_phrase_tokens = min(int(max_phrase_tokens), MAX_PHRASE_TOKENS)
    max_phrases = min(int(max_phrases), MAX_PHRASES_PER_QUERY)
    stops = _function_words(language)
    runs: list[list[str]] = []
    current: list[str] = []
    for t in tokens:
        if t in stops:
            if current:
                runs.append(current)
                current = []
            continue
        current.append(t)
    if current:
        runs.append(current)

    phrases: list[str] = []
    seen: set[str] = set()
    # Prefer longer phrases first; no unbounded n-gram explosion.
    for run in runs:
        if len(run) < 2:
            continue
        upper = min(len(run), max_phrase_tokens)
        for length in range(upper, 1, -1):
            for i in range(0, len(run) - length + 1):
                phrase = " ".join(run[i : i + length])
                if phrase in seen:
                    continue
                seen.add(phrase)
                phrases.append(phrase)
                if len(phrases) >= max_phrases:
                    return tuple(phrases)
    return tuple(phrases)


def formulate_lexical_query_plan(
    query: str,
    *,
    language: str = "en",
    alias_hints: Optional[Sequence[str]] = None,
) -> LexicalQueryPlan:
    """Build PRIMARY (+ optional FALLBACK) lexical query strings.

    PRIMARY: normalized query minus function words (bounded).
    FALLBACK: further drop soft care-scaffolding; keep acronyms/long terms.
    phrases: adjacent multi-token metadata (does not replace PRIMARY/FALLBACK).
    Never expands into unbounded OR over every token.

    CASE04: explicit negation markers must not silently disappear into an
    opposite-polarity FTS query. When markers are present, lexical FTS is
    fail-closed (empty PRIMARY/FALLBACK); original_query is preserved for
    semantic/embedding paths.
    """
    original = query or ""
    normalized = normalize_for_language(original, language)
    original_tokens = _tokenize(normalized)
    negation_present, negation_markers = detect_explicit_negation(
        original_tokens, language=language
    )

    # Fail-closed lexical path: do not emit an FTS string that drops polarity.
    if negation_present:
        return LexicalQueryPlan(
            original_query=original,
            language=(language or "en"),
            normalized_original=normalized,
            primary_query="",
            fallback_query=None,
            original_tokens=original_tokens,
            primary_tokens=(),
            fallback_tokens=(),
            phrases=(),
            alias_hints=(),
            negation_present=True,
            negation_markers=negation_markers,
            negation_policy=NEGATION_POLICY_FAIL_CLOSED,
        )

    primary_tokens = _content_tokens(original_tokens, language)
    primary_query = " ".join(primary_tokens)

    fallback_tokens = _select_fallback_tokens(primary_tokens)
    fallback_query: Optional[str] = None
    if fallback_tokens and tuple(fallback_tokens) != tuple(primary_tokens):
        fallback_query = " ".join(fallback_tokens)
    elif fallback_tokens and len(primary_tokens) > _MAX_FALLBACK_TOKENS:
        fallback_query = " ".join(fallback_tokens)

    phrases = extract_important_phrases(original_tokens, language=language)
    hints: Tuple[str, ...] = ()
    if alias_hints:
        # Bound + dedupe; never inflate PRIMARY token budget.
        seen_h: set[str] = set()
        collected: list[str] = []
        for h in alias_hints:
            nh = normalize_for_language(str(h or ""), language).strip()
            if not nh or nh in seen_h or nh == primary_query:
                continue
            seen_h.add(nh)
            collected.append(nh)
            if len(collected) >= 4:
                break
        hints = tuple(collected)

    # If PRIMARY empty but original had tokens, keep empty (fail closed).
    return LexicalQueryPlan(
        original_query=original,
        language=(language or "en"),
        normalized_original=normalized,
        primary_query=primary_query,
        fallback_query=fallback_query,
        original_tokens=original_tokens,
        primary_tokens=primary_tokens,
        fallback_tokens=fallback_tokens if fallback_query else (),
        phrases=phrases,
        alias_hints=hints,
        negation_present=False,
        negation_markers=(),
        negation_policy=NEGATION_POLICY_NONE,
    )


def token_coverage_score(text: str, tokens: Sequence[str]) -> float:
    """Fraction of plan tokens present in haystack (deterministic noise demotion)."""
    if not tokens:
        return 0.0
    hay = f" {normalize_for_language(text or '', 'en')} "
    hits = 0
    for t in tokens:
        if f" {t} " in hay or hay.startswith(f"{t} ") or hay.endswith(f" {t}") or hay.strip() == t:
            hits += 1
    return hits / float(len(tokens))


def phrase_coverage_score(text: str, phrases: Sequence[str], *, language: str = "en") -> float:
    """Fraction of preserved phrases present as contiguous spans in haystack."""
    if not phrases:
        return 0.0
    hay = f" {normalize_for_language(text or '', language)} "
    hits = 0
    for p in phrases:
        needle = f" {p} "
        if needle in hay or hay.strip() == p:
            hits += 1
    return hits / float(len(phrases))
