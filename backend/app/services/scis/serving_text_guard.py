"""Serving text guard (R-044, principle 1: the knowledge Sedi holds must be exactly usable).

What the chat receives is the text of a retrieved CHUNK. Audit of production (2026-10-31) found chunks that are not
knowledge at all and still ranked first for real questions:

- the internal extraction warning tag ``candidate_only_not_approved_knowledge`` (186 chunks of ELIGIBLE units),
- page navigation / link lists such as ``depression in adults diagnosis - depression in adults treatment - ...``,
- headings of one or two words that carry no answer.

This leaf module (no app imports, no I/O) decides whether a text is fit to be served. It only FILTERS what is
served; nothing is deleted, no eligibility state changes, and the medical-safety / governance gates are untouched
(it can only remove text, never add or relax anything). Deterministic and fail-open: any doubt keeps the text.
"""

from __future__ import annotations

import re
from typing import Optional

# Internal tags that leaked into chunk text. Prefix match, case-insensitive.
_INTERNAL_TAG_PREFIXES = ("candidate_only",)
# A lone snake_case token (a tag, not prose): letters/digits/underscores, at least one underscore, no space.
_SNAKE_TAG = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")
# Words that mark a page footer / table of contents rather than content.
_PAGE_FURNITURE = re.compile(r"\b(?:on this page|additional resources|related publications|table of contents)\b", re.I)
_SENTENCE_END = re.compile(r"[.!?؟۔](?:\s|$)")

MIN_WORDS = 4
NAV_MIN_SEPARATORS = 3
NAV_SEPARATOR_DENSITY = 0.10  # at least one " - " per ten words
NAV_MAX_SENTENCE_ENDS = 1


def _words(text: str) -> list[str]:
    return text.split()


def is_internal_tag(text: Optional[str]) -> bool:
    """True for the extraction warning tags (``candidate_only_*``) and any bare snake_case token."""
    s = (text or "").strip().lower()
    if not s:
        return False
    if s.startswith(_INTERNAL_TAG_PREFIXES):
        return True
    return bool(_SNAKE_TAG.match(s))


def looks_like_navigation(text: Optional[str]) -> bool:
    """True for link lists / tables of contents: many ' - ' separators (or page furniture) and almost no sentences."""
    s = (text or "").strip()
    if not s:
        return False
    sentence_ends = len(_SENTENCE_END.findall(s))
    if sentence_ends > NAV_MAX_SENTENCE_ENDS:
        return False
    words = _words(s)
    separators = s.count(" - ")
    if separators >= NAV_MIN_SEPARATORS and separators / max(1, len(words)) >= NAV_SEPARATOR_DENSITY:
        return True
    if len(_PAGE_FURNITURE.findall(s)) >= 2:
        return True
    return False


def is_servable_text(text: Optional[str]) -> bool:
    """False when the text is empty, an internal tag, a navigation list or too short to answer anything."""
    s = (text or "").strip()
    if not s:
        return False
    if is_internal_tag(s):
        return False
    if len(_words(s)) < MIN_WORDS:
        return False
    if looks_like_navigation(s):
        return False
    return True


def pick_servable_statement(*candidates: Optional[str]) -> Optional[str]:
    """First candidate (chunk text, then the unit statement) that is fit to be served, else None."""
    for c in candidates:
        if is_servable_text(c):
            return str(c).strip()
    return None
