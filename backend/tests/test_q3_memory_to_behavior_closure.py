"""Q3 — Memory → behavior closure (I6→I2→CHAT, adaptive, I7, I8, governance).

TEST-FIRST / report-only. No production repairs in this gate.
"""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import inspect
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.app import models
from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
from backend.app.services.a3_bounded_context_projection import (
    format_i8_context_block,
    project_bounded_i8_actions,
)
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import list_facts, list_facts_readonly_or_empty, write_fact
from backend.app.services.i7.derived_continuity import (
    get_bounded_continuity_topic,
    parse_bounded_continuity,
    refresh_bounded_continuity,
)
from backend.app.services.intelligence.adaptive_interaction import (
    REASON_LISTEN_BEFORE_ADVICE,
    REASON_RESPONSE_LENGTH_BRIEF,
    resolve_adaptive_interaction,
)
from backend.app.services.intelligence.adapters import (
    CurrentMemoryContextAdapter,
    LifestyleContextAdapter,
)
from backend.app.services.intelligence.assembler import AuthorizedContextAssembler
from backend.app.services.intelligence.context_types import (
    ContextItem,
    ContextProvenance,
    ContextSection,
    ContextSnapshot,
    ContextSource,
    SOURCE_SORT_RANK,
)
from backend.app.services.intelligence.contracts import (
    IntentConfidenceBand,
    IntentId,
    IntentResult,
    ReadinessResult,
    ReadinessStatus,
    RequestKind,
)
from backend.app.services.intelligence.next_best_question import select_next_best_question
from backend.app.services.memory.memory_contract import MemoryContract
from backend.app.services.notification_runtime import ai_enhancer


# ---- helpers ----


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _grant(db, user_id: int) -> None:
    grant_memory_consent(db, user_id, commit=True)


def _intent(
    intent_id: IntentId = IntentId.GENERAL,
    kind: RequestKind = RequestKind.INFORMATIONAL,
) -> IntentResult:
    return IntentResult(
        registry_version="t",
        intent_id=intent_id,
        request_kind=kind,
        confidence_band=IntentConfidenceBand.HIGH,
        rule_id="t",
    )


def _ready(intent: IntentResult) -> ReadinessResult:
    return ReadinessResult(
        status=ReadinessStatus.READY,
        intent_id=intent.intent_id,
        request_kind=intent.request_kind,
        outcomes=(),
        missing_fact_keys=(),
        clarification=None,
    )


def _item(
    key: str,
    value="x",
    *,
    active: bool = True,
    owner: int = 1,
    may_send: bool = True,
    sensitivity: str = "medium",
    epistemic: str | None = "USER_STATED",
) -> ContextItem:
    return ContextItem(
        canonical_key=key,
        section="profile",
        source=ContextSource.PROFILE,
        structured_value=value,
        display_text=f"{key.split('.', 1)[-1]}={value}",
        provenance=ContextProvenance(
            source=ContextSource.PROFILE, owner_user_id=owner, query_label="t"
        ),
        observed_at=None,
        freshness="unknown",
        sensitivity=sensitivity,  # type: ignore[arg-type]
        consent="legacy_scope",
        may_send_to_llm=may_send,
        sort_rank=SOURCE_SORT_RANK[ContextSource.PROFILE],
        active=active,
        conflicted=False,
        epistemic_class=epistemic,
    )


def _snap(items: list[ContextItem], owner: int = 1) -> ContextSnapshot:
    return ContextSnapshot(
        request_id="q3",
        owner_user_id=owner,
        sections={"profile": ContextSection(name="profile", items=list(items))},
        items=list(items),
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("profile",),
    )


