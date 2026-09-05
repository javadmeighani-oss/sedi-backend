"""Stage B reusable canonical family dataset (SEDI-V1-REAL-FAMILY-CARE-E2E-01).

Son Account + SELF HS; Mother MANAGED ALS HS (linked_user_id=NULL);
Son gateway ≠ Mother health-data owner. No fake Mother Account.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.health_subject_condition_service import report_subject_condition
from backend.app.services.i10.care_network_grants import create_subject_notification_grant
from backend.app.services.i10.policy_types import I10NotificationScope
from backend.app.services.i9.device_binding_service import bind_device_to_subject
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.core.device_auth import hash_device_token


SCENARIO_ID = "SEDI-V1-REAL-FAMILY-CARE-E2E-01"


@dataclass
class StageBFamily:
    son: models.User
    stranger: models.User
    son_self_hs: models.HealthSubject
    mother_hs: models.HealthSubject
    mother_condition: models.HealthSubjectCondition
    device: models.Device | None
    when: datetime


def _als_catalog(db: Session) -> models.MedicalCondition:
    row = db.query(models.MedicalCondition).filter(models.MedicalCondition.code == "ALS").first()
    if row:
        return row
    row = models.MedicalCondition(
        code="ALS",
        name="Amyotrophic lateral sclerosis",
        description="ALS / Lou Gehrig's disease",
        category="neurology",
    )
    db.add(row)
    db.flush()
    return row


def _prefs(db: Session, user_id: int, *, enabled: bool = True) -> None:
    existing = (
        db.query(models.NotificationPrefs).filter(models.NotificationPrefs.user_id == user_id).first()
    )
    if existing:
        existing.companion_enabled = enabled
        existing.health_alert_enabled = enabled
        existing.reminder_medication_enabled = enabled
        existing.reminder_appointment_enabled = enabled
        existing.reminder_system_enabled = enabled
        return
    db.add(
        models.NotificationPrefs(
            user_id=user_id,
            companion_enabled=enabled,
            health_alert_enabled=enabled,
            reminder_medication_enabled=enabled,
            reminder_appointment_enabled=enabled,
            reminder_system_enabled=enabled,
        )
    )


def _push(db: Session, user_id: int, token: str) -> None:
    db.add(
        models.PushDevice(
            user_id=user_id,
            platform="android",
            fcm_token=token,
            is_active=True,
        )
    )


def seed_stage_b_family(
    db: Session,
    *,
    with_device: bool = True,
    with_i10_grants: bool = True,
    when: datetime | None = None,
    commit: bool = True,
) -> StageBFamily:
    """Seed one reusable Son/Mother family. Asserts canonical identity law."""
    when = when or datetime(2026, 9, 1, 9, 0, 0, tzinfo=timezone.utc)
    suffix = uuid4().hex[:8]
    son = models.User(
        name=f"StageB-Son-{suffix}",
        secret_key=f"sk-son-{suffix}",
        preferred_language="en",
    )
    stranger = models.User(
        name=f"StageB-Stranger-{suffix}",
        secret_key=f"sk-str-{suffix}",
        preferred_language="en",
    )
    db.add_all([son, stranger])
    db.flush()

    son_self = ensure_self_subject_for_account(db, son.id, display_name="SON_SELF", commit=False)
    mother = create_managed_subject_without_account(
        db,
        account_user_id=son.id,
        display_name="MOTHER_ALS",
        access_role="MANAGER",
        commit=False,
    )
    als = _als_catalog(db)
    hsc = report_subject_condition(
        db,
        actor_account_user_id=son.id,
        health_subject_id=mother.id,
        condition_id=als.id,
        notes="Stage B Mother ALS primary condition",
        commit=False,
    )

    # Identity law
    assert son.id != mother.id
    assert son_self.id != mother.id
    assert mother.linked_user_id is None
    assert mother.subject_kind == "managed"
    assert son_self.linked_user_id == son.id
    assert son_self.subject_kind == "self"

    device = None
    if with_device:
        device = models.Device(
            user_id=son.id,  # Son phone gateway Account
            device_id=f"StageBDev-{suffix}",
            device_type="heart_rate",
            status="active",
            token_hash=hash_device_token(f"tok-{suffix}"),
        )
        db.add(device)
        db.flush()
        bind_device_to_subject(
            db,
            device=device,
            health_subject_id=mother.id,  # health-data owner = Mother HS
            bound_by_account_user_id=son.id,
            bound_at=when - timedelta(days=1),
            commit=False,
        )
        assert device.user_id == son.id
        assert device.health_subject_id == mother.id
        assert device.user_id != mother.linked_user_id  # gateway != data owner Account

    if with_i10_grants:
        for scope in (
            I10NotificationScope.GENERAL_STATUS,
            I10NotificationScope.DEVICE_STATUS,
            I10NotificationScope.CARE_ACTION,
            I10NotificationScope.SAFETY_ESCALATION,
        ):
            create_subject_notification_grant(
                db,
                actor_user_id=son.id,
                health_subject_id=mother.id,
                recipient_user_id=son.id,
                notification_scope=scope,
                commit=False,
            )
        _prefs(db, son.id, enabled=True)
        _push(db, son.id, f"fcm-stage-b-{suffix}")

    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(son)
    db.refresh(stranger)
    db.refresh(son_self)
    db.refresh(mother)
    db.refresh(hsc)
    if device is not None:
        db.refresh(device)

    return StageBFamily(
        son=son,
        stranger=stranger,
        son_self_hs=son_self,
        mother_hs=mother,
        mother_condition=hsc,
        device=device,
        when=when,
    )
