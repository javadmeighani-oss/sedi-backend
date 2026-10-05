"""Q4.2A foundation — natural progressive invited discovery (I3/NBQ→fatigue→RD→I6→I2)."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from datetime import datetime, timedelta, timezone

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import list_facts
from backend.app.services.i6.relationship_discovery import (
    INVITED_MARKER_PREFIX,
    MARKER_PREFIX,
    DiscoveryDisposition,
    classify_discovery_reply,
    format_relationship_discovery_marker,
    parse_relationship_discovery_marker,
    peek_relationship_discovery_state,
    process_relationship_discovery_answer,
)
from backend.app.services.intelligence.adapters import LifestyleContextAdapter
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
from backend.app.services.intelligence.next_best_question import (
    _INVITATION_SOFT_PRIORITY,
    detect_discovery_invitation,
    select_next_best_question,
)
from backend.app.services.intelligence.psychological_interaction import (
    InteractionNeed,
    classify_interaction_need,
)
from backend.app.services.knowledge.kc_fatigue_policy import (
    check_can_ask,
    check_can_ask_relationship_discovery,
    mark_asked,
    mark_answer,
)


_PHYSICAL_FA = "خوب نمی‌خوای اطلاعات بیشتری داشته باشی؟"


def _intent(intent_id: IntentId = IntentId.GENERAL) -> IntentResult:
    return IntentResult(
        registry_version="t",
        intent_id=intent_id,
        request_kind=RequestKind.INFORMATIONAL,
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


def _item(key: str, *, owner: int = 1) -> ContextItem:
    return ContextItem(
        canonical_key=key,
        section="profile",
        source=ContextSource.PROFILE,
        structured_value="x",
        display_text=f"{key}=x",
        provenance=ContextProvenance(
            source=ContextSource.PROFILE, owner_user_id=owner, query_label="t"
        ),
        observed_at=None,
        freshness="unknown",
        sensitivity="medium",
        consent="legacy_scope",
        may_send_to_llm=False,
        sort_rank=SOURCE_SORT_RANK[ContextSource.PROFILE],
        active=True,
        conflicted=False,
    )


def _snap(items: list[ContextItem], owner: int = 1) -> ContextSnapshot:
    return ContextSnapshot(
        request_id="q42a",
        owner_user_id=owner,
        sections={"profile": ContextSection(name="profile", items=list(items))},
        items=list(items),
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("profile",),
    )


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def test_q42a_physical_fa_invitation_detected():
    assert detect_discovery_invitation(_PHYSICAL_FA, "fa") is True
    intent = _intent()
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language="fa",
        message=_PHYSICAL_FA,
    )
    assert d is not None
    assert d.question_id.startswith("nbq.q.invitation.")
    assert d.target_key == "preferences.interests"


def test_q42a_en_ar_bounded_invitations_detected():
    assert detect_discovery_invitation(
        "do you want more information about me", "en"
    )
    assert detect_discovery_invitation("want to know more about me", "en")
    assert detect_discovery_invitation("get to know me better", "en")
    assert detect_discovery_invitation("ask me whatever you need", "en")
    assert detect_discovery_invitation("هل تريد معلومات أكثر عني", "ar")
    assert detect_discovery_invitation("تعرف علي أكثر", "ar")
    assert detect_discovery_invitation("اسألني ما تحتاج", "ar")


def test_q42a_invitation_targets_widened_order():
    assert _INVITATION_SOFT_PRIORITY[0] == "preferences.interests"
    assert _INVITATION_SOFT_PRIORITY[1] == "work.occupation"
    assert "work.work_schedule" in _INVITATION_SOFT_PRIORITY
    assert "lifestyle.sleep_quality" in _INVITATION_SOFT_PRIORITY
    assert "routines.bedtime" in _INVITATION_SOFT_PRIORITY
    assert "barriers.time_constraints" not in _INVITATION_SOFT_PRIORITY


def test_q42a_normal_rd_spacing_10_min_no_daily_cap(db):
    user = _user(db, "q42a-space")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Three prior asks block generic KC daily cap.
    for i in range(3):
        mark_asked(
            db,
            user.id,
            now - timedelta(hours=5 - i),
            f"confirm_candidate:{i}",
        )
    allowed_kc, reason_kc, _, _ = check_can_ask(db, user.id, now)
    assert allowed_kc is False
    assert reason_kc == "fatigue_control"

    # Normal RD ignores daily count when last ask is older than 10 minutes.
    mark_asked(
        db,
        user.id,
        now - timedelta(minutes=11),
        f"{MARKER_PREFIX}preferences.interests",
    )
    # asked_count still >= 3 from ensure_state day, but RD has no daily cap.
    allowed_rd, reason_rd, _, snap = check_can_ask_relationship_discovery(
        db, user.id, now, invited=False
    )
    assert allowed_rd is True
    assert reason_rd is None
    assert snap["asked_today"] >= 3

    # Within 10 minutes → blocked for normal RD.
    mark_asked(
        db,
        user.id,
        now - timedelta(minutes=3),
        f"{MARKER_PREFIX}preferences.interests",
    )
    allowed_rd3, reason_rd3, _, _ = check_can_ask_relationship_discovery(
        db, user.id, now, invited=False
    )
    assert allowed_rd3 is False
    assert reason_rd3 == "fatigue_control"


def test_q42a_generic_kc_policy_still_3_90(db, monkeypatch):
    monkeypatch.delenv("KC_DAILY_QUESTION_CAP", raising=False)
    monkeypatch.delenv("KC_COOLDOWN_MINUTES", raising=False)
    from backend.app.services.knowledge import kc_fatigue_policy as fat

    assert fat._get_daily_cap() == 3
    assert fat._get_cooldown_minutes() == 90
    user = _user(db, "q42a-kc")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(db, user.id, now - timedelta(minutes=5), "confirm_candidate:x")
    allowed, reason, _, snap = check_can_ask(db, user.id, now)
    assert allowed is False
    assert reason == "fatigue_control"
    assert snap["daily_cap"] == 3


def test_q42a_invited_bypasses_time_spacing(db):
    user = _user(db, "q42a-invbypass")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(
        db,
        user.id,
        now - timedelta(minutes=1),
        f"{MARKER_PREFIX}preferences.interests",
    )
    blocked, _, _, _ = check_can_ask_relationship_discovery(
        db, user.id, now, invited=False
    )
    assert blocked is False
    allowed, reason, _, _ = check_can_ask_relationship_discovery(
        db, user.id, now, invited=True
    )
    assert allowed is True
    assert reason is None


def test_q42a_invited_marker_origin_and_parse():
    normal = format_relationship_discovery_marker(
        "preferences.interests", invited=False
    )
    invited = format_relationship_discovery_marker(
        "preferences.interests", invited=True
    )
    assert normal == f"{MARKER_PREFIX}preferences.interests"
    assert invited == f"{INVITED_MARKER_PREFIX}preferences.interests"
    k1, inv1 = parse_relationship_discovery_marker(normal)
    k2, inv2 = parse_relationship_discovery_marker(invited)
    assert k1 == k2 == "preferences.interests"
    assert inv1 is False
    assert inv2 is True


def test_q42a_invited_answer_writes_i6_and_continues(db):
    user = _user(db, "q42a-write")
    grant_memory_consent(db, user.id, commit=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(
        db,
        user.id,
        now,
        format_relationship_discovery_marker(
            "preferences.response_length", invited=True
        ),
    )
    target, invited = peek_relationship_discovery_state(db, user.id)
    assert target == "preferences.response_length"
    assert invited is True

    clf = classify_discovery_reply(
        "preferences.response_length", "brief please", "en"
    )
    assert clf.disposition is DiscoveryDisposition.ANSWER
    out = process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="brief please",
        language="en",
        allow_binding=True,
        classification=clf,
    )
    assert out.disposition is DiscoveryDisposition.ANSWER
    facts = list_facts(db, user.id, domain="preferences")
    row = next(f for f in facts if f.key == "response_length")
    assert "brief" in (row.value_json or "").lower()
    assert row.source == "relationship_discovery"
    # Marker consumed — progressive continue uses force_invitation, not residual marker.
    assert peek_relationship_discovery_state(db, user.id) == (None, False)

    # Same-turn next invited target (interests still missing).
    d = select_next_best_question(
        snapshot=_snap([_item("preferences.response_length")]),
        intent=_intent(),
        readiness=_ready(_intent()),
        language="en",
        message="brief please",
        force_invitation=True,
    )
    assert d is not None
    assert d.question_id.startswith("nbq.q.invitation.")
    assert d.target_key == "preferences.interests"
    # Immediate: invited fatigue allows even after mark seconds ago.
    allowed, _, _, _ = check_can_ask_relationship_discovery(
        db, user.id, now + timedelta(seconds=5), invited=True
    )
    assert allowed is True


def test_q42a_known_fact_skipped_on_invitation():
    intent = _intent()
    d = select_next_best_question(
        snapshot=_snap([_item("preferences.interests")]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="ask me something",
    )
    assert d is not None
    assert d.target_key != "preferences.interests"
    assert d.target_key == "work.occupation"


def test_q42a_decline_and_topic_shift_stop_continuation(db):
    user = _user(db, "q42a-stop")
    grant_memory_consent(db, user.id, commit=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(
        db,
        user.id,
        now,
        format_relationship_discovery_marker("preferences.interests", invited=True),
    )
    skip = classify_discovery_reply("preferences.interests", "skip", "en")
    assert skip.disposition is DiscoveryDisposition.SKIP
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="skip",
        language="en",
        allow_binding=True,
        classification=skip,
    )
    assert peek_relationship_discovery_state(db, user.id) == (None, False)
    # After skip, force_invitation would still select — orchestrator must NOT set
    # continue_invited on SKIP (only ANSWER). Prove SKIP is not ANSWER.
    assert skip.disposition is not DiscoveryDisposition.ANSWER

    mark_asked(
        db,
        user.id,
        now,
        format_relationship_discovery_marker("preferences.interests", invited=True),
    )
    shift = classify_discovery_reply(
        "preferences.interests", "create a meal plan for me", "en"
    )
    assert shift.disposition is DiscoveryDisposition.UNRELATED
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="create a meal plan for me",
        language="en",
        allow_binding=True,
        classification=shift,
    )
    assert peek_relationship_discovery_state(db, user.id) == (None, False)


def test_q42a_be_heard_and_i4_precedence():
    msg = "I feel overwhelmed and just need to talk, ask me something"
    need = classify_interaction_need(message=msg, intent=_intent(), language="en")
    assert need is InteractionNeed.BE_HEARD
    visible = need is not InteractionNeed.BE_HEARD
    assert visible is False

    intent = _intent()
    assert (
        select_next_best_question(
            snapshot=_snap([]),
            intent=intent,
            readiness=ReadinessResult(
                status=ReadinessStatus.NEEDS_CLARIFICATION,
                intent_id=intent.intent_id,
                request_kind=intent.request_kind,
                outcomes=(),
                missing_fact_keys=("x",),
                clarification=None,
            ),
            language="en",
            message=_PHYSICAL_FA,
            force_invitation=True,
        )
        is None
    )


def test_q42a_time_constraints_contextual_only():
    intent = _intent()
    # Invitation must not select time_constraints even when all invite targets known.
    known = [_item(k) for k in _INVITATION_SOFT_PRIORITY]
    d = select_next_best_question(
        snapshot=_snap(known),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="ask me something",
    )
    assert d is None or d.target_key != "barriers.time_constraints"

    # Contextual still can when relevance cues match (existing NBQ cues).
    d2 = select_next_best_question(
        snapshot=_snap(known),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="I have limited time and not enough time today",
    )
    assert d2 is not None
    assert d2.target_key == "barriers.time_constraints"


def test_q42a_no_duplicate_i6_write_on_same_answer(db):
    user = _user(db, "q42a-dup")
    grant_memory_consent(db, user.id, commit=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(
        db,
        user.id,
        now,
        format_relationship_discovery_marker(
            "preferences.response_length", invited=True
        ),
    )
    clf = classify_discovery_reply(
        "preferences.response_length", "brief", "en"
    )
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="brief",
        language="en",
        allow_binding=True,
        classification=clf,
    )
    # Second process with no marker → NO_MARKER, no extra row churn as new domain.
    out2 = process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="brief",
        language="en",
        allow_binding=True,
    )
    assert out2.disposition is DiscoveryDisposition.NO_MARKER
    facts = [f for f in list_facts(db, user.id, domain="preferences") if f.key == "response_length"]
    assert len(facts) == 1


def test_q42a_i6_fact_reusable_via_i2_adapter(db):
    user = _user(db, "q42a-i2")
    grant_memory_consent(db, user.id, commit=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(
        db,
        user.id,
        now,
        format_relationship_discovery_marker(
            "preferences.response_length", invited=True
        ),
    )
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="detailed",
        language="en",
        allow_binding=True,
        classification=classify_discovery_reply(
            "preferences.response_length", "detailed", "en"
        ),
    )
    adapter = LifestyleContextAdapter()
    items = adapter.load(db, authenticated_user_id=user.id)
    keys = {i.canonical_key for i in items}
    assert "preferences.response_length" in keys


def test_q42a_reject_streak_still_blocks_invited(db):
    """Decline protection: explicit cooldown_until still blocks invited RD."""
    user = _user(db, "q42a-reject")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(db, user.id, now - timedelta(minutes=30), "confirm_candidate:1")
    mark_answer(db, user.id, now, "skipped")
    mark_answer(db, user.id, now, "skipped")  # streak → cooldown_until
    allowed, reason, _, _ = check_can_ask_relationship_discovery(
        db, user.id, now, invited=True
    )
    assert allowed is False
    assert reason == "fatigue_control"


def test_q42a_no_schema_discovery_session_or_i11():
    import os

    models_src = open(
        os.path.join("backend", "app", "models.py"), encoding="utf-8"
    ).read()
    assert "DiscoverySession" not in models_src
    assert "relationship_discovery_invited" not in models_src  # column not added
    # Marker strings live in code only; column remains last_question_type.
    assert "last_question_type" in models_src
