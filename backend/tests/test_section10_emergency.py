"""Section 10 — emergency escalation and voice-call foundation."""

from backend.app import models
from backend.app.services.section10.emergency_escalation_service import (
    EscalationPolicy,
    create_escalation_record,
    resolve_emergency_caregiver_order,
)
from backend.app.services.section10.voice_call_request_service import (
    create_voice_call_request,
    get_voice_message_template,
)


def test_escalation_policy_defaults_none():
    pol = EscalationPolicy.from_env()
    assert pol.inactivity_window_minutes is None


def test_voice_templates_multilingual():
    for lang in ("fa", "en", "ar"):
        msg = get_voice_message_template("caregiver_no_response_check", lang)
        assert "Sedi" in msg or "سدی" in msg or "صدي" in msg
        assert "emergency" not in msg.lower() or "not" in msg.lower() or "نیست" in msg


def test_escalation_record_created(db):
    user = models.User(name="e", secret_key="k")
    db.add(user)
    db.commit()
    rec = create_escalation_record(db, user.id, "inactivity")
    assert rec.current_state == "monitoring"


def test_voice_call_suppressed_by_default(db):
    user = models.User(name="e2", secret_key="k")
    db.add(user)
    db.flush()
    cg = models.UserCaregiver(owner_user_id=user.id, name="CG", is_active=True)
    db.add(cg)
    db.commit()
    req = create_voice_call_request(
        db,
        owner_user_id=user.id,
        caregiver_id=cg.id,
        template_key="caregiver_no_response_check",
        language="fa",
    )
    assert req.status == "suppressed"


def test_emergency_caregiver_order_emergency_priority(db):
    user = models.User(name="e3", secret_key="k")
    db.add(user)
    db.flush()
    cg1 = models.UserCaregiver(
        owner_user_id=user.id, name="A", notify_emergency=True, emergency_priority=2, is_active=True
    )
    cg2 = models.UserCaregiver(
        owner_user_id=user.id, name="B", notify_emergency=True, emergency_priority=1, is_active=True
    )
    db.add_all([cg1, cg2])
    db.commit()
    ordered = resolve_emergency_caregiver_order(db, user.id)
    assert [c.name for c in ordered] == ["B", "A"]
