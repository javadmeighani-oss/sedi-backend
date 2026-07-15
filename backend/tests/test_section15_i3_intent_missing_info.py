"""Section 15-I3 — Intent resolution + missing-information engine tests.

Tests are authored for CI collection; this package must not execute them locally.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.intelligence.adapters import ProfileContextAdapter
from backend.app.services.intelligence.context_types import (
    ContextItem,
    ContextProvenance,
    ContextSnapshot,
    ContextSource,
    SOURCE_SORT_RANK,
)
from backend.app.services.intelligence.contracts import (
    STAGE_ORDER,
    STRUCTURED_READINESS_REASON_CODES,
    FactRequirementStatus,
    IntelligenceContext,
    IntentId,
    IntentResult,
    IntentConfidenceBand,
    OrchestrationError,
    ReadinessStatus,
    ReasonCode,
    RequestKind,
    StageName,
)
from backend.app.services.intelligence.intent_registry import (
    REGISTRY_VERSION,
    list_intent_ids,
    list_rule_ids,
    normalize_match_text,
    resolve_intent,
)
from backend.app.services.intelligence.missing_information import (
    CONFIRMED_NONE_ALLERGIES,
    CONFIRMED_NONE_CONDITIONS,
    CONFIRMED_NONE_MEDICATIONS,
    CONFIRMED_NONE_RESTRICTIONS,
    MissingInformationError,
    evaluate_readiness,
)
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator


def _item(
    *,
    key: str,
    section: str,
    source: ContextSource,
    value,
    owner: int,
    display: str | None = None,
    consent: str = "legacy_scope",
    may_send: bool = True,
    conflicted: bool = False,
    active: bool = True,
    freshness: str = "unknown",
):
    item = ContextItem(
        canonical_key=key,
        section=section,  # type: ignore[arg-type]
        source=source,
        structured_value=value,
        display_text=display or f"{key}={value}",
        provenance=ContextProvenance(
            source=source, owner_user_id=owner, query_label="t"
        ),
        observed_at=None,
        freshness=freshness,  # type: ignore[arg-type]
        sensitivity="medium",  # type: ignore[arg-type]
        consent=consent,  # type: ignore[arg-type]
        may_send_to_llm=may_send,
        sort_rank=SOURCE_SORT_RANK[source],
    )
    item.conflicted = conflicted
    item.active = active
    return item


def _snap(owner: int, items: list[ContextItem], request_id: str = "r1") -> ContextSnapshot:
    return ContextSnapshot(
        request_id=request_id,
        owner_user_id=owner,
        sections={},
        items=items,
        preferred_name=None,
        conflict_count=sum(1 for i in items if i.conflicted),
        truncated_count=0,
        reason_codes=(),
        adapter_order=(),
    )


def _intent(
    intent_id: IntentId = IntentId.NUTRITION,
    kind: RequestKind = RequestKind.PERSONALIZED_PLAN,
) -> IntentResult:
    return IntentResult(
        registry_version=REGISTRY_VERSION,
        intent_id=intent_id,
        request_kind=kind,
        confidence_band=IntentConfidenceBand.HIGH,
        rule_id="i3.rule.test.v1",
    )


# ---------------------------------------------------------------------------
# A. Intent registry
# ---------------------------------------------------------------------------


def test_registry_version_and_unique_rule_ids():
    assert REGISTRY_VERSION == "sedi.intent.registry.v1"
    ids = list_rule_ids()
    assert len(ids) == len(set(ids))
    assert set(list_intent_ids()) == set(IntentId)


def test_intent_all_ten_ids_reachable():
    samples = {
        IntentId.REMINDER: ("en", "remind me tomorrow"),
        IntentId.SYMPTOM: ("en", "I have a fever tonight"),
        IntentId.NUTRITION: ("en", "create a personal meal plan"),
        IntentId.MEDICATION: ("en", "about my medication"),
        IntentId.VITALS: ("en", "check my blood pressure"),
        IntentId.SLEEP: ("en", "how is my sleep quality"),
        IntentId.ACTIVITY: ("en", "my steps today"),
        IntentId.HEALTH: ("en", "healthy lifestyle tips"),
        IntentId.GENERAL: ("en", "hello there"),
    }
    found = {IntentId.NOTIFICATION_FOLLOW_UP}
    for expected, (lang, msg) in samples.items():
        r = resolve_intent(message=msg, language=lang)  # type: ignore[arg-type]
        assert r.intent_id is expected
        found.add(r.intent_id)
    r_n = resolve_intent(
        message="anything", language="en", has_verified_notification_origin=True
    )
    assert r_n.intent_id is IntentId.NOTIFICATION_FOLLOW_UP
    assert found == set(IntentId)


def test_intent_fa_ar_en_and_normalization():
    fa = resolve_intent(message="برنامه غذایی شخصی بساز", language="fa")
    assert fa.intent_id is IntentId.NUTRITION
    assert fa.request_kind is RequestKind.PERSONALIZED_PLAN
    ar = resolve_intent(message="ما الأطعمة التي تحتوي بروتين", language="ar")
    assert ar.intent_id is IntentId.NUTRITION
    assert ar.request_kind is RequestKind.INFORMATIONAL
    assert "ك" not in normalize_match_text("يك")
    assert normalize_match_text("  Hello!! ") == "hello"


def test_fa_nutrition_personalized_positive_cases():
    positives = (
        "رژیم بساز",
        "برایم برنامه غذایی طراحی کن",
        "برام برنامه غذایی تنظیم کن",
        "برنامه غذایی شخصی می‌خواهم",
        "برنامه غذایی میخواهم",
    )
    for msg in positives:
        r = resolve_intent(message=msg, language="fa")
        assert r.intent_id is IntentId.NUTRITION
        assert r.request_kind is RequestKind.PERSONALIZED_PLAN


def test_fa_nutrition_informational_negation_and_collision_cases():
    cases = (
        "برایم توضیح بده برنامه غذایی چیست",
        "می‌خواهم بدانم برنامه غذایی چیست",
        "میخواهم بدانم برنامه غذایی چیست",
        "برایم برنامه غذایی نساز",
        "برنامه غذایی نمی‌خواهم",
        "برنامه غذایی نمیخواهم",
        "برایم برنامه غذایی",
        "چطور برنامه غذایی طراحی کنم؟",
    )
    for msg in cases:
        r = resolve_intent(message=msg, language="fa")
        assert r.intent_id is IntentId.NUTRITION
        assert r.request_kind is RequestKind.INFORMATIONAL


def test_fa_nutrition_bare_and_informational_not_personalized():
    cases = (
        "برنامه غذایی",
        "برنامه تغذیه",
        "برنامه غذایی چیست؟",
        "برنامه تغذیه برای کودکان چیست؟",
        "یک برنامه غذایی سالم چه ویژگی‌هایی دارد؟",
        "درباره برنامه غذایی توضیح بده",
        "درباره برنامه غذایی شخصی توضیح بده",
    )
    for msg in cases:
        r = resolve_intent(message=msg, language="fa")
        assert r.intent_id is IntentId.NUTRITION
        assert r.request_kind is RequestKind.INFORMATIONAL


def test_ar_nutrition_informational_deterministic():
    samples = (
        "ما مصادر البروتين في الغذاء",
        "ما هو الغذاء الصحي",
        "اشرح التغذية الصحية",
    )
    for msg in samples:
        r = resolve_intent(message=msg, language="ar")
        assert r.intent_id is IntentId.NUTRITION
        assert r.request_kind is RequestKind.INFORMATIONAL


def test_intent_broad_token_substring_boundaries():
    assert resolve_intent(message="I spilled water on the pillow", language="en").intent_id is IntentId.GENERAL
    assert resolve_intent(message="take a pill every morning", language="en").intent_id is IntentId.MEDICATION
    assert resolve_intent(message="کیفیت خواب من چطور است", language="fa").intent_id is IntentId.SLEEP
    assert resolve_intent(message="اعراض المرض عندي", language="ar").intent_id is IntentId.SYMPTOM
    assert resolve_intent(message="هذا نص عام بدون اعراض", language="ar").intent_id is IntentId.GENERAL


def test_intent_general_fallback_and_nutrition_kinds():
    g = resolve_intent(message="hello friend", language="en")
    assert g.intent_id is IntentId.GENERAL
    assert g.confidence_band.value == "fallback"
    info = resolve_intent(message="What foods contain protein?", language="en")
    assert info.intent_id is IntentId.NUTRITION
    assert info.request_kind is RequestKind.INFORMATIONAL
    plan = resolve_intent(message="Create a personal meal plan for me", language="en")
    assert plan.intent_id is IntentId.NUTRITION
    assert plan.request_kind is RequestKind.PERSONALIZED_PLAN


def test_intent_precedence_notification_reminder_symptom():
    n = resolve_intent(
        message="remind me about medication",
        language="en",
        has_verified_notification_origin=True,
    )
    assert n.intent_id is IntentId.NOTIFICATION_FOLLOW_UP
    assert n.request_kind is RequestKind.FOLLOW_UP
    rem = resolve_intent(message="remind me to take medication", language="en")
    assert rem.intent_id is IntentId.REMINDER
    sym = resolve_intent(message="I have chest pain and medication questions", language="en")
    assert sym.intent_id is IntentId.SYMPTOM


def test_intent_result_has_no_raw_message_fragment():
    secret = "SECRET_MSG_FRAGMENT_ZZZ"
    r = resolve_intent(message=secret, language="en")
    blob = f"{r.registry_version}{r.intent_id.value}{r.request_kind.value}{r.rule_id}{r.confidence_band.value}"
    assert secret not in blob
    assert "FRAGMENT" not in blob


# ---------------------------------------------------------------------------
# B. Readiness
# ---------------------------------------------------------------------------


def test_readiness_exact_and_prefix_and_unsupported():
    items = [
        _item(
            key="profile.height_cm",
            section="profile",
            source=ContextSource.PROFILE,
            value=170,
            owner=7,
        ),
        _item(
            key="lifestyle.goal.walk",
            section="lifestyle",
            source=ContextSource.LIFESTYLE,
            value="walk",
            owner=7,
        ),
    ]
    r = evaluate_readiness(
        snapshot=_snap(7, items),
        intent=_intent(),
        authenticated_user_id=7,
        language="en",
    )
    by_id = {o.requirement_id: o for o in r.outcomes}
    assert by_id["nut.height"].status is FactRequirementStatus.PRESENT
    assert by_id["nut.goal"].status is FactRequirementStatus.PRESENT
    assert by_id["nut.activity"].status is FactRequirementStatus.UNAVAILABLE
    assert by_id["nut.birth_year"].status is FactRequirementStatus.MISSING


def test_readiness_conflict_denied_stale_unknown_freshness_and_confirmation():
    conflicted = _item(
        key="profile.weight_kg",
        section="profile",
        source=ContextSource.PROFILE,
        value=70,
        owner=1,
        conflicted=True,
        active=False,
    )
    r = evaluate_readiness(
        snapshot=_snap(1, [conflicted]),
        intent=_intent(),
        authenticated_user_id=1,
        language="en",
    )
    assert r.status is ReadinessStatus.BLOCKED_CONFLICT

    denied = _item(
        key="profile.height_cm",
        section="profile",
        source=ContextSource.PROFILE,
        value=160,
        owner=1,
        consent="denied",
    )
    # Fill higher-priority blockers as present so denial can surface first among height.
    base = [
        _item(
            key="lifestyle.goal.g1",
            section="lifestyle",
            source=ContextSource.LIFESTYLE,
            value="x",
            owner=1,
        ),
        _item(
            key="profile.birth_year",
            section="profile",
            source=ContextSource.PROFILE,
            value=1990,
            owner=1,
        ),
        _item(
            key="profile.sex",
            section="profile",
            source=ContextSource.PROFILE,
            value="female",
            owner=1,
        ),
        denied,
    ]
    r2 = evaluate_readiness(
        snapshot=_snap(1, base),
        intent=_intent(),
        authenticated_user_id=1,
        language="en",
    )
    assert r2.status is ReadinessStatus.BLOCKED_DENIED

    unknown = _item(
        key="profile.height_cm",
        section="profile",
        source=ContextSource.PROFILE,
        value=165,
        owner=1,
        freshness="unknown",
    )
    # Unknown freshness must not alone create STALE.
    assert unknown.freshness == "unknown"
    r_unknown = evaluate_readiness(
        snapshot=_snap(
            1,
            [
                _item(
                    key="lifestyle.goal.g1",
                    section="lifestyle",
                    source=ContextSource.LIFESTYLE,
                    value="x",
                    owner=1,
                ),
                _item(
                    key="profile.birth_year",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value=1990,
                    owner=1,
                ),
                _item(
                    key="profile.sex",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value="female",
                    owner=1,
                ),
                unknown,
                _item(
                    key="profile.weight_kg",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value=60,
                    owner=1,
                    freshness="unknown",
                ),
            ],
        ),
        intent=_intent(),
        authenticated_user_id=1,
        language="en",
    )
    by_unknown = {o.requirement_id: o for o in r_unknown.outcomes}
    assert by_unknown["nut.height"].status is FactRequirementStatus.PRESENT

    stale = _item(
        key="health.condition.diabetes",
        section="health",
        source=ContextSource.HEALTH,
        value="diabetes",
        owner=1,
        freshness="stale",
    )
    r_stale = evaluate_readiness(
        snapshot=_snap(
            1,
            [
                _item(
                    key="lifestyle.goal.g1",
                    section="lifestyle",
                    source=ContextSource.LIFESTYLE,
                    value="x",
                    owner=1,
                ),
                _item(
                    key="profile.birth_year",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value=1990,
                    owner=1,
                ),
                _item(
                    key="profile.sex",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value="female",
                    owner=1,
                ),
                _item(
                    key="profile.height_cm",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value=165,
                    owner=1,
                ),
                _item(
                    key="profile.weight_kg",
                    section="profile",
                    source=ContextSource.PROFILE,
                    value=60,
                    owner=1,
                ),
                stale,
            ],
        ),
        intent=_intent(),
        authenticated_user_id=1,
        language="en",
    )
    assert r_stale.status is ReadinessStatus.BLOCKED_STALE
    by_stale = {o.requirement_id: o for o in r_stale.outcomes}
    assert by_stale["nut.conditions"].status is FactRequirementStatus.STALE


def test_readiness_condition_medication_needs_confirmation():
    base = [
        _item(
            key="lifestyle.goal.g1",
            section="lifestyle",
            source=ContextSource.LIFESTYLE,
            value="x",
            owner=4,
        ),
        _item(
            key="profile.birth_year",
            section="profile",
            source=ContextSource.PROFILE,
            value=1990,
            owner=4,
        ),
        _item(
            key="profile.sex",
            section="profile",
            source=ContextSource.PROFILE,
            value="female",
            owner=4,
        ),
        _item(
            key="profile.height_cm",
            section="profile",
            source=ContextSource.PROFILE,
            value=165,
            owner=4,
        ),
        _item(
            key="profile.weight_kg",
            section="profile",
            source=ContextSource.PROFILE,
            value=60,
            owner=4,
        ),
    ]
    legacy_condition = _item(
        key="health.condition.hypertension",
        section="health",
        source=ContextSource.HEALTH,
        value="hypertension",
        owner=4,
        consent="legacy_scope",
        freshness="unknown",
    )
    r = evaluate_readiness(
        snapshot=_snap(4, base + [legacy_condition]),
        intent=_intent(),
        authenticated_user_id=4,
        language="en",
    )
    by_id = {o.requirement_id: o for o in r.outcomes}
    assert by_id["nut.conditions"].status is FactRequirementStatus.NEEDS_CONFIRMATION
    assert r.status is ReadinessStatus.NEEDS_CONFIRMATION

    explicit = _item(
        key="health.medication.metformin",
        section="health",
        source=ContextSource.HEALTH,
        value="metformin",
        owner=4,
        consent="explicit",
    )
    r2 = evaluate_readiness(
        snapshot=_snap(
            4,
            base
            + [
                _item(
                    key=CONFIRMED_NONE_CONDITIONS,
                    section="health",
                    source=ContextSource.HEALTH,
                    value="none",
                    owner=4,
                ),
                explicit,
                _item(
                    key=CONFIRMED_NONE_RESTRICTIONS,
                    section="lifestyle",
                    source=ContextSource.LIFESTYLE,
                    value="none",
                    owner=4,
                ),
            ],
        ),
        intent=_intent(),
        authenticated_user_id=4,
        language="en",
    )
    by2 = {o.requirement_id: o for o in r2.outcomes}
    assert by2["nut.medications"].status is FactRequirementStatus.PRESENT


def test_readiness_mixed_conflicted_and_unconfirmed_prefers_conflict():
    base = [
        _item(
            key="lifestyle.goal.g1",
            section="lifestyle",
            source=ContextSource.LIFESTYLE,
            value="x",
            owner=8,
        ),
        _item(
            key="profile.birth_year",
            section="profile",
            source=ContextSource.PROFILE,
            value=1990,
            owner=8,
        ),
        _item(
            key="profile.sex",
            section="profile",
            source=ContextSource.PROFILE,
            value="female",
            owner=8,
        ),
        _item(
            key="profile.height_cm",
            section="profile",
            source=ContextSource.PROFILE,
            value=165,
            owner=8,
        ),
        _item(
            key="profile.weight_kg",
            section="profile",
            source=ContextSource.PROFILE,
            value=60,
            owner=8,
        ),
    ]
    conflicted = _item(
        key="health.condition.a",
        section="health",
        source=ContextSource.HEALTH,
        value="a",
        owner=8,
        consent="legacy_scope",
        conflicted=True,
        active=False,
    )
    unconfirmed = _item(
        key="health.condition.b",
        section="health",
        source=ContextSource.HEALTH,
        value="b",
        owner=8,
        consent="legacy_scope",
        freshness="unknown",
    )
    r = evaluate_readiness(
        snapshot=_snap(8, base + [conflicted, unconfirmed]),
        intent=_intent(),
        authenticated_user_id=8,
        language="en",
    )
    by_id = {o.requirement_id: o for o in r.outcomes}
    assert by_id["nut.conditions"].status is FactRequirementStatus.CONFLICTED
    assert r.status is ReadinessStatus.BLOCKED_CONFLICT


def test_readiness_mixed_denied_and_unconfirmed_prefers_denied():
    base = [
        _item(
            key="lifestyle.goal.g1",
            section="lifestyle",
            source=ContextSource.LIFESTYLE,
            value="x",
            owner=9,
        ),
        _item(
            key="profile.birth_year",
            section="profile",
            source=ContextSource.PROFILE,
            value=1990,
            owner=9,
        ),
        _item(
            key="profile.sex",
            section="profile",
            source=ContextSource.PROFILE,
            value="female",
            owner=9,
        ),
        _item(
            key="profile.height_cm",
            section="profile",
            source=ContextSource.PROFILE,
            value=165,
            owner=9,
        ),
        _item(
            key="profile.weight_kg",
            section="profile",
            source=ContextSource.PROFILE,
            value=60,
            owner=9,
        ),
    ]
    denied = _item(
        key="health.condition.a",
        section="health",
        source=ContextSource.HEALTH,
        value="a",
        owner=9,
        consent="denied",
    )
    unconfirmed = _item(
        key="health.condition.b",
        section="health",
        source=ContextSource.HEALTH,
        value="b",
        owner=9,
        consent="legacy_scope",
        freshness="unknown",
    )
    r = evaluate_readiness(
        snapshot=_snap(9, base + [denied, unconfirmed]),
        intent=_intent(),
        authenticated_user_id=9,
        language="en",
    )
    by_id = {o.requirement_id: o for o in r.outcomes}
    assert by_id["nut.conditions"].status is FactRequirementStatus.DENIED
    assert r.status is ReadinessStatus.BLOCKED_DENIED


def test_readiness_confirmed_satisfier_still_present_with_sibling_conflict():
    """Valid confirmed fact still PRESENT; conflict sibling must not erase it."""
    confirmed = _item(
        key="health.condition.ok",
        section="health",
        source=ContextSource.HEALTH,
        value="ok",
        owner=8,
        consent="explicit",
    )
    conflicted = _item(
        key="health.condition.bad",
        section="health",
        source=ContextSource.HEALTH,
        value="bad",
        owner=8,
        consent="legacy_scope",
        conflicted=True,
        active=False,
    )
    r = evaluate_readiness(
        snapshot=_snap(8, [confirmed, conflicted]),
        intent=_intent(),
        authenticated_user_id=8,
        language="en",
    )
    by_id = {o.requirement_id: o for o in r.outcomes}
    assert by_id["nut.conditions"].status is FactRequirementStatus.PRESENT


def test_readiness_confirmed_none_and_absence_not_none():
    none_item = _item(
        key=CONFIRMED_NONE_CONDITIONS,
        section="health",
        source=ContextSource.HEALTH,
        value="none",
        owner=3,
    )
    r = evaluate_readiness(
        snapshot=_snap(3, [none_item]),
        intent=_intent(),
        authenticated_user_id=3,
        language="en",
    )
    by_id = {o.requirement_id: o for o in r.outcomes}
    assert by_id["nut.conditions"].status is FactRequirementStatus.PRESENT
    # Absence of confirmed-none + no members → missing for conditions when evaluating empty.
    r2 = evaluate_readiness(
        snapshot=_snap(3, []),
        intent=_intent(),
        authenticated_user_id=3,
        language="en",
    )
    by2 = {o.requirement_id: o for o in r2.outcomes}
    assert by2["nut.conditions"].status is FactRequirementStatus.MISSING


def test_readiness_allergy_confirmed_none_when_positive_unsupported():
    none_item = _item(
        key=CONFIRMED_NONE_ALLERGIES,
        section="health",
        source=ContextSource.HEALTH,
        value="none",
        owner=6,
    )
    r = evaluate_readiness(
        snapshot=_snap(6, [none_item]),
        intent=_intent(),
        authenticated_user_id=6,
        language="en",
    )
    by_id = {o.requirement_id: o for o in r.outcomes}
    assert by_id["nut.allergies"].status is FactRequirementStatus.PRESENT


def test_readiness_allergy_absence_stays_unavailable():
    r = evaluate_readiness(
        snapshot=_snap(6, []),
        intent=_intent(),
        authenticated_user_id=6,
        language="en",
    )
    by_id = {o.requirement_id: o for o in r.outcomes}
    assert by_id["nut.allergies"].status is FactRequirementStatus.UNAVAILABLE
    assert by_id["nut.allergies"].status is not FactRequirementStatus.MISSING


def test_readiness_one_clarification_no_values_in_metadata():
    r = evaluate_readiness(
        snapshot=_snap(9, []),
        intent=_intent(),
        authenticated_user_id=9,
        language="en",
    )
    assert r.status is ReadinessStatus.NEEDS_CLARIFICATION
    assert r.clarification is not None
    assert r.clarification.target_key
    assert r.clarification.localized_message
    # Priority chooses goal first among missing supported facts.
    assert r.clarification.target_key.startswith("lifestyle.goal")
    # No injected user values (snapshot empty).
    for o in r.outcomes:
        assert o.canonical_key
        assert o.status in FactRequirementStatus


def test_readiness_cross_user_fails_closed():
    with pytest.raises(MissingInformationError):
        evaluate_readiness(
            snapshot=_snap(1, []),
            intent=_intent(),
            authenticated_user_id=2,
            language="en",
        )


def test_informational_nutrition_ready_without_profile():
    intent = _intent(IntentId.NUTRITION, RequestKind.INFORMATIONAL)
    r = evaluate_readiness(
        snapshot=_snap(1, []),
        intent=intent,
        authenticated_user_id=1,
        language="en",
    )
    assert r.status is ReadinessStatus.READY
    assert r.clarification is None
    assert r.outcomes == ()


# ---------------------------------------------------------------------------
# C. Nutrition localized height clarifier
# ---------------------------------------------------------------------------


def test_nutrition_missing_height_asks_only_height_template():
    items = [
        _item(
            key="lifestyle.goal.g1",
            section="lifestyle",
            source=ContextSource.LIFESTYLE,
            value="lose",
            owner=5,
        ),
        _item(
            key="profile.birth_year",
            section="profile",
            source=ContextSource.PROFILE,
            value=1988,
            owner=5,
        ),
        _item(
            key="profile.sex",
            section="profile",
            source=ContextSource.PROFILE,
            value="male",
            owner=5,
        ),
    ]
    r = evaluate_readiness(
        snapshot=_snap(5, items),
        intent=_intent(),
        authenticated_user_id=5,
        language="en",
    )
    assert r.clarification is not None
    assert r.clarification.target_key == "profile.height_cm"
    assert "centimeter" in r.clarification.localized_message.lower()
    assert "meal plan" not in r.clarification.localized_message.lower()


def test_height_weight_present_not_reasked():
    items = [
        _item(
            key="lifestyle.goal.g1",
            section="lifestyle",
            source=ContextSource.LIFESTYLE,
            value="gain",
            owner=5,
        ),
        _item(
            key="profile.birth_year",
            section="profile",
            source=ContextSource.PROFILE,
            value=1991,
            owner=5,
        ),
        _item(
            key="profile.sex",
            section="profile",
            source=ContextSource.PROFILE,
            value="female",
            owner=5,
        ),
        _item(
            key="profile.height_cm",
            section="profile",
            source=ContextSource.PROFILE,
            value=165,
            owner=5,
        ),
        _item(
            key="profile.weight_kg",
            section="profile",
            source=ContextSource.PROFILE,
            value=60.5,
            owner=5,
        ),
        _item(
            key=CONFIRMED_NONE_CONDITIONS,
            section="health",
            source=ContextSource.HEALTH,
            value="none",
            owner=5,
        ),
        _item(
            key=CONFIRMED_NONE_MEDICATIONS,
            section="health",
            source=ContextSource.HEALTH,
            value="none",
            owner=5,
        ),
        _item(
            key=CONFIRMED_NONE_RESTRICTIONS,
            section="lifestyle",
            source=ContextSource.LIFESTYLE,
            value="none",
            owner=5,
        ),
    ]
    r = evaluate_readiness(
        snapshot=_snap(5, items),
        intent=_intent(),
        authenticated_user_id=5,
        language="en",
    )
    by_id = {o.requirement_id: o for o in r.outcomes}
    assert by_id["nut.height"].status is FactRequirementStatus.PRESENT
    assert by_id["nut.weight"].status is FactRequirementStatus.PRESENT
    # Still blocked by unsupported activity / allergies / meal fields — not height/weight.
    assert r.clarification is not None
    assert r.clarification.target_key != "profile.height_cm"
    assert r.clarification.target_key != "profile.weight_kg"


# ---------------------------------------------------------------------------
# D. Height/weight adapter expansion
# ---------------------------------------------------------------------------


def test_profile_adapter_emits_height_weight_from_pack():
    pack = MagicMock()
    pack.preferred_name = None
    pack.birth_year = None
    pack.sex = None
    pack.addressing_preference = None
    pack.height_cm = 172
    pack.weight_kg = 68.0
    adapter = ProfileContextAdapter()
    with patch.object(
        ProfileContextAdapter, "_load_user_profile_knowledge", return_value=[]
    ):
        items = adapter.load(
            MagicMock(), authenticated_user_id=11, user_context_pack=pack
        )
    keys = {i.canonical_key for i in items}
    assert "profile.height_cm" in keys
    assert "profile.weight_kg" in keys
    assert all(i.provenance.owner_user_id == 11 for i in items)


def test_profile_adapter_absent_height_weight_emits_nothing():
    pack = MagicMock()
    pack.preferred_name = None
    pack.birth_year = None
    pack.sex = None
    pack.addressing_preference = None
    pack.height_cm = None
    pack.weight_kg = None
    adapter = ProfileContextAdapter()
    with patch.object(
        ProfileContextAdapter, "_load_user_profile_knowledge", return_value=[]
    ):
        items = adapter.load(
            MagicMock(), authenticated_user_id=11, user_context_pack=pack
        )
    keys = {i.canonical_key for i in items}
    assert "profile.height_cm" not in keys
    assert "profile.weight_kg" not in keys


def test_ucs_pack_fields_include_height_weight_annotations():
    from backend.app.services.user_context.context_models import UserContextPack

    fields = UserContextPack.model_fields
    assert "height_cm" in fields
    assert "weight_kg" in fields


def test_i3_modules_forbid_db_session_in_signatures():
    import backend.app.services.intelligence.intent_registry as ir
    import backend.app.services.intelligence.missing_information as mi

    for mod in (ir, mi):
        src = inspect.getsource(mod)
        assert "Session" not in src or "No DB" in src or "no DB" in src.lower()
        assert "UserContextService" not in src
        assert "question_engine" not in src
        assert "is_medical_care_intent" not in src


# ---------------------------------------------------------------------------
# E. Orchestrator integration
# ---------------------------------------------------------------------------


def test_compatibility_skips_i3_and_calls_generator_once():
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "compat-ok", "language": "fa"}

    orch = IntelligenceOrchestrator(legacy_generator=gen, structured_mode=False)
    result = orch.process(authenticated_user_id=1, message="meal plan for me", language="en")
    assert result.rollout_mode == "compatibility"
    assert result.message == "compat-ok"
    assert calls["n"] == 1
    assert ReasonCode.INTENT_RESOLUTION_SKIPPED_COMPATIBILITY.value in result.reason_codes
    assert ReasonCode.READINESS_EVALUATION_SKIPPED_COMPATIBILITY.value in result.reason_codes
    assert ReasonCode.CLARIFICATION_SKIPPED_COMPATIBILITY.value in result.reason_codes
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]
    pub = result.public_brain_dict()
    assert set(pub.keys()) <= {"message", "language", "detected_name"}
    assert "intent_id" not in pub
    assert result.intent_id is None


def test_structured_ready_calls_generator_once(monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "ready-ok", "language": "en"}

    class StubAsm:
        def assemble(self, *a, **k):
            return _snap(1, [], request_id="x")

        def build_compatibility_projection(self, snapshot):
            return MagicMock(
                text="[STRUCTURED_CONTEXT]",
                preferred_name=None,
                truncated=False,
            )

    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
    )
    result = orch.process(authenticated_user_id=1, message="hello", language="en")
    assert result.message == "ready-ok"
    assert calls["n"] == 1
    assert ReasonCode.READINESS_READY.value in result.reason_codes
    assert ReasonCode.CLARIFICATION_NOT_REQUIRED.value in result.reason_codes
    assert ReasonCode.MISSING_INFORMATION_ENGINE_CONNECTED.value in result.reason_codes
    assert ReasonCode.MISSING_INFORMATION_ENGINE_NOT_CONNECTED.value not in result.reason_codes
    assert ReasonCode.STRUCTURED_MODE_NOT_PRODUCTION_READY.value in result.reason_codes
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]


def test_structured_clarification_skips_generator(monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "should-not", "language": "en"}

    class StubAsm:
        def assemble(self, *a, **k):
            return _snap(1, [], request_id="x")

        def build_compatibility_projection(self, snapshot):
            return MagicMock(
                text="[STRUCTURED_CONTEXT]",
                preferred_name=None,
                truncated=False,
            )

    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
    )
    result = orch.process(
        authenticated_user_id=1,
        message="Create a personal meal plan for me",
        language="en",
    )
    assert calls["n"] == 0
    assert result.message
    assert result.clarification_question_id
    assert ReasonCode.GENERATOR_SKIPPED_FOR_CLARIFICATION.value in result.reason_codes
    assert ReasonCode.CLARIFICATION_RESPONSE_VALIDATED.value in result.reason_codes
    assert result.readiness_status == ReadinessStatus.NEEDS_CLARIFICATION.value
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]
    pub = result.public_brain_dict()
    assert "readiness_status" not in pub
    assert "missing_fact_keys" not in pub
    assert set(pub.keys()) <= {"message", "language", "detected_name"}


def test_structured_intent_failure_zero_generator(monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")
    calls = {"n": 0}
    captured: list[tuple[str, str]] = []
    orig_append = IntelligenceContext.append_stage

    def spy_append(self, stage, status, reason_code, duration_ms=0.0):
        captured.append((stage.value, status))
        return orig_append(self, stage, status, reason_code, duration_ms=duration_ms)

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "x", "language": "en"}

    class StubAsm:
        def assemble(self, *a, **k):
            return _snap(1, [], request_id="x")

        def build_compatibility_projection(self, snapshot):
            return MagicMock(text="[STRUCTURED_CONTEXT]", preferred_name=None, truncated=False)

    def boom_resolver(**_k):
        raise RuntimeError("intent_boom")

    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
        intent_resolver=boom_resolver,
    )
    with patch.object(IntelligenceContext, "append_stage", spy_append):
        with pytest.raises(OrchestrationError):
            orch.process(authenticated_user_id=1, message="hello", language="en")
    assert calls["n"] == 0
    order = [s.value for s in STAGE_ORDER]
    assert [name for name, _ in captured] == order[: order.index(StageName.RESOLVE_INTENT.value) + 1]
    assert captured[-1] == (StageName.RESOLVE_INTENT.value, "failed")
    assert len(captured) < len(order)


def test_structured_success_records_full_stage_order(monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")

    def gen(*_a, **_k):
        return {"message": "ok", "language": "en"}

    class StubAsm:
        def assemble(self, *a, **k):
            return _snap(1, [], request_id="x")

        def build_compatibility_projection(self, snapshot):
            return MagicMock(text="[STRUCTURED_CONTEXT]", preferred_name=None, truncated=False)

    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
    )
    result = orch.process(authenticated_user_id=1, message="hello", language="en")
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]


def test_structured_readiness_failure_zero_generator(monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "x", "language": "en"}

    class StubAsm:
        def assemble(self, *a, **k):
            return _snap(1, [], request_id="x")

        def build_compatibility_projection(self, snapshot):
            return MagicMock(text="[STRUCTURED_CONTEXT]", preferred_name=None, truncated=False)

    def boom_engine(**_k):
        raise RuntimeError("ready_boom")

    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
        missing_information_engine=boom_engine,
    )
    with pytest.raises(OrchestrationError):
        orch.process(authenticated_user_id=1, message="hello", language="en")
    assert calls["n"] == 0


def test_structured_cross_user_snapshot_fails_closed(monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "x", "language": "en"}

    class BadAsm:
        def assemble(self, *a, **k):
            return _snap(999, [], request_id="x")  # wrong owner

        def build_compatibility_projection(self, snapshot):
            return MagicMock(text="[STRUCTURED_CONTEXT]", preferred_name=None, truncated=False)

    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=BadAsm(),
    )
    with pytest.raises(OrchestrationError):
        orch.process(authenticated_user_id=1, message="hello", language="en")
    assert calls["n"] == 0


def test_trace_privacy_no_message_or_values(monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")

    def gen(*_a, **_k):
        return {"message": "ok", "language": "en"}

    class StubAsm:
        def assemble(self, *a, **k):
            return _snap(
                1,
                [
                    _item(
                        key="profile.height_cm",
                        section="profile",
                        source=ContextSource.PROFILE,
                        value=171,
                        owner=1,
                        display="height_cm=171",
                    )
                ],
                request_id="x",
            )

        def build_compatibility_projection(self, snapshot):
            return MagicMock(text="[STRUCTURED_CONTEXT]", preferred_name=None, truncated=False)

    secret = "PRIVATE_USER_MESSAGE_TOKEN"
    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=StubAsm(),
    )
    result = orch.process(authenticated_user_id=1, message=secret, language="en")
    blob = " ".join(result.reason_codes) + " ".join(result.stage_names)
    assert secret not in blob
    assert "171" not in blob
    assert "PRIVATE_USER" not in blob
    for readiness in STRUCTURED_READINESS_REASON_CODES:
        assert readiness.value in result.reason_codes
