"""Q4 audit — updated expectations after Q4.2A foundation (still no max-2)."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import inspect
from datetime import datetime, timedelta, timezone

from backend.app.services.i6.relationship_discovery import (
    INVITED_MARKER_PREFIX,
    MARKER_PREFIX,
    SUPPORTED_TARGETS,
    DiscoveryDisposition,
    classify_discovery_reply,
    format_relationship_discovery_marker,
    parse_relationship_discovery_marker,
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
    _DISCOVERY_INVITATION_CUES,
    _INVITATION_SOFT_PRIORITY,
    detect_discovery_invitation,
    select_next_best_question,
)
from backend.app.services.intelligence.context_types import (
    ContextItem,
    ContextProvenance,
    ContextSection,
    ContextSnapshot,
    ContextSource,
    SOURCE_SORT_RANK,
)
from backend.app.services.knowledge import kc_fatigue_policy as fatigue
from backend.app.services.knowledge.kc_fatigue_policy import (
    check_can_ask,
    check_can_ask_relationship_discovery,
    mark_asked,
)


_PHYSICAL_FA_INVITATION = "خوب نمی‌خوای اطلاعات بیشتری داشته باشی؟"

_Q4_SAFE_EXISTING_TARGETS = (
    "preferences.interests",
    "work.occupation",
    "work.work_schedule",
    "lifestyle.activity_level",
    "lifestyle.food_habits",
    "lifestyle.sleep_quality",
    "routines.exercise_schedule",
    "routines.bedtime",
    "routines.wake_time",
    "preferences.communication_style",
    "preferences.listen_before_advice",
    "preferences.response_length",
)


def _intent() -> IntentResult:
    return IntentResult(
        registry_version="t",
        intent_id=IntentId.GENERAL,
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


def _snap(items: list[ContextItem] | None = None) -> ContextSnapshot:
    items = list(items or [])
    return ContextSnapshot(
        request_id="q4-audit",
        owner_user_id=1,
        sections={"profile": ContextSection(name="profile", items=items)},
        items=items,
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("profile",),
    )


def test_q4_physical_fa_invitation_now_detected():
    assert detect_discovery_invitation(_PHYSICAL_FA_INVITATION, "fa") is True
    d = select_next_best_question(
        snapshot=_snap(),
        intent=_intent(),
        readiness=_ready(_intent()),
        language="fa",
        message=_PHYSICAL_FA_INVITATION,
    )
    assert d is not None
    assert d.question_id.startswith("nbq.q.invitation.")


def test_q4_invitation_soft_priority_covers_safe_set():
    assert tuple(_INVITATION_SOFT_PRIORITY) == _Q4_SAFE_EXISTING_TARGETS
    for key in _Q4_SAFE_EXISTING_TARGETS:
        assert key in SUPPORTED_TARGETS
    assert "barriers.time_constraints" not in _INVITATION_SOFT_PRIORITY


def test_q4_fatigue_defaults_and_rd_seam(monkeypatch):
    monkeypatch.delenv("KC_DAILY_QUESTION_CAP", raising=False)
    monkeypatch.delenv("KC_COOLDOWN_MINUTES", raising=False)
    monkeypatch.delenv("KC_BURST_GUARD_MINUTES", raising=False)
    assert fatigue._get_daily_cap() == 3
    assert fatigue._get_cooldown_minutes() == 90
    assert fatigue._get_burst_guard_minutes() == 10
    assert fatigue._RD_NORMAL_SPACING_MINUTES == 10


def test_q4_invited_marker_encoding():
    assert MARKER_PREFIX == "relationship_discovery:"
    assert INVITED_MARKER_PREFIX == "relationship_discovery_invited:"
    k, inv = parse_relationship_discovery_marker(
        format_relationship_discovery_marker("work.occupation", invited=True)
    )
    assert k == "work.occupation"
    assert inv is True


def test_q4_generic_kc_unchanged_when_rd_allows(db):
    from backend.app import models

    user = models.User(name="q4a", secret_key="sk-q4a", preferred_language="en")
    db.add(user)
    db.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for i in range(3):
        mark_asked(db, user.id, now - timedelta(hours=3), f"confirm_candidate:{i}")
    mark_asked(
        db, user.id, now - timedelta(minutes=11), f"{MARKER_PREFIX}preferences.interests"
    )
    assert check_can_ask(db, user.id, now)[0] is False
    assert check_can_ask_relationship_discovery(db, user.id, now, invited=False)[0] is True
    assert check_can_ask_relationship_discovery(db, user.id, now, invited=True)[0] is True


def test_q4_max2_still_not_implemented():
    """Q4.2A keeps single visible question; dual binding deferred."""
    dual = "preferences.interests|preferences.communication_style"
    clf = classify_discovery_reply(dual, "music", "en")
    assert clf.disposition is DiscoveryDisposition.UNSUPPORTED
    orch = inspect.getsource(
        __import__("backend.app.services.intelligence.orchestrator", fromlist=["*"])
    )
    assert "check_can_ask_relationship_discovery" in orch
    assert "force_invitation" in orch


def test_q4_fa_cue_family_present():
    joined = " | ".join(_DISCOVERY_INVITATION_CUES["fa"])
    assert "اطلاعات بیشتری داشته باشی" in joined
    assert "بیشتر منو بشناس" in joined
    assert "هرچی لازم داری بپرس" in joined
