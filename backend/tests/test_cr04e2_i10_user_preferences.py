"""CR-04E2 — I10 interruption from typed I6 user preferences (suppress-only)."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent, revoke_memory_consent
from backend.app.services.i6.memory_writes import list_facts, write_fact
from backend.app.services.i10.canonical_policy import (
    I10_CANONICAL_POLICY_VERSION,
    USER_FOLLOW_UP_PREFERENCE_SUPPRESS,
    USER_PROACTIVE_CHECKIN_PREFERENCE_SUPPRESS,
    evaluate_i10_canonical_policy,
)
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.decision_ledger import record_notification_decision
from backend.app.services.i10.policy_types import I10DecisionValue, I10NotificationScope, I10SemanticFamily
from backend.app.services.intelligence.adapters import LifestyleContextAdapter
from backend.app.services.intelligence.assembler import AuthorizedContextAssembler


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _grant(db, user_id: int) -> None:
    grant_memory_consent(db, user_id, commit=False)
    db.flush()


def _candidate(user_id: int, family: I10SemanticFamily, *, subject_id: int = 1) -> I10NotificationCandidate:
    return I10NotificationCandidate(
        candidate_key=f"i10:cr04e2:{family.value}:{user_id}",
        health_subject_id=subject_id,
        recipient_user_id=user_id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        source_owner="TEST",
        source_type="test",
        source_id=str(user_id),
        semantic_family=family,
    )


def _write_pref(
    db,
    user_id: int,
    key: str,
    value,
    *,
    provenance_class: str = "USER_STATED",
    sensitivity_class: str = "standard",
) -> models.UserMemoryFact:
    return write_fact(
        db,
        user_id,
        "preferences",
        key,
        value,
        provenance_class=provenance_class,
        sensitivity_class=sensitivity_class,
        commit=False,
    )


def _gate4_allow():
    decision = SimpleNamespace(action="allow", reason="allowed", defer_until=None)
    return SimpleNamespace(decision=decision, reason_code="allowed")


def _gate4_suppress():
    decision = SimpleNamespace(action="suppress", reason="do_not_notify", defer_until=None)
    return SimpleNamespace(decision=decision, reason_code="do_not_notify")


def _eval(db, user_id: int, family: I10SemanticFamily, *, gate4=_gate4_allow):
    with patch(
        "backend.app.services.i10.canonical_policy.resolve_notification_policy",
        side_effect=lambda *a, **k: gate4(),
    ):
        return evaluate_i10_canonical_policy(
            db,
            candidate=_candidate(user_id, family),
            payload_metadata={"priority": "normal"},
        )


# ---- follow_up_preference ----


def test_cr04e2_follow_up_false_user_stated_suppresses_general_contextual(db):
    user = _user(db, "fu-stated")
    _grant(db, user.id)
    _write_pref(db, user.id, "follow_up_preference", False, provenance_class="USER_STATED")
    out = _eval(db, user.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP)
    assert out.decision == I10DecisionValue.SUPPRESS
    assert out.reason_code == USER_FOLLOW_UP_PREFERENCE_SUPPRESS


def test_cr04e2_follow_up_false_user_confirmed_suppresses(db):
    user = _user(db, "fu-confirmed")
    _grant(db, user.id)
    _write_pref(db, user.id, "follow_up_preference", False, provenance_class="USER_CONFIRMED")
    out = _eval(db, user.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP)
    assert out.decision == I10DecisionValue.SUPPRESS
    assert out.reason_code == USER_FOLLOW_UP_PREFERENCE_SUPPRESS


def test_cr04e2_follow_up_true_does_not_force_send(db):
    user = _user(db, "fu-true")
    _grant(db, user.id)
    _write_pref(db, user.id, "follow_up_preference", True)
    out = _eval(
        db,
        user.id,
        I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP,
        gate4=_gate4_suppress,
    )
    assert out.decision == I10DecisionValue.SUPPRESS
    assert out.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS
    assert out.reason_code == "DO_NOT_NOTIFY"


def test_cr04e2_follow_up_false_does_not_suppress_post_event(db):
    user = _user(db, "fu-post")
    _grant(db, user.id)
    _write_pref(db, user.id, "follow_up_preference", False)
    out = _eval(db, user.id, I10SemanticFamily.POST_EVENT_FOLLOW_UP)
    assert out.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS
    assert out.decision == I10DecisionValue.SEND


# ---- proactive_checkin_preference ----


def test_cr04e2_proactive_false_suppresses_presence_reengagement(db):
    user = _user(db, "pr-presence")
    _grant(db, user.id)
    _write_pref(db, user.id, "proactive_checkin_preference", False)
    out = _eval(db, user.id, I10SemanticFamily.PRESENCE_REENGAGEMENT)
    assert out.decision == I10DecisionValue.SUPPRESS
    assert out.reason_code == USER_PROACTIVE_CHECKIN_PREFERENCE_SUPPRESS


def test_cr04e2_proactive_false_suppresses_engagement_nudge(db):
    user = _user(db, "pr-nudge")
    _grant(db, user.id)
    _write_pref(db, user.id, "proactive_checkin_preference", False)
    out = _eval(db, user.id, I10SemanticFamily.ENGAGEMENT_NUDGE)
    assert out.decision == I10DecisionValue.SUPPRESS
    assert out.reason_code == USER_PROACTIVE_CHECKIN_PREFERENCE_SUPPRESS


def test_cr04e2_proactive_true_does_not_force_send(db):
    user = _user(db, "pr-true")
    _grant(db, user.id)
    _write_pref(db, user.id, "proactive_checkin_preference", True)
    out = _eval(
        db,
        user.id,
        I10SemanticFamily.PRESENCE_REENGAGEMENT,
        gate4=_gate4_suppress,
    )
    assert out.decision == I10DecisionValue.SUPPRESS
    assert out.reason_code != USER_PROACTIVE_CHECKIN_PREFERENCE_SUPPRESS


def test_cr04e2_proactive_false_preserves_daily_digest_and_morning(db):
    user = _user(db, "pr-digest")
    _grant(db, user.id)
    _write_pref(db, user.id, "proactive_checkin_preference", False)
    digest = _eval(db, user.id, I10SemanticFamily.DAILY_WELLNESS_DIGEST)
    morning = _eval(db, user.id, I10SemanticFamily.MORNING_CHECK_IN)
    assert digest.reason_code != USER_PROACTIVE_CHECKIN_PREFERENCE_SUPPRESS
    assert morning.reason_code != USER_PROACTIVE_CHECKIN_PREFERENCE_SUPPRESS
    assert digest.decision == I10DecisionValue.SEND
    assert morning.decision == I10DecisionValue.SEND


def test_cr04e2_proactive_false_preserves_safety_reminder_health_families(db):
    user = _user(db, "pr-safe")
    _grant(db, user.id)
    _write_pref(db, user.id, "proactive_checkin_preference", False)
    families = (
        I10SemanticFamily.SAFETY_ESCALATION,
        I10SemanticFamily.CARE_SAFETY_ESCALATION,
        I10SemanticFamily.MEDICATION_DUE,
        I10SemanticFamily.MEDICATION_FOLLOW_UP,
        I10SemanticFamily.REMINDER,
        I10SemanticFamily.DOCTOR_APPOINTMENT_REMINDER,
        I10SemanticFamily.LAB_APPOINTMENT_REMINDER,
        I10SemanticFamily.CARE_STATUS_DIGEST,
        I10SemanticFamily.CARE_DATA_GAP,
        I10SemanticFamily.DEVICE_STATUS,
        I10SemanticFamily.HR_INSTABILITY,
    )
    for family in families:
        out = _eval(db, user.id, family)
        assert out.reason_code != USER_PROACTIVE_CHECKIN_PREFERENCE_SUPPRESS, family
        assert out.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS, family


# ---- ignore unsupported ----


def test_cr04e2_system_derived_ignored(db):
    user = _user(db, "sys-der")
    _grant(db, user.id)
    _write_pref(
        db,
        user.id,
        "follow_up_preference",
        False,
        provenance_class="SYSTEM_DERIVED",
    )
    out = _eval(db, user.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP)
    assert out.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS
    assert out.decision == I10DecisionValue.SEND


def test_cr04e2_unknown_provenance_ignored(db):
    user = _user(db, "unk-prov")
    _grant(db, user.id)
    _write_pref(
        db,
        user.id,
        "follow_up_preference",
        False,
        provenance_class="CONVERSATION_DERIVED",
    )
    out = _eval(db, user.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP)
    assert out.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS


def test_cr04e2_high_critical_ignored(db):
    user = _user(db, "sens")
    _grant(db, user.id)
    _write_pref(
        db,
        user.id,
        "follow_up_preference",
        False,
        sensitivity_class="high",
    )
    _write_pref(
        db,
        user.id,
        "proactive_checkin_preference",
        False,
        sensitivity_class="critical",
    )
    fu = _eval(db, user.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP)
    pr = _eval(db, user.id, I10SemanticFamily.PRESENCE_REENGAGEMENT)
    assert fu.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS
    assert pr.reason_code != USER_PROACTIVE_CHECKIN_PREFERENCE_SUPPRESS


def test_cr04e2_1_sensitivity_standard_and_medium_accepted(db):
    u_std = _user(db, "sens-std")
    u_med = _user(db, "sens-med")
    _grant(db, u_std.id)
    _grant(db, u_med.id)
    _write_pref(db, u_std.id, "follow_up_preference", False, sensitivity_class="standard")
    _write_pref(db, u_med.id, "follow_up_preference", False, sensitivity_class="medium")
    assert (
        _eval(db, u_std.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP).reason_code
        == USER_FOLLOW_UP_PREFERENCE_SUPPRESS
    )
    assert (
        _eval(db, u_med.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP).reason_code
        == USER_FOLLOW_UP_PREFERENCE_SUPPRESS
    )


def test_cr04e2_1_sensitivity_null_empty_unknown_ignored(db):
    user = _user(db, "sens-unk")
    _grant(db, user.id)
    for label, sens in (
        ("null", None),
        ("empty", ""),
        ("unknown", "unknown"),
        ("restricted", "restricted"),
    ):
        u = _user(db, f"sens-{label}")
        _grant(db, u.id)
        fact = _write_pref(db, u.id, "follow_up_preference", False, sensitivity_class="standard")
        fact.sensitivity_class = sens
        db.flush()
        out = _eval(db, u.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP)
        assert out.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS, label


def test_cr04e2_1_expired_fact_neutral(db):
    user = _user(db, "exp-neut")
    _grant(db, user.id)
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    fact = write_fact(
        db,
        user.id,
        "preferences",
        "follow_up_preference",
        False,
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        valid_until=past,
        commit=False,
    )
    assert fact.fact_status == "active"
    out = _eval(db, user.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP)
    assert out.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS
    assert out.decision == I10DecisionValue.SEND


def test_cr04e2_1_expired_fact_unmutated_after_i10_decision_commit(db):
    """I10 policy read must not expire/mutate I6 facts when decision ledger commits."""
    from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account

    models.I10NotificationDecision.__table__.create(bind=db.get_bind(), checkfirst=True)
    user = _user(db, "exp-mut")
    _grant(db, user.id)
    subject = ensure_self_subject_for_account(db, user.id, commit=False)
    db.flush()
    past = datetime.now(timezone.utc) - timedelta(hours=3)
    fact = write_fact(
        db,
        user.id,
        "preferences",
        "follow_up_preference",
        False,
        provenance_class="USER_STATED",
        sensitivity_class="standard",
        valid_until=past,
        commit=False,
    )
    db.flush()
    before_status = fact.fact_status
    before_until = fact.valid_until
    before_updated = fact.updated_at
    before_soft = fact.soft_invalidated_at
    assert before_status == "active"

    cand = _candidate(
        user.id,
        I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP,
        subject_id=int(subject.id),
    )
    with patch(
        "backend.app.services.i10.canonical_policy.resolve_notification_policy",
        side_effect=lambda *a, **k: _gate4_allow(),
    ):
        out = evaluate_i10_canonical_policy(
            db,
            candidate=cand,
            payload_metadata={"priority": "normal"},
        )
    assert out.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS

    record_notification_decision(
        db,
        candidate=cand,
        decision=out.decision,
        reason_code=out.reason_code,
        commit=True,
    )
    db.refresh(fact)
    assert fact.fact_status == "active"
    assert fact.fact_status == before_status
    assert fact.valid_until == before_until
    assert fact.updated_at == before_updated
    assert fact.soft_invalidated_at == before_soft


def test_cr04e2_1_revoked_read_consent_neutral(db):
    user = _user(db, "rev-read")
    _grant(db, user.id)
    _write_pref(db, user.id, "follow_up_preference", False)
    revoke_memory_consent(db, user.id, commit=False)
    db.flush()
    out = _eval(db, user.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP)
    assert out.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS
    assert out.decision == I10DecisionValue.SEND


def test_cr04e2_1_policy_version_b18_3():
    assert I10_CANONICAL_POLICY_VERSION == "i10.b18.3"


def test_cr04e2_string_false_ignored(db):
    user = _user(db, "str-false")
    _grant(db, user.id)
    _write_pref(db, user.id, "follow_up_preference", "false")
    out = _eval(db, user.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP)
    assert out.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS
    assert out.decision == I10DecisionValue.SEND


def test_cr04e2_cross_user_isolation(db):
    a = _user(db, "iso-a")
    b = _user(db, "iso-b")
    _grant(db, a.id)
    _grant(db, b.id)
    _write_pref(db, a.id, "follow_up_preference", False)
    out_b = _eval(db, b.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP)
    out_a = _eval(db, a.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP)
    assert out_b.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS
    assert out_a.reason_code == USER_FOLLOW_UP_PREFERENCE_SUPPRESS


def test_cr04e2_missing_preference_preserves_existing_policy(db):
    user = _user(db, "missing")
    _grant(db, user.id)
    out = _eval(db, user.id, I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP)
    assert out.reason_code != USER_FOLLOW_UP_PREFERENCE_SUPPRESS
    assert out.decision == I10DecisionValue.SEND


def test_cr04e2_no_i6_write_from_policy(db):
    user = _user(db, "no-write")
    _grant(db, user.id)
    before = len(list_facts(db, user.id))
    with patch(
        "backend.app.services.i6.memory_writes.write_fact",
        side_effect=AssertionError("I10 must not write I6"),
    ):
        _eval(db, user.id, I10SemanticFamily.PRESENCE_REENGAGEMENT)
    assert len(list_facts(db, user.id)) == before


# ---- LLM projection block ----


def test_cr04e2_control_prefs_blocked_from_llm_projection(db):
    user = _user(db, "llm-block")
    _grant(db, user.id)
    # Domain slice max is 3 — load only control keys + one non-control.
    for key, value in (
        ("follow_up_preference", False),
        ("proactive_checkin_preference", False),
        ("interaction_style", "calm"),
    ):
        _write_pref(db, user.id, key, value)
    # Separate user for response_length / listen_before_advice preservation.
    user2 = _user(db, "llm-block-adaptive")
    _grant(db, user2.id)
    _write_pref(db, user2.id, "response_length", "brief")
    _write_pref(db, user2.id, "listen_before_advice", True)

    adapter = LifestyleContextAdapter()
    items = adapter._load_i6_user_understanding_facts(db, authenticated_user_id=user.id)
    by_key = {i.canonical_key: i for i in items}
    assert by_key["preferences.follow_up_preference"].may_send_to_llm is False
    assert by_key["preferences.proactive_checkin_preference"].may_send_to_llm is False
    assert by_key["preferences.interaction_style"].may_send_to_llm is True

    items2 = adapter._load_i6_user_understanding_facts(db, authenticated_user_id=user2.id)
    by_key2 = {i.canonical_key: i for i in items2}
    assert by_key2["preferences.response_length"].may_send_to_llm is False
    assert by_key2["preferences.listen_before_advice"].may_send_to_llm is False

    from backend.app.services.intelligence.context_types import ContextSnapshot, ContextSection

    section_items = list(items) + list(items2)
    snapshot = ContextSnapshot(
        request_id="cr04e2",
        owner_user_id=user.id,
        sections={"profile": ContextSection(name="profile", items=section_items)},
        items=section_items,
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=("lifestyle",),
    )
    asm = AuthorizedContextAssembler()
    proj = asm.build_compatibility_projection(snapshot)
    assert "follow_up_preference" not in proj.text
    assert "proactive_checkin_preference" not in proj.text
    assert "response_length" not in proj.text
    assert "listen_before_advice" not in proj.text
