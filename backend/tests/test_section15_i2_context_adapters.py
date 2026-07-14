"""Section 15-I2 — Connected authorized context adapters + assembler tests."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models import User
from backend.app.services.intelligence.adapters import (
    CurrentMemoryContextAdapter,
    HealthContextAdapter,
    LifestyleContextAdapter,
    ProfileContextAdapter,
    SAFE_NOTIFICATION_LLM_KEYS,
    SafeNotificationContextAdapter,
)
from backend.app.services.intelligence.assembler import (
    AuthorizedContextAssembler,
    ContextAssemblyError,
)
from backend.app.services.intelligence.context_types import (
    ADAPTER_ORDER,
    BUDGET_CLASSIFICATION_TECHNICAL_DEFAULT,
    ContextBudgets,
    ContextItem,
    ContextProvenance,
    ContextSource,
    SOURCE_SORT_RANK,
)
from backend.app.services.intelligence.contracts import (
    CONTRACT_VERSION,
    STAGE_ORDER,
    STRUCTURED_READINESS_REASON_CODES,
    ReasonCode,
)
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator


@pytest.fixture
def user_a(db):
    u = User(name="I2 User A", secret_key="i2a", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def user_b(db):
    u = User(name="I2 User B", secret_key="i2b", preferred_language="fa")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _owner_ok(items, uid: int):
    for item in items:
        assert item.provenance.owner_user_id == uid


def _empty_adapter():
    return type(
        "E",
        (),
        {"load": lambda self, *a, **k: []},
    )()


def _item(
    *,
    key: str,
    section: str,
    source: ContextSource,
    value: str,
    owner: int,
    display: str | None = None,
    consent: str = "legacy_scope",
    may_send: bool = True,
    sensitivity: str = "medium",
):
    return ContextItem(
        canonical_key=key,
        section=section,  # type: ignore[arg-type]
        source=source,
        structured_value=value,
        display_text=display or f"{key}={value}",
        provenance=ContextProvenance(
            source=source, owner_user_id=owner, query_label="t"
        ),
        observed_at=None,
        freshness="unknown",
        sensitivity=sensitivity,  # type: ignore[arg-type]
        consent=consent,  # type: ignore[arg-type]
        may_send_to_llm=may_send,
        sort_rank=SOURCE_SORT_RANK[source],
    )


def test_adapter_order_is_deterministic_not_authority():
    assert ADAPTER_ORDER == (
        ContextSource.PROFILE,
        ContextSource.LIFESTYLE,
        ContextSource.HEALTH,
        ContextSource.MEMORY,
        ContextSource.NOTIFICATION,
    )
    # Sort ranks exist for ordering only; conflict policy must not supersede by rank.
    assert SOURCE_SORT_RANK[ContextSource.PROFILE] != SOURCE_SORT_RANK[ContextSource.HEALTH]


def test_budget_classification_is_technical_default():
    budgets = ContextBudgets()
    assert budgets.classification == BUDGET_CLASSIFICATION_TECHNICAL_DEFAULT
    assert "ConversationBrain" in budgets.memory_turns_provenance
    assert budgets.max_memory_turns == 10
    assert "token" not in budgets.classification.lower()


def test_profile_adapter_filters_by_authenticated_user(db, user_a, user_b):
    items_a = ProfileContextAdapter().load(db, authenticated_user_id=user_a.id)
    items_b = ProfileContextAdapter().load(db, authenticated_user_id=user_b.id)
    _owner_ok(items_a, user_a.id)
    _owner_ok(items_b, user_b.id)
    assert all(i.provenance.owner_user_id == user_a.id for i in items_a)


def test_lifestyle_adapter_user_isolation(db, user_a, user_b):
    a = LifestyleContextAdapter().load(db, authenticated_user_id=user_a.id)
    b = LifestyleContextAdapter().load(db, authenticated_user_id=user_b.id)
    _owner_ok(a, user_a.id)
    _owner_ok(b, user_b.id)


def test_health_adapter_user_isolation(db, user_a, user_b):
    a = HealthContextAdapter().load(db, authenticated_user_id=user_a.id)
    b = HealthContextAdapter().load(db, authenticated_user_id=user_b.id)
    _owner_ok(a, user_a.id)
    _owner_ok(b, user_b.id)


def test_memory_adapter_user_isolation(db, user_a, user_b):
    a = CurrentMemoryContextAdapter().load(db, authenticated_user_id=user_a.id)
    b = CurrentMemoryContextAdapter().load(db, authenticated_user_id=user_b.id)
    _owner_ok(a, user_a.id)
    _owner_ok(b, user_b.id)


def test_empty_sections_are_valid(db, user_a):
    snap = AuthorizedContextAssembler().assemble(
        db, authenticated_user_id=user_a.id, request_id="empty"
    )
    assert snap.owner_user_id == user_a.id
    for name in ("profile", "lifestyle", "health", "memory", "notification"):
        assert name in snap.sections


def test_notification_safe_ids_only_no_raw_body(db, user_a):
    snap = AuthorizedContextAssembler().assemble(
        db,
        authenticated_user_id=user_a.id,
        request_id="notif",
        source_notification_id=99,
        notification_context={
            "category": "reminder",
            "body": "SECRET BODY",
            "dose": "5mg",
            "unexpected_leak": "SHOULD_NOT_APPEAR",
            "risk_level": "low",
        },
    )
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "SECRET BODY" not in proj.text
    assert "5mg" not in proj.text
    assert "SHOULD_NOT_APPEAR" not in proj.text
    assert "category=reminder" in proj.text
    assert "unexpected_leak" not in SAFE_NOTIFICATION_LLM_KEYS


def test_missing_timestamp_freshness_unknown(db, user_a):
    items = ProfileContextAdapter().load(db, authenticated_user_id=user_a.id)
    for item in items:
        if item.observed_at is None:
            assert item.freshness == "unknown"


def test_legacy_scope_consent_not_fabricated_explicit(db, user_a):
    snap = AuthorizedContextAssembler().assemble(
        db, authenticated_user_id=user_a.id, request_id="req-consent"
    )
    for item in snap.items:
        assert item.consent in ("legacy_scope", "unknown", "denied")
        assert item.consent != "explicit"


def test_identical_value_coalesce_retains_provenance():
    class Dup:
        def load(self, *a, **k):
            uid = k["authenticated_user_id"]
            return [
                _item(
                    key="lifestyle.goal.walk",
                    section="lifestyle",
                    source=ContextSource.LIFESTYLE,
                    value="Walk",
                    owner=uid,
                    display="goal=Walk",
                ),
                _item(
                    key="lifestyle.goal.walk",
                    section="lifestyle",
                    source=ContextSource.LIFESTYLE,
                    value="Walk",
                    owner=uid,
                    display="goal=Walk",
                ),
            ]

    assembler = AuthorizedContextAssembler(
        profile_adapter=_empty_adapter(),
        lifestyle_adapter=Dup(),
        health_adapter=_empty_adapter(),
        memory_adapter=_empty_adapter(),
        notification_adapter=SafeNotificationContextAdapter(),
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=7, request_id="coal")
    active = [i for i in snap.items if i.active and not i.conflicted]
    assert len(active) == 1
    assert active[0].coalesced_provenance
    assert snap.conflict_count == 0
    assert ReasonCode.CONTEXT_CONFLICT_DETECTED.value not in snap.reason_codes


def test_equal_trust_conflict_excluded_no_silent_supersession():
    class Twin:
        def load(self, *a, **k):
            uid = k["authenticated_user_id"]
            return [
                _item(
                    key="profile.preferred_name",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value="A",
                    owner=uid,
                    display="preferred_name=A",
                ),
                _item(
                    key="profile.preferred_name",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value="B",
                    owner=uid,
                    display="preferred_name=B",
                ),
            ]

    assembler = AuthorizedContextAssembler(
        profile_adapter=Twin(),
        lifestyle_adapter=_empty_adapter(),
        health_adapter=_empty_adapter(),
        memory_adapter=_empty_adapter(),
        notification_adapter=SafeNotificationContextAdapter(),
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=7, request_id="c")
    assert snap.conflict_count >= 1
    assert ReasonCode.CONTEXT_CONFLICT_DETECTED.value in snap.reason_codes
    proj = assembler.build_compatibility_projection(snap)
    assert "preferred_name=A" not in proj.text
    assert "preferred_name=B" not in proj.text


def test_cross_source_conflict_without_authority_no_supersession():
    """Different sources + different values → conflict; SOURCE_SORT_RANK is not authority."""

    class Mix:
        def load(self, *a, **k):
            uid = k["authenticated_user_id"]
            if self is profile:
                return [
                    _item(
                        key="lifestyle.goal.shared",
                        section="lifestyle",
                        source=ContextSource.PROFILE,
                        value="Alpha",
                        owner=uid,
                        display="goal=Alpha",
                    )
                ]
            return [
                _item(
                    key="lifestyle.goal.shared",
                    section="lifestyle",
                    source=ContextSource.LIFESTYLE,
                    value="Beta",
                    owner=uid,
                    display="goal=Beta",
                )
            ]

    profile = Mix()
    lifestyle = Mix()
    assembler = AuthorizedContextAssembler(
        profile_adapter=profile,
        lifestyle_adapter=lifestyle,
        health_adapter=_empty_adapter(),
        memory_adapter=_empty_adapter(),
        notification_adapter=SafeNotificationContextAdapter(),
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=3, request_id="xs")
    assert snap.conflict_count >= 1
    proj = assembler.build_compatibility_projection(snap)
    assert "goal=Alpha" not in proj.text
    assert "goal=Beta" not in proj.text


def test_budget_truncation_deterministic_and_overrideable():
    class Flood:
        def load(self, *a, **k):
            uid = k["authenticated_user_id"]
            out = []
            for i in range(20):
                out.append(
                    _item(
                        key=f"lifestyle.goal.g{i}",
                        section="lifestyle",
                        source=ContextSource.LIFESTYLE,
                        value=str(i),
                        owner=uid,
                        display=f"goal={i}",
                    )
                )
            return out

    tiny = ContextBudgets(
        max_items_per_section=3,
        max_total_context_items=3,
        max_compatibility_projection_chars=500,
        max_memory_turns=10,
    )
    assembler = AuthorizedContextAssembler(
        profile_adapter=_empty_adapter(),
        lifestyle_adapter=Flood(),
        health_adapter=_empty_adapter(),
        memory_adapter=_empty_adapter(),
        notification_adapter=SafeNotificationContextAdapter(),
        budgets=tiny,
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=1, request_id="b")
    active = [i for i in snap.items if i.active and not i.conflicted]
    assert len(active) <= 3
    assert snap.truncated_count >= 1
    assert ReasonCode.CONTEXT_BUDGET_TRUNCATED.value in snap.reason_codes
    assert snap.budget_classification == BUDGET_CLASSIFICATION_TECHNICAL_DEFAULT


def test_no_false_budget_truncated_reason_when_under_limit(db, user_a):
    snap = AuthorizedContextAssembler().assemble(
        db, authenticated_user_id=user_a.id, request_id="nofalse"
    )
    if snap.truncated_count == 0:
        assert ReasonCode.CONTEXT_BUDGET_TRUNCATED.value not in snap.reason_codes


def test_projection_truncates_whole_lines_not_mid_value():
    class OneBig:
        def load(self, *a, **k):
            uid = k["authenticated_user_id"]
            return [
                _item(
                    key="profile.preferred_name",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value="Short",
                    owner=uid,
                    display="preferred_name=Short",
                ),
                _item(
                    key="profile.sex",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value="x",
                    owner=uid,
                    display="sex=" + ("Z" * 200),
                ),
            ]

    tiny = ContextBudgets(
        max_items_per_section=10,
        max_total_context_items=40,
        max_compatibility_projection_chars=80,
        max_memory_turns=10,
    )
    assembler = AuthorizedContextAssembler(
        profile_adapter=OneBig(),
        lifestyle_adapter=_empty_adapter(),
        health_adapter=_empty_adapter(),
        memory_adapter=_empty_adapter(),
        notification_adapter=SafeNotificationContextAdapter(),
        budgets=tiny,
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=1, request_id="cut")
    proj = assembler.build_compatibility_projection(snap)
    assert proj.truncated is True
    assert "ZZZZ" not in proj.text or proj.text.endswith("ZZZZ") is False
    # No mid-token ellipsis cut marker when dropping whole lines.
    assert "...[truncated]" not in proj.text
    assert "[STRUCTURED_CONTEXT]" in proj.text


def test_projection_excludes_user_and_db_ids_and_raw_body(db, user_a):
    snap = AuthorizedContextAssembler().assemble(
        db,
        authenticated_user_id=user_a.id,
        request_id="req-proj",
        source_notification_id=55,
        notification_context={"category": "reminder", "body": "SECRET BODY"},
    )
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "SECRET BODY" not in proj.text
    assert f"user_id={user_a.id}" not in proj.text
    assert "authenticated_user_id" not in proj.text
    assert "consent=" not in proj.text
    assert "provenance" not in proj.text
    assert "[STRUCTURED_CONTEXT]" in proj.text


def test_projection_excludes_denied_and_ineligible():
    class Mix:
        def load(self, *a, **k):
            uid = k["authenticated_user_id"]
            return [
                _item(
                    key="profile.preferred_name",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value="Visible",
                    owner=uid,
                    display="preferred_name=Visible",
                ),
                _item(
                    key="profile.secret",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value="Nope",
                    owner=uid,
                    display="preferred_name=HIDDEN_DENIED",
                    consent="denied",
                    sensitivity="critical",
                ),
                _item(
                    key="profile.internal",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value="NoLLM",
                    owner=uid,
                    display="preferred_name=HIDDEN_NOLLM",
                    may_send=False,
                ),
            ]

    assembler = AuthorizedContextAssembler(
        profile_adapter=Mix(),
        lifestyle_adapter=_empty_adapter(),
        health_adapter=_empty_adapter(),
        memory_adapter=_empty_adapter(),
        notification_adapter=SafeNotificationContextAdapter(),
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=3, request_id="elig")
    proj = assembler.build_compatibility_projection(snap)
    assert "Visible" in proj.text
    assert "HIDDEN_DENIED" not in proj.text
    assert "HIDDEN_NOLLM" not in proj.text


def test_compatibility_mode_skips_assembly(monkeypatch):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "ok", "language": "en"}

    orch = IntelligenceOrchestrator(legacy_generator=gen, structured_mode=False)
    result = orch.process(authenticated_user_id=1, message="hi", language="en")
    assert result.rollout_mode == "compatibility"
    assert ReasonCode.CONTEXT_ASSEMBLY_SKIPPED_COMPATIBILITY.value in result.reason_codes
    assert ReasonCode.STRUCTURED_MODE_NOT_PRODUCTION_READY.value not in result.reason_codes
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]
    assert calls["n"] == 1


def test_structured_mode_invokes_assembler_readiness_and_passes_projection(
    db, user_a, monkeypatch
):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")
    seen = {"n": 0}

    def gen(
        user_id,
        user_message,
        user_name=None,
        *,
        notification_context=None,
        structured_context_projection=None,
        structured_preferred_name=None,
        use_structured_context=False,
        **_k,
    ):
        seen["n"] += 1
        seen["use"] = use_structured_context
        seen["projection"] = structured_context_projection
        seen["notification_context"] = notification_context
        return {"message": "structured-ok", "language": "en"}

    orch = IntelligenceOrchestrator(db=db, legacy_generator=gen)
    result = orch.process(authenticated_user_id=user_a.id, message="hello", language="en")
    assert result.rollout_mode == "structured"
    assert result.message == "structured-ok"
    assert seen["use"] is True
    assert seen["n"] == 1
    assert seen["projection"] and "[STRUCTURED_CONTEXT]" in seen["projection"]
    assert seen["notification_context"] is None
    assert ReasonCode.CONTEXT_ASSEMBLED.value in result.reason_codes
    for readiness in STRUCTURED_READINESS_REASON_CODES:
        assert readiness.value in result.reason_codes
    assert ReasonCode.GOVERNED_KB_NOT_CONNECTED.value in result.reason_codes
    assert ReasonCode.STRUCTURED_MODE_NOT_PRODUCTION_READY.value in result.reason_codes
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]


def test_structured_assembly_failure_does_not_bypass_to_brain(db, user_a, monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "should-not-run", "language": "en"}

    class BoomAssembler:
        def assemble(self, *a, **k):
            raise RuntimeError("adapter_boom")

        def build_compatibility_projection(self, snapshot):
            raise AssertionError("should not project")

    orch = IntelligenceOrchestrator(
        db=db,
        legacy_generator=gen,
        context_assembler=BoomAssembler(),
    )
    from backend.app.services.intelligence.contracts import OrchestrationError

    with pytest.raises(OrchestrationError):
        orch.process(authenticated_user_id=user_a.id, message="hi", language="en")
    assert calls["n"] == 0


def test_brain_skips_covered_loaders_when_structured_projection_supplied(db, user_a):
    from backend.app.core.conversation.brain import ConversationBrain

    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context"
    ) as mock_ucs, patch(
        "backend.app.core.conversation.brain._build_user_knowledge_context",
        return_value="",
    ) as mock_knowledge, patch(
        "backend.app.core.conversation.brain._maybe_append_rag_context_v1"
    ) as mock_rag, patch(
        "backend.app.core.conversation.brain._maybe_append_local_rag_context"
    ) as mock_local_rag, patch(
        "backend.app.core.conversation.brain._maybe_append_gate3_care_context"
    ) as mock_gate3, patch(
        "backend.app.core.conversation.brain._gate3_check_emergency_short_circuit",
        return_value="ok",
    ), patch(
        "backend.app.core.conversation.prompts.build_system_prompt_with_context",
        return_value="PERSONA_ACTIVE",
    ) as mock_persona, patch.object(
        ConversationBrain,
        "_extract_name_from_message",
        return_value="SHOULD_NOT_USE",
    ) as mock_extract:
        brain = ConversationBrain(db, language="en")
        mock_mem = MagicMock()
        brain.memory = mock_mem
        result = brain.process_message(
            user_a.id,
            "hi",
            structured_context_projection="[STRUCTURED_CONTEXT]\n- [profile] preferred_name=Test",
            structured_preferred_name="Test",
            use_structured_context=True,
        )
        assert result["message"] == "ok"
        assert result.get("detected_name") is None
        mock_ucs.assert_not_called()
        mock_knowledge.assert_not_called()
        mock_rag.assert_not_called()
        mock_local_rag.assert_not_called()
        mock_gate3.assert_not_called()
        mock_mem.get_recent_messages.assert_not_called()
        mock_extract.assert_not_called()
        mock_persona.assert_called_once()
        # Persona receives assembled preferred_name; never conversation-inferred.
        assert mock_persona.call_args.args[1] == "Test"


def test_structured_without_preferred_name_does_not_invent_or_reload(db, user_a):
    from backend.app.core.conversation.brain import ConversationBrain

    with patch(
        "backend.app.core.conversation.brain._gate3_check_emergency_short_circuit",
        return_value="ok",
    ), patch(
        "backend.app.core.conversation.prompts.build_system_prompt_with_context",
        return_value="PERSONA_ACTIVE",
    ) as mock_persona, patch.object(
        ConversationBrain, "_extract_name_from_message", return_value="HACK"
    ) as mock_extract:
        brain = ConversationBrain(db, language="en")
        mock_mem = MagicMock()
        brain.memory = mock_mem
        result = brain.process_message(
            user_a.id,
            "my name is Alice from history",
            structured_context_projection="[STRUCTURED_CONTEXT]\n- [lifestyle] goal=walk",
            structured_preferred_name=None,
            use_structured_context=True,
        )
        assert result["message"] == "ok"
        assert result.get("detected_name") is None
        mock_mem.get_recent_messages.assert_not_called()
        mock_extract.assert_not_called()
        assert mock_persona.call_args.args[1] is None


def test_compatibility_mode_still_loads_recent_messages_for_name(db, user_a):
    from backend.app.core.conversation.brain import ConversationBrain

    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ), patch(
        "backend.app.core.conversation.brain._build_user_knowledge_context",
        return_value="",
    ), patch(
        "backend.app.core.conversation.brain._maybe_append_rag_context_v1",
    ), patch(
        "backend.app.core.conversation.brain._maybe_append_local_rag_context",
    ), patch(
        "backend.app.core.conversation.brain._maybe_append_gate3_care_context",
    ), patch(
        "backend.app.core.conversation.brain._gate3_check_emergency_short_circuit",
        return_value="ok",
    ), patch(
        "backend.app.core.conversation.prompts.build_system_prompt_with_context",
        return_value="PERSONA_ACTIVE",
    ):
        brain = ConversationBrain(db, language="en")
        mock_mem = MagicMock()
        mock_mem.get_recent_messages.return_value = []
        mock_mem.get_conversation_count.return_value = 0
        brain.memory = mock_mem
        result = brain.process_message(user_a.id, "hello", use_structured_context=False)
        assert result["message"] == "ok"
        assert mock_mem.get_recent_messages.call_count >= 1


def test_ucs_loaded_once_when_pack_is_none(db, user_a):
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ) as mock_ucs:
        AuthorizedContextAssembler().assemble(
            db, authenticated_user_id=user_a.id, request_id="once-none"
        )
        assert mock_ucs.call_count == 1


def test_ucs_loaded_once_when_pack_is_object(db, user_a):
    pack = MagicMock()
    pack.preferred_name = "Pat"
    pack.birth_year = None
    pack.sex = None
    pack.addressing_preference = None
    pack.goals = MagicMock(items=[])
    pack.lifestyle = None
    pack.daily_memory_summary = None
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=pack,
    ) as mock_ucs:
        assembler = AuthorizedContextAssembler()
        snap = assembler.assemble(
            db, authenticated_user_id=user_a.id, request_id="once-obj"
        )
        assert mock_ucs.call_count == 1
        # Snapshot must not publish preferred_name before final projection.
        assert snap.preferred_name is None
        proj = assembler.build_compatibility_projection(snap)
        assert proj.preferred_name == "Pat"


def test_ucs_exception_fails_closed_single_attempt_no_generator(db, user_a, monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")
    calls = {"gen": 0, "ucs": 0}

    def boom(*_a, **_k):
        calls["ucs"] += 1
        raise RuntimeError("ucs_boom")

    def gen(*_a, **_k):
        calls["gen"] += 1
        return {"message": "nope", "language": "en"}

    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        side_effect=boom,
    ):
        from backend.app.services.intelligence.contracts import OrchestrationError

        orch = IntelligenceOrchestrator(db=db, legacy_generator=gen)
        with pytest.raises(OrchestrationError):
            orch.process(authenticated_user_id=user_a.id, message="hi", language="en")
    assert calls["ucs"] == 1
    assert calls["gen"] == 0


def test_ucs_two_users_do_not_share_pack_cache(db, user_a, user_b):
    seen = []

    def fake_get(uid):
        seen.append(uid)
        return None

    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        side_effect=lambda self, uid: fake_get(uid),
    ):
        AuthorizedContextAssembler().assemble(
            db, authenticated_user_id=user_a.id, request_id="a"
        )
        AuthorizedContextAssembler().assemble(
            db, authenticated_user_id=user_b.id, request_id="b"
        )
    assert seen == [user_a.id, user_b.id]


def test_concurrent_users_isolated_snapshots(db, user_a, user_b):
    barrier = threading.Barrier(2)
    out = {}

    def worker(uid):
        barrier.wait(timeout=5)
        snap = AuthorizedContextAssembler().assemble(
            db, authenticated_user_id=uid, request_id=f"r-{uid}"
        )
        out[uid] = snap

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(worker, user_a.id)
        f2 = pool.submit(worker, user_b.id)
        f1.result(timeout=10)
        f2.result(timeout=10)
    assert out[user_a.id].owner_user_id == user_a.id
    assert out[user_b.id].owner_user_id == user_b.id
    assert out[user_a.id].request_id != out[user_b.id].request_id


def test_public_interaction_response_unchanged_schema():
    from backend.app.schemas.interaction import InteractionResponse
    from datetime import datetime as dt

    resp = InteractionResponse(
        message="hi",
        language="en",
        user_id=1,
        timestamp=dt.utcnow(),
    )
    assert resp.message == "hi"
    assert not hasattr(resp, "structured_context")
    assert CONTRACT_VERSION.startswith("sedi.intelligence")


def test_cross_user_item_rejected():
    class Bad:
        def load(self, *a, **k):
            uid = k["authenticated_user_id"]
            return [
                _item(
                    key="profile.preferred_name",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value="x",
                    owner=uid + 1,
                )
            ]

    assembler = AuthorizedContextAssembler(
        profile_adapter=Bad(),
        lifestyle_adapter=_empty_adapter(),
        health_adapter=_empty_adapter(),
        memory_adapter=_empty_adapter(),
        notification_adapter=SafeNotificationContextAdapter(),
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        with pytest.raises(ContextAssemblyError):
            assembler.assemble(MagicMock(), authenticated_user_id=1, request_id="x")


def test_excluded_i2_sources_not_imported_by_adapters():
    import inspect
    import backend.app.services.intelligence.adapters as adapters_mod

    src = inspect.getsource(adapters_mod)
    banned = (
        "KcUserFact",
        "caregiver",
        "emergency_contact",
        "InteractionEvent",
        "DeviceSignal",
        "VitalReading",
        "list_doctors",
        "quiet_hours",
    )
    for name in banned:
        assert name not in src


def test_health_projection_allowlist_excludes_raw_vitals_and_ids():
    class Health:
        def load(self, *a, **k):
            uid = k["authenticated_user_id"]
            return [
                _item(
                    key="health.condition.diabetes",
                    section="health",
                    source=ContextSource.HEALTH,
                    value="diabetes",
                    owner=uid,
                    display="condition=diabetes",
                    sensitivity="high",
                ),
                _item(
                    key="health.raw.vital",
                    section="health",
                    source=ContextSource.HEALTH,
                    value="hr=120",
                    owner=uid,
                    display="vital=hr=120 db_id=999",
                    sensitivity="critical",
                    consent="unknown",
                    may_send=False,
                ),
            ]

    assembler = AuthorizedContextAssembler(
        profile_adapter=_empty_adapter(),
        lifestyle_adapter=_empty_adapter(),
        health_adapter=Health(),
        memory_adapter=_empty_adapter(),
        notification_adapter=SafeNotificationContextAdapter(),
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=1, request_id="h")
    proj = assembler.build_compatibility_projection(snap)
    assert "condition=diabetes" in proj.text
    assert "hr=120" not in proj.text
    assert "db_id=999" not in proj.text


def test_i1_stage_trace_privacy_intact_with_i2(db, user_a, monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")

    def gen(*_a, **_k):
        return {"message": "ok", "language": "en"}

    orch = IntelligenceOrchestrator(db=db, legacy_generator=gen)
    result = orch.process(
        authenticated_user_id=user_a.id,
        message="SUPER_SECRET_USER_MESSAGE_XYZ",
        language="en",
        notification_context={"body": "RAW_NOTIF_BODY", "category": "reminder"},
    )
    joined = " ".join(result.reason_codes) + " ".join(result.stage_names)
    assert "SUPER_SECRET_USER_MESSAGE_XYZ" not in joined
    assert "RAW_NOTIF_BODY" not in joined
    assert str(user_a.id) not in result.reason_codes


def test_no_external_network_in_i2_unit_paths(db, user_a):
    with patch("backend.app.core.conversation.brain.ConversationBrain") as Brain:
        orch = IntelligenceOrchestrator(
            db=db,
            legacy_generator=lambda *a, **k: {"message": "ok", "language": "en"},
            structured_mode=True,
        )
        orch.process(authenticated_user_id=user_a.id, message="hi", language="en")
        Brain.assert_not_called()


def test_provenance_query_label_preserved(db, user_a):
    items = ProfileContextAdapter().load(db, authenticated_user_id=user_a.id)
    for item in items:
        assert item.provenance.query_label
        assert item.provenance.owner_user_id == user_a.id
        assert item.provenance.record_hint is None


def _prefer_assembler_with_profile_items(items):
    class Prof:
        def load(self, *a, **k):
            return items

    return AuthorizedContextAssembler(
        profile_adapter=Prof(),
        lifestyle_adapter=_empty_adapter(),
        health_adapter=_empty_adapter(),
        memory_adapter=_empty_adapter(),
        notification_adapter=SafeNotificationContextAdapter(),
    )


def test_preferred_name_included_eligible_reaches_projection():
    assembler = _prefer_assembler_with_profile_items(
        [
            _item(
                key="profile.preferred_name",
                section="profile",
                source=ContextSource.PROFILE,
                value="Pat",
                owner=7,
                display="preferred_name=Pat",
            )
        ]
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=7, request_id="pn1")
    assert snap.preferred_name is None
    proj = assembler.build_compatibility_projection(snap)
    assert proj.preferred_name == "Pat"
    assert "preferred_name=Pat" in proj.text


def test_preferred_name_none_when_may_send_false():
    assembler = _prefer_assembler_with_profile_items(
        [
            _item(
                key="profile.preferred_name",
                section="profile",
                source=ContextSource.PROFILE,
                value="Hidden",
                owner=7,
                display="preferred_name=Hidden",
                may_send=False,
            )
        ]
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=7, request_id="pn2")
    proj = assembler.build_compatibility_projection(snap)
    assert proj.preferred_name is None
    assert "Hidden" not in proj.text


def test_preferred_name_none_when_consent_denied():
    assembler = _prefer_assembler_with_profile_items(
        [
            _item(
                key="profile.preferred_name",
                section="profile",
                source=ContextSource.PROFILE,
                value="Denied",
                owner=7,
                display="preferred_name=Denied",
                consent="denied",
                sensitivity="critical",
            )
        ]
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=7, request_id="pn3")
    proj = assembler.build_compatibility_projection(snap)
    assert proj.preferred_name is None


def test_preferred_name_none_when_inactive_via_item_budget():
    tiny = ContextBudgets(
        max_items_per_section=1,
        max_total_context_items=1,
        max_compatibility_projection_chars=5000,
        max_memory_turns=10,
    )
    # Sort key puts addressing before preferred_name? section profile, keys:
    # addressing_preference sorts before preferred_name alphabetically.
    items = [
        _item(
            key="profile.addressing_preference",
            section="profile",
            source=ContextSource.PROFILE,
            value="formal",
            owner=7,
            display="addressing=formal",
        ),
        _item(
            key="profile.preferred_name",
            section="profile",
            source=ContextSource.PROFILE,
            value="Late",
            owner=7,
            display="preferred_name=Late",
        ),
    ]
    assembler = AuthorizedContextAssembler(
        profile_adapter=type("P", (), {"load": lambda self, *a, **k: items})(),
        lifestyle_adapter=_empty_adapter(),
        health_adapter=_empty_adapter(),
        memory_adapter=_empty_adapter(),
        notification_adapter=SafeNotificationContextAdapter(),
        budgets=tiny,
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=7, request_id="pn4")
    name_items = [i for i in snap.items if i.canonical_key == "profile.preferred_name"]
    assert name_items
    assert name_items[0].truncated is True or name_items[0].active is False
    proj = assembler.build_compatibility_projection(snap)
    assert proj.preferred_name is None


def test_preferred_name_none_when_dropped_by_char_budget():
    # One short lifestyle line first (sort_rank lifestyle after profile actually).
    # PROFILE sort_rank is 10, so preferred_name comes first unless we make display huge.
    # Force char budget to exclude the preferred_name line by making it the only bulky
    # eligible line after a tiny reserved line that fills budget.
    tiny = ContextBudgets(
        max_items_per_section=10,
        max_total_context_items=40,
        max_compatibility_projection_chars=40,
        max_memory_turns=10,
    )
    items = [
        _item(
            key="profile.preferred_name",
            section="profile",
            source=ContextSource.PROFILE,
            value="VeryLongNameThatWillNotFit",
            owner=7,
            display="preferred_name=" + ("X" * 80),
        )
    ]
    assembler = AuthorizedContextAssembler(
        profile_adapter=type("P", (), {"load": lambda self, *a, **k: items})(),
        lifestyle_adapter=_empty_adapter(),
        health_adapter=_empty_adapter(),
        memory_adapter=_empty_adapter(),
        notification_adapter=SafeNotificationContextAdapter(),
        budgets=tiny,
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=7, request_id="pn5")
    proj = assembler.build_compatibility_projection(snap)
    assert proj.truncated is True
    assert proj.preferred_name is None
    assert proj.item_count == 0


def test_preferred_name_none_when_conflicted():
    items = [
        _item(
            key="profile.preferred_name",
            section="profile",
            source=ContextSource.PROFILE,
            value="A",
            owner=7,
            display="preferred_name=A",
        ),
        _item(
            key="profile.preferred_name",
            section="profile",
            source=ContextSource.PROFILE,
            value="B",
            owner=7,
            display="preferred_name=B",
        ),
    ]
    assembler = _prefer_assembler_with_profile_items(items)
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=7, request_id="pn6")
    proj = assembler.build_compatibility_projection(snap)
    assert snap.conflict_count >= 1
    assert proj.preferred_name is None


def test_preferred_name_none_when_whitespace_value():
    assembler = _prefer_assembler_with_profile_items(
        [
            _item(
                key="profile.preferred_name",
                section="profile",
                source=ContextSource.PROFILE,
                value="   ",
                owner=7,
                display="preferred_name=   ",
            )
        ]
    )
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=7, request_id="pn7")
    proj = assembler.build_compatibility_projection(snap)
    assert proj.preferred_name is None


def test_preferred_name_coalesced_identical_values_allowed():
    items = [
        _item(
            key="profile.preferred_name",
            section="profile",
            source=ContextSource.PROFILE,
            value="Same",
            owner=7,
            display="preferred_name=Same",
        ),
        _item(
            key="profile.preferred_name",
            section="profile",
            source=ContextSource.PROFILE,
            value="Same",
            owner=7,
            display="preferred_name=Same",
        ),
    ]
    assembler = _prefer_assembler_with_profile_items(items)
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = assembler.assemble(MagicMock(), authenticated_user_id=7, request_id="pn8")
    proj = assembler.build_compatibility_projection(snap)
    assert snap.conflict_count == 0
    assert proj.preferred_name == "Same"


def test_preferred_name_not_in_reason_codes_or_stages(db, user_a, monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")
    pack = MagicMock()
    pack.preferred_name = "SecretNameXYZ"
    pack.birth_year = None
    pack.sex = None
    pack.addressing_preference = None
    pack.goals = MagicMock(items=[])
    pack.lifestyle = None
    pack.daily_memory_summary = None
    seen = {}

    def gen(*_a, **k):
        seen["preferred"] = k.get("structured_preferred_name")
        return {"message": "ok", "language": "en"}

    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=pack,
    ):
        orch = IntelligenceOrchestrator(db=db, legacy_generator=gen)
        result = orch.process(authenticated_user_id=user_a.id, message="hi", language="en")
    assert seen.get("preferred") == "SecretNameXYZ"
    assert "SecretNameXYZ" not in " ".join(result.reason_codes)
    assert "SecretNameXYZ" not in " ".join(result.stage_names)


def test_preferred_name_shared_eligibility_policy():
    from backend.app.services.intelligence.context_types import is_llm_projection_eligible

    good = _item(
        key="profile.preferred_name",
        section="profile",
        source=ContextSource.PROFILE,
        value="Pat",
        owner=1,
    )
    bad = _item(
        key="profile.preferred_name",
        section="profile",
        source=ContextSource.PROFILE,
        value="Nope",
        owner=1,
        may_send=False,
    )
    assert is_llm_projection_eligible(good) is True
    assert is_llm_projection_eligible(bad) is False
