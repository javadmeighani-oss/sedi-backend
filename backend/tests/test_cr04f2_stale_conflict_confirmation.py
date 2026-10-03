"""CR-04F.2 — Governed stale and conflict confirmation."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import (
    confirm_fact,
    list_facts_readonly,
    list_stale_facts_readonly,
    write_fact,
)
from backend.app.services.i6.relationship_discovery import (
    DiscoveryDisposition,
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
    is_llm_projection_eligible,
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
    TIER_C_NEVER_MISSING_DRIVEN,
    CoverageState,
    coverage_state_for_key,
)
from backend.app.services.knowledge.kc_fatigue_policy import mark_asked
from backend.app.services.knowledge.service import create_candidate


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


def _not_ready(intent: IntentResult) -> ReadinessResult:
    return ReadinessResult(
        status=ReadinessStatus.NEEDS_CLARIFICATION,
        intent_id=intent.intent_id,
        request_kind=intent.request_kind,
        outcomes=(),
        missing_fact_keys=("x",),
        clarification=None,
    )


def _item(
    key: str,
    *,
    active: bool = True,
    conflicted: bool = False,
    consent: str = "legacy_scope",
    freshness: str = "unknown",
    may_send_to_llm: bool = False,
    owner: int = 1,
    value: object = "x",
    display_text: Optional[str] = None,
) -> ContextItem:
    return ContextItem(
        canonical_key=key,
        section="profile",
        source=ContextSource.PROFILE,
        structured_value=value,
        display_text=display_text or f"{key}={value}",
        provenance=ContextProvenance(
            source=ContextSource.PROFILE, owner_user_id=owner, query_label="t"
        ),
        observed_at=None,
        freshness=freshness,  # type: ignore[arg-type]
        sensitivity="medium",
        consent=consent,  # type: ignore[arg-type]
        may_send_to_llm=may_send_to_llm,
        sort_rank=SOURCE_SORT_RANK[ContextSource.PROFILE],
        active=active,
        conflicted=conflicted,
    )


def _snap(items: list[ContextItem], owner: int = 1) -> ContextSnapshot:
    return ContextSnapshot(
        request_id="cr04f2",
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
    mark_asked(
        db,
        user_id,
        datetime.now(timezone.utc),
        f"relationship_discovery:{target_key}",
    )


def _stage_rd_conflict(
    db,
    *,
    user_id: int,
    target_key: str,
    domain: str,
    key: str,
    value,
) -> models.KcFactCandidate:
    return create_candidate(
        db,
        user_id=user_id,
        source="chat",
        fact_type=key,
        value_json=json.dumps({"value": value}, ensure_ascii=False),
        confidence=0.85,
        evidence="conflict",
        metadata_json=json.dumps(
            {
                "needs_confirmation": True,
                "source": "relationship_discovery",
                "target_key": target_key,
                "domain": domain,
                "key": key,
            },
            sort_keys=True,
        ),
    )


def _active(db, user_id: int, domain: str, key: str):
    return (
        db.query(models.UserMemoryFact)
        .filter_by(
            user_id=user_id,
            domain=domain,
            key=key,
            fact_status="active",
        )
        .filter(models.UserMemoryFact.soft_invalidated_at.is_(None))
        .first()
    )


# ---- A) STALE runtime ----


def test_cr04f2_stale_runtime_coverage_and_no_mutation(db):
    user = _user(db, "f2-stale")
    _grant(db, user.id)
    past = datetime.now(timezone.utc) - timedelta(days=2)
    fact = write_fact(
        db,
        user.id,
        "preferences",
        "interests",
        ["sleep"],
        valid_until=past,
        commit=True,
    )
    before = (
        fact.fact_status,
        fact.valid_until,
        fact.soft_invalidated_at,
        fact.updated_at,
    )

    assert list_facts_readonly(db, user.id, domain="preferences") == []
    stale_rows = list_stale_facts_readonly(db, user.id, domain="preferences")
    assert len(stale_rows) == 1
    assert stale_rows[0].id == fact.id

    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    hit = next(i for i in items if i.canonical_key == "preferences.interests")
    assert hit.freshness == "stale"
    assert hit.may_send_to_llm is False
    assert coverage_state_for_key(_snap([hit]), "preferences.interests") is CoverageState.STALE
    assert not is_llm_projection_eligible(hit)

    db.commit()
    db.refresh(fact)
    assert (
        fact.fact_status,
        fact.valid_until,
        fact.soft_invalidated_at,
        fact.updated_at,
    ) == before


# ---- B) CONFLICT runtime ----


def test_cr04f2_relationship_conflict_runtime_isolation(db):
    user = _user(db, "f2-conflict")
    other = _user(db, "f2-other")
    _grant(db, user.id)
    _grant(db, other.id)
    write_fact(
        db,
        user.id,
        "preferences",
        "interests",
        ["a"],
        commit=True,
    )
    secret = "SECRET_CANDIDATE_VALUE_XYZ"
    _stage_rd_conflict(
        db,
        user_id=user.id,
        target_key="preferences.interests",
        domain="preferences",
        key="interests",
        value=secret,
    )
    # Generic KC candidate (no RD metadata) must not create CONFLICTED.
    create_candidate(
        db,
        user_id=user.id,
        source="chat",
        fact_type="interests",
        value_json=json.dumps({"value": "generic"}),
        confidence=0.5,
        evidence="generic",
        metadata_json=json.dumps({"needs_confirmation": True, "source": "other"}),
    )
    # Cross-user RD candidate invisible.
    _stage_rd_conflict(
        db,
        user_id=other.id,
        target_key="preferences.communication_style",
        domain="preferences",
        key="communication_style",
        value="direct",
    )

    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    conflict = next(
        i for i in items if i.canonical_key == "preferences.interests" and i.conflicted
    )
    assert conflict.may_send_to_llm is False
    assert secret not in (conflict.display_text or "")
    assert conflict.structured_value is None
    assert not is_llm_projection_eligible(conflict)
    assert coverage_state_for_key(_snap([conflict]), "preferences.interests") is (
        CoverageState.CONFLICTED
    )

    other_items = LifestyleContextAdapter().load(
        db, authenticated_user_id=other.id, user_context_pack=None
    )
    assert not any(
        i.canonical_key == "preferences.interests" and i.conflicted for i in other_items
    )
    # User must not see other user's conflict key as theirs.
    assert not any(
        i.canonical_key == "preferences.communication_style" and i.conflicted
        for i in items
    )


# ---- C) selector ----


def test_cr04f2_selector_priority_and_guards():
    intent = _intent(IntentId.GENERAL)
    ready = _ready(intent)

    # Conflict before stale before missing F1.
    snap = _snap(
        [
            _item("preferences.interests", conflicted=True),
            _item("preferences.communication_style", freshness="stale"),
        ]
    )
    d = select_next_best_question(
        snapshot=snap, intent=intent, readiness=ready, language="en"
    )
    assert d is not None
    assert d.target_key == "preferences.interests"
    assert "conflicting" in d.localized_question.lower()

    snap2 = _snap([_item("preferences.interests", freshness="stale")])
    d2 = select_next_best_question(
        snapshot=snap2, intent=intent, readiness=ready, language="en"
    )
    assert d2 is not None
    assert d2.target_key == "preferences.interests"
    assert "older" in d2.localized_question.lower()

    # Stale before F1 missing discovery of later Tier-A.
    snap3 = _snap([_item("preferences.communication_style", freshness="stale")])
    d3 = select_next_best_question(
        snapshot=snap3, intent=intent, readiness=ready, language="en"
    )
    assert d3 is not None
    assert d3.target_key == "preferences.communication_style"

    # Hard clarification / not READY.
    assert (
        select_next_best_question(
            snapshot=_snap([_item("preferences.interests", conflicted=True)]),
            intent=intent,
            readiness=_not_ready(intent),
            language="en",
        )
        is None
    )

    # Suppressed intents.
    symptom = _intent(IntentId.SYMPTOM)
    assert (
        select_next_best_question(
            snapshot=_snap([_item("preferences.interests", conflicted=True)]),
            intent=symptom,
            readiness=_ready(symptom),
            language="en",
        )
        is None
    )

    # Work/time requires relevance (must not ask work confirmation without cues).
    sleep = _intent(IntentId.SLEEP)
    snap_work = _snap([_item("work.work_schedule", conflicted=True)])
    d_no_rel = select_next_best_question(
        snapshot=snap_work,
        intent=sleep,
        readiness=_ready(sleep),
        language="en",
        message="hello",
    )
    assert d_no_rel is None or d_no_rel.target_key != "work.work_schedule"
    d_work = select_next_best_question(
        snapshot=snap_work,
        intent=sleep,
        readiness=_ready(sleep),
        language="en",
        message="My night shifts are hard",
    )
    assert d_work is not None
    assert d_work.target_key == "work.work_schedule"

    # Tier-C and DENIED never asked for confirmation.
    for key in sorted(TIER_C_NEVER_MISSING_DRIVEN)[:2]:
        d_c = select_next_best_question(
            snapshot=_snap([_item(key, conflicted=True)]),
            intent=intent,
            readiness=ready,
            language="en",
        )
        assert d_c is None or d_c.target_key != key

    d_denied = select_next_best_question(
        snapshot=_snap([_item("preferences.interests", consent="denied")]),
        intent=intent,
        readiness=ready,
        language="en",
    )
    assert d_denied is not None
    assert d_denied.target_key != "preferences.interests"

    # Max one question.
    d_one = select_next_best_question(
        snapshot=_snap(
            [
                _item("preferences.interests", conflicted=True),
                _item("preferences.response_length", conflicted=True),
            ]
        ),
        intent=intent,
        readiness=ready,
        language="en",
    )
    assert d_one is not None
    assert d_one.target_key == "preferences.interests"


# ---- D) stale binding ----


def test_cr04f2_stale_same_and_changed_value(db):
    user = _user(db, "f2-stale-bind")
    _grant(db, user.id)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    old = write_fact(
        db,
        user.id,
        "preferences",
        "response_length",
        "brief",
        valid_until=past,
        commit=True,
    )
    old_id = old.id

    # Same value confirmation.
    _mark_discovery(db, user.id, "preferences.response_length")
    out = process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="brief",
        language="en",
        allow_binding=True,
    )
    assert out.disposition is DiscoveryDisposition.ANSWER
    row = _active(db, user.id, "preferences", "response_length")
    assert row is not None
    assert row.id == old_id
    assert row.provenance_class == "USER_CONFIRMED"
    assert row.valid_until is None
    assert json.loads(row.value_json) == "brief"
    actives = (
        db.query(models.UserMemoryFact)
        .filter_by(
            user_id=user.id,
            domain="preferences",
            key="response_length",
            fact_status="active",
        )
        .filter(models.UserMemoryFact.soft_invalidated_at.is_(None))
        .all()
    )
    assert len(actives) == 1

    # Changed value → supersede.
    past2 = datetime.now(timezone.utc) - timedelta(hours=1)
    row.valid_until = past2.replace(tzinfo=None) if row.valid_until is None else past2
    # Force stale again for second confirm path.
    row.valid_until = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
    db.commit()

    _mark_discovery(db, user.id, "preferences.response_length")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="detailed",
        language="en",
        allow_binding=True,
    )
    new = _active(db, user.id, "preferences", "response_length")
    assert new is not None
    assert new.id != old_id
    assert new.provenance_class == "USER_CONFIRMED"
    assert json.loads(new.value_json) == "detailed"
    db.refresh(old)
    assert old.fact_status == "superseded"


def test_cr04f2_confirm_fact_i7_invalidation_on_stale_refresh(db, monkeypatch):
    user = _user(db, "f2-i7")
    _grant(db, user.id)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    write_fact(
        db,
        user.id,
        "preferences",
        "interests",
        "music and reading",
        valid_until=past,
        commit=True,
    )
    calls: list[str] = []

    def _spy(db_sess, user_id, *, reason, commit):
        calls.append(reason)

    monkeypatch.setattr(
        "backend.app.services.i6.memory_writes._invalidate_i7",
        _spy,
    )
    confirm_fact(
        db, user.id, "preferences", "interests", "music and reading", commit=True
    )
    row = _active(db, user.id, "preferences", "interests")
    assert row is not None
    assert row.valid_until is None
    assert row.provenance_class == "USER_CONFIRMED"
    assert "confirmation_refresh" in calls


# ---- E) conflict binding ----


def test_cr04f2_conflict_accept_keep_third(db):
    user = _user(db, "f2-cbind")
    _grant(db, user.id)
    write_fact(
        db,
        user.id,
        "work",
        "work_schedule",
        "day shift",
        commit=True,
    )
    cand = _stage_rd_conflict(
        db,
        user_id=user.id,
        target_key="work.work_schedule",
        domain="work",
        key="work_schedule",
        value="night shifts",
    )

    # Accept candidate value.
    _mark_discovery(db, user.id, "work.work_schedule")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="night shifts",
        language="en",
        allow_binding=True,
    )
    db.refresh(cand)
    assert cand.status == "accepted"
    row = _active(db, user.id, "work", "work_schedule")
    assert row is not None
    assert json.loads(row.value_json) == "night shifts"
    assert row.provenance_class == "USER_CONFIRMED"
    assert (
        db.query(models.KcFactCandidate)
        .filter_by(user_id=user.id, status="pending")
        .count()
        == 0
    )

    # Keep existing.
    write_fact(
        db,
        user.id,
        "work",
        "work_schedule",
        "day shift",
        provenance_class="USER_STATED",
        source="manual",
        commit=True,
    )
    cand2 = _stage_rd_conflict(
        db,
        user_id=user.id,
        target_key="work.work_schedule",
        domain="work",
        key="work_schedule",
        value="rotating",
    )
    _mark_discovery(db, user.id, "work.work_schedule")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="day shift",
        language="en",
        allow_binding=True,
    )
    db.refresh(cand2)
    assert cand2.status == "rejected"
    kept = _active(db, user.id, "work", "work_schedule")
    assert kept is not None
    assert json.loads(kept.value_json) == "day shift"
    assert kept.provenance_class == "USER_CONFIRMED"

    # Third value + no recursive conflict.
    write_fact(
        db,
        user.id,
        "work",
        "work_schedule",
        "day shift",
        provenance_class="USER_STATED",
        source="manual",
        commit=True,
    )
    cand3 = _stage_rd_conflict(
        db,
        user_id=user.id,
        target_key="work.work_schedule",
        domain="work",
        key="work_schedule",
        value="night shifts",
    )
    before_pending = (
        db.query(models.KcFactCandidate)
        .filter_by(user_id=user.id, status="pending")
        .count()
    )
    assert before_pending == 1
    _mark_discovery(db, user.id, "work.work_schedule")
    process_relationship_discovery_answer(
        db,
        user_id=user.id,
        message="I work weekend shifts only",
        language="en",
        allow_binding=True,
    )
    db.refresh(cand3)
    assert cand3.status == "rejected"
    third = _active(db, user.id, "work", "work_schedule")
    assert third is not None
    assert "weekend" in json.loads(third.value_json).lower()
    assert third.provenance_class == "USER_CONFIRMED"
    assert (
        db.query(models.KcFactCandidate)
        .filter_by(user_id=user.id, status="pending")
        .count()
        == 0
    )


def test_cr04f2_no_silent_overwrite_still_stages(db):
    """Fresh active + different discovery answer still stages (no silent overwrite)."""
    user = _user(db, "f2-nosilent")
    _grant(db, user.id)
    old = write_fact(
        db,
        user.id,
        "work",
        "work_schedule",
        "day shift",
        commit=True,
    )
    _mark_discovery(db, user.id, "work.work_schedule")
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
    assert (
        db.query(models.KcFactCandidate)
        .filter_by(user_id=user.id, status="pending")
        .count()
        == 1
    )


# ---- F) EN/FA/AR templates ----


def test_cr04f2_en_fa_ar_confirmation_templates():
    for tid in ("nbq.confirm.stale.v1", "nbq.confirm.conflict.v1"):
        block = _TEMPLATES[tid]
        for lang in ("en", "fa", "ar"):
            assert lang in block
            assert "{field}" in block[lang]
            assert block[lang].strip()

    intent = _intent(IntentId.GENERAL)
    ready = _ready(intent)
    snap = _snap([_item("preferences.interests", freshness="stale")])
    for lang in ("en", "fa", "ar"):
        d = select_next_best_question(
            snapshot=snap, intent=intent, readiness=ready, language=lang
        )
        assert d is not None
        assert d.localized_question
        assert "{" not in d.localized_question


# ---- G) CR-04F.1 regression ----


def test_cr04f2_cr04f1_missing_tier_a_unchanged():
    intent = _intent(IntentId.GENERAL)
    ready = _ready(intent)
    d = select_next_best_question(
        snapshot=_snap([]), intent=intent, readiness=ready, language="en"
    )
    assert d is not None
    assert d.target_key == "preferences.interests"
    assert "Optional" in d.localized_question or "اختیاری" in d.localized_question


# ---- CR-04F.2.1 confirmation evidence under saturation ----


def _i6_known_items(items):
    return [
        i
        for i in items
        if i.provenance.query_label == "I6.list_facts_readonly_or_empty"
    ]


def _confirmation_items(items):
    return [
        i
        for i in items
        if i.provenance.query_label
        in (
            "I6.list_stale_facts_readonly",
            "KC.relationship_discovery.pending_confirmation",
        )
    ]


def test_cr04f21_stale_survives_same_domain_saturation(db):
    """Ordinary per-domain=3 must not drop registered STALE confirmation evidence."""
    from backend.app.services.i6.relationship_discovery import SUPPORTED_TARGETS

    user = _user(db, "f21-domain-sat")
    _grant(db, user.id)
    past = datetime.now(timezone.utc) - timedelta(days=1)

    for key, value in (
        ("interests", "gardening"),
        ("communication_style", "direct"),
        ("response_length", "brief"),
    ):
        write_fact(db, user.id, "preferences", key, value, commit=True)

    stale = write_fact(
        db,
        user.id,
        "preferences",
        "listen_before_advice",
        True,
        valid_until=past,
        commit=True,
    )
    before = (
        stale.fact_status,
        stale.valid_until,
        stale.soft_invalidated_at,
        stale.updated_at,
    )

    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    known_prefs = [
        i
        for i in _i6_known_items(items)
        if i.canonical_key.startswith("preferences.")
    ]
    assert len(known_prefs) == 3

    hit = next(
        i for i in items if i.canonical_key == "preferences.listen_before_advice"
    )
    assert hit.freshness == "stale"
    assert hit.may_send_to_llm is False
    assert coverage_state_for_key(_snap([hit]), "preferences.listen_before_advice") is (
        CoverageState.STALE
    )
    assert not is_llm_projection_eligible(hit)
    assert len(_confirmation_items(items)) <= len(SUPPORTED_TARGETS)

    db.commit()
    db.refresh(stale)
    assert (
        stale.fact_status,
        stale.valid_until,
        stale.soft_invalidated_at,
        stale.updated_at,
    ) == before


def test_cr04f21_conflict_survives_total_saturation(db):
    """Ordinary max_total=12 must not drop relationship CONFLICT confirmation evidence."""
    from backend.app.services.i6.relationship_discovery import SUPPORTED_TARGETS

    user = _user(db, "f21-total-sat")
    other = _user(db, "f21-total-other")
    _grant(db, user.id)
    _grant(db, other.id)

    normals = (
        ("preferences", "interests", "gardening"),
        ("preferences", "communication_style", "direct"),
        ("preferences", "response_length", "brief"),
        ("routines", "bedtime", "22:00"),
        ("routines", "wake_time", "06:30"),
        ("routines", "meal_times", "regular meals"),
        ("lifestyle", "sleep_quality", "fair sleep"),
        ("lifestyle", "activity_level", "moderate"),
        ("lifestyle", "food_habits", "home cooked"),
        ("work", "work_schedule", "day shift"),
        ("work", "occupation", "engineer"),
        ("work", "work_stressors", "tight deadlines"),
    )
    assert len(normals) >= 12
    for domain, key, value in normals:
        write_fact(db, user.id, domain, key, value, commit=True)

    secret = "SECRET_TOTAL_SAT_CANDIDATE_QQQ"
    _stage_rd_conflict(
        db,
        user_id=user.id,
        target_key="preferences.listen_before_advice",
        domain="preferences",
        key="listen_before_advice",
        value=secret,
    )
    _stage_rd_conflict(
        db,
        user_id=other.id,
        target_key="work.work_schedule",
        domain="work",
        key="work_schedule",
        value="night shifts",
    )

    adapter = LifestyleContextAdapter()
    # Ordinary budget is owned by _load_i6_user_understanding_facts (max_total=12).
    # LifestyleContextAdapter.load also has a separate lifestyle preview loop.
    uu_items = adapter._load_i6_user_understanding_facts(
        db, authenticated_user_id=user.id
    )
    known = _i6_known_items(uu_items)
    assert len(known) == 12

    items = adapter.load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    conflict = next(
        i
        for i in items
        if i.canonical_key == "preferences.listen_before_advice" and i.conflicted
    )
    assert conflict.may_send_to_llm is False
    assert conflict.structured_value is None
    assert secret not in (conflict.display_text or "")
    assert not is_llm_projection_eligible(conflict)
    assert coverage_state_for_key(
        _snap([conflict]), "preferences.listen_before_advice"
    ) is CoverageState.CONFLICTED

    assert not any(
        i.canonical_key == "work.work_schedule" and i.conflicted for i in items
    )
    other_items = LifestyleContextAdapter().load(
        db, authenticated_user_id=other.id, user_context_pack=None
    )
    assert not any(
        i.canonical_key == "preferences.listen_before_advice" and i.conflicted
        for i in other_items
    )
    assert len(_confirmation_items(items)) <= len(SUPPORTED_TARGETS)


def test_cr04f21_confirmation_evidence_is_bounded(db):
    """Many stale+conflict entries remain within the independent confirmation cap."""
    from backend.app.services.i6.relationship_discovery import SUPPORTED_TARGETS

    user = _user(db, "f21-bound")
    _grant(db, user.id)
    past = datetime.now(timezone.utc) - timedelta(days=3)

    stale_targets = (
        ("preferences", "interests", "old-interests"),
        ("preferences", "communication_style", "old-style"),
        ("preferences", "response_length", "brief"),
        ("preferences", "listen_before_advice", True),
        ("routines", "bedtime", "21:00"),
        ("routines", "wake_time", "07:00"),
        ("lifestyle", "sleep_quality", "poor"),
        ("lifestyle", "food_habits", "irregular"),
        ("lifestyle", "activity_level", "low"),
        ("routines", "exercise_schedule", "rarely"),
        ("work", "work_schedule", "rotating"),
        ("barriers", "time_constraints", "very limited"),
    )
    for domain, key, value in stale_targets:
        write_fact(
            db, user.id, domain, key, value, valid_until=past, commit=True
        )

    conflict_targets = (
        ("preferences.interests", "preferences", "interests", "new-a"),
        ("preferences.communication_style", "preferences", "communication_style", "new-b"),
        ("work.work_schedule", "work", "work_schedule", "new-c"),
        ("barriers.time_constraints", "barriers", "time_constraints", "new-d"),
        ("routines.bedtime", "routines", "bedtime", "23:30"),
    )
    for target_key, domain, key, value in conflict_targets:
        _stage_rd_conflict(
            db,
            user_id=user.id,
            target_key=target_key,
            domain=domain,
            key=key,
            value=value,
        )

    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    confirmation = _confirmation_items(items)
    assert len(confirmation) <= len(SUPPORTED_TARGETS)
    assert len(confirmation) >= 1
    # Conflict preferred into the confirmation budget; raw values never projected.
    conflicted = [i for i in confirmation if i.conflicted]
    assert conflicted
    for item in conflicted:
        assert item.structured_value is None
        assert item.may_send_to_llm is False
        assert "new-" not in (item.display_text or "")
    for item in confirmation:
        assert item.may_send_to_llm is False
        assert not is_llm_projection_eligible(item)
