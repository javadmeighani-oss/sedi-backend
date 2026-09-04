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


@dataclass(frozen=True)
class LexicalQueryPlan:
    """At most PRIMARY + one FALLBACK formulation."""

    original_query: str
    language: str
    normalized_original: str
    primary_query: str
    fallback_query: Optional[str]
    original_tokens: Tuple[str, ...]
    primary_tokens: Tuple[str, ...]
    fallback_tokens: Tuple[str, ...]

    @property
    def original_token_count(self) -> int:
        return len(self.original_tokens)

    @property
    def primary_token_count(self) -> int:
        return len(self.primary_tokens)

    @property
    def fallback_token_count(self) -> int:
        return len(self.fallback_tokens)


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


def formulate_lexical_query_plan(query: str, *, language: str = "en") -> LexicalQueryPlan:
    """Build PRIMARY (+ optional FALLBACK) lexical query strings.

    PRIMARY: normalized query minus function words (bounded).
    FALLBACK: further drop soft care-scaffolding; keep acronyms/long terms.
    Never expands into unbounded OR over every token.
    """
    original = query or ""
    normalized = normalize_for_language(original, language)
    original_tokens = _tokenize(normalized)
    primary_tokens = _content_tokens(original_tokens, language)
    primary_query = " ".join(primary_tokens)

    fallback_tokens = _select_fallback_tokens(primary_tokens)
    fallback_query: Optional[str] = None
    if fallback_tokens and tuple(fallback_tokens) != tuple(primary_tokens):
        fallback_query = " ".join(fallback_tokens)
    elif fallback_tokens and len(primary_tokens) > _MAX_FALLBACK_TOKENS:
        fallback_query = " ".join(fallback_tokens)

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
