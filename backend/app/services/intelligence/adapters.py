"""Section 15-I2 — connected authorized context adapters (request-scoped)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app.services.intelligence.context_types import (
    DEFAULT_CONTEXT_BUDGETS,
    SOURCE_SORT_RANK,
    USER_CONTEXT_PACK_UNSET,
    ConsentState,
    ContextBudgets,
    ContextItem,
    ContextProvenance,
    ContextSource,
    FreshnessState,
    SensitivityClass,
)

# Keys already injected by ConversationBrain._format_notification_context_block /
# Gate4 build_safe_chat_context. Unknown keys are ignored (no open dump).
SAFE_NOTIFICATION_LLM_KEYS = frozenset(
    {
        "category",
        "template_key",
        "risk_level",
        "source_type",
        "source_id",
        "notification_title",
        "notification_summary",
        "conversation_id",
        "interaction_source",
    }
)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _freshness(observed_at: Optional[datetime]) -> FreshnessState:
    # I2: no invented expiry; missing or present stamp → unknown without domain rule.
    return "unknown"


def _slug(text: str, *, max_len: int = 64) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in text.strip().lower())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")[:max_len] or "item"


def _item(
    *,
    canonical_key: str,
    section: str,
    source: ContextSource,
    value: Any,
    display_text: str,
    owner_user_id: int,
    query_label: str,
    observed_at: Optional[datetime],
    sensitivity: SensitivityClass,
    may_send_to_llm: bool = True,
    consent: ConsentState = "legacy_scope",
) -> ContextItem:
    return ContextItem(
        canonical_key=canonical_key,
        section=section,  # type: ignore[arg-type]
        source=source,
        structured_value=value,
        display_text=display_text.strip()[:500],
        provenance=ContextProvenance(
            source=source,
            owner_user_id=owner_user_id,
            query_label=query_label,
        ),
        observed_at=_utc(observed_at),
        freshness=_freshness(observed_at),
        sensitivity=sensitivity,
        consent=consent,
        may_send_to_llm=may_send_to_llm,
        sort_rank=SOURCE_SORT_RANK[source],
    )


class ProfileContextAdapter:
    """Basic USER_CONTEXT profile fields + USER_PROFILE knowledge already on brain path."""

    def load(
        self,
        db: Session,
        *,
        authenticated_user_id: int,
        user_context_pack: Any = USER_CONTEXT_PACK_UNSET,
    ) -> list[ContextItem]:
        if user_context_pack is USER_CONTEXT_PACK_UNSET:
            from backend.app.services.user_context import UserContextService

            pack = UserContextService(db).get_user_context(authenticated_user_id)
        else:
            pack = user_context_pack

        items: list[ContextItem] = []
        if pack is not None:
            if getattr(pack, "preferred_name", None):
                items.append(
                    _item(
                        canonical_key="profile.preferred_name",
                        section="profile",
                        source=ContextSource.PROFILE,
                        value=pack.preferred_name,
                        display_text=f"preferred_name={pack.preferred_name}",
                        owner_user_id=authenticated_user_id,
                        query_label="UserContextService.get_user_context",
                        observed_at=None,
                        sensitivity="medium",
                    )
                )
            if getattr(pack, "birth_year", None) is not None:
                items.append(
                    _item(
                        canonical_key="profile.birth_year",
                        section="profile",
                        source=ContextSource.PROFILE,
                        value=pack.birth_year,
                        display_text=f"birth_year={pack.birth_year}",
                        owner_user_id=authenticated_user_id,
                        query_label="UserContextService.get_user_context",
                        observed_at=None,
                        sensitivity="medium",
                    )
                )
            if getattr(pack, "sex", None):
                items.append(
                    _item(
                        canonical_key="profile.sex",
                        section="profile",
                        source=ContextSource.PROFILE,
                        value=pack.sex,
                        display_text=f"sex={pack.sex}",
                        owner_user_id=authenticated_user_id,
                        query_label="UserContextService.get_user_context",
                        observed_at=None,
                        sensitivity="high",
                    )
                )
            if getattr(pack, "addressing_preference", None):
                items.append(
                    _item(
                        canonical_key="profile.addressing_preference",
                        section="profile",
                        source=ContextSource.PROFILE,
                        value=pack.addressing_preference,
                        display_text=f"addressing={pack.addressing_preference}",
                        owner_user_id=authenticated_user_id,
                        query_label="UserContextService.get_user_context",
                        observed_at=None,
                        sensitivity="low",
                    )
                )

        items.extend(
            self._load_user_profile_knowledge(db, authenticated_user_id=authenticated_user_id)
        )
        return items

    def _load_user_profile_knowledge(
        self, db: Session, *, authenticated_user_id: int
    ) -> list[ContextItem]:
        """Mirror ConversationBrain._build_user_knowledge_context (legacy [USER_PROFILE])."""
        items: list[ContextItem] = []
        try:
            from backend.app import models
        except Exception:
            return items

        try:
            profile = (
                db.query(models.UserProfileKnowledge)
                .filter(models.UserProfileKnowledge.user_id == authenticated_user_id)
                .first()
            )
        except Exception as exc:
            raise RuntimeError("profile_knowledge_query_failed") from exc

        if profile is not None:
            if profile.baseline_summary and str(profile.baseline_summary).strip():
                text = str(profile.baseline_summary).strip()[:400]
                items.append(
                    _item(
                        canonical_key="profile.knowledge.baseline",
                        section="profile",
                        source=ContextSource.PROFILE,
                        value=text,
                        display_text=f"baseline={text[:200]}",
                        owner_user_id=authenticated_user_id,
                        query_label="UserProfileKnowledge.baseline_summary",
                        observed_at=None,
                        sensitivity="high",
                    )
                )
            if profile.goals_json and str(profile.goals_json).strip():
                text = str(profile.goals_json).strip()[:300]
                items.append(
                    _item(
                        canonical_key="profile.knowledge.goals",
                        section="profile",
                        source=ContextSource.PROFILE,
                        value=text,
                        display_text=f"knowledge_goals={text[:200]}",
                        owner_user_id=authenticated_user_id,
                        query_label="UserProfileKnowledge.goals_json",
                        observed_at=None,
                        sensitivity="medium",
                    )
                )
            if profile.constraints_json and str(profile.constraints_json).strip():
                text = str(profile.constraints_json).strip()[:300]
                items.append(
                    _item(
                        canonical_key="profile.knowledge.constraints",
                        section="profile",
                        source=ContextSource.PROFILE,
                        value=text,
                        display_text=f"constraints={text[:200]}",
                        owner_user_id=authenticated_user_id,
                        query_label="UserProfileKnowledge.constraints_json",
                        observed_at=None,
                        sensitivity="high",
                    )
                )
            if profile.preferences_json and str(profile.preferences_json).strip():
                text = str(profile.preferences_json).strip()[:300]
                items.append(
                    _item(
                        canonical_key="profile.knowledge.preferences",
                        section="profile",
                        source=ContextSource.PROFILE,
                        value=text,
                        display_text=f"preferences={text[:200]}",
                        owner_user_id=authenticated_user_id,
                        query_label="UserProfileKnowledge.preferences_json",
                        observed_at=None,
                        sensitivity="medium",
                    )
                )

        try:
            facts = (
                db.query(models.UserFact)
                .filter(models.UserFact.user_id == authenticated_user_id)
                .order_by(models.UserFact.updated_at.desc())
                .limit(30)
                .all()
            )
        except Exception as exc:
            raise RuntimeError("profile_facts_query_failed") from exc

        for fact in facts:
            key = str(getattr(fact, "key", "") or "").strip()
            val = str(getattr(fact, "value_json", "") or "").strip()
            if not key or not val:
                continue
            if len(val) > 80:
                val = val[:77] + "..."
            items.append(
                _item(
                    canonical_key=f"profile.fact.{_slug(key)}",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value=val,
                    display_text=f"fact_{key}={val}",
                    owner_user_id=authenticated_user_id,
                    query_label="UserFact.key_value",
                    observed_at=getattr(fact, "updated_at", None),
                    sensitivity="high",
                )
            )

        try:
            from backend.app.services.user_profile_fact_service import (
                get_profile_facts_for_context,
            )

            identity = get_profile_facts_for_context(db, authenticated_user_id, limit=10) or []
        except Exception:
            identity = []
        for raw in identity:
            text = str(raw).strip()
            if not text:
                continue
            items.append(
                _item(
                    canonical_key=f"profile.identity.{_slug(text)}",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value=text[:200],
                    display_text=f"profile_fact={text[:200]}",
                    owner_user_id=authenticated_user_id,
                    query_label="get_profile_facts_for_context",
                    observed_at=None,
                    sensitivity="medium",
                )
            )
        return items


class LifestyleContextAdapter:
    """Goals / lifestyle / Gate2 habits+restrictions already injected via USER_CONTEXT / RAG."""

    def load(
        self,
        db: Session,
        *,
        authenticated_user_id: int,
        user_context_pack: Any = USER_CONTEXT_PACK_UNSET,
    ) -> list[ContextItem]:
        if user_context_pack is USER_CONTEXT_PACK_UNSET:
            from backend.app.services.user_context import UserContextService

            pack = UserContextService(db).get_user_context(authenticated_user_id)
        else:
            pack = user_context_pack

        items: list[ContextItem] = []
        if pack is not None:
            goals_obj = getattr(pack, "goals", None)
            goal_items = []
            if goals_obj is not None:
                goal_items = list(getattr(goals_obj, "items", None) or [])
            for goal in goal_items[:5]:
                text = str(goal).strip()
                if not text:
                    continue
                items.append(
                    _item(
                        canonical_key=f"lifestyle.goal.{_slug(text)}",
                        section="lifestyle",
                        source=ContextSource.LIFESTYLE,
                        value=text,
                        display_text=f"goal={text[:200]}",
                        owner_user_id=authenticated_user_id,
                        query_label="UserContextService.goals",
                        observed_at=None,
                        sensitivity="medium",
                    )
                )
            lifestyle = getattr(pack, "lifestyle", None)
            lifestyle_text = None
            if lifestyle is not None:
                lifestyle_text = getattr(lifestyle, "text", None)
            if lifestyle_text:
                line = str(lifestyle_text).strip().splitlines()[0][:200]
                if line:
                    items.append(
                        _item(
                            canonical_key="lifestyle.summary",
                            section="lifestyle",
                            source=ContextSource.LIFESTYLE,
                            value=line,
                            display_text=f"lifestyle={line}",
                            owner_user_id=authenticated_user_id,
                            query_label="UserContextService.lifestyle",
                            observed_at=None,
                            sensitivity="medium",
                        )
                    )

        items.extend(
            self._load_gate2_lifestyle(db, authenticated_user_id=authenticated_user_id)
        )
        return items

    def _load_gate2_lifestyle(
        self, db: Session, *, authenticated_user_id: int
    ) -> list[ContextItem]:
        """Authorized subset already serialized by RAG_CONTEXT (not doctors/care_plan dump)."""
        items: list[ContextItem] = []
        try:
            from backend.app.services.gate2_data_service import (
                list_goals,
                list_habits,
                list_restrictions,
                list_events,
            )
        except Exception:
            return items

        try:
            g2_goals = [
                g["title"]
                for g in list_goals(db, authenticated_user_id)[:5]
                if g.get("status") == "active" and g.get("title")
            ]
            for title in g2_goals:
                text = str(title).strip()
                items.append(
                    _item(
                        canonical_key=f"lifestyle.goal.{_slug(text)}",
                        section="lifestyle",
                        source=ContextSource.LIFESTYLE,
                        value=text,
                        display_text=f"goal={text[:200]}",
                        owner_user_id=authenticated_user_id,
                        query_label="gate2.list_goals",
                        observed_at=None,
                        sensitivity="medium",
                    )
                )
            habits = [
                h["name"]
                for h in list_habits(db, authenticated_user_id)[:5]
                if h.get("status") == "active" and h.get("name")
            ]
            for name in habits:
                text = str(name).strip()
                items.append(
                    _item(
                        canonical_key=f"lifestyle.habit.{_slug(text)}",
                        section="lifestyle",
                        source=ContextSource.LIFESTYLE,
                        value=text,
                        display_text=f"habit={text[:200]}",
                        owner_user_id=authenticated_user_id,
                        query_label="gate2.list_habits",
                        observed_at=None,
                        sensitivity="medium",
                    )
                )
            restrictions = [
                f"{r.get('restriction_type')}: {r.get('title')}"
                for r in list_restrictions(db, authenticated_user_id)[:5]
                if r.get("status") == "active" and r.get("title")
            ]
            for text in restrictions:
                text = str(text).strip()
                items.append(
                    _item(
                        canonical_key=f"lifestyle.restriction.{_slug(text)}",
                        section="lifestyle",
                        source=ContextSource.LIFESTYLE,
                        value=text,
                        display_text=f"restriction={text[:200]}",
                        owner_user_id=authenticated_user_id,
                        query_label="gate2.list_restrictions",
                        observed_at=None,
                        sensitivity="high",
                    )
                )
            upcoming = list_events(db, authenticated_user_id, upcoming_only=True)[:5]
            for event in upcoming:
                title = str(event.get("title") or "").strip()
                if not title:
                    continue
                domain = event.get("event_domain") or ""
                etype = event.get("event_type") or ""
                text = f"{title} ({domain}/{etype})"
                items.append(
                    _item(
                        canonical_key=f"lifestyle.event.{_slug(title)}",
                        section="lifestyle",
                        source=ContextSource.LIFESTYLE,
                        value=text,
                        display_text=f"upcoming={text[:200]}",
                        owner_user_id=authenticated_user_id,
                        query_label="gate2.list_events",
                        observed_at=None,
                        sensitivity="medium",
                    )
                )
        except Exception as exc:
            raise RuntimeError("lifestyle_gate2_failed") from exc
        return items


class HealthContextAdapter:
    """Conditions/medications already injected via RAG_CONTEXT (same helpers/strings)."""

    def load(self, db: Session, *, authenticated_user_id: int) -> list[ContextItem]:
        items: list[ContextItem] = []
        try:
            from backend.app.services.rag_context.rag_context_builder import (
                MEDICATIONS_CONTEXT_MAX,
                _get_medical_conditions_for_user,
                _get_user_medications_for_context,
            )
        except Exception:
            return items

        try:
            conditions = _get_medical_conditions_for_user(db, authenticated_user_id) or []
        except Exception as exc:
            raise RuntimeError("health_adapter_conditions_failed") from exc
        for name in list(conditions)[:10]:
            text = str(name).strip()
            if not text:
                continue
            items.append(
                _item(
                    canonical_key=f"health.condition.{_slug(text)}",
                    section="health",
                    source=ContextSource.HEALTH,
                    value=text,
                    display_text=f"condition={text}",
                    owner_user_id=authenticated_user_id,
                    query_label="rag_context_builder.conditions",
                    observed_at=None,
                    sensitivity="high",
                )
            )

        try:
            meds = _get_user_medications_for_context(db, authenticated_user_id) or []
        except Exception as exc:
            raise RuntimeError("health_adapter_medications_failed") from exc
        # Proven legacy RAG path already projects name + optional dosage + schedule times.
        for med in list(meds)[:MEDICATIONS_CONTEXT_MAX]:
            text = str(med).strip()
            if not text:
                continue
            items.append(
                _item(
                    canonical_key=f"health.medication.{_slug(text, max_len=80)}",
                    section="health",
                    source=ContextSource.HEALTH,
                    value=text,
                    display_text=f"medication={text[:200]}",
                    owner_user_id=authenticated_user_id,
                    query_label="rag_context_builder.medications",
                    observed_at=None,
                    sensitivity="high",
                )
            )
        return items


class CurrentMemoryContextAdapter:
    """DailyMemorySummary (USER_CONTEXT Recent) + bounded recent Memory turns."""

    def load(
        self,
        db: Session,
        *,
        authenticated_user_id: int,
        user_context_pack: Any = USER_CONTEXT_PACK_UNSET,
        budgets: Optional[ContextBudgets] = None,
    ) -> list[ContextItem]:
        budgets = budgets or DEFAULT_CONTEXT_BUDGETS
        items: list[ContextItem] = []

        # Assembler always passes pack (object or None). Only standalone adapter
        # calls omit it (UNSET) and may load UCS once themselves.
        pack = user_context_pack
        if pack is USER_CONTEXT_PACK_UNSET:
            from backend.app.services.user_context import UserContextService

            pack = UserContextService(db).get_user_context(authenticated_user_id)

        daily_text = None
        daily_observed = None
        if pack is not None:
            daily_text = getattr(pack, "daily_memory_summary", None)
        if daily_text and str(daily_text).strip():
            summary = str(daily_text).strip()[:150]
            items.append(
                _item(
                    canonical_key="memory.daily_summary",
                    section="memory",
                    source=ContextSource.MEMORY,
                    value=summary,
                    display_text=f"recent={summary}",
                    owner_user_id=authenticated_user_id,
                    query_label="UserContextPack.daily_memory_summary",
                    observed_at=None,
                    sensitivity="medium",
                )
            )
        else:
            from backend.app.models import DailyMemorySummary

            dms = (
                db.query(DailyMemorySummary)
                .filter(DailyMemorySummary.user_id == authenticated_user_id)
                .order_by(DailyMemorySummary.created_at.desc())
                .first()
            )
            if dms is not None and getattr(dms, "summary", None):
                summary = str(dms.summary).strip()[:150]
                if summary:
                    daily_observed = getattr(dms, "created_at", None)
                    items.append(
                        _item(
                            canonical_key="memory.daily_summary",
                            section="memory",
                            source=ContextSource.MEMORY,
                            value=summary,
                            display_text=f"recent={summary}",
                            owner_user_id=authenticated_user_id,
                            query_label="DailyMemorySummary.latest",
                            observed_at=daily_observed,
                            sensitivity="medium",
                        )
                    )

        from backend.app.core.conversation.memory import ConversationMemory

        mem = ConversationMemory(db)
        recent = mem.get_recent_messages(
            authenticated_user_id, limit=budgets.max_memory_turns
        )
        ordered = list(reversed(list(recent)))
        for idx, row in enumerate(ordered):
            user_msg = (getattr(row, "user_message", None) or "").strip()
            sedi_msg = (getattr(row, "sedi_response", None) or "").strip()
            if not user_msg and not sedi_msg:
                continue
            created = getattr(row, "created_at", None)
            if user_msg:
                items.append(
                    _item(
                        canonical_key=f"memory.turn.{idx}.user",
                        section="memory",
                        source=ContextSource.MEMORY,
                        value=user_msg[:500],
                        display_text=f"user_turn={user_msg[:200]}",
                        owner_user_id=authenticated_user_id,
                        query_label="ConversationMemory.get_recent_messages",
                        observed_at=created,
                        sensitivity="high",
                        may_send_to_llm=True,
                    )
                )
            if sedi_msg:
                items.append(
                    _item(
                        canonical_key=f"memory.turn.{idx}.assistant",
                        section="memory",
                        source=ContextSource.MEMORY,
                        value=sedi_msg[:500],
                        display_text=f"assistant_turn={sedi_msg[:200]}",
                        owner_user_id=authenticated_user_id,
                        query_label="ConversationMemory.get_recent_messages",
                        observed_at=created,
                        sensitivity="high",
                        may_send_to_llm=True,
                    )
                )
        return items


class SafeNotificationContextAdapter:
    """Safe notification origin already verified by A1 / build_safe_chat_context."""

    def load(
        self,
        *,
        authenticated_user_id: int,
        notification_context: Optional[Mapping[str, Any]],
        source_notification_id: Optional[int],
    ) -> list[ContextItem]:
        items: list[ContextItem] = []
        if source_notification_id is None and not notification_context:
            return items
        if source_notification_id is not None:
            items.append(
                _item(
                    canonical_key="notification.source_notification_id",
                    section="notification",
                    source=ContextSource.NOTIFICATION,
                    value=source_notification_id,
                    display_text=f"source_notification_id={source_notification_id}",
                    owner_user_id=authenticated_user_id,
                    query_label="verified_notification_origin",
                    observed_at=None,
                    sensitivity="low",
                    may_send_to_llm=True,
                    consent="legacy_scope",
                )
            )
        if not notification_context:
            return items

        for key in sorted(SAFE_NOTIFICATION_LLM_KEYS):
            if key not in notification_context:
                continue
            val = notification_context.get(key)
            if val is None:
                continue
            text = str(val).strip()
            if not text:
                continue
            items.append(
                _item(
                    canonical_key=f"notification.{key}",
                    section="notification",
                    source=ContextSource.NOTIFICATION,
                    value=text[:256],
                    display_text=f"{key}={text[:200]}",
                    owner_user_id=authenticated_user_id,
                    query_label="build_safe_chat_context",
                    observed_at=None,
                    sensitivity="medium",
                    may_send_to_llm=True,
                )
            )

        hints = notification_context.get("context_hints")
        if isinstance(hints, dict):
            for hint_key in sorted(hints.keys()):
                hint_value = hints.get(hint_key)
                if hint_value is None:
                    continue
                text = str(hint_value).strip()
                if not text:
                    continue
                items.append(
                    _item(
                        canonical_key=f"notification.hint.{_slug(str(hint_key))}",
                        section="notification",
                        source=ContextSource.NOTIFICATION,
                        value=text[:256],
                        display_text=f"hint_{hint_key}={text[:200]}",
                        owner_user_id=authenticated_user_id,
                        query_label="build_safe_chat_context.context_hints",
                        observed_at=None,
                        sensitivity="medium",
                        may_send_to_llm=True,
                    )
                )
        return items
