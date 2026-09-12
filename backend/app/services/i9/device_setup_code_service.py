"""V1 device setup-code authority — HMAC verifier/fingerprint; never persist plaintext."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app import models

SETUP_CODE_PEPPER_ENV = "SEDI_DEVICE_SETUP_CODE_PEPPER"
SETUP_CODE_VERSION_V1 = 1
SETUP_CODE_GENERATION_ATTEMPTS = 32
SETUP_CODE_FAILURE_LIMIT = 5
SETUP_CODE_WINDOW_MINUTES = 15
SETUP_CODE_LOCK_MINUTES = 15


class DeviceSetupCodeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_pepper() -> bytes:
    """Lazy load; fail closed only when setup-code operations are invoked."""
    raw = os.environ.get(SETUP_CODE_PEPPER_ENV)
    if raw is None or not str(raw).strip():
        raise DeviceSetupCodeError(
            "SETUP_CODE_PEPPER_MISSING",
            "Device setup-code pepper is not configured",
        )
    return str(raw).strip().encode("utf-8")


def generate_setup_code_v1() -> str:
    """Exactly 4 decimal digits, leading zeros preserved."""
    return f"{secrets.randbelow(10000):04d}"


def normalize_setup_code(setup_code: str) -> str:
    code = (setup_code or "").strip()
    if len(code) != 4 or not code.isdigit():
        raise DeviceSetupCodeError("SETUP_CODE_INVALID_FORMAT", "Setup code must be exactly 4 digits")
    return code


def setup_code_verifier_hex(*, device_id: str, setup_code: str, pepper: Optional[bytes] = None) -> str:
    pepper_b = pepper if pepper is not None else _load_pepper()
    msg = f"verify:{device_id}:{setup_code}".encode("utf-8")
    return hmac.new(pepper_b, msg, hashlib.sha256).hexdigest()


def setup_code_fingerprint_hex(*, setup_code: str, pepper: Optional[bytes] = None) -> str:
    pepper_b = pepper if pepper is not None else _load_pepper()
    msg = f"unique:{setup_code}".encode("utf-8")
    return hmac.new(pepper_b, msg, hashlib.sha256).hexdigest()


def verify_setup_code_constant_time(device: models.Device, setup_code: str) -> bool:
    if not device.setup_code_verifier:
        return False
    code = normalize_setup_code(setup_code)
    expected = setup_code_verifier_hex(device_id=device.device_id, setup_code=code)
    return hmac.compare_digest(expected, device.setup_code_verifier)


def assert_setup_code_not_locked(device: models.Device, *, now: Optional[datetime] = None) -> None:
    now = now or utc_now()
    locked_until = device.setup_code_locked_until
    if locked_until is None:
        return
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    if locked_until > now:
        raise DeviceSetupCodeError(
            "SETUP_CODE_TEMPORARILY_LOCKED",
            "Setup code temporarily locked after repeated failures",
        )


def _reset_failure_window_if_expired(device: models.Device, *, now: datetime) -> None:
    started = device.setup_code_failure_window_started_at
    if started is None:
        return
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if now - started >= timedelta(minutes=SETUP_CODE_WINDOW_MINUTES):
        device.setup_code_failed_attempts = 0
        device.setup_code_failure_window_started_at = None


def record_setup_code_failure(
    db: Session,
    device: models.Device,
    *,
    commit: bool = True,
) -> None:
    """Persist only bounded failure/lock state for invalid setup codes."""
    now = utc_now()
    _reset_failure_window_if_expired(device, now=now)
    if device.setup_code_failure_window_started_at is None:
        device.setup_code_failure_window_started_at = now
        device.setup_code_failed_attempts = 0
    device.setup_code_failed_attempts = int(device.setup_code_failed_attempts or 0) + 1
    if device.setup_code_failed_attempts >= SETUP_CODE_FAILURE_LIMIT:
        device.setup_code_locked_until = now + timedelta(minutes=SETUP_CODE_LOCK_MINUTES)
    db.add(device)
    if commit:
        db.commit()
        db.refresh(device)
    else:
        db.flush()


def reset_setup_code_failure_state(device: models.Device) -> None:
    device.setup_code_failed_attempts = 0
    device.setup_code_failure_window_started_at = None
    device.setup_code_locked_until = None


def assign_unique_setup_code(
    db: Session,
    device: models.Device,
    *,
    commit: bool = False,
) -> str:
    """Generate V1 setup code; persist verifier/fingerprint/version only. Returns plaintext once."""
    pepper = _load_pepper()
    last_error: Optional[Exception] = None
    for _ in range(SETUP_CODE_GENERATION_ATTEMPTS):
        code = generate_setup_code_v1()
        fingerprint = setup_code_fingerprint_hex(setup_code=code, pepper=pepper)
        conflict = (
            db.query(models.Device.id)
            .filter(
                models.Device.setup_code_fingerprint == fingerprint,
                models.Device.id != device.id,
            )
            .first()
        )
        if conflict is not None:
            continue
        device.setup_code_verifier = setup_code_verifier_hex(
            device_id=device.device_id, setup_code=code, pepper=pepper
        )
        device.setup_code_fingerprint = fingerprint
        device.setup_code_version = SETUP_CODE_VERSION_V1
        reset_setup_code_failure_state(device)
        db.add(device)
        try:
            with db.begin_nested():
                db.flush()
            if commit:
                db.commit()
                db.refresh(device)
            return code
        except IntegrityError as exc:
            last_error = exc
            device.setup_code_verifier = None
            device.setup_code_fingerprint = None
            device.setup_code_version = None
            continue
    raise DeviceSetupCodeError(
        "SETUP_CODE_GENERATION_EXHAUSTED",
        "Unable to allocate a unique setup code",
    ) from last_error


def validate_category_and_label(
    *,
    device_category: Optional[str],
    user_label: Optional[str],
    require_category: bool,
) -> Tuple[Optional[str], Optional[str]]:
    category = (device_category or "").strip().upper() if device_category is not None else None
    label = user_label.strip() if isinstance(user_label, str) else user_label
    if label == "":
        label = None

    if require_category:
        if category not in ("SELF", "OTHER"):
            raise DeviceSetupCodeError(
                "DEVICE_CATEGORY_REQUIRED",
                "device_category must be SELF or OTHER",
            )
    elif category is not None and category not in ("SELF", "OTHER"):
        raise DeviceSetupCodeError("DEVICE_CATEGORY_INVALID", "device_category must be SELF or OTHER")

    if category == "OTHER":
        if not label:
            raise DeviceSetupCodeError(
                "USER_LABEL_REQUIRED_FOR_OTHER",
                "user_label is required for OTHER devices",
            )
        if len(label) > 80:
            raise DeviceSetupCodeError("USER_LABEL_TOO_LONG", "user_label max length is 80")
    elif label is not None and len(label) > 80:
        raise DeviceSetupCodeError("USER_LABEL_TOO_LONG", "user_label max length is 80")

    return category, label
