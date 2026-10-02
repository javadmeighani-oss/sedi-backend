"""CR-04B — Contextual user understanding: work/time NBQ → I6 → I2 reuse."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.i6.relationship_discovery import (
    DiscoveryDisposition,
    SUPPORTED_TARGETS,
    classify_discovery_reply,
    peek_relationship_discovery_marker,
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
    STAGE_ORDER,
    IntentConfidenceBand,
    IntentId,
    IntentResult,
    PostGenerationSafetyResult,
    PostGenerationSafetyStatus,
    ReadinessResult,
    ReadinessStatus,
    ReasonCode,
    RequestKind,
    RiskAssessment,
    RiskDomain,
    RiskLevel,
    SafetyAction,
)
from backend.app.services.intelligence.next_best_question import select_next_best_question
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.app.services.knowledge.kc_fatigue_policy import mark_asked


# ---- helpers ----


def _intent(
    intent_id: IntentId, kind: RequestKind = RequestKind.INFORMATIONAL
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


def _item(key: str, *, active: bool = True, owner: int = 1) -> ContextItem:
    return ContextItem(
        canonical_key=key,
        section="lifestyle",
        source=ContextSource.LIFESTYLE,
        structured_value="x",
        display_text=f"{key}=x",
        provenance=ContextProvenance(
            source=ContextSource.LIFESTYLE, owner_user_id=owner, query_label="t"
        ),
        observed_at=None,
        freshness="unknown",
        sensitivity="medium",
        consent="legacy_scope",
        may_send_to_llm=True,
        sort_rank=SOURCE_SORT_RANK[ContextSource.LIFESTYLE],
        active=active,
        conflicted=False,
    )


def _snap(items=None, owner: int = 1) -> ContextSnapshot:
    items = list(items or [])
    return ContextSnapshot(
        request_id="cr04b",
        owner_user_id=owner,
        sections={"lifestyle": ContextSection(name="lifestyle", items=items)},
        items=items,
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(ReasonCode.CONTEXT_ASSEMBLED.value,),
        adapter_order=("lifestyle",),
    )


def _user(db, name: str, *, language: str = "en") -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language=language)
    db.add(row)
    db.flush()
    return row


def _set_marker(db, user_id: int, target_key: str) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(db, user_id, now, f"relationship_discovery:{target_key}")


def _active(db, user_id: int, domain: str, key: str):
    return (
        db.query(models.UserMemoryFact)
        .filter(
            models.UserMemoryFact.user_id == user_id,
            models.UserMemoryFact.domain == domain,
            models.UserMemoryFact.key == key,
            models.UserMemoryFact.fact_status == "active",
            models.UserMemoryFact.soft_invalidated_at.is_(None),
        )
        .first()
    )


def _fact_count(db, user_id: int) -> int:
    return db.query(models.UserMemoryFact).filter_by(user_id=user_id).count()


def _lifestyle_only(db, user_id: int):
    with patch.object(
        LifestyleContextAdapter, "_load_gate2_lifestyle", return_value=[]
    ):
        return LifestyleContextAdapter().load(
            db, authenticated_user_id=user_id, user_context_pack=None
        )


class StubAsm:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or _snap()

    def assemble(self, *a, **k):
        return self.snapshot

    def build_compatibility_projection(self, snapshot):
        return MagicMock(text="[CTX]", preferred_name=None, truncated=False)


def _orch(**kwargs):
    intent = kwargs.pop("intent", _intent(IntentId.SLEEP))
    readiness = kwargs.pop("readiness", _ready(intent))
    assess = kwargs.pop(
        "assess",
        lambda **k: RiskAssessment(
            registry_version="t",
            level=RiskLevel.NONE,
            action=SafetyAction.CONTINUE,
            domain=RiskDomain.NONE,
            rule_id="none",
            language="en",
        ),
    )
    validate = kwargs.pop(
        "validate",
        lambda **k: PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.SAFE,
            violation_code=None,
            message=k["text"],
        ),
    )
    calls = kwargs.pop("calls", {"n": 0})

    def gen(uid, msg, name=None, **kw):
        calls["n"] += 1
        return {"message": "Primary helpful answer.", "language": "en"}

    gen = kwargs.pop("gen", gen)
    db = kwargs.pop("db", MagicMock())
    return (
        IntelligenceOrchestrator(
            db=db,
            legacy_generator=gen,
            structured_mode=True,
            context_assembler=StubAsm(kwargs.pop("snapshot", None)),
            intent_resolver=lambda **k: intent,
            missing_information_engine=lambda **k: readiness,
            safety_assessor=assess,
            safety_validator=validate,
            safety_response_builder=lambda a: MagicMock(
                localized_message="SAFETY-FIXED"
            ),
        ),
        calls,
    )


# ---- 1) contextual NBQ relevance ----


@pytest.mark.parametrize(
    "message,language,intent_id",
    [
        ("My night shifts are making sleep difficult", "en", IntentId.GENERAL),
        ("شیفت کاری‌ام خوابم را به‌هم زده", "fa", IntentId.GENERAL),
        ("دوام العمل الليلي يؤثر على نومي", "ar", IntentId.SLEEP),
    ],
)
def test_cr04b_relevant_work_message_selects_work_schedule(
    message, language, intent_id
):
    intent = _intent(intent_id)
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language=language,
        message=message,
    )
    assert d is not None
    assert d.target_key == "work.work_schedule"
    assert d.sensitivity == "medium"


@pytest.mark.parametrize(
    "message,language,intent_id",
    [
        ("I don't have enough time to exercise", "en", IntentId.ACTIVITY),
        ("برای ورزش وقت کم دارم", "fa", IntentId.ACTIVITY),
        ("ليس لدي وقت كاف للتمرين", "ar", IntentId.GENERAL),
    ],
)
def test_cr04b_relevant_time_pressure_selects_time_constraints(
    message, language, intent_id
):
    intent = _intent(intent_id)
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language=language,
        message=message,
    )
    assert d is not None
    assert d.target_key == "barriers.time_constraints"
    assert d.sensitivity == "high"


@pytest.mark.parametrize(
    "message,intent_id,expected_legacy",
    [
        ("Tell me about sleep", IntentId.GENERAL, "preferences.response_length"),
        ("Hello", IntentId.GENERAL, "preferences.response_length"),
        ("Tell me about sleep", IntentId.SLEEP, "routines.bedtime"),
        ("Hello", IntentId.SLEEP, "routines.bedtime"),
        ("", IntentId.SLEEP, "routines.bedtime"),
    ],
)
def test_cr04b_irrelevant_messages_keep_legacy_nbq(
    message, intent_id, expected_legacy
):
    intent = _intent(intent_id)
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message=message,
    )
    assert d is not None
    assert d.target_key == expected_legacy
    assert d.target_key not in (
        "work.work_schedule",
        "barriers.time_constraints",
    )


def test_cr04b_existing_sleep_nutrition_activity_nbq_unchanged_without_context():
    sleep = _intent(IntentId.SLEEP)
    assert (
        select_next_best_question(
            snapshot=_snap([]), intent=sleep, readiness=_ready(sleep), language="en"
        ).target_key
        == "routines.bedtime"
    )
    nutrition = _intent(IntentId.NUTRITION)
    assert (
        select_next_best_question(
            snapshot=_snap([]),
            intent=nutrition,
            readiness=_ready(nutrition),
            language="en",
        ).target_key
        == "lifestyle.food_habits"
    )
    activity = _intent(IntentId.ACTIVITY)
    assert (
        select_next_best_question(
            snapshot=_snap([]),
            intent=activity,
            readiness=_ready(activity),
            language="en",
        ).target_key
        == "lifestyle.activity_level"
    )


def test_cr04b_contextual_outranks_legacy_only_when_relevant():
    intent = _intent(IntentId.SLEEP)
    with_ctx = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="My night shifts are making sleep difficult",
    )
    without = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="How is my sleep quality lately?",
    )
    assert with_ctx.target_key == "work.work_schedule"
    assert without.target_key == "routines.bedtime"


def test_cr04b_max_one_nbq_directive():
    intent = _intent(IntentId.GENERAL)
    # Message that could theoretically match both cue families if poorly gated.
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="My night shifts leave me with not enough time",
    )
    assert d is not None
    assert d.target_key == "work.work_schedule"  # priority 1 wins over barriers


# ---- 2) orchestrator gates ----


def test_cr04b_orchestrator_passes_message_for_contextual_nbq(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    marked = {"key": None}

    def _mark(db, *, user_id, target_key):
        marked["key"] = target_key

    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._mark_relationship_discovery_asked",
        _mark,
    )
    orch, calls = _orch(intent=_intent(IntentId.GENERAL))
    result = orch.process(
        authenticated_user_id=1,
        message="My night shifts are making sleep difficult",
        language="en",
    )
    assert calls["n"] == 1
    assert result.discovery_target_key == "work.work_schedule"
    assert marked["key"] == "work.work_schedule"
    parts = result.message.split("\n\n")
    assert len(parts) == 2


def test_cr04b_be_heard_suppresses_visible_nbq(monkeypatch):
    from backend.app.services.intelligence.psychological_interaction import (
        InteractionNeed,
    )

    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "backend.app.services.intelligence.psychological_interaction.classify_interaction_need",
        lambda **k: InteractionNeed.BE_HEARD,
    )
    orch, _ = _orch(intent=_intent(IntentId.GENERAL))
    result = orch.process(
        authenticated_user_id=1,
        message="My night shifts are making sleep difficult",
        language="en",
    )
    assert result.discovery_target_key == "work.work_schedule"
    assert "\n\n" not in result.message


@pytest.mark.parametrize(
    "iid",
    [
        IntentId.SYMPTOM,
        IntentId.MEDICATION,
        IntentId.VITALS,
        IntentId.REMINDER,
        IntentId.NOTIFICATION_FOLLOW_UP,
    ],
)
def test_cr04b_protected_intents_no_contextual_nbq(iid, monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.intelligence.orchestrator._fatigue_permits_discovery",
        lambda *a, **k: True,
    )
    intent = _intent(iid)
    # Pure selector
    assert (
        select_next_best_question(
            snapshot=_snap([]),
            intent=intent,
            readiness=_ready(intent),
            language="en",
            message="My night shifts are making sleep difficult",
        )
        is None
    )
    orch, _ = _orch(intent=intent)
    result = orch.process(
        authenticated_user_id=1,
        message="My night shifts are making sleep difficult",
        language="en",
    )
    assert result.discovery_target_key is None


def test_cr04b_stage_order_unchanged():
    assert list(STAGE_ORDER) == [
        "initialize_request",
        "resolve_safe_identity",
        "resolve_locale_context",
        "resolve_conversation_origin",
        "assess_safety_risk",
        "assemble_authorized_context",
        "resolve_intent",
        "evaluate_information_readiness",
        "build_clarification_response",
        "build_safety_response",
        "prepare_compatibility_generation",
        "generate_with_legacy_brain",
        "validate_generation_result",
        "complete",
    ]


# ---- 3) I6 relationship binding ----


def test_cr04b_supported_targets_include_contextual_keys():
    assert "work.work_schedule" in SUPPORTED_TARGETS
    assert "barriers.time_constraints" in SUPPORTED_TARGETS


@pytest.mark.parametrize(
    "message,language",
    [
        ("9 to 5 weekdays", "en"),
        ("night shifts", "en"),
        ("شیفت شب", "fa"),
        ("دوام ليلي", "ar"),
    ],
)
def test_cr04b_work_schedule_direct_answer_writes_one_fact(db, message, language):
    user = _user(db, f"work-{hash(message) % 100000}", language=language)
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "work.work_schedule")
    clf = classify_discovery_reply("work.work_schedule", message, language)
    assert clf.disposition is DiscoveryDisposition.ANSWER
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
        classification=clf,
    )
    assert _fact_count(db, user.id) == 1
    row = _active(db, user.id, "work", "work_schedule")
    assert row is not None
    assert row.source == "relationship_discovery"
    assert peek_relationship_discovery_marker(db, user.id) is None


@pytest.mark.parametrize(
    "message,language",
    [
        ("I only have 20 minutes after work", "en"),
        ("بعد از کار وقت خیلی کمی دارم", "fa"),
        ("عندي نصف ساعة فقط", "ar"),
    ],
)
def test_cr04b_time_constraints_direct_answer_writes_one_fact(db, message, language):
    user = _user(db, f"time-{hash(message) % 100000}", language=language)
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, "barriers.time_constraints")
    clf = classify_discovery_reply("barriers.time_constraints", message, language)
    assert clf.disposition is DiscoveryDisposition.ANSWER
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
        classification=clf,
    )
    assert _fact_count(db, user.id) == 1
    assert _active(db, user.id, "barriers", "time_constraints") is not None
    assert peek_relationship_discovery_marker(db, user.id) is None


@pytest.mark.parametrize(
    "target,message,language,expected",
    [
        ("work.work_schedule", "yes", "en", DiscoveryDisposition.AMBIGUOUS),
        ("barriers.time_constraints", "بله", "fa", DiscoveryDisposition.AMBIGUOUS),
        ("work.work_schedule", "later", "en", DiscoveryDisposition.SKIP),
        (
            "barriers.time_constraints",
            "How much should I exercise?",
            "en",
            DiscoveryDisposition.UNRELATED,
        ),
        (
            "work.work_schedule",
            "create a meal plan for me",
            "en",
            DiscoveryDisposition.UNRELATED,
        ),
    ],
)
def test_cr04b_decline_ambiguous_unrelated_zero_fact(
    db, target, message, language, expected
):
    user = _user(db, f"neg-{hash((target, message)) % 100000}", language=language)
    grant_memory_consent(db, user.id, commit=True)
    _set_marker(db, user.id, target)
    clf = classify_discovery_reply(target, message, language)
    assert clf.disposition is expected
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message=message,
        language=language,
        allow_binding=True,
        classification=clf,
    )
    assert _fact_count(db, user.id) == 0
    assert peek_relationship_discovery_marker(db, user.id) is None


def test_cr04b_conflict_no_silent_overwrite(db):
    user = _user(db, "work-conflict")
    grant_memory_consent(db, user.id, commit=True)
    old = write_fact(
        db,
        user.id,
        "work",
        "work_schedule",
        "day shift",
        provenance_class="USER_STATED",
        source="manual",
        commit=True,
    )
    _set_marker(db, user.id, "work.work_schedule")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="night shifts",
        language="en",
        allow_binding=True,
    )
    still = _active(db, user.id, "work", "work_schedule")
    assert still is not None
    assert still.id == old.id
    assert json.loads(still.value_json) == "day shift"
    cands = db.query(models.KcFactCandidate).filter_by(user_id=user.id).all()
    assert len(cands) == 1
    meta = json.loads(cands[0].metadata_json or "{}")
    assert meta.get("needs_confirmation") is True


# ---- 4) I2 later-turn reuse + isolation ----


def test_cr04b_i2_later_turn_reuses_work_and_time_facts(db):
    user = _user(db, "i2-reuse")
    other = _user(db, "i2-other")
    grant_memory_consent(db, user.id, commit=True)
    grant_memory_consent(db, other.id, commit=True)

    _set_marker(db, user.id, "work.work_schedule")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="night shifts",
        language="en",
        allow_binding=True,
    )
    _set_marker(db, user.id, "barriers.time_constraints")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="I only have 20 minutes after work",
        language="en",
        allow_binding=True,
    )

    items = _lifestyle_only(db, user.id)
    keys = {i.canonical_key for i in items}
    assert "work.work_schedule" in keys
    assert "barriers.time_constraints" in keys
    assert all(i.provenance.owner_user_id == user.id for i in items)

    other_items = _lifestyle_only(db, other.id)
    other_keys = {i.canonical_key for i in other_items}
    assert "work.work_schedule" not in other_keys
    assert "barriers.time_constraints" not in other_keys

    # NBQ must not re-ask once fact is active in snapshot.
    sleep = _intent(IntentId.SLEEP)
    snap = ContextSnapshot(
        request_id="later",
        owner_user_id=user.id,
        sections={"lifestyle": ContextSection(name="lifestyle", items=list(items))},
        items=list(items),
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("lifestyle",),
    )
    d = select_next_best_question(
        snapshot=snap,
        intent=sleep,
        readiness=_ready(sleep),
        language="en",
        message="My night shifts are making sleep difficult",
    )
    assert d is None or d.target_key != "work.work_schedule"


def test_cr04b_cross_user_isolation_on_bind(db):
    a = _user(db, "iso-a")
    b = _user(db, "iso-b")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    _set_marker(db, a.id, "work.work_schedule")
    process_relationship_discovery_answer(
        db,
        user_id=a.id,
        message="9 to 5 weekdays",
        language="en",
        allow_binding=True,
    )
    assert _active(db, a.id, "work", "work_schedule") is not None
    assert _active(db, b.id, "work", "work_schedule") is None
    assert _fact_count(db, b.id) == 0


# ---- 5) CR-04A corpus remains green ----


def test_cr04b_cr04a_corpus_still_green():
    from backend.tests.test_cr04a_multilingual_semantic_quality import (
        test_cr04a_corpus_schema,
        test_cr04a_semantic_contract,
        _load_corpus,
        _cases,
    )

    corpus = _load_corpus()
    test_cr04a_corpus_schema(corpus)
    for case in _cases():
        test_cr04a_semantic_contract(case)
