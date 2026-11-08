"""R-074 step 8a - deterministic Persian/Arabic -> English search bridge for EVERY health topic of the governed library.

The governed knowledge is English official text. A Persian/Arabic question reaches it through English keyword alternatives.
`psychology_query_bridge` already answers psychology / wellbeing questions instantly; this module does the same for the
other topic families of the library, from the data file `config/i5/health_query_lexicon_v1.yaml` (one entry per topic
family, official English page names, fa/ar marker words). No model call, no I/O after load, deterministic.

- Output is a non-authoritative search hint (same contract as ``query_translation``): evidence still comes from governed,
  ELIGIBLE knowledge units only.
- Fail-open: a missing / invalid lexicon yields [] and the existing translation path runs unchanged.
- A question that also matches a psychology topic is NOT bridged here (the caller sends combined questions to the model).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from backend.app.services.i5.psychology_query_bridge import MAX_ALTERNATIVES, MAX_TOPICS, normalize

_LEXICON = Path(__file__).resolve().parents[3] / "config" / "i5" / "health_query_lexicon_v1.yaml"
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class _Entry(NamedTuple):
    key: str
    alternatives: tuple[str, ...]
    markers: tuple[tuple[re.Pattern, int], ...]  # (compiled pattern, marker length)


def _norm(text: str) -> str:
    return normalize(str(text or "").translate(_DIGITS))


def _marker_pattern(marker: str) -> re.Pattern:
    """<=3 letters: whole word; 4-5 letters: must start a word (Persian suffixes attach); longer: substring."""
    body = re.escape(marker)
    if len(marker) <= 3:
        return re.compile(rf"(?<!\S){body}(?!\S)")
    if len(marker) <= 5:
        return re.compile(rf"(?<!\S){body}")
    return re.compile(body)


@lru_cache(maxsize=1)
def _entries() -> tuple[_Entry, ...]:
    try:
        import yaml

        raw = yaml.safe_load(_LEXICON.read_text(encoding="utf-8")) or {}
        out: list[_Entry] = []
        for row in raw.get("entries") or []:
            alts = tuple(str(a).strip() for a in (row.get("en") or []) if str(a).strip())
            markers: list[tuple[re.Pattern, int]] = []
            for m in list(row.get("fa") or []) + list(row.get("ar") or []):
                nm = _norm(m)
                if len(nm) >= 2:
                    markers.append((_marker_pattern(nm), len(nm)))
            if alts and markers:
                out.append(_Entry(str(row.get("k")), alts, tuple(markers)))
        return tuple(out)
    except Exception:  # noqa: BLE001 — retrieval aid only; fail-open to the existing path
        return ()


def _longest_hit(entry: _Entry, text: str) -> int:
    best = 0
    for pat, length in entry.markers:
        if length > best and pat.search(text):
            best = length
    return best


def matched_topics(query: str) -> list[str]:
    """Keys of the topic families the question names, most specific first (for tests and diagnostics)."""
    s = _norm(query)
    if not s:
        return []
    hits = [(_longest_hit(e, s), -i, e.key) for i, e in enumerate(_entries())]
    return [k for h, _i, k in sorted((x for x in hits if x[0] > 0), reverse=True)]


def health_bridge_alternatives(query: str) -> list[str]:
    """English keyword alternatives (specific first, at most MAX_ALTERNATIVES) for a clear health-topic question, else []."""
    s = _norm(query)
    if not s:
        return []
    ranked = sorted(
        ((_longest_hit(e, s), -i, e) for i, e in enumerate(_entries())),
        key=lambda x: (x[0], x[1]),
        reverse=True,
    )
    chosen = [e for hit, _i, e in ranked if hit > 0][:MAX_TOPICS]
    if not chosen:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for depth in range(max(len(e.alternatives) for e in chosen)):  # most specific name of each topic first
        for e in chosen:
            if depth < len(e.alternatives):
                cand = e.alternatives[depth]
                if cand.lower() not in seen:
                    seen.add(cand.lower())
                    out.append(cand)
                if len(out) == MAX_ALTERNATIVES:
                    return out
    return out
