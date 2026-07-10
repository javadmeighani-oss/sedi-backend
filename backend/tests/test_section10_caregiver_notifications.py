"""Section 10 — caregiver notification resolver and intent foundation."""

from backend.app import models
from backend.app.services.section10.caregiver_notification_intent_service import (
    create_caregiver_notification_intent,
)
from backend.app.services.section10.caregiver_notification_resolver import (
    caregiver_eligible_for_notification,
    resolve_eligible_caregivers,
)


def _caregiver(**kwargs):
    defaults = dict(
        id=1,
        owner_user_id=10,
        name="Test",
        notify_daily_status=False,
        notify_emergency=False,
        notify_care_summary=False,
        notify_vital_alerts=False,
        is_active=True,
        priority=0,
    )
    defaults.update(kwargs)
    return models.UserCaregiver(**defaults)


def test_preference_resolver_maps_types():
    cg = _caregiver(notify_vital_alerts=True)
    assert caregiver_eligible_for_notification(cg, "important_vital_alert") is True
    assert caregiver_eligible_for_notification(cg, "care_summary") is False
    assert caregiver_eligible_for_notification(_caregiver(is_active=False), "important_vital_alert") is False


def test_intent_created_suppressed_by_default(db):
    user = models.User(name="u", secret_key="k")
    db.add(user)
    db.flush()
    cg = models.UserCaregiver(
        owner_user_id=user.id,
        name="CG",
        notify_vital_alerts=True,
        is_active=True,
    )
    db.add(cg)
    db.commit()

    intent = create_caregiver_notification_intent(
        db,
        owner_user_id=user.id,
        caregiver_id=cg.id,
        notification_type="important_vital_alert",
        dedupe_bucket="test",
    )
    assert intent is not None
    assert intent.status == "suppressed"


def test_resolve_eligible_caregivers_order(db):
    user = models.User(name="u2", secret_key="k")
    db.add(user)
    db.flush()
    cg1 = models.UserCaregiver(owner_user_id=user.id, name="A", notify_emergency=True, priority=2, is_active=True)
    cg2 = models.UserCaregiver(owner_user_id=user.id, name="B", notify_emergency=True, priority=1, is_active=True)
    db.add_all([cg1, cg2])
    db.commit()
    ordered = resolve_eligible_caregivers(db, user.id, "emergency_escalation")
    assert [c.name for c in ordered] == ["B", "A"]
