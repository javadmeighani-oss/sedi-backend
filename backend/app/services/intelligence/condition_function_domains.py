"""Condition -> body-function domains (I1, read-only, data-driven; Stage 06 / B1).

Deterministic and snapshot-only: maps the condition texts a user already has on file to the function
domains worth asking about before a personalized nutrition/activity plan. The mapping lives in
`backend/config/i1/condition_function_domains_v1.yaml`; a condition with no match falls back to the
generic domain, so any condition is covered. No DB, no LLM, no new storage.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

import yaml

_CONFIG = Path(__file__).resolve().parents[3] / "config" / "i1" / "condition_function_domains_v1.yaml"
FUNCTION_TARGET_PREFIX = "function."


@lru_cache(maxsize=1)
def _load() -> dict:
    return yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))


def known_domains() -> tuple[str, ...]:
    return tuple(_load()["domains"])


def target_key(domain: str) -> str:
    return f"{FUNCTION_TARGET_PREFIX}{domain}"


def all_target_keys() -> tuple[str, ...]:
    return tuple(target_key(d) for d in known_domains())


def _has_phrase(text: str, phrase: str) -> bool:
    if phrase.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None
    return phrase in text


def domains_for_conditions(condition_texts: Iterable[str]) -> list[str]:
    """Ordered, de-duplicated domains for the given condition texts (fallback when nothing matches)."""
    cfg = _load()
    out: list[str] = []
    saw_condition = False
    for raw in condition_texts:
        text = " ".join(str(raw or "").lower().split())
        if not text:
            continue
        saw_condition = True
        matched = False
        for entry in cfg["conditions"]:
            if any(_has_phrase(text, p.lower()) for p in entry["phrases"]):
                matched = True
                out.extend(d for d in entry["domains"] if d not in out)
        if not matched:
            out.extend(d for d in cfg["fallback_domains"] if d not in out)
    return out if saw_condition else []


def first_unanswered_domain(domains: Sequence[str], answered_keys: Iterable[str]) -> str | None:
    answered = set(answered_keys)
    for d in domains:
        if target_key(d) not in answered:
            return d
    return None
