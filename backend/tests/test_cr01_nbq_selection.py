"""CR-01 — Pure NBQ selection engine tests (no DB / network / writes)."""

from __future__ import annotations

import inspect

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
from backend.app.services.intelligence import next_best_question as nbq
from backend.app.services.intelligence.next_best_question import select_next_best_question


def _intent(intent_id: IntentId, kind: RequestKind = RequestKind.INFORMATIONAL) -> IntentResult:
    return IntentResult(
        registry_version="test",
        intent_id=intent_id,
        request_kind=kind,
        confidence_band=IntentConfidenceBand.HIGH,
        rule_id="test.rule",
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
        section="lifestyle",
        source=ContextSource.LIFESTYLE,
        structured_value="x",
        display_text=f"{key}=x",
        provenance=ContextProvenance(
            source=ContextSource.LIFESTYLE, owner_user_id=owner, query_label="t"
        ),
        observed_at=None,
        freshness=freshness,  # type: ignore[arg-type]
        sensitivity="medium",
        consent=consent,  # type: ignore[arg-type]
        may_send_to_llm=True,
        sort_rank=SOURCE_SORT_RANK[ContextSource.LIFESTYLE],
        active=active,
        conflicted=conflicted,
    )


def _snap(items: list[ContextItem], owner: int = 1) -> ContextSnapshot:
    return ContextSnapshot(
        request_id="nbq",
        owner_user_id=owner,
        sections={"lifestyle": ContextSection(name="lifestyle", items=list(items))},
        items=list(items),
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("lifestyle",),
    )


def test_nbq_deterministic_sleep_selects_first_missing():
    intent = _intent(IntentId.SLEEP)
    d1 = select_next_best_question(
        snapshot=_snap([]), intent=intent, readiness=_ready(intent), language="en"
    )
    d2 = select_next_best_question(
        snapshot=_snap([]), intent=intent, readiness=_ready(intent), language="en"
    )
    assert d1 is not None and d2 is not None
    assert d1 == d2
    assert d1.target_key == "routines.bedtime"
    assert "bed" in d1.localized_question.lower() or "خواب" in d1.localized_question


def test_nbq_existing_fact_skips_to_next():
    intent = _intent(IntentId.SLEEP)
    snap = _snap([_item("routines.bedtime")])
    d = select_next_best_question(
        snapshot=snap, intent=intent, readiness=_ready(intent), language="en"
    )
    assert d is not None
    assert d.target_key == "routines.wake_time"


def test_nbq_denied_conflicted_stale_not_selected():
    intent = _intent(IntentId.SLEEP)
    for item in (
        _item("routines.bedtime", consent="denied"),
        _item("routines.bedtime", conflicted=True),
        _item("routines.bedtime", freshness="stale"),
    ):
        d = select_next_best_question(
            snapshot=_snap([item]),
            intent=intent,
            readiness=_ready(intent),
            language="fa",
        )
        assert d is not None
        assert d.target_key == "routines.wake_time"


def test_nbq_all_candidates_present_yields_none():
    intent = _intent(IntentId.SLEEP)
    snap = _snap(
        [
            _item("routines.bedtime"),
            _item("routines.wake_time"),
            _item("lifestyle.sleep_quality"),
        ]
    )
    assert (
        select_next_best_question(
            snapshot=snap, intent=intent, readiness=_ready(intent), language="ar"
        )
        is None
    )


def test_nbq_hard_clarification_suppresses():
    intent = _intent(IntentId.NUTRITION, RequestKind.PERSONALIZED_PLAN)
    readiness = ReadinessResult(
        status=ReadinessStatus.NEEDS_CLARIFICATION,
        intent_id=intent.intent_id,
        request_kind=intent.request_kind,
        outcomes=(),
        missing_fact_keys=("profile.birth_year",),
        clarification=None,
    )
    assert (
        select_next_best_question(
            snapshot=_snap([]), intent=intent, readiness=readiness, language="en"
        )
        is None
    )


def test_nbq_safety_sensitive_intents_suppress():
    for iid in (
        IntentId.SYMPTOM,
        IntentId.MEDICATION,
        IntentId.VITALS,
        IntentId.REMINDER,
        IntentId.NOTIFICATION_FOLLOW_UP,
    ):
        intent = _intent(iid)
        assert (
            select_next_best_question(
                snapshot=_snap([]),
                intent=intent,
                readiness=_ready(intent),
                language="en",
            )
            is None
        )


def test_nbq_general_and_nutrition_and_activity_mappings():
    g = _intent(IntentId.GENERAL)
    assert (
        select_next_best_question(
            snapshot=_snap([]), intent=g, readiness=_ready(g), language="en"
        ).target_key
        == "preferences.interests"
    )
    n = _intent(IntentId.NUTRITION)
    assert (
        select_next_best_question(
            snapshot=_snap([]), intent=n, readiness=_ready(n), language="en"
        ).target_key
        == "lifestyle.food_habits"
    )
    a = _intent(IntentId.ACTIVITY)
    assert (
        select_next_best_question(
            snapshot=_snap([]), intent=a, readiness=_ready(a), language="en"
        ).target_key
        == "lifestyle.activity_level"
    )


def test_nbq_templates_cover_en_fa_ar():
    intent = _intent(IntentId.GENERAL)
    for lang in ("en", "fa", "ar"):
        d = select_next_best_question(
            snapshot=_snap([]), intent=intent, readiness=_ready(intent), language=lang
        )
        assert d is not None
        assert isinstance(d.localized_question, str) and d.localized_question.strip()


def test_nbq_selector_is_pure_no_writes_no_legacy_kc():
    src = inspect.getsource(nbq)
    assert "Session" not in src
    assert "write_fact" not in src
    assert "db." not in src
    assert "UserFact" not in src
    assert "KcUserFact" not in src
    assert "openai" not in src.lower()
    assert "requests" not in src
    # Max one directive: return after first hit (structural).
    intent = _intent(IntentId.SLEEP)
    d = select_next_best_question(
        snapshot=_snap([]), intent=intent, readiness=_ready(intent), language="en"
    )
    assert d is not None
    assert d.priority == 10
