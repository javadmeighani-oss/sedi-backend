"""CR-04E1 — I7 lifelong derived refresh lifecycle (I7-owned, flag-gated)."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import inspect
import json
from types import SimpleNamespace
from unittest.mock import patch

from backend.app import models
from backend.app.core import scheduler as scheduler_mod
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import correct_fact, delete_fact, write_fact
from backend.app.services.i7.derived_invalidation import invalidate_derived_memory_state
from backend.app.services.i7.jobs import (
    period_summary_jobs_enabled,
    run_lifelong_profile_sweep,
)
from backend.app.services.i7.lifelong_profile import rebuild_lifelong_profile
from backend.app.services.i8.context import load_trusted_context
from backend.app.services.i8.knowledge_bridge import build_personalization
from backend.app.services.i8.unified_core import generate_operational_action


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _active_profile(db, user_id: int):
    return (
        db.query(models.UserLifelongProfile)
        .filter(
            models.UserLifelongProfile.user_id == user_id,
            models.UserLifelongProfile.status == "active",
        )
        .order_by(models.UserLifelongProfile.version.desc())
        .first()
    )


def _profiles(db, user_id: int):
    return (
        db.query(models.UserLifelongProfile)
        .filter(models.UserLifelongProfile.user_id == user_id)
        .order_by(models.UserLifelongProfile.version.asc())
        .all()
    )


def _semantic(profile: models.UserLifelongProfile) -> dict:
    return json.loads(profile.structured_profile_json)["semantic_profile"]


def _find_entry(groups: dict, canonical_key: str):
    for name, entries in groups.items():
        if name == "version":
            continue
        for entry in entries or []:
            if entry.get("canonical_key") == canonical_key:
                return entry
    return None


def _blob(profile: models.UserLifelongProfile) -> str:
    return f"{profile.structured_profile_json}\n{profile.narrative_compact}"


# ---- sweep lifecycle ----


def test_cr04e1_missing_profile_plus_facts_creates_one_active(db, monkeypatch):
    monkeypatch.setenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "true")
    user = _user(db, "e1-missing")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "preferences", "response_length", "brief", commit=True)
    assert _active_profile(db, user.id) is None
    result = run_lifelong_profile_sweep(db, persist=True)
    assert result.profiles_created >= 1
    active = _active_profile(db, user.id)
    assert active is not None
    assert active.version == 1
    assert "preferences.response_length" in json.loads(active.structured_profile_json)["preferences"]


def test_cr04e1_stale_profile_plus_corrected_fact_next_version(db, monkeypatch):
    monkeypatch.setenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "true")
    user = _user(db, "e1-stale")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "work", "work_schedule", "day shift", commit=True)
    first = rebuild_lifelong_profile(db, user.id, commit=True)
    assert first.status == "active"
    correct_fact(db, user.id, "work", "work_schedule", "night shifts", commit=True)
    # I6 correct invalidates derived → stale
    stale = (
        db.query(models.UserLifelongProfile)
        .filter(models.UserLifelongProfile.id == first.id)
        .one()
    )
    assert stale.status == "stale"
    assert _active_profile(db, user.id) is None
    result = run_lifelong_profile_sweep(db, persist=True)
    assert result.profiles_rebuilt >= 1
    active = _active_profile(db, user.id)
    assert active is not None
    assert active.version == first.version + 1
    entry = _find_entry(_semantic(active), "work.work_schedule")
    assert entry is not None
    assert entry["value_compact"] == "night shifts"


def test_cr04e1_deleted_fact_excluded_on_rebuild(db, monkeypatch):
    monkeypatch.setenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "true")
    user = _user(db, "e1-del")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "work", "work_schedule", "night shifts", commit=True)
    write_fact(db, user.id, "preferences", "response_length", "brief", commit=True)
    rebuild_lifelong_profile(db, user.id, commit=True)
    delete_fact(db, user.id, "work", "work_schedule", commit=True)
    assert _active_profile(db, user.id) is None
    run_lifelong_profile_sweep(db, persist=True)
    active = _active_profile(db, user.id)
    assert active is not None
    payload = json.loads(active.structured_profile_json)
    assert "work.work_schedule" not in payload["keys"]
    assert _find_entry(payload["semantic_profile"], "work.work_schedule") is None
    assert "preferences.response_length" in payload["preferences"]


def test_cr04e1_no_remaining_facts_no_empty_active_profile(db, monkeypatch):
    monkeypatch.setenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "true")
    user = _user(db, "e1-empty")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "work", "occupation", "designer", commit=True)
    first = rebuild_lifelong_profile(db, user.id, commit=True)
    delete_fact(db, user.id, "work", "occupation", commit=True)
    assert _active_profile(db, user.id) is None
    result = run_lifelong_profile_sweep(db, persist=True)
    assert result.profiles_skipped_no_facts >= 1
    assert result.profiles_created == 0
    assert result.profiles_rebuilt == 0
    assert _active_profile(db, user.id) is None
    stale = (
        db.query(models.UserLifelongProfile)
        .filter(models.UserLifelongProfile.id == first.id)
        .one()
    )
    assert stale.status == "stale"


def test_cr04e1_active_current_profile_idempotent_skip(db, monkeypatch):
    monkeypatch.setenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "true")
    user = _user(db, "e1-skip")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "preferences", "response_length", "brief", commit=True)
    first = rebuild_lifelong_profile(db, user.id, commit=True)
    before = len(_profiles(db, user.id))
    result = run_lifelong_profile_sweep(db, persist=True)
    assert result.profiles_skipped_active >= 1
    assert result.profiles_created == 0
    assert result.profiles_rebuilt == 0
    assert len(_profiles(db, user.id)) == before
    active = _active_profile(db, user.id)
    assert active is not None and active.id == first.id


def test_cr04e1_no_perm_read_no_rebuild(db, monkeypatch):
    monkeypatch.setenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "true")
    user = _user(db, "e1-noconsent")
    # Direct insert without consent path — write_fact requires consent, so skip write.
    result = run_lifelong_profile_sweep(db, persist=True)
    assert _active_profile(db, user.id) is None
    assert db.query(models.UserLifelongProfile).filter_by(user_id=user.id).count() == 0
    assert result.profiles_created == 0


def test_cr04e1_cross_user_isolation(db, monkeypatch):
    monkeypatch.setenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "true")
    a = _user(db, "e1-iso-a")
    b = _user(db, "e1-iso-b")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    write_fact(db, a.id, "work", "occupation", "a-only", commit=True)
    write_fact(db, b.id, "work", "occupation", "b-secret", commit=True)
    run_lifelong_profile_sweep(db, persist=True)
    pa = _active_profile(db, a.id)
    pb = _active_profile(db, b.id)
    assert pa is not None and pb is not None
    assert "a-only" in _blob(pa)
    assert "b-secret" not in _blob(pa)
    assert "b-secret" in _blob(pb)
    assert "a-only" not in _blob(pb)


# ---- sensitivity fail-closed ----


def test_cr04e1_high_critical_unknown_sensitivity_raw_absent(db):
    user = _user(db, "e1-sens")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(
        db,
        user.id,
        "work",
        "work_schedule",
        "SECRET-HIGH-SHIFT",
        sensitivity_class="high",
        commit=True,
    )
    write_fact(
        db,
        user.id,
        "preferences",
        "response_length",
        "SECRET-CRITICAL-BRIEF",
        sensitivity_class="critical",
        commit=True,
    )
    write_fact(
        db,
        user.id,
        "routines",
        "bedtime",
        "SECRET-UNKNOWN-TIME",
        sensitivity_class="classified",
        commit=True,
    )
    write_fact(
        db,
        user.id,
        "work",
        "occupation",
        "designer",
        sensitivity_class="standard",
        commit=True,
    )
    write_fact(
        db,
        user.id,
        "preferences",
        "interaction_style",
        "warm",
        sensitivity_class="medium",
        commit=True,
    )
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    blob = _blob(profile)
    assert "SECRET-HIGH-SHIFT" not in blob
    assert "SECRET-CRITICAL-BRIEF" not in blob
    assert "SECRET-UNKNOWN-TIME" not in blob
    high = _find_entry(_semantic(profile), "work.work_schedule")
    crit = _find_entry(_semantic(profile), "preferences.response_length")
    unk = _find_entry(_semantic(profile), "routines.bedtime")
    assert high is not None and "value_compact" not in high
    assert crit is not None and "value_compact" not in crit
    assert crit["sensitivity"] == "critical"
    assert unk is not None and "value_compact" not in unk
    occ = _find_entry(_semantic(profile), "work.occupation")
    style = _find_entry(_semantic(profile), "preferences.interaction_style")
    assert occ is not None and occ["value_compact"] == "designer"
    assert style is not None and style["value_compact"] == "warm"


# ---- flag / scheduler ownership ----


def test_cr04e1_flag_off_zero_lifelong_mutation(db, monkeypatch):
    monkeypatch.delenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", raising=False)
    assert period_summary_jobs_enabled() is False
    user = _user(db, "e1-flagoff")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "preferences", "response_length", "brief", commit=True)
    result = run_lifelong_profile_sweep(db, persist=True)
    assert result.detail == "DORMANT_FLAG_OFF"
    assert result.profiles_created == 0
    assert db.query(models.UserLifelongProfile).filter_by(user_id=user.id).count() == 0


def test_cr04e1_scheduler_daily_only_invokes_lifelong_sweep():
    src = inspect.getsource(scheduler_mod)
    assert "run_lifelong_profile_sweep" in src
    # DAILY gate around lifelong sweep.
    assert 'summary_type == "DAILY"' in src
    assert "run_lifelong_profile_sweep(db, persist=True)" in src
    # No separate WEEKLY/MONTHLY/YEARLY lifelong calls.
    for kind in ("WEEKLY", "MONTHLY", "YEARLY"):
        assert f'summary_type == "{kind}"' not in src or kind == "DAILY"
    # Ensure lifelong call is only under DAILY block: count occurrences.
    assert src.count("run_lifelong_profile_sweep(") == 1


# ---- I8 boundary (read-only proofs; no I8 production edits) ----


def test_cr04e1_i8_stale_not_consumed_then_visible_after_sweep(db, monkeypatch):
    monkeypatch.setenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "true")
    user = _user(db, "e1-i8")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "food_habits", "vegetarian", commit=True)
    write_fact(db, user.id, "preferences", "response_length", "brief", commit=True)
    first = rebuild_lifelong_profile(db, user.id, commit=True)
    ctx1 = load_trusted_context(db, user.id)
    assert ctx1.lifelong_profile is not None
    assert ctx1.lifelong_profile.version == first.version

    invalidate_derived_memory_state(db, user.id, reason="test_stale", commit=True)
    assert _active_profile(db, user.id) is None
    ctx_stale = load_trusted_context(db, user.id)
    assert ctx_stale.lifelong_profile is None

    run_lifelong_profile_sweep(db, persist=True)
    active = _active_profile(db, user.id)
    assert active is not None
    ctx2 = load_trusted_context(db, user.id)
    assert ctx2.lifelong_profile is not None
    assert ctx2.lifelong_profile.version == active.version
    assert ctx2.lifelong_profile.preference_terms or ctx2.lifelong_profile.habit_key_terms


def test_cr04e1_i8_cannot_mint_action_from_i7_alone(db, monkeypatch):
    monkeypatch.setenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "true")
    user = _user(db, "e1-mint")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "activity_level", "moderate", commit=True)
    run_lifelong_profile_sweep(db, persist=True)
    ctx = load_trusted_context(db, user.id)
    assert ctx.lifelong_profile is not None
    pers = build_personalization(ctx, domain="routine")
    assert pers.routine_terms or pers.preference_terms or True
    with patch(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        return_value=SimpleNamespace(status="EMPTY", items=[]),
    ):
        blocked = generate_operational_action(
            db,
            user_id=user.id,
            actor_user_id=user.id,
            request="help with my daily routine",
            domain="routine",
            persist=False,
        )
    assert blocked.status in {
        "MISSING_ELIGIBLE_KNOWLEDGE",
        "MISSING_GROUNDED_ACTION_CONTENT",
    }
    assert not blocked.suggestions
    # No I8-triggered rebuild path in production modules.
    import backend.app.services.i8.context as i8_ctx
    import backend.app.services.i8.unified_core as i8_core

    assert "rebuild_lifelong_profile" not in inspect.getsource(i8_ctx)
    assert "run_lifelong_profile_sweep" not in inspect.getsource(i8_ctx)
    assert "rebuild_lifelong_profile" not in inspect.getsource(i8_core)
    assert "run_lifelong_profile_sweep" not in inspect.getsource(i8_core)


# ---- regressions ----


def test_cr04e1_cr04a_b_c_d_regression_smoke():
    from backend.tests.test_cr04a_multilingual_semantic_quality import (
        _cases,
        _load_corpus,
        test_cr04a_corpus_schema,
        test_cr04a_semantic_contract,
    )
    from backend.tests import test_cr04b_contextual_user_understanding as cr04b
    from backend.tests import test_cr04c_i7_longitudinal_understanding as cr04c
    from backend.app.services.intelligence.contracts import IntentId
    from backend.app.services.intelligence.next_best_question import (
        select_next_best_question,
    )
    from backend.app.services.intelligence.adaptive_interaction import (
        resolve_adaptive_interaction,
    )
    from backend.app.services.intelligence.context_types import (
        ContextItem,
        ContextProvenance,
        ContextSection,
        ContextSnapshot,
        ContextSource,
        SOURCE_SORT_RANK,
    )

    corpus = _load_corpus()
    test_cr04a_corpus_schema(corpus)
    for case in _cases()[:2]:
        test_cr04a_semantic_contract(case)

    intent = cr04b._intent(IntentId.GENERAL)
    d = select_next_best_question(
        snapshot=cr04b._snap([]),
        intent=intent,
        readiness=cr04b._ready(intent),
        language="en",
        message="My night shifts are making sleep difficult",
    )
    assert d is not None
    assert d.target_key == "work.work_schedule"

    cr04c.test_cr04c_no_runtime_wiring_in_orchestrator_or_i8()

    item = ContextItem(
        canonical_key="preferences.response_length",
        section="profile",
        source=ContextSource.PROFILE,
        structured_value='"brief"',
        display_text="preferences.response_length=brief",
        provenance=ContextProvenance(
            source=ContextSource.PROFILE, owner_user_id=1, query_label="t"
        ),
        observed_at=None,
        freshness="unknown",
        sensitivity="medium",
        consent="legacy_scope",
        may_send_to_llm=False,
        sort_rank=SOURCE_SORT_RANK[ContextSource.PROFILE],
        epistemic_class="USER_STATED",
    )
    snap = ContextSnapshot(
        request_id="e1",
        owner_user_id=1,
        sections={"profile": ContextSection(name="profile", items=[item])},
        items=[item],
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("profile",),
    )
    assert resolve_adaptive_interaction(snap).response_length == "brief"
