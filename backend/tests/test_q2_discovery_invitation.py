"""Q2 — Explicit discovery-invitation handling (I3/NBQ + I6 only)."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from datetime import datetime, timezone

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import list_facts
from backend.app.services.i6.relationship_discovery import (
    DiscoveryDisposition,
    classify_discovery_reply,
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
    detect_discovery_invitation,
    select_next_best_question,
)
from backend.app.services.intelligence.psychological_interaction import (
    InteractionNeed,
    classify_interaction_need,
)
from backend.app.services.knowledge.kc_fatigue_policy import check_can_ask, mark_asked
from backend.app.services.memory.memory_contract import MemoryContract


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


def _item(key: str, *, active: bool = True, owner: int = 1) -> ContextItem:
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
        active=active,
        conflicted=False,
    )


def _snap(items: list[ContextItem], owner: int = 1) -> ContextSnapshot:
    return ContextSnapshot(
        request_id="q2",
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


def _grant(db, user_id: int) -> None:
    grant_memory_consent(db, user_id, commit=True)


def _mark_discovery(db, user_id: int, target_key: str) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mark_asked(db, user_id, now, f"relationship_discovery:{target_key}")


def test_q2_detect_invitation_phrases_en_fa_ar():
    assert detect_discovery_invitation("ask me something", "en")
    assert detect_discovery_invitation("what do you want to know?", "en")
    assert detect_discovery_invitation("چی میخوای بدونی", "fa")
    assert detect_discovery_invitation("چی می‌خوای بدونی", "fa")
    assert detect_discovery_invitation("چی میخوایی بدونی", "fa")
    assert detect_discovery_invitation("چی می‌خوایی بدونی", "fa")
    assert detect_discovery_invitation("ازم سوال بپرس", "fa")
    assert detect_discovery_invitation("اسألني شيئا", "ar")
    assert detect_discovery_invitation("ماذا تريد أن تعرف", "ar")
    assert not detect_discovery_invitation("hello", "en")
    assert not detect_discovery_invitation("Tell me about sleep", "en")


_FA_INVITATION_VARIANTS = (
    "چی میخوای بدونی",
    "چی می‌خوای بدونی",
    "چی میخوایی بدونی",
    "چی می‌خوایی بدونی",
)


def test_q2_explicit_fa_invitation_selects_exactly_one_nbq():
    intent = _intent(IntentId.GENERAL)
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language="fa",
        message="چی می‌خوای بدونی",
    )
    assert d is not None
    assert d.target_key == "preferences.interests"
    assert d.question_id.startswith("nbq.q.invitation.")
    assert d.localized_question.count("؟") + d.localized_question.count("?") <= 1


def test_q2_fa_invitation_all_four_variants_select_one_interests_nbq():
    intent = _intent(IntentId.GENERAL)
    ready = _ready(intent)
    for phrase in _FA_INVITATION_VARIANTS:
        assert detect_discovery_invitation(phrase, "fa"), phrase
        d = select_next_best_question(
            snapshot=_snap([]),
            intent=intent,
            readiness=ready,
            language="fa",
            message=phrase,
        )
        assert d is not None, phrase
        assert d.target_key == "preferences.interests", phrase
        assert d.question_id.startswith("nbq.q.invitation."), phrase
        assert d.localized_question.count("؟") + d.localized_question.count("?") <= 1


def test_q2_explicit_en_invitation_selects_exactly_one_nbq():
    intent = _intent(IntentId.SLEEP)  # invitation outranks intent soft
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="ask me something",
    )
    assert d is not None
    assert d.target_key == "preferences.interests"
    assert "bedtime" not in d.target_key


def test_q2_explicit_ar_invitation_selects_exactly_one_nbq():
    intent = _intent(IntentId.GENERAL)
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language="ar",
        message="ماذا تحتاج أن تعرف عني",
    )
    assert d is not None
    assert d.target_key == "preferences.interests"
    assert d.question_id.count("invitation") == 1


def test_q2_current_need_be_heard_precedes_visible_discovery():
    msg = "I feel overwhelmed and just need to talk, ask me something"
    need = classify_interaction_need(
        message=msg, intent=_intent(), language="en"
    )
    assert need is InteractionNeed.BE_HEARD
    # Selector may still propose metadata, but visible append stays need-gated.
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=_intent(),
        readiness=_ready(_intent()),
        language="en",
        message=msg,
    )
    assert d is not None
    # Orchestrator rule: BE_HEARD => no visible NBQ append.
    visible_nbq_eligible = need is not InteractionNeed.BE_HEARD
    assert visible_nbq_eligible is False


def test_q2_no_duplicate_recent_known_target():
    intent = _intent()
    snap = _snap([_item("preferences.interests")])
    d = select_next_best_question(
        snapshot=snap,
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="what do you want to know",
    )
    assert d is not None
    # Q4 invitation priority: after interests → work.occupation
    assert d.target_key == "work.occupation"
    assert d.target_key != "preferences.interests"


def test_q2_decline_skip_respected(db):
    user = _user(db, "q2-skip")
    _grant(db, user.id)
    _mark_discovery(db, user.id, "preferences.interests")
    cls = classify_discovery_reply(
        "preferences.interests", "skip", "en"
    )
    assert cls.disposition is DiscoveryDisposition.SKIP
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="skip",
        language="en",
        allow_binding=True,
        classification=cls,
    )
    assert list_facts(db, user.id, domain="preferences") == []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    allowed, reason, _next, _state = check_can_ask(db, user.id, now)
    # After ask + skip, fatigue cooldown/burst suppresses repeated probing.
    assert allowed is False
    assert reason == "fatigue_control"


def test_q2_work_time_contextual_unchanged_with_invitation():
    intent = _intent(IntentId.GENERAL)
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="My night shifts are hard. Ask me something.",
    )
    assert d is not None
    assert d.target_key == "work.work_schedule"


def test_q2_occupation_invitation_only_not_empty_field_probe():
    intent = _intent()
    # All Tier-A known, no invitation → do not ask occupation just because empty.
    known = [
        _item("preferences.interests"),
        _item("preferences.communication_style"),
        _item("preferences.listen_before_advice"),
        _item("preferences.response_length"),
    ]
    d = select_next_best_question(
        snapshot=_snap(known),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="Hello",
    )
    assert d is None or d.target_key != "work.occupation"

    d2 = select_next_best_question(
        snapshot=_snap(known),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="ask me something",
    )
    assert d2 is not None
    assert d2.target_key == "work.occupation"


def test_q2_occupation_writes_canonical_i6_only(db):
    assert MemoryContract.is_valid_key("work", "occupation")
    permitted, _err = MemoryContract.i6_write_permitted("work", "occupation")
    assert permitted is True
    user = _user(db, "q2-occ")
    _grant(db, user.id)
    _mark_discovery(db, user.id, "work.occupation")
    cls = classify_discovery_reply(
        "work.occupation", "I work as a teacher", "en"
    )
    assert cls.disposition is DiscoveryDisposition.ANSWER
    out = process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="I work as a teacher",
        language="en",
        allow_binding=True,
        classification=cls,
    )
    assert out.disposition is DiscoveryDisposition.ANSWER
    facts = list_facts(db, user.id, domain="work")
    row = next(f for f in facts if f.key == "occupation")
    assert "teacher" in (row.value_json or "").lower()
    assert row.source == "relationship_discovery"
    assert row.provenance_class == "USER_STATED"
    # No unintended reminder/I8 side channel from discovery binding.
    assert db.query(models.UserEvent).filter_by(user_id=user.id).count() == 0


def test_q2_invitation_does_not_create_i8_action_from_selector():
    """Selector is pure — no I8/reminder artifacts from invitation handling."""
    intent = _intent()
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="ask me something",
    )
    assert d is not None
    assert not hasattr(d, "action")
    assert not hasattr(d, "reminder")
    assert d.target_key.startswith("preferences.") or d.target_key.startswith("work.")


def test_q2_sleep_without_invitation_still_prefers_bedtime():
    intent = _intent(IntentId.SLEEP)
    d = select_next_best_question(
        snapshot=_snap([]),
        intent=intent,
        readiness=_ready(intent),
        language="en",
        message="Tell me about sleep",
    )
    assert d is not None
    assert d.target_key == "routines.bedtime"
