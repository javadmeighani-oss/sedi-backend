"""G1 Device identity / classification / setup-code authority — PostgreSQL targeted."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from alembic import command
from sqlalchemy import text

from backend.app import models
from backend.app.services import auth_otp_service as svc
from backend.app.services.i9.device_binding_service import get_active_binding, rebind_device
from backend.app.services.i9.device_claim_service import (
    claim_device_to_health_subject,
    provision_unclaimed_device_platform,
    provision_unclaimed_device_v1,
)
from backend.app.services.i9.device_gateway_service import (
    authorize_mobile_gateway,
    disconnect_mobile_gateway,
    list_active_gateways,
)
from backend.app.services.i9.device_lifecycle_service import release_device, transfer_device
from backend.app.services.i9.device_setup_code_service import (
    DeviceSetupCodeError,
    SETUP_CODE_FAILURE_LIMIT,
    assign_unique_setup_code,
    generate_setup_code_v1,
    setup_code_fingerprint_hex,
)
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.tests.helpers.i10_postgresql_harness import (
    ALEMBIC_HEAD,
    I10IsolatedPgDb,
    _REV_083,
    _REV_084,
)

_TEST_ADMIN = "g1-admin-token"
_PEPPER = "g1-test-setup-code-pepper"


def _user_token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def _admin_headers(monkeypatch) -> dict[str, str]:
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN)
    return {"X-Admin-Token": _TEST_ADMIN}


@pytest.fixture
def pepper(monkeypatch):
    monkeypatch.setenv("SEDI_DEVICE_SETUP_CODE_PEPPER", _PEPPER)
    return _PEPPER


@pytest.fixture
def account_user(db):
    user = models.User(name="G1User", secret_key="k-g1", preferred_language="en", phone="+989191100001")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_g1_01_migration_083_084_cycle_single_head():
    isolated = I10IsolatedPgDb.create(suffix="g1mig084", revision=_REV_083)
    try:
        assert isolated.head() == _REV_083
        command.upgrade(isolated.cfg, _REV_084)
        assert isolated.head() == _REV_084
        with isolated.engine.connect() as conn:
            cols = {
                r[0]
                for r in conn.execute(
                    text(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name='devices'
                          AND column_name IN (
                            'device_category','user_label','setup_code_verifier',
                            'setup_code_fingerprint','setup_code_version',
                            'setup_code_failed_attempts','setup_code_failure_window_started_at',
                            'setup_code_locked_until'
                          )
                        """
                    )
                )
            }
            assert "device_category" in cols
            assert "setup_code_fingerprint" in cols
        command.downgrade(isolated.cfg, _REV_083)
        assert isolated.head() == _REV_083
        with isolated.engine.connect() as conn:
            gone = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_name='devices' AND column_name='setup_code_verifier'
                    """
                )
            ).scalar_one()
            assert gone == 0
        command.upgrade(isolated.cfg, _REV_084)
        assert isolated.head() == _REV_084
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config("backend/alembic.ini")
        cfg.set_main_option("script_location", "backend/alembic")
        heads = ScriptDirectory.from_config(cfg).get_heads()
        assert heads == [ALEMBIC_HEAD]
        assert ALEMBIC_HEAD == _REV_084
    finally:
        isolated.close()


def test_g1_02_provision_valid_4char_leading_zero(client, db, monkeypatch, pepper):
    with patch(
        "backend.app.services.i9.device_setup_code_service.secrets.randbelow",
        return_value=42,
    ):
        resp = client.post(
            "/devices/provision",
            json={"device_id": "SEDI-ECG-000000000831"},
            headers=_admin_headers(monkeypatch),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["setup_code"] == "0042"
    assert body["data"]["token"]
    assert body["data"]["device_id"] == "SEDI-ECG-000000000831"


def test_g1_03_04_unique_fingerprint_and_no_plaintext(db, pepper):
    d1, _t1, c1 = provision_unclaimed_device_v1(
        db, device_id="SEDI-BP-000000000101"
    )
    assert c1 and len(c1) == 4
    assert d1.setup_code_fingerprint
    assert d1.setup_code_verifier
    assert c1 not in (d1.setup_code_verifier, d1.setup_code_fingerprint)
    row = db.execute(
        text("SELECT setup_code_verifier, setup_code_fingerprint FROM devices WHERE device_id=:d"),
        {"d": d1.device_id},
    ).one()
    assert c1 not in row

    d2, _t2 = provision_unclaimed_device_platform(
        db, device_id="SEDI-BP-000000000102", commit=False
    )
    with patch(
        "backend.app.services.i9.device_setup_code_service.generate_setup_code_v1",
        side_effect=[c1, "7777"],
    ):
        code = assign_unique_setup_code(db, d2, commit=False)
    assert code == "7777"
    assert d2.setup_code_fingerprint != d1.setup_code_fingerprint
    fps = [
        r[0]
        for r in db.execute(
            text(
                "SELECT setup_code_fingerprint FROM devices WHERE setup_code_fingerprint IS NOT NULL"
            )
        )
    ]
    assert len(fps) == len(set(fps))
    assert c1 not in fps
    assert "7777" not in fps


def test_g1_05_missing_pepper_fails_closed_only_setup_ops(client, db, monkeypatch, account_user):
    monkeypatch.delenv("SEDI_DEVICE_SETUP_CODE_PEPPER", raising=False)
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN)
    # Unrelated list route still works
    token = _user_token(client, db, monkeypatch, account_user.phone)
    listed = client.get("/devices", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    assert listed.json()["ok"] is True

    prov = client.post(
        "/devices/provision",
        json={"device_id": "SEDI-SPO2-000000000019"},
        headers={"X-Admin-Token": _TEST_ADMIN},
    )
    assert prov.status_code == 200
    assert prov.json()["ok"] is False
    assert prov.json()["error"]["code"] == "SETUP_CODE_PEPPER_MISSING"


def test_g1_06_v1_claim_pass_self_optional_gateway(client, db, monkeypatch, pepper, account_user):
    admin = client.post(
        "/devices/provision",
        json={"device_id": "SEDI-ECG-000000000201"},
        headers=_admin_headers(monkeypatch),
    )
    token = admin.json()["data"]["token"]
    setup_code = admin.json()["data"]["setup_code"]
    user_token = _user_token(client, db, monkeypatch, account_user.phone)
    claim = client.post(
        "/devices/claim",
        json={
            "device_id": "SEDI-ECG-000000000201",
            "possession_proof": token,
            "setup_code": setup_code,
            "device_category": "SELF",
            "gateway_install_id": "gateway-install-g1-001",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert claim.status_code == 200
    body = claim.json()
    assert body["ok"] is True
    assert body["data"]["device_category"] == "SELF"
    device = db.query(models.Device).filter_by(device_id="SEDI-ECG-000000000201").one()
    assert device.owner_account_user_id == account_user.id
    assert get_active_binding(db, device.id) is not None
    assert list_active_gateways(db, device.id)


def test_g1_07_other_without_label_rejected(client, db, monkeypatch, pepper, account_user):
    admin = client.post(
        "/devices/provision",
        json={"device_id": "SEDI-ECG-000000000202"},
        headers=_admin_headers(monkeypatch),
    )
    token = admin.json()["data"]["token"]
    setup_code = admin.json()["data"]["setup_code"]
    user_token = _user_token(client, db, monkeypatch, account_user.phone)
    claim = client.post(
        "/devices/claim",
        json={
            "device_id": "SEDI-ECG-000000000202",
            "possession_proof": token,
            "setup_code": setup_code,
            "device_category": "OTHER",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert claim.json()["ok"] is False
    assert claim.json()["error"]["code"] == "USER_LABEL_REQUIRED_FOR_OTHER"
    device = db.query(models.Device).filter_by(device_id="SEDI-ECG-000000000202").one()
    assert device.device_category is None
    assert get_active_binding(db, device.id) is None


def test_g1_08_09_10_wrong_code_rate_limit_no_mutation(client, db, monkeypatch, pepper, account_user):
    admin = client.post(
        "/devices/provision",
        json={"device_id": "SEDI-ECG-000000000203"},
        headers=_admin_headers(monkeypatch),
    )
    token = admin.json()["data"]["token"]
    user_token = _user_token(client, db, monkeypatch, account_user.phone)
    for i in range(SETUP_CODE_FAILURE_LIMIT):
        claim = client.post(
            "/devices/claim",
            json={
                "device_id": "SEDI-ECG-000000000203",
                "possession_proof": token,
                "setup_code": "0000",
                "device_category": "SELF",
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert claim.json()["ok"] is False
        code = claim.json()["error"]["code"]
        if i < SETUP_CODE_FAILURE_LIMIT - 1:
            assert code == "SETUP_CODE_INVALID"
        else:
            # 5th invalid either INVALID then lock on next, or lock depending on order
            assert code in ("SETUP_CODE_INVALID", "SETUP_CODE_TEMPORARILY_LOCKED")
    device = db.query(models.Device).filter_by(device_id="SEDI-ECG-000000000203").one()
    assert device.setup_code_failed_attempts >= SETUP_CODE_FAILURE_LIMIT
    assert device.setup_code_locked_until is not None
    assert device.device_category is None
    assert get_active_binding(db, device.id) is None
    assert list_active_gateways(db, device.id) == []

    locked = client.post(
        "/devices/claim",
        json={
            "device_id": "SEDI-ECG-000000000203",
            "possession_proof": token,
            "setup_code": admin.json()["data"]["setup_code"],
            "device_category": "SELF",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert locked.json()["error"]["code"] == "SETUP_CODE_TEMPORARILY_LOCKED"


def test_g1_11_valid_code_failed_possession_no_mutation(client, db, monkeypatch, pepper, account_user):
    admin = client.post(
        "/devices/provision",
        json={"device_id": "SEDI-ECG-000000000204"},
        headers=_admin_headers(monkeypatch),
    )
    setup_code = admin.json()["data"]["setup_code"]
    user_token = _user_token(client, db, monkeypatch, account_user.phone)
    claim = client.post(
        "/devices/claim",
        json={
            "device_id": "SEDI-ECG-000000000204",
            "possession_proof": "wrong-token-not-valid",
            "setup_code": setup_code,
            "device_category": "SELF",
            "gateway_install_id": "gateway-should-not-pair",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert claim.json()["ok"] is False
    device = db.query(models.Device).filter_by(device_id="SEDI-ECG-000000000204").one()
    assert device.claim_lifecycle_status == "unclaimed"
    assert device.device_category is None
    assert get_active_binding(db, device.id) is None
    assert list_active_gateways(db, device.id) == []


def test_g1_12_successful_claim_clears_failure_state(db, pepper, account_user):
    device, token, setup_code = provision_unclaimed_device_v1(
        db, device_id="SEDI-ECG-000000000205"
    )
    device.setup_code_failed_attempts = 3
    device.setup_code_failure_window_started_at = datetime.now(timezone.utc)
    device.setup_code_locked_until = None
    db.commit()
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
        setup_code=setup_code,
        device_category="SELF",
    )
    db.refresh(device)
    assert device.setup_code_failed_attempts == 0
    assert device.setup_code_failure_window_started_at is None
    assert device.setup_code_locked_until is None


def test_g1_13_legacy_device_without_verifier_claim_compat(db, account_user):
    device, token = provision_unclaimed_device_platform(
        db, device_id="LegacyClaimDev001"
    )
    assert device.setup_code_verifier is None
    subject = ensure_self_subject_for_account(db, account_user.id)
    binding = claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
    )
    assert binding.id
    assert device.claim_lifecycle_status == "claimed"
    assert device.device_category is None


def test_g1_14_patch_owner_success_unauthorized_fail(client, db, monkeypatch, pepper, account_user):
    admin = client.post(
        "/devices/provision",
        json={"device_id": "SEDI-ECG-000000000206"},
        headers=_admin_headers(monkeypatch),
    )
    token = admin.json()["data"]["token"]
    setup_code = admin.json()["data"]["setup_code"]
    user_token = _user_token(client, db, monkeypatch, account_user.phone)
    client.post(
        "/devices/claim",
        json={
            "device_id": "SEDI-ECG-000000000206",
            "possession_proof": token,
            "setup_code": setup_code,
            "device_category": "SELF",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    ok = client.patch(
        "/devices/SEDI-ECG-000000000206",
        json={"device_category": "OTHER", "user_label": "Mom BP"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert ok.json()["ok"] is True
    assert ok.json()["data"]["device_category"] == "OTHER"
    assert ok.json()["data"]["user_label"] == "Mom BP"

    other = models.User(name="G1Other", secret_key="k-g1o", preferred_language="en", phone="+989191100099")
    db.add(other)
    db.commit()
    other_token = _user_token(client, db, monkeypatch, other.phone)
    bad = client.patch(
        "/devices/SEDI-ECG-000000000206",
        json={"device_category": "SELF"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert bad.json()["ok"] is False
    assert bad.json()["error"]["code"] == "DEVICE_NOT_FOUND"


def test_g1_15_16_disconnect_preserves_release_clears(db, pepper, account_user):
    device, token, setup_code = provision_unclaimed_device_v1(
        db, device_id="SEDI-ECG-000000000207"
    )
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
        setup_code=setup_code,
        device_category="OTHER",
        user_label="Guest cuff",
        gateway_install_id="gw-a",
    )
    authorize_mobile_gateway(
        db, device=device, gateway_install_id="gw-b", account_user_id=account_user.id
    )
    binding_before = get_active_binding(db, device.id)
    assert binding_before is not None
    hist_id = binding_before.id
    assert device.device_category == "OTHER"
    assert device.user_label == "Guest cuff"
    assert len(list_active_gateways(db, device.id)) == 2

    disconnect_mobile_gateway(
        db, device=device, gateway_install_id="gw-a", account_user_id=account_user.id
    )
    db.refresh(device)
    assert device.claim_lifecycle_status == "claimed"
    assert device.device_category == "OTHER"
    assert device.user_label == "Guest cuff"
    assert get_active_binding(db, device.id).id == hist_id
    assert len(list_active_gateways(db, device.id)) == 1

    verifier_before = device.setup_code_verifier
    fp_before = device.setup_code_fingerprint
    release_device(db, device=device, account_user_id=account_user.id)
    db.refresh(device)
    assert device.claim_lifecycle_status == "released"
    assert device.device_category is None
    assert device.user_label is None
    assert device.setup_code_verifier == verifier_before
    assert device.setup_code_fingerprint == fp_before
    assert list_active_gateways(db, device.id) == []
    closed = db.query(models.DeviceSubjectBinding).filter_by(id=hist_id).one()
    assert closed.unbound_at is not None


def test_g1_17_transfer_rebind_does_not_rewrite_category(db, pepper, account_user):
    device, token, setup_code = provision_unclaimed_device_v1(
        db, device_id="SEDI-ECG-000000000208"
    )
    self_hs = ensure_self_subject_for_account(db, account_user.id)
    managed = create_managed_subject_without_account(
        db, account_user_id=account_user.id, display_name="Father"
    )
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=self_hs.id,
        possession_proof=token,
        setup_code=setup_code,
        device_category="SELF",
    )
    assert device.device_category == "SELF"
    transfer_device(
        db,
        device=device,
        account_user_id=account_user.id,
        new_health_subject_id=managed.id,
        possession_proof=token,
    )
    db.refresh(device)
    assert device.device_category == "SELF"
    assert device.user_label is None
    rebind_device(
        db,
        device=device,
        new_health_subject_id=self_hs.id,
        bound_by_account_user_id=account_user.id,
    )
    db.refresh(device)
    assert device.device_category == "SELF"


def test_g1_18_list_exposes_category_label(client, db, monkeypatch, pepper, account_user):
    admin = client.post(
        "/devices/provision",
        json={"device_id": "SEDI-ECG-000000000209"},
        headers=_admin_headers(monkeypatch),
    )
    user_token = _user_token(client, db, monkeypatch, account_user.phone)
    client.post(
        "/devices/claim",
        json={
            "device_id": "SEDI-ECG-000000000209",
            "possession_proof": admin.json()["data"]["token"],
            "setup_code": admin.json()["data"]["setup_code"],
            "device_category": "OTHER",
            "user_label": "Kitchen SpO2",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    listed = client.get("/devices", headers={"Authorization": f"Bearer {user_token}"})
    assert listed.json()["ok"] is True
    row = next(d for d in listed.json()["data"]["devices"] if d["device_id"] == "SEDI-ECG-000000000209")
    assert row["device_category"] == "OTHER"
    assert row["user_label"] == "Kitchen SpO2"


def test_g1_19_no_raw_setup_code_in_audit(db, pepper, account_user, caplog):
    with caplog.at_level(logging.INFO):
        device, token, setup_code = provision_unclaimed_device_v1(
            db, device_id="SEDI-ECG-000000000210"
        )
        subject = ensure_self_subject_for_account(db, account_user.id)
        claim_device_to_health_subject(
            db,
            device=device,
            account_user_id=account_user.id,
            health_subject_id=subject.id,
            possession_proof=token,
            setup_code=setup_code,
            device_category="SELF",
        )
    audits = (
        db.query(models.DeviceLifecycleAuditLog)
        .filter(models.DeviceLifecycleAuditLog.device_row_id == device.id)
        .all()
    )
    for a in audits:
        blob = a.detail_json or ""
        assert setup_code not in blob
        if blob:
            detail = json.loads(blob)
            assert "setup_code" not in detail
    for rec in caplog.records:
        assert setup_code not in rec.getMessage()


def test_g1_generate_setup_code_format():
    for _ in range(20):
        code = generate_setup_code_v1()
        assert len(code) == 4 and code.isdigit()