def _seed_canonical_understanding(db, user_id: int) -> None:
    write_fact(
        db,
        user_id,
        "preferences",
        "interests",
        "hiking",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    write_fact(
        db,
        user_id,
        "work",
        "occupation",
        "designer",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    write_fact(
        db,
        user_id,
        "work",
        "work_schedule",
        "day shift",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    write_fact(
        db,
        user_id,
        "barriers",
        "time_constraints",
        "limited time",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )


# ---- A) I6 → I2 → CHAT ----


def test_q3_i6_to_i2_canonical_facts_reach_authorized_snapshot(db):
    user = _user(db, "q3-i6i2")
    _grant(db, user.id)
    _seed_canonical_understanding(db, user.id)

    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    by_key = {i.canonical_key: i for i in items}

    assert "preferences.interests" in by_key
    assert "work.occupation" in by_key
    assert "work.work_schedule" in by_key
    assert "barriers.time_constraints" in by_key

    assert all(i.provenance.owner_user_id == user.id for i in by_key.values())
    assert "hiking" in str(by_key["preferences.interests"].structured_value)
    assert "designer" in str(by_key["work.occupation"].structured_value)
    assert "day shift" in str(by_key["work.work_schedule"].structured_value)
    assert "limited time" in str(by_key["barriers.time_constraints"].structured_value)


def test_q3_i2_to_chat_eligible_facts_enter_compatibility_projection(db):
    user = _user(db, "q3-i2chat")
    _grant(db, user.id)
    _seed_canonical_understanding(db, user.id)

    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    snap = ContextSnapshot(
        request_id="q3-proj",
        owner_user_id=user.id,
        sections={"lifestyle": ContextSection(name="lifestyle", items=items)},
        items=items,
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("lifestyle",),
    )
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)

    # Eligible ordinary known-context reaches chat generator projection.
    assert "hiking" in proj.text
    assert "interests" in proj.text
    assert "designer" in proj.text
    assert "occupation" in proj.text
    assert "day shift" in proj.text
    assert "work_schedule" in proj.text

    # Q3.1: sole barriers exception — ordinary time_constraints is LLM-eligible.
    barrier = next(i for i in items if i.canonical_key == "barriers.time_constraints")
    assert barrier.sensitivity == "medium"
    assert barrier.may_send_to_llm is True
    assert "limited time" in proj.text
    assert "time_constraints" in proj.text


# ---- B) MEMORY REUSE ----


def test_q3_known_interest_not_reasked():
    intent = _intent()
    snap = _snap([_item("preferences.interests", "hiking")])
    d = select_next_best_question(
        snapshot=snap,
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="What should I do this weekend?",
    )
    assert d is None or d.target_key != "preferences.interests"


# ---- C) PERSONALIZED BEHAVIOR (prompt/context availability, not LLM wording) ----


def test_q3_interest_and_work_available_for_later_recommendation_context(db):
    user = _user(db, "q3-pers")
    _grant(db, user.id)
    _seed_canonical_understanding(db, user.id)

    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    proj = AuthorizedContextAssembler().build_compatibility_projection(
        ContextSnapshot(
            request_id="q3-pers",
            owner_user_id=user.id,
            sections={"lifestyle": ContextSection(name="lifestyle", items=items)},
            items=items,
            preferred_name=None,
            conflict_count=0,
            truncated_count=0,
            reason_codes=(),
            adapter_order=("lifestyle",),
        )
    )
    # Activity-recommendation style context can see interest + work + time constraint.
    assert "hiking" in proj.text
    assert "day shift" in proj.text
    assert "limited time" in proj.text


# ---- D) ADAPTIVE PREFERENCES ----


def test_q3_adaptive_prefs_guide_relationship_not_dumped_as_profile(db):
    user = _user(db, "q3-adapt")
    _grant(db, user.id)
    write_fact(
        db,
        user.id,
        "preferences",
        "response_length",
        "brief",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    write_fact(
        db,
        user.id,
        "preferences",
        "listen_before_advice",
        True,
        provenance_class="USER_CONFIRMED",
        sensitivity_class="standard",
        commit=True,
    )
    write_fact(
        db,
        user.id,
        "preferences",
        "interests",
        "hiking",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )

    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    by_key = {i.canonical_key: i for i in items}
    assert by_key["preferences.response_length"].may_send_to_llm is False
    assert by_key["preferences.listen_before_advice"].may_send_to_llm is False

    snap = ContextSnapshot(
        request_id="q3-adapt",
        owner_user_id=user.id,
        sections={"profile": ContextSection(name="profile", items=items)},
        items=items,
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("lifestyle",),
    )
    adaptive = resolve_adaptive_interaction(snap)
    assert adaptive.response_length == "brief"
    assert adaptive.listen_before_advice is True
    assert REASON_RESPONSE_LENGTH_BRIEF in adaptive.reason_codes
    assert REASON_LISTEN_BEFORE_ADVICE in adaptive.reason_codes

    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "response_length" not in proj.text
    assert "listen_before_advice" not in proj.text
    assert "brief" not in proj.text.lower()
    assert "hiking" in proj.text

    guidance = PersonaPolicyV1.relationship_guidance_block(
        "general",
        "en",
        response_length=adaptive.response_length,
        listen_before_advice=adaptive.listen_before_advice,
    )
    assert "concise" in guidance.lower()
    assert "acknowledge" in guidance.lower() or "listen" in guidance.lower()
    assert "response_length" not in guidance
    assert "listen_before_advice" not in guidance


# ---- E) I7 derived continuity ----


def test_q3_i7_derived_only_not_canonical_i6(db):
    user = _user(db, "q3-i7")
    _grant(db, user.id)
    mem = models.Memory(
        user_id=user.id,
        user_message="Planning a short evening walk",
        sedi_response="Sounds good.",
    )
    db.add(mem)
    db.flush()

    before = {
        (f.domain, f.key, str(f.value_json))
        for f in list_facts_readonly_or_empty(db, user.id, domain="preferences")
    }
    before |= {
        (f.domain, f.key, str(f.value_json))
        for f in list_facts_readonly_or_empty(db, user.id, domain="lifestyle")
    }

    row = refresh_bounded_continuity(db, user_id=user.id, memory=mem)
    assert row is not None
    bc = parse_bounded_continuity(row)
    assert bc.get("not_i6_fact") is True
    assert bc.get("not_transcript") is True
    topic = get_bounded_continuity_topic(db, user.id)
    assert topic
    assert "walk" in topic.lower()

    # Derived topic is not written into canonical I6 facts by refresh.
    after = {
        (f.domain, f.key, str(f.value_json))
        for f in list_facts_readonly_or_empty(db, user.id, domain="preferences")
    }
    after |= {
        (f.domain, f.key, str(f.value_json))
        for f in list_facts_readonly_or_empty(db, user.id, domain="lifestyle")
    }
    assert after == before
    assert not MemoryContract.is_valid_key("memory", "derived_continuity")

    with patch(
        "backend.app.services.i7.derived_continuity.should_project_derived_continuity",
        return_value=True,
    ):
        mem_items = CurrentMemoryContextAdapter().load(
            db,
            authenticated_user_id=user.id,
            user_context_pack=SimpleNamespace(daily_memory_summary=None),
        )
    derived = [i for i in mem_items if i.canonical_key == "memory.derived_continuity"]
    assert derived
    assert derived[0].source == ContextSource.MEMORY
    assert derived[0].provenance.owner_user_id == user.id
    assert "UserPeriodSummary" in (derived[0].provenance.query_label or "")
    assert topic[:80] in str(derived[0].structured_value)


# ---- F) I8 ownership + chat context ----


def test_q3_i8_bounded_context_reaches_chat_without_i6_copy(db):
    user = _user(db, "q3-i8")
    _grant(db, user.id)
    summary = "Take a 10-minute stretch break"

    plan = SimpleNamespace(id=11, user_local_date=date(2026, 10, 3))
    action = SimpleNamespace(
        status="ACTIVE",
        safety_state="SAFE",
        action_domain="routine",
        summary_text=summary,
    )
    repo = MagicMock()
    repo.get_active_plan.return_value = plan
    repo.list_actions_for_plan.return_value = [action]

    facts_before = list(list_facts(db, user.id))
    with patch(
        "backend.app.services.a3_bounded_context_projection.I8OperationalRepository",
        return_value=repo,
    ):
        items = project_bounded_i8_actions(
            db, user.id, today_local_date="2026-10-03"
        )
    block = format_i8_context_block(items)
    assert summary in block
    assert "[I8_BOUNDED_ACTIONS]" in block
    assert "not plan authority" in block.lower()

    # Projection does not copy the action into I6 canonical memory.
    facts_after = list(list_facts(db, user.id))
    assert len(facts_after) == len(facts_before)
    assert not any(summary in str(getattr(f, "value_json", "")) for f in facts_after)

    # Brain seam imports the same I8 formatter (ownership stays I8-owned).
    from backend.app.core.conversation import brain as brain_mod

    src = inspect.getsource(brain_mod._append_a3_lifecycle_and_bounded_context)
    assert "project_bounded_i8_actions" in src
    assert "format_i8_context_block" in src


# ---- G) SECURITY / GOVERNANCE ----


def test_q3_cross_user_isolation_no_leak(db):
    a = _user(db, "q3-iso-a")
    b = _user(db, "q3-iso-b")
    _grant(db, a.id)
    _grant(db, b.id)
    write_fact(
        db,
        a.id,
        "preferences",
        "interests",
        "secret-hiking-a",
        provenance_class="USER_STATED",
        commit=True,
    )
    write_fact(
        db,
        b.id,
        "preferences",
        "interests",
        "secret-gardening-b",
        provenance_class="USER_STATED",
        commit=True,
    )

    items_a = LifestyleContextAdapter().load(
        db, authenticated_user_id=a.id, user_context_pack=None
    )
    items_b = LifestyleContextAdapter().load(
        db, authenticated_user_id=b.id, user_context_pack=None
    )
    text_a = " ".join(str(i.structured_value) for i in items_a)
    text_b = " ".join(str(i.structured_value) for i in items_b)
    assert "secret-hiking-a" in text_a
    assert "secret-gardening-b" not in text_a
    assert "secret-gardening-b" in text_b
    assert "secret-hiking-a" not in text_b
    assert all(i.provenance.owner_user_id == a.id for i in items_a)
    assert all(i.provenance.owner_user_id == b.id for i in items_b)


def test_q3_sensitivity_fail_closed_and_assemble_is_read_only(db):
    user = _user(db, "q3-gov")
    _grant(db, user.id)
    _seed_canonical_understanding(db, user.id)
    write_fact(
        db,
        user.id,
        "social",
        "support_network",
        "private-friends",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )

    count_before = len(list(list_facts(db, user.id)))
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap = AuthorizedContextAssembler().assemble(
            db, authenticated_user_id=user.id, request_id="q3-gov"
        )
    count_after = len(list(list_facts(db, user.id)))
    assert count_after == count_before

    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    assert "private-friends" not in proj.text
    assert "limited time" in proj.text
    assert "hiking" in proj.text


# ---- Q3.1 barriers.time_constraints projection exception ----


def test_q31_time_constraints_medium_reaches_llm_projection(db):
    user = _user(db, "q31-tc-med")
    _grant(db, user.id)
    write_fact(
        db,
        user.id,
        "barriers",
        "time_constraints",
        "limited time",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    hit = next(i for i in items if i.canonical_key == "barriers.time_constraints")
    assert hit.sensitivity == "medium"
    assert hit.may_send_to_llm is True
    proj = AuthorizedContextAssembler().build_compatibility_projection(
        ContextSnapshot(
            request_id="q31-tc-med",
            owner_user_id=user.id,
            sections={"lifestyle": ContextSection(name="lifestyle", items=items)},
            items=items,
            preferred_name=None,
            conflict_count=0,
            truncated_count=0,
            reason_codes=(),
            adapter_order=("lifestyle",),
        )
    )
    assert "limited time" in proj.text
    assert "time_constraints" in proj.text


def test_q31_time_constraints_high_row_blocked(db):
    user = _user(db, "q31-tc-high")
    _grant(db, user.id)
    write_fact(
        db,
        user.id,
        "barriers",
        "time_constraints",
        "limited time high",
        provenance_class="USER_STATED",
        sensitivity_class="high",
        commit=True,
    )
    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    hit = next(i for i in items if i.canonical_key == "barriers.time_constraints")
    assert hit.sensitivity == "high"
    assert hit.may_send_to_llm is False
    proj = AuthorizedContextAssembler().build_compatibility_projection(
        ContextSnapshot(
            request_id="q31-tc-high",
            owner_user_id=user.id,
            sections={"lifestyle": ContextSection(name="lifestyle", items=items)},
            items=items,
            preferred_name=None,
            conflict_count=0,
            truncated_count=0,
            reason_codes=(),
            adapter_order=("lifestyle",),
        )
    )
    assert "limited time high" not in proj.text


def test_q31_other_barriers_remain_blocked(db):
    user = _user(db, "q31-bar-block")
    _grant(db, user.id)
    write_fact(
        db,
        user.id,
        "barriers",
        "time_constraints",
        "limited time",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    write_fact(
        db,
        user.id,
        "barriers",
        "financial_constraints",
        "tight budget secret",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    write_fact(
        db,
        user.id,
        "barriers",
        "motivation_barriers",
        "low energy secret",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    by_key = {i.canonical_key: i for i in items}
    assert by_key["barriers.time_constraints"].may_send_to_llm is True
    assert by_key["barriers.financial_constraints"].sensitivity == "high"
    assert by_key["barriers.financial_constraints"].may_send_to_llm is False
    assert by_key["barriers.motivation_barriers"].sensitivity == "high"
    assert by_key["barriers.motivation_barriers"].may_send_to_llm is False

    proj = AuthorizedContextAssembler().build_compatibility_projection(
        ContextSnapshot(
            request_id="q31-bar-block",
            owner_user_id=user.id,
            sections={"lifestyle": ContextSection(name="lifestyle", items=items)},
            items=items,
            preferred_name=None,
            conflict_count=0,
            truncated_count=0,
            reason_codes=(),
            adapter_order=("lifestyle",),
        )
    )
    assert "limited time" in proj.text
    assert "tight budget secret" not in proj.text
    assert "low energy secret" not in proj.text
    assert "financial_constraints" not in proj.text
    assert "motivation_barriers" not in proj.text


def test_q31_time_constraints_cross_user_and_assemble_read_only(db):
    a = _user(db, "q31-iso-a")
    b = _user(db, "q31-iso-b")
    _grant(db, a.id)
    _grant(db, b.id)
    write_fact(
        db,
        a.id,
        "barriers",
        "time_constraints",
        "only-user-a-time",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    write_fact(
        db,
        b.id,
        "barriers",
        "time_constraints",
        "only-user-b-time",
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        commit=True,
    )
    count_a = len(list(list_facts(db, a.id)))
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=None,
    ):
        snap_a = AuthorizedContextAssembler().assemble(
            db, authenticated_user_id=a.id, request_id="q31-iso-a"
        )
        snap_b = AuthorizedContextAssembler().assemble(
            db, authenticated_user_id=b.id, request_id="q31-iso-b"
        )
    assert len(list(list_facts(db, a.id))) == count_a

    proj_a = AuthorizedContextAssembler().build_compatibility_projection(snap_a)
    proj_b = AuthorizedContextAssembler().build_compatibility_projection(snap_b)
    assert "only-user-a-time" in proj_a.text
    assert "only-user-b-time" not in proj_a.text
    assert "only-user-b-time" in proj_b.text
    assert "only-user-a-time" not in proj_b.text
    assert all(i.provenance.owner_user_id == a.id for i in snap_a.items)
    assert all(i.provenance.owner_user_id == b.id for i in snap_b.items)


# ---- H) NOTIFICATION personalized context (read-only seam check) ----


def test_q3_notification_ai_enhancer_has_no_authorized_i6_context_seam():
    src = inspect.getsource(ai_enhancer.enhance_with_ai)
    # Current AI notification generation only receives name/health/hours — no I2/I6 pack.
    assert "generate_notification_text" in src
    assert "AuthorizedContextAssembler" not in src
    assert "structured_context" not in src
    assert "user_context_pack" not in src
    assert "LifestyleContextAdapter" not in src
    sig = inspect.signature(ai_enhancer.enhance_with_ai)
    assert list(sig.parameters.keys()) == ["payload"]
