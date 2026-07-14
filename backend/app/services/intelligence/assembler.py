"""Section 15-I2 — canonical request-scoped authorized context assembler."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app.services.intelligence.adapters import (
    CurrentMemoryContextAdapter,
    HealthContextAdapter,
    LifestyleContextAdapter,
    ProfileContextAdapter,
    SafeNotificationContextAdapter,
)
from backend.app.services.intelligence.context_types import (
    ADAPTER_ORDER,
    DEFAULT_CONTEXT_BUDGETS,
    CompatibilityProjection,
    ContextBudgets,
    ContextItem,
    ContextSection,
    ContextSnapshot,
    ContextSource,
    is_llm_projection_eligible,
    preferred_name_from_included_items,
    safe_item_sort_key,
)
from backend.app.services.intelligence.contracts import ReasonCode


class ContextAssemblyError(Exception):
    def __init__(self, code: str = "context_assembly_failed"):
        self.code = code
        super().__init__(code)


def _normalized_value(value: Any) -> str:
    return str(value).strip().lower()


class AuthorizedContextAssembler:
    """Deterministic assembler used by structured orchestration mode."""

    def __init__(
        self,
        *,
        profile_adapter: Optional[ProfileContextAdapter] = None,
        lifestyle_adapter: Optional[LifestyleContextAdapter] = None,
        health_adapter: Optional[HealthContextAdapter] = None,
        memory_adapter: Optional[CurrentMemoryContextAdapter] = None,
        notification_adapter: Optional[SafeNotificationContextAdapter] = None,
        budgets: Optional[ContextBudgets] = None,
    ) -> None:
        self._profile = profile_adapter or ProfileContextAdapter()
        self._lifestyle = lifestyle_adapter or LifestyleContextAdapter()
        self._health = health_adapter or HealthContextAdapter()
        self._memory = memory_adapter or CurrentMemoryContextAdapter()
        self._notification = notification_adapter or SafeNotificationContextAdapter()
        self._budgets = budgets or DEFAULT_CONTEXT_BUDGETS

    def assemble(
        self,
        db: Session,
        *,
        authenticated_user_id: int,
        request_id: str,
        notification_context: Optional[Mapping[str, Any]] = None,
        source_notification_id: Optional[int] = None,
    ) -> ContextSnapshot:
        if not isinstance(authenticated_user_id, int) or authenticated_user_id <= 0:
            raise ContextAssemblyError("invalid_owner")

        reason_codes: list[str] = []
        raw_items: list[ContextItem] = []
        budgets = self._budgets

        # Single request-scoped UserContextService load shared by profile/lifestyle/memory.
        # Distinguish loaded-None from not-loaded: always pass the result (object or None).
        try:
            from backend.app.services.user_context import UserContextService

            user_context_pack = UserContextService(db).get_user_context(
                authenticated_user_id
            )
        except Exception as exc:
            raise ContextAssemblyError("context_assembly_failed") from exc

        try:
            for source in ADAPTER_ORDER:
                if source is ContextSource.PROFILE:
                    section_items = self._profile.load(
                        db,
                        authenticated_user_id=authenticated_user_id,
                        user_context_pack=user_context_pack,
                    )
                elif source is ContextSource.LIFESTYLE:
                    section_items = self._lifestyle.load(
                        db,
                        authenticated_user_id=authenticated_user_id,
                        user_context_pack=user_context_pack,
                    )
                elif source is ContextSource.HEALTH:
                    section_items = self._health.load(
                        db, authenticated_user_id=authenticated_user_id
                    )
                elif source is ContextSource.MEMORY:
                    section_items = self._memory.load(
                        db,
                        authenticated_user_id=authenticated_user_id,
                        user_context_pack=user_context_pack,
                        budgets=budgets,
                    )
                else:
                    section_items = self._notification.load(
                        authenticated_user_id=authenticated_user_id,
                        notification_context=notification_context,
                        source_notification_id=source_notification_id,
                    )
                for item in section_items:
                    if item.provenance.owner_user_id != authenticated_user_id:
                        raise ContextAssemblyError("cross_user_context_rejected")
                if not section_items:
                    reason_codes.append(ReasonCode.CONTEXT_SECTION_EMPTY.value)
                raw_items.extend(section_items)
        except ContextAssemblyError:
            raise
        except Exception as exc:
            raise ContextAssemblyError("context_assembly_failed") from exc

        resolved, conflict_count = _resolve_conflicts(raw_items)
        if conflict_count:
            reason_codes.append(ReasonCode.CONTEXT_CONFLICT_DETECTED.value)

        truncated, truncated_count = _apply_budgets(resolved, budgets)
        if truncated_count:
            reason_codes.append(ReasonCode.CONTEXT_BUDGET_TRUNCATED.value)

        truncated.sort(key=safe_item_sort_key)
        sections = _group_sections(truncated)
        reason_codes.append(ReasonCode.CONTEXT_ASSEMBLED.value)

        return ContextSnapshot(
            request_id=request_id,
            owner_user_id=authenticated_user_id,
            sections=sections,
            items=truncated,
            # Preferred name is bound only after final projection inclusion.
            preferred_name=None,
            conflict_count=conflict_count,
            truncated_count=truncated_count,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            adapter_order=tuple(s.value for s in ADAPTER_ORDER),
            budget_classification=budgets.classification,
        )

    def build_compatibility_projection(
        self, snapshot: ContextSnapshot
    ) -> CompatibilityProjection:
        budgets = self._budgets
        eligible_pairs: list[tuple[ContextItem, str]] = []
        excluded_conflicts = 0
        for item in sorted(snapshot.items, key=safe_item_sort_key):
            if item.conflicted:
                excluded_conflicts += 1
                continue
            if not is_llm_projection_eligible(item):
                continue
            # Never project consent/provenance internals or owner IDs.
            line = f"- [{item.section}] {item.display_text}"
            eligible_pairs.append((item, line))

        header = "[STRUCTURED_CONTEXT]"
        truncated = False
        included_items: list[ContextItem] = []
        kept_lines: list[str] = []
        # Deterministic whole-line char budget; retain included item refs.
        for item, line in eligible_pairs:
            candidate = "\n".join([header, *kept_lines, line])
            if len(candidate) > budgets.max_compatibility_projection_chars:
                truncated = True
                break
            kept_lines.append(line)
            included_items.append(item)

        text = "\n".join([header, *kept_lines]) if kept_lines else header
        return CompatibilityProjection(
            text=text,
            item_count=len(included_items),
            char_count=len(text),
            truncated=truncated,
            excluded_conflict_count=excluded_conflicts,
            preferred_name=preferred_name_from_included_items(included_items),
        )


def _resolve_conflicts(
    items: Sequence[ContextItem],
) -> tuple[list[ContextItem], int]:
    """
    Conservative conflict policy (no unsupported source supersession):

    - identical values for same canonical key → coalesce (keep combined provenance)
    - different active values → mark conflicted; exclude from LLM projection
    - recency / SOURCE_SORT_RANK alone never selects a winner
    """
    by_key: dict[str, list[ContextItem]] = {}
    for item in items:
        by_key.setdefault(item.canonical_key, []).append(item)

    out: list[ContextItem] = []
    conflicts = 0
    for key in sorted(by_key.keys()):
        group = list(by_key[key])
        if len(group) == 1:
            out.append(group[0])
            continue

        value_groups: dict[str, list[ContextItem]] = {}
        for item in group:
            value_groups.setdefault(_normalized_value(item.structured_value), []).append(
                item
            )

        if len(value_groups) == 1:
            # Identical-value coalesce: deterministic primary; retain provenance.
            ranked = sorted(group, key=safe_item_sort_key)
            primary = ranked[0]
            for other in ranked[1:]:
                other.active = False
                other.conflicted = False
                primary.coalesced_provenance.append(other.provenance)
                out.append(other)
            out.append(primary)
            continue

        # Different values, no proven authority relation → conflict all.
        conflicts += 1
        for item in sorted(group, key=safe_item_sort_key):
            item.conflicted = True
            item.active = False
            out.append(item)
    return out, conflicts


def _apply_budgets(
    items: Sequence[ContextItem], budgets: ContextBudgets
) -> tuple[list[ContextItem], int]:
    sorted_items = sorted(items, key=safe_item_sort_key)
    per_section: dict[str, int] = {}
    kept: list[ContextItem] = []
    truncated = 0
    for item in sorted_items:
        if not item.active or item.conflicted:
            kept.append(item)
            continue
        sec_count = per_section.get(item.section, 0)
        if sec_count >= budgets.max_items_per_section:
            item.truncated = True
            item.active = False
            truncated += 1
            kept.append(item)
            continue
        active_kept = sum(1 for k in kept if k.active and not k.conflicted)
        if active_kept >= budgets.max_total_context_items:
            item.truncated = True
            item.active = False
            truncated += 1
            kept.append(item)
            continue
        per_section[item.section] = sec_count + 1
        kept.append(item)
    return kept, truncated


def _group_sections(items: Sequence[ContextItem]) -> dict[str, ContextSection]:
    sections: dict[str, ContextSection] = {
        name: ContextSection(name=name)  # type: ignore[arg-type]
        for name in ("profile", "lifestyle", "health", "memory", "notification")
    }
    for item in items:
        sections[item.section].items.append(item)
    for name, section in sections.items():
        if not section.items:
            section.empty_reason = "no_data"
    return sections
