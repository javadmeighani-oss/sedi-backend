"""Stage 06 / B1: body-function intake before personalized plans — generic for any condition (offline, pure)."""
from __future__ import annotations

import pytest

from backend.app.services.i6.relationship_discovery import (
    FUNCTION_DOMAINS,
    FUNCTION_TARGETS,
    SUPPORTED_TARGETS,
    _OPEN_TEXT_TARGETS,
    _target_fit,
)
from backend.app.services.intelligence import condition_function_domains as cfd
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
from backend.app.services.intelligence.user_understanding_coverage import REGISTERED_TARGETS
from backend.app.services.memory.memory_contract import ALLOWED_DOMAINS, ALLOWED_KEYS, MemoryContract


def _intent(intent_id: IntentId) -> IntentResult:
    return IntentResult(
        registry_version="test",
        intent_id=intent_id,
        request_kind=RequestKind.INFORMATIONAL,
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


def _item(key: str, value: str) -> ContextItem:
    return ContextItem(
        canonical_key=key,
        section="lifestyle",
        source=ContextSource.LIFESTYLE,
        structured_value=value,
        display_text=f"{key}={value}",
        provenance=ContextProvenance(source=ContextSource.LIFESTYLE, owner_user_id=1, query_label="t"),
        observed_at=None,
        freshness="unknown",  # type: ignore[arg-type]
        sensitivity="high",
        consent="legacy_scope",  # type: ignore[arg-type]
        may_send_to_llm=False,
        sort_rank=SOURCE_SORT_RANK[ContextSource.LIFESTYLE],
        active=True,
        conflicted=False,
    )


def _snap(items: list[ContextItem]) -> ContextSnapshot:
    return ContextSnapshot(
        request_id="b1",
        owner_user_id=1,
        sections={"lifestyle": ContextSection(name="lifestyle", items=list(items))},
        items=list(items),
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("lifestyle",),
    )


def _ask(conditions, intent_id=IntentId.NUTRITION, language="fa", answered=(), goal_known=True, plan_domain=None):
    items = [_item(f"health.condition.c{i}", c) for i, c in enumerate(conditions)]
    items += [_item(k, "answered") for k in answered]
    if goal_known:
        items.append(_item("intake.goal", "answered"))
    intent = _intent(intent_id)
    return select_next_best_question(
        snapshot=_snap(items),
        intent=intent,
        readiness=_ready(intent),
        language=language,
        plan_domain=plan_domain,
    )


# ≈24 varied conditions (fa/en/ar), mapped and unmapped — the generality acceptance set.
SCENARIOS = [
    "ALS", "اس ال اس", "multiple sclerosis", "پارکینسون", "stroke", "Alzheimer", "آلزایمر",
    "heart failure", "فشار خون بالا", "hypertension", "type 2 diabetes", "دیابت", "السكري",
    "chronic kidney disease", "دیالیز", "COPD", "آسم", "الربو", "breast cancer", "سرطان",
    "Crohn's disease", "کولیت", "arthritis", "آرتروز", "depression", "اضطراب",
    "glaucoma", "some very rare syndrome", "یک بیماری نادر ناشناخته", "متلازمة نادرة",
]


@pytest.mark.parametrize("condition", SCENARIOS)
@pytest.mark.parametrize("intent_id", [IntentId.NUTRITION, IntentId.ACTIVITY])
def test_any_condition_gets_a_function_question(condition, intent_id):
    for lang in ("fa", "en", "ar"):
        d = _ask([condition], intent_id=intent_id, language=lang)
        assert d is not None, (condition, lang)
        assert d.target_key.startswith(("function.", "intake."))
        assert d.target_key in SUPPORTED_TARGETS and d.target_key in REGISTERED_TARGETS
        assert d.localized_question.strip()
        assert not any(bad in d.localized_question for bad in ("سدی", "سِدی"))


def test_unmapped_condition_falls_back_to_general_domain():
    assert cfd.domains_for_conditions(["some very rare syndrome"]) == ["general"]


def test_multiple_conditions_union_in_order():
    domains = cfd.domains_for_conditions(["diabetes", "kidney disease"])
    assert domains[:3] == ["glucose", "appetite", "senses"] and "digestion" in domains


def test_no_conditions_or_non_plan_intent_asks_no_function_question():
    d0 = _ask([])
    # no condition: the established soft question (food habits) comes first, then the friendly intake
    assert d0 is not None and d0.target_key == "lifestyle.food_habits"
    assert _ask([], answered=["lifestyle.food_habits"]).target_key == "intake.allergies"
    d = _ask(["ALS"], intent_id=IntentId.GENERAL)
    assert d is None or not d.target_key.startswith(("function.", "intake."))


def test_answered_domain_is_skipped_in_order():
    first = _ask(["ALS"])
    assert first.target_key == "function.swallowing"
    second = _ask(["ALS"], answered=["function.swallowing"])
    assert second.target_key == "function.mobility"
    done_keys = [f"function.{d}" for d in cfd.domains_for_conditions(["ALS"])]
    after_function = _ask(["ALS"], answered=done_keys + ["lifestyle.food_habits"])
    assert after_function.target_key == "intake.allergies"


def test_contract_data_and_templates_stay_in_sync():
    assert tuple(cfd.known_domains()) == tuple(FUNCTION_DOMAINS)
    assert "function" in ALLOWED_DOMAINS and tuple(ALLOWED_KEYS["function"]) == tuple(FUNCTION_DOMAINS)
    assert FUNCTION_TARGETS <= SUPPORTED_TARGETS and FUNCTION_TARGETS <= _OPEN_TEXT_TARGETS
    for d in FUNCTION_DOMAINS:
        tpl = _TEMPLATES[f"nbq.function.{d}.v1"]
        assert set(tpl) == {"en", "fa", "ar"} and all(v.strip() for v in tpl.values())
        assert MemoryContract.is_i6_context_projectable("function", d)
        assert MemoryContract.validate_fact("function", d)[0]


def test_function_answer_binds_only_when_it_is_an_answer_not_another_request():
    assert _target_fit("function.swallowing", "گاهی موقع قورت دادن غذا سرفه می‌کنم")
    assert not _target_fit("function.swallowing", "یه برنامه غذایی بساز برام")
    assert not _target_fit("function.swallowing", "remind me to take my pills")


def test_every_mapped_condition_domain_is_a_known_function_domain():
    cfg = cfd._load()
    known = set(cfd.known_domains())
    assert set(cfg["fallback_domains"]) <= known
    for entry in cfg["conditions"]:
        assert set(entry["domains"]) <= known, entry["id"]


# ---- who is the plan for + plan trailer (supportive boundary, lifestyle pointer) ----
from backend.app.services.i8 import plan_notes
from backend.app.services.intelligence.plan_subject import mentions_other_person, plan_subject_question


@pytest.mark.parametrize(
    "text,lang,expected",
    [
        ("یک برنامه غذایی برای پدرم که ALS دارد بساز", "fa", True),
        ("برنامه ورزشی برای مادرم می‌خوام", "fa", True),
        ("برای خودم یک برنامه غذایی بساز، مادرم هم دیابت داره", "fa", False),
        ("make a meal plan for my father", "en", True),
        ("make a meal plan for myself", "en", False),
        ("خطة غذائية لأبي", "ar", True),
        ("یک برنامه غذایی برای من بساز", "fa", False),
        ("", "fa", False),
    ],
)
def test_plan_subject_detection(text, lang, expected):
    assert mentions_other_person(text, lang) is expected


def test_plan_subject_question_all_languages_and_brand_safe():
    for lang in ("fa", "en", "ar"):
        q = plan_subject_question(lang)
        assert q.strip() and "سدی" not in q


def test_trailer_has_pointer_always_and_boundary_only_with_a_condition(monkeypatch):
    monkeypatch.setattr(plan_notes, "has_registered_condition", lambda db, uid: False)
    plain = plan_notes.build_plan_trailer(None, 1, "fa", "nutrition")
    assert "سبک زندگی" in plain and "تیم درمان" not in plain
    monkeypatch.setattr(plan_notes, "has_registered_condition", lambda db, uid: True)
    for lang in ("fa", "en", "ar"):
        for domain in ("nutrition", "exercise"):
            t = plan_notes.build_plan_trailer(None, 1, lang, domain)
            assert len(t.split("\n")) == 2
    fa = plan_notes.build_plan_trailer(None, 1, "fa", "nutrition")
    assert "تیم درمان" in fa and "نه رژیم یا نسخه‌ی درمانی" in fa
    assert "سدی" not in fa


# ---- B1.5-a: friendly plan intake (goal first, then function, then domain questions) ----
from backend.app.services.i6.relationship_discovery import INTAKE_KEYS, INTAKE_TARGETS
from backend.app.services.intelligence.missing_information import FactRequirement, _items_for_requirement


def test_intake_goal_comes_first_then_function_then_domain_questions():
    # the goal itself is asked by the I3 readiness clarification (friendly single question, bound to intake.goal)
    from backend.app.services.intelligence.missing_information import _TEMPLATES as _READY_TPL

    goal_q = _READY_TPL["tpl.goal.v1"]["fa"]
    assert goal_q.count("؟") == 1 and "هدفت" in goal_q
    order = []
    answered = ["lifestyle.food_habits"]
    while True:
        d = _ask(["ALS"], answered=answered)
        if d is None:
            break
        order.append(d.target_key)
        answered.append(d.target_key)
    assert order[:4] == ["function.swallowing", "function.mobility", "function.breathing", "function.balance"]
    # the established soft nutrition question (lifestyle.food_habits) may follow the plan intake
    assert [k for k in order[4:] if k.startswith("intake.")] == [
        "intake.allergies", "intake.food_preferences", "intake.budget", "intake.cooking_time", "intake.meal_times",
    ]


def test_activity_intake_asks_exercise_questions_and_continues_via_plan_domain():
    order, answered = [], []
    while True:
        d = _ask([], intent_id=IntentId.ACTIVITY, answered=answered)
        if d is None:
            break
        order.append(d.target_key)
        answered.append(d.target_key)
    assert [k for k in order if k.startswith("intake.")] == [
        "intake.exercise_preferences", "intake.exercise_time", "intake.equipment",
    ]
    # a reply turn (discovery-reply intent) keeps going when the orchestrator passes the plan domain
    cont = _ask([], intent_id=IntentId.GENERAL, plan_domain="nutrition")
    assert cont is not None and cont.target_key == "intake.allergies"


def test_intake_contract_templates_and_brand():
    assert tuple(INTAKE_KEYS) == tuple(ALLOWED_KEYS["intake"]) and INTAKE_TARGETS <= SUPPORTED_TARGETS
    assert INTAKE_TARGETS <= _OPEN_TEXT_TARGETS and INTAKE_TARGETS <= REGISTERED_TARGETS
    for k in INTAKE_KEYS:
        tid = "nbq.intake.goal_nutrition.v1" if k == "goal" else f"nbq.intake.{k}.v1"
        tpl = _TEMPLATES[tid]
        assert set(tpl) == {"en", "fa", "ar"} and all(v.strip() for v in tpl.values())
        assert not any(bad in tpl["fa"] for bad in ("سدی", "سِدی", "مایلید"))
    assert "nbq.intake.goal_exercise.v1" in _TEMPLATES
    assert MemoryContract.is_i6_context_projectable("intake", "goal")


def test_stated_goal_item_satisfies_the_readiness_goal_requirement():
    req = FactRequirement("nut.goal", "lifestyle.goal.*", 10, "prefix")
    assert _items_for_requirement([_item("lifestyle.goal.stated", "x")], req)
    assert not _items_for_requirement([_item("intake.goal", "x")], req)


def test_intake_answer_binds_like_any_open_text_reply():
    assert _target_fit("intake.allergies", "به بادام زمینی آلرژی دارم")
    assert _target_fit("intake.budget", "متوسط")
    assert not _target_fit("intake.allergies", "یادآوری کن دارو بخورم")
