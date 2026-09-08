"""Phase2-A CASE_10 — bounded curated alias expansion (non-authoritative).

GENERATIVE_EXPANSION=NO / LLM=NO / TRANSLATION_EXPANSION=NO.
Aliases are retrieval hints only. ALIAS_AUTHORITY=NONAUTHORITATIVE.

Production registry ships empty until a governed alias source is approved.
Tests inject synthetic maps via AliasRegistry(entries=...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence, Tuple

from backend.app.services.scis.normalize import normalize_for_language

ALIAS_REGISTRY_VERSION = "v1-empty-nonauthoritative"
ALIAS_AUTHORITY = "NONAUTHORITATIVE"
MAX_ALIAS_EXPANSIONS_PER_QUERY = 4

# Empty by design — do not hardcode unreviewed clinical mappings.
_DEFAULT_ENTRIES: dict[str, tuple[str, ...]] = {}


@dataclass(frozen=True)
class AliasExpansionResult:
    expansions: Tuple[str, ...]
    registry_version: str
    authority: str = ALIAS_AUTHORITY
    matched_keys: Tuple[str, ...] = ()

    def to_audit_dict(self) -> dict:
        return {
            "expansions": list(self.expansions),
            "expansion_count": len(self.expansions),
            "registry_version": self.registry_version,
            "authority": self.authority,
            "matched_keys": list(self.matched_keys),
            "ALIAS_AUTHORITY": self.authority,
        }


@dataclass(frozen=True)
class AliasRegistry:
    """Versioned in-process alias map. Never clinical SoT."""

    version: str = ALIAS_REGISTRY_VERSION
    entries: Mapping[str, Sequence[str]] = field(default_factory=dict)
    authority: str = ALIAS_AUTHORITY

    def expand(
        self,
        query: str,
        *,
        language: str = "en",
        max_expansions: int = MAX_ALIAS_EXPANSIONS_PER_QUERY,
    ) -> AliasExpansionResult:
        max_expansions = max(0, min(int(max_expansions), MAX_ALIAS_EXPANSIONS_PER_QUERY))
        entries = self.entries or _DEFAULT_ENTRIES
        if max_expansions == 0 or not entries:
            return AliasExpansionResult(
                expansions=(),
                registry_version=self.version,
                authority=self.authority,
            )
        norm = normalize_for_language(query or "", language)
        tokens = tuple(t for t in norm.split(" ") if t)
        hay = f" {norm} "
        expansions: list[str] = []
        matched: list[str] = []
        seen: set[str] = set()

        # Longest key first for stable deterministic matching.
        keys = sorted(entries.keys(), key=lambda k: (-len(k), k))
        for key in keys:
            nk = normalize_for_language(key, language)
            if not nk:
                continue
            if f" {nk} " not in hay and nk not in tokens and hay.strip() != nk:
                continue
            matched.append(nk)
            for alias in entries[key]:
                na = normalize_for_language(str(alias or ""), language).strip()
                if not na or na in seen or na == norm or na == nk:
                    continue
                seen.add(na)
                expansions.append(na)
                if len(expansions) >= max_expansions:
                    return AliasExpansionResult(
                        expansions=tuple(expansions),
                        registry_version=self.version,
                        authority=self.authority,
                        matched_keys=tuple(matched),
                    )
        return AliasExpansionResult(
            expansions=tuple(expansions),
            registry_version=self.version,
            authority=self.authority,
            matched_keys=tuple(matched),
        )


_PRODUCT_REGISTRY = AliasRegistry()


def get_product_alias_registry() -> AliasRegistry:
    """Canonical product registry (empty until governed content approved)."""
    return _PRODUCT_REGISTRY


def expand_query_aliases(
    query: str,
    *,
    language: str = "en",
    registry: Optional[AliasRegistry] = None,
    max_expansions: int = MAX_ALIAS_EXPANSIONS_PER_QUERY,
) -> AliasExpansionResult:
    reg = registry or get_product_alias_registry()
    return reg.expand(query, language=language, max_expansions=max_expansions)
