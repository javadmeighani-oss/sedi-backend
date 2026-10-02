"""CR-04F.1 — Progressive user understanding: coverage + Tier-A NBQ + I6 binding."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import json

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import list_facts, write_fact
from backend.app.services.i6.relationship_discovery import (
    DiscoveryDisposition,
    SUPPORTED_TARGETS,
    classify_discovery_reply,
    normalize_discovery_value,
    process_relationship_discovery_answer,
)
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
    _TEMPLATES,
    select_next_best_question,
)
from backend.app.services.intelligence.user_understanding_coverage import (
    TIER_A_GENERAL_PRIORITY,
    TIER_C_NEVER_MISSING_DRIVEN,
    CoverageState,
    coverage_state_for_key,
    first_missing_tier_a,
)
from backend.app.services.knowledge.kc_fatigue_policy import mark_asked


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


def _item(
    key: str,
    *,
    active: bool = True,
    conflicted: bool = False,
    consent: str = "legacy_scope",
    freshness: str = "unknown",
    owner: int = 1,
) -> ContextItem:
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
        freshness=freshness,  # type: ignore[arg-type]
        sensitivity="medium",
        consent=consent,  # type: ignore[arg-type]
        may_send_to_llm=False,
        sort_rank=SOURCE_SORT_RANK[ContextSource.PROFILE],
        active=active,
        conflicted=conflicted,
    )


def _snap(items: list[ContextItem], owner: int = 1) -> ContextSnapshot:
    return ContextSnapshot(
        request_id="cr04f1",
        owner_user_id=owner,
        sections={"profile": ContextSection(name="profile", items=list(items))},
        items=list(items),
        preferred_name=None,
        conflict_count=sum(1 for i in items if i.conflicted),
        truncated_count=0,
        reason_codes=(),
        adapter_order=("profile",),
    )


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _grant(db, user_id: int) -> None:
    grant_memory_consent(db, user_id, commit=True)


def _mark_discovery(db, user_id: int, target_key: str) -> None:
    from datetime import datetime, timezone

    mark_asked(
        db,
        user_id,
        datetime.now(timezone.utc),
        f"relationship_discovery:{target_key}",
    )


# ---- coverage ----


def test_cr04f1_coverage_states():
    snap = _snap([])
    assert (
        coverage_state_for_key(snap, "preferences.interests") is CoverageState.MISSING
    )

    snap = _snap([_item("preferences.interests")])
    assert coverage_state_for_key(snap, "preferences.interests") is CoverageState.KNOWN

    snap = _snap([_item("preferences.interests", consent="denied")])
    assert coverage_state_for_key(snap, "preferences.interests") is CoverageState.DENIED

    snap = _snap([_item("preferences.interests", conflicted=True)])
    assert (
        coverage_state_for_key(snap, "preferences.interests")
        is CoverageState.CONFLICTED
    )

    snap = _snap([_item("preferences.interests", freshness="stale")])
    assert coverage_state_for_key(snap, "preferences.interests") is CoverageState.STALE

    snap = _snap([])
    assert (
        coverage_state_for_key(snap, "preferences.timezone")
        is CoverageState.NOT_APPLICABLE
    )


def test_cr04f1_general_selects_tier_a_progressively():
    intent = _intent(IntentId.GENERAL)
    ready = _ready(intent)
    d1 = select_next_best_question(
        snapshot=_snap([]), intent=intent, readiness=ready, language="en"
    )
    assert d1 is not None
    assert d1.target_key == "preferences.interests"

    known = _snap([_item("preferences.interests")])
    d2 = select_next_best_question(
        snapshot=known, intent=intent, readiness=ready, language="en"
    )
    assert d2 is not None
    assert d2.target_key == "preferences.communication_style"

    more = _snap(
        [
            _item("preferences.interests"),
            _item("preferences.communication_style"),
        ]
    )
    d3 = select_next_best_question(
        snapshot=more, intent=intent, readiness=ready, language="en"
    )
    assert d3 is not None
    assert d3.target_key == "preferences.listen_before_advice"

    all_but_len = _snap(
        [
            _item("preferences.interests"),
            _item("preferences.communication_style"),
            _item("preferences.listen_before_advice"),
        ]
    )
    d4 = select_next_best_question(
        snapshot=all_but_len, intent=intent, readiness=ready, language="en"
    )
    assert d4 is not None
    assert d4.target_key == "preferences.response_length"

    assert TIER_A_GENERAL_PRIORITY[0] == "preferences.interests"
    assert first_missing_tier_a(known) == "preferences.communication_style"


def test_cr04f1_known_denied_conflicted_stale_skipped():
    intent = _intent(IntentId.GENERAL)
    ready = _ready(intent)
    for item in (
        _item("preferences.interests"),
        _item("preferences.interests", consent="denied"),
        _item("preferences.interests", conflicted=True),
        _item("preferences.interests", freshness="stale"),
    ):
        d = select_next_best_question(
            snapshot=_snap([item]), intent=intent, readiness=ready, language="en"
        )
        assert d is not None
        assert d.target_key != "preferences.interests"


def test_cr04f1_at_most_one_question():
    intent = _intent(IntentId.GENERAL)
    d = select_next_best_question(
        snapshot=_snap([]), intent=intent, readiness=_ready(intent), language="en"
    )
    assert d is not None
    assert isinstance(d.target_key, str)
    assert d.target_key.count(".") == 1


def test_cr04f1_contextual_beats_tier_a():
    intent = _intent(IntentId.GENERAL)
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="I work night shifts and my schedule is hard",
    )
    assert d is not None
    assert d.target_key == "work.work_schedule"


def test_cr04f1_suppressed_intents_ask_zero():
    for iid in (
        IntentId.SYMPTOM,
        IntentId.MEDICATION,
        IntentId.VITALS,
        IntentId.REMINDER,
        IntentId.NOTIFICATION_FOLLOW_UP,
    ):
        intent = _intent(iid)
        d = select_next_best_question(
            snapshot=_snap([]), intent=intent, readiness=_ready(intent), language="en"
        )
        assert d is None


def test_cr04f1_tier_c_never_missing_driven():
    intent = _intent(IntentId.GENERAL)
    d = select_next_best_question(
        snapshot=_snap([]), intent=intent, readiness=_ready(intent), language="en"
    )
    assert d is not None
    assert d.target_key not in TIER_C_NEVER_MISSING_DRIVEN
    assert not d.target_key.startswith("social.")
    assert not d.target_key.startswith("values.")
    assert d.target_key != "barriers.financial_constraints"
    assert d.target_key != "barriers.motivation_barriers"


def test_cr04f1_en_fa_ar_templates():
    for tid in (
        "nbq.general.interests.v1",
        "nbq.general.communication_style.v1",
        "nbq.general.listen_before_advice.v1",
        "nbq.general.response_length.v1",
    ):
        block = _TEMPLATES[tid]
        assert block["en"].strip()
        assert block["fa"].strip()
        assert block["ar"].strip()
    intent = _intent(IntentId.GENERAL)
    ready = _ready(intent)
    for lang in ("en", "fa", "ar"):
        d = select_next_best_question(
            snapshot=_snap([]), intent=intent, readiness=ready, language=lang
        )
        assert d is not None
        assert d.localized_question.strip()


def test_cr04f1_sleep_intent_still_prefers_bedtime():
    """Tier-A is GENERAL-only; sleep soft path unchanged."""
    intent = _intent(IntentId.SLEEP)
    d = select_next_best_question(
        snapshot=_snap([]), intent=intent, readiness=_ready(intent), language="en"
    )
    assert d is not None
    assert d.target_key == "routines.bedtime"


# ---- answer binding ----


def test_cr04f1_interests_write(db):
    user = _user(db, "f1-int")
    _grant(db, user.id)
    _mark_discovery(db, user.id, "preferences.interests")
    cls = classify_discovery_reply(
        "preferences.interests",
        "Sleep quality and daily habits matter most to me",
        "en",
    )
    assert cls.disposition is DiscoveryDisposition.ANSWER
    out = process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="Sleep quality and daily habits matter most to me",
        language="en",
        allow_binding=True,
        classification=cls,
    )
    assert out.disposition is DiscoveryDisposition.ANSWER
    facts = list_facts(db, user.id, domain="preferences")
    assert any(f.key == "interests" for f in facts)
    row = next(f for f in facts if f.key == "interests")
    assert "sleep" in (row.value_json or "").lower()
    assert row.provenance_class == "USER_STATED"
    assert row.source == "relationship_discovery"


def test_cr04f1_communication_style_write(db):
    user = _user(db, "f1-style")
    _grant(db, user.id)
    _mark_discovery(db, user.id, "preferences.communication_style")
    cls = classify_discovery_reply(
        "preferences.communication_style", "I prefer a supportive style", "en"
    )
    assert cls.normalized_value == "supportive"
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="I prefer a supportive style",
        language="en",
        allow_binding=True,
        classification=cls,
    )
    facts = list_facts(db, user.id, domain="preferences")
    row = next(f for f in facts if f.key == "communication_style")
    assert json.loads(row.value_json) == "supportive"


def test_cr04f1_listen_before_advice_boolean_write(db):
    user = _user(db, "f1-listen")
    _grant(db, user.id)
    _mark_discovery(db, user.id, "preferences.listen_before_advice")
    cls = classify_discovery_reply(
        "preferences.listen_before_advice",
        "Please listen first before suggesting solutions",
        "en",
    )
    assert cls.disposition is DiscoveryDisposition.ANSWER
    assert cls.normalized_value is True
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="Please listen first before suggesting solutions",
        language="en",
        allow_binding=True,
        classification=cls,
    )
    facts = list_facts(db, user.id, domain="preferences")
    row = next(f for f in facts if f.key == "listen_before_advice")
    assert json.loads(row.value_json) is True


def test_cr04f1_listen_before_advice_false_write(db):
    user = _user(db, "f1-advice")
    _grant(db, user.id)
    _mark_discovery(db, user.id, "preferences.listen_before_advice")
    cls = classify_discovery_reply(
        "preferences.listen_before_advice", "Please give advice first", "en"
    )
    assert cls.normalized_value is False
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="Please give advice first",
        language="en",
        allow_binding=True,
        classification=cls,
    )
    row = next(
        f
        for f in list_facts(db, user.id, domain="preferences")
        if f.key == "listen_before_advice"
    )
    assert json.loads(row.value_json) is False


def test_cr04f1_ambiguous_boolean_zero_write(db):
    user = _user(db, "f1-amb")
    _grant(db, user.id)
    _mark_discovery(db, user.id, "preferences.listen_before_advice")
    before = len(list_facts(db, user.id))
    for msg in ("yes", "no", "ok", "unsure"):
        cls = classify_discovery_reply(
            "preferences.listen_before_advice", msg, "en"
        )
        assert cls.disposition is DiscoveryDisposition.AMBIGUOUS
        assert normalize_discovery_value(
            "preferences.listen_before_advice", msg
        ) is None
        process_relationship_discovery_answer(
            db,
            user_id=user.id,
            message=msg,
            language="en",
            allow_binding=True,
            classification=cls,
        )
    assert len(list_facts(db, user.id)) == before


def test_cr04f1_skip_reject_classify():
    cls = classify_discovery_reply("preferences.interests", "skip", "en")
    assert cls.disposition is DiscoveryDisposition.SKIP


def test_cr04f1_supported_targets_include_tier_a():
    assert "preferences.interests" in SUPPORTED_TARGETS
    assert "preferences.communication_style" in SUPPORTED_TARGETS
    assert "preferences.listen_before_advice" in SUPPORTED_TARGETS
    assert "social.household_context" not in SUPPORTED_TARGETS


def test_cr04f1_user_isolation(db):
    a = _user(db, "f1-a")
    b = _user(db, "f1-b")
    _grant(db, a.id)
    _grant(db, b.id)
    _mark_discovery(db, a.id, "preferences.interests")
    cls = classify_discovery_reply(
        "preferences.interests", "Nutrition and cooking routines", "en"
    )
    process_relationship_discovery_answer(
        db,
        user_id=a.id,
        message="Nutrition and cooking routines",
        language="en",
        allow_binding=True,
        classification=cls,
    )
    assert any(f.key == "interests" for f in list_facts(db, a.id))
    assert not any(f.key == "interests" for f in list_facts(db, b.id))


def test_cr04f1_no_silent_overwrite(db):
    user = _user(db, "f1-ow")
    _grant(db, user.id)
    write_fact(
        db,
        user.id,
        "preferences",
        "interests",
        "sleep",
        provenance_class="USER_STATED",
        source="manual",
        commit=True,
    )
    _mark_discovery(db, user.id, "preferences.interests")
    cls = classify_discovery_reply(
        "preferences.interests", "Nutrition tracking and meal planning", "en"
    )
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="Nutrition tracking and meal planning",
        language="en",
        allow_binding=True,
        classification=cls,
    )
    active = [
        f
        for f in list_facts(db, user.id, domain="preferences")
        if f.key == "interests"
    ]
    # Existing differing value stages conflict candidate; active value unchanged.
    assert len(active) == 1
    assert "sleep" in (active[0].value_json or "").lower()
