"""Q4.2B — adaptive max-2 invited discovery (safe pairs only)."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from datetime import datetime, timedelta, timezone

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import list_facts
from backend.app.services.i6.relationship_discovery import (
    INVITED_MARKER_PREFIX,
    MARKER_PREFIX,
    PAIR_DELIMITER,
    DiscoveryDisposition,
    classify_discovery_reply,
    format_relationship_discovery_marker,
    parse_relationship_discovery_targets,
    peek_relationship_discovery_targets,
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
    _INVITED_SAFE_PAIRS,
    _invited_companion_key,
    detect_discovery_invitation,
    select_next_best_question,
)
from backend.app.services.intelligence.psychological_interaction import (
    InteractionNeed,
    append_discovery_questions,
    classify_interaction_need,
)
from backend.app.services.knowledge.kc_fatigue_policy import (
    check_can_ask,
    check_can_ask_relationship_discovery,
    mark_asked,
)


def _intent(iid: IntentId = IntentId.GENERAL) -> IntentResult:
    return IntentResult(
        registry_version="t",
        intent_id=iid,
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


def _item(key: str) -> ContextItem:
    return ContextItem(
        canonical_key=key,
        section="profile",
        source=ContextSource.PROFILE,
        structured_value="x",
        display_text=f"{key}=x",
        provenance=ContextProvenance(
            source=ContextSource.PROFILE, owner_user_id=1, query_label="t"
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


def _snap(keys: list[str] | None = None) -> ContextSnapshot:
    items = [_item(k) for k in (keys or [])]
    return ContextSnapshot(
        request_id="q42b",
        owner_user_id=1,
        sections={"profile": ContextSection(name="profile", items=items)},
        items=items,
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("profile",),
    )


def _user(db, name: str) -> models.User:
    u = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(u)
    db.flush()
    return u


def test_q42b_normal_discovery_still_max1():
    intent = _intent()
    d = select_next_best_question(
        snapshot=_snap(),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="Hello",
    )
    assert d is not None
    assert d.companion_target_key is None
    assert d.companion_localized_question is None


def test_q42b_invited_emits_safe_occupation_schedule_pair():
    intent = _intent()
    d = select_next_best_question(
        snapshot=_snap(["preferences.interests"]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="ask me something",
    )
    assert d is not None
    assert d.target_key == "work.occupation"
    assert d.companion_target_key == "work.work_schedule"
    assert d.companion_localized_question
    out = append_discovery_questions(
        "Sure.",
        (d.localized_question, d.companion_localized_question),
    )
    assert out.count("?") + out.count("؟") >= 2
    assert out.startswith("Sure.")


def test_q42b_progressive_continuation_can_emit_max2():
    intent = _intent()
    d = select_next_best_question(
        snapshot=_snap(["preferences.interests"]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="brief",
        force_invitation=True,
        exclude_keys=frozenset({"preferences.response_length"}),
    )
    assert d is not None
    assert d.target_key == "work.occupation"
    assert d.companion_target_key == "work.work_schedule"


def test_q42b_append_never_more_than_two():
    out = append_discovery_questions("A", ("Q1?", "Q2?", "Q3?", "Q4?"))
    assert out.count("Q3") == 0
    assert "Q1?" in out and "Q2?" in out


def test_q42b_safe_pair_policy_bounded():
    assert len(_INVITED_SAFE_PAIRS) == 3
    assert _invited_companion_key("work.occupation") == "work.work_schedule"
    assert _invited_companion_key("lifestyle.activity_level") == "routines.exercise_schedule"
    assert _invited_companion_key("routines.bedtime") == "routines.wake_time"
    assert _invited_companion_key("preferences.interests") is None
    assert _invited_companion_key("preferences.communication_style") is None


def test_q42b_arbitrary_pair_not_created():
    intent = _intent()
    d = select_next_best_question(
        snapshot=_snap(),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="ask me something",
    )
    assert d is not None
    assert d.target_key == "preferences.interests"
    assert d.companion_target_key is None


def test_q42b_pair_marker_format_and_legacy():
    pair = format_relationship_discovery_marker(
        "work.occupation", invited=True, companion_key="work.work_schedule"
    )
    assert pair == (
        f"{INVITED_MARKER_PREFIX}work.occupation"
        f"{PAIR_DELIMITER}work.work_schedule"
    )
    targets, invited = parse_relationship_discovery_targets(pair)
    assert invited is True
    assert targets == ("work.occupation", "work.work_schedule")

    single = format_relationship_discovery_marker(
        "preferences.interests", invited=True
    )
    assert parse_relationship_discovery_targets(single) == (
        ("preferences.interests",),
        True,
    )
    normal = format_relationship_discovery_marker(
        "preferences.interests", invited=False
    )
    assert normal.startswith(MARKER_PREFIX)
    assert PAIR_DELIMITER not in normal


def test_q42b_malformed_pair_fail_closed():
    assert parse_relationship_discovery_targets(
        f"{INVITED_MARKER_PREFIX}a|b|c"
    ) == ((), True)
    assert parse_relationship_discovery_targets(
        f"{INVITED_MARKER_PREFIX}|"
    ) == ((), True)
    assert parse_relationship_discovery_targets(
        f"{INVITED_MARKER_PREFIX}only|"
    ) == ((), True)
    assert parse_relationship_discovery_targets(
        f"{MARKER_PREFIX}work.occupation|work.work_schedule"
    ) == ((), False)


def test_q42b_occupation_schedule_binds_both(db):
    user = _user(db, "q42b-both")
    grant_memory_consent(db, user.id, commit=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(
        db,
        user.id,
        now,
        format_relationship_discovery_marker(
            "work.occupation",
            invited=True,
            companion_key="work.work_schedule",
        ),
    )
    msg = "I work as a teacher on night shifts"
    out = process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=msg,
        language="en",
        allow_binding=True,
    )
    assert out.disposition is DiscoveryDisposition.ANSWER
    assert set(out.answered_keys) == {"work.occupation", "work.work_schedule"}
    facts = list_facts(db, user.id, domain="work")
    keys = {f.key for f in facts}
    assert "occupation" in keys and "work_schedule" in keys


def test_q42b_activity_exercise_binds_independently(db):
    user = _user(db, "q42b-act")
    grant_memory_consent(db, user.id, commit=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(
        db,
        user.id,
        now,
        format_relationship_discovery_marker(
            "lifestyle.activity_level",
            invited=True,
            companion_key="routines.exercise_schedule",
        ),
    )
    msg = "I walk daily and exercise three times a week"
    out = process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=msg,
        language="en",
        allow_binding=True,
    )
    assert out.disposition is DiscoveryDisposition.ANSWER
    assert "lifestyle.activity_level" in out.answered_keys
    assert "routines.exercise_schedule" in out.answered_keys


def test_q42b_bedtime_wake_binds_independently(db):
    user = _user(db, "q42b-sleep")
    grant_memory_consent(db, user.id, commit=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(
        db,
        user.id,
        now,
        format_relationship_discovery_marker(
            "routines.bedtime",
            invited=True,
            companion_key="routines.wake_time",
        ),
    )
    # Two clear times in one reply.
    msg = "I usually go to bed at 11pm and wake up at 7am"
    out = process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=msg,
        language="en",
        allow_binding=True,
    )
    assert out.disposition is DiscoveryDisposition.ANSWER
    assert set(out.answered_keys) == {"routines.bedtime", "routines.wake_time"}


def test_q42b_partial_answer_writes_one_and_excludes_same_turn(db):
    user = _user(db, "q42b-partial")
    grant_memory_consent(db, user.id, commit=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(
        db,
        user.id,
        now,
        format_relationship_discovery_marker(
            "work.occupation",
            invited=True,
            companion_key="work.work_schedule",
        ),
    )
    out = process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="I work as an engineer",
        language="en",
        allow_binding=True,
    )
    assert out.disposition is DiscoveryDisposition.ANSWER
    assert out.answered_keys == ("work.occupation",)
    assert "work_schedule" not in {
        f.key for f in list_facts(db, user.id, domain="work")
    }
    # Same-turn continuation excludes both marker keys — schedule not immediately reasked.
    d = select_next_best_question(
        snapshot=_snap(["preferences.interests"]),
        intent=_intent(),
        readiness=_ready(_intent()),
        language="en",
        message="I work as an engineer",
        force_invitation=True,
        exclude_keys=frozenset(out.marker_keys),
    )
    assert d is not None
    assert d.target_key != "work.work_schedule"
    assert d.companion_target_key != "work.work_schedule"


def test_q42b_known_companion_skipped():
    intent = _intent()
    d = select_next_best_question(
        snapshot=_snap(["preferences.interests", "work.work_schedule"]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="ask me something",
    )
    assert d is not None
    assert d.target_key == "work.occupation"
    assert d.companion_target_key is None


def test_q42b_conflicted_companion_not_selected_as_missing():
    conflicted = _item("work.work_schedule")
    # recreate with conflicted flag
    conflicted = ContextItem(
        canonical_key="work.work_schedule",
        section="profile",
        source=ContextSource.PROFILE,
        structured_value="x",
        display_text="work.work_schedule=x",
        provenance=ContextProvenance(
            source=ContextSource.PROFILE, owner_user_id=1, query_label="t"
        ),
        observed_at=None,
        freshness="unknown",
        sensitivity="medium",
        consent="legacy_scope",
        may_send_to_llm=False,
        sort_rank=SOURCE_SORT_RANK[ContextSource.PROFILE],
        active=True,
        conflicted=True,
    )
    snap = ContextSnapshot(
        request_id="q42b-c",
        owner_user_id=1,
        sections={
            "profile": ContextSection(
                name="profile", items=[_item("preferences.interests"), conflicted]
            )
        },
        items=[_item("preferences.interests"), conflicted],
        preferred_name=None,
        conflict_count=1,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("profile",),
    )
    d = select_next_best_question(
        snapshot=snap,
        intent=_intent(),
        readiness=_ready(_intent()),
        language="en",
        message="ask me something",
    )
    assert d is not None
    assert d.target_key == "work.occupation"
    assert d.companion_target_key is None


def test_q42b_decline_topic_be_heard_i4():
    assert (
        classify_discovery_reply("work.occupation", "skip", "en").disposition
        is DiscoveryDisposition.SKIP
    )
    assert (
        classify_discovery_reply(
            "work.occupation", "create a meal plan for me", "en"
        ).disposition
        is DiscoveryDisposition.UNRELATED
    )
    need = classify_interaction_need(
        message="I feel overwhelmed and just need to talk, ask me something",
        intent=_intent(),
        language="en",
    )
    assert need is InteractionNeed.BE_HEARD
    assert (
        select_next_best_question(
            snapshot=_snap(),
            intent=_intent(),
            readiness=ReadinessResult(
                status=ReadinessStatus.NEEDS_CLARIFICATION,
                intent_id=IntentId.GENERAL,
                request_kind=RequestKind.INFORMATIONAL,
                outcomes=(),
                missing_fact_keys=("x",),
                clarification=None,
            ),
            language="en",
            message="ask me something",
            force_invitation=True,
        )
        is None
    )


def test_q42b_fatigue_and_i2_reuse(db):
    user = _user(db, "q42b-fat")
    grant_memory_consent(db, user.id, commit=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for i in range(3):
        mark_asked(db, user.id, now - timedelta(hours=4), f"confirm_candidate:{i}")
    mark_asked(
        db, user.id, now - timedelta(minutes=11), f"{MARKER_PREFIX}preferences.interests"
    )
    assert check_can_ask(db, user.id, now)[0] is False
    assert check_can_ask_relationship_discovery(db, user.id, now, invited=False)[0]
    assert check_can_ask_relationship_discovery(db, user.id, now, invited=True)[0]

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
        message="brief",
        language="en",
        allow_binding=True,
        classification=classify_discovery_reply(
            "preferences.response_length", "brief", "en"
        ),
    )
    items = LifestyleContextAdapter().load(db, authenticated_user_id=user.id)
    assert "preferences.response_length" in {i.canonical_key for i in items}
    assert peek_relationship_discovery_targets(db, user.id) == ((), False)


def test_q42b_legacy_single_marker_still_binds(db):
    user = _user(db, "q42b-legacy")
    grant_memory_consent(db, user.id, commit=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(
        db,
        user.id,
        now,
        f"{INVITED_MARKER_PREFIX}preferences.response_length",
    )
    out = process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="detailed",
        language="en",
        allow_binding=True,
    )
    assert out.disposition is DiscoveryDisposition.ANSWER
    assert out.answered_keys == ("preferences.response_length",)
