# app/services/auth_otp_service.py – Stage 25 Phone OTP (production-oriented, minimal)
import hashlib
import hmac
import os
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.core.security import SECRET_KEY, create_access_token
from backend.app.services.i18n.locale import parse_accept_language

logger = logging.getLogger(__name__)

# Config from env
OTP_EXPIRE_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RATE_LIMIT_COUNT = int(os.getenv("OTP_RATE_LIMIT_COUNT", "5"))
OTP_RATE_LIMIT_WINDOW_MINUTES = int(os.getenv("OTP_RATE_LIMIT_WINDOW_MINUTES", "10"))
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

OTP_PURPOSE_LOGIN = "LOGIN"
OTP_PURPOSE_PHONE_CHANGE = "PHONE_CHANGE"
_OTP_PURPOSES = frozenset({OTP_PURPOSE_LOGIN, OTP_PURPOSE_PHONE_CHANGE})

# Fail-safe SMS: if SMS_DISABLED=true do not call provider; log [OTP_DEV] and return success (Stage 25 Step 2.2)
SMS_DISABLED = os.environ.get("SMS_DISABLED", "").strip().lower() in ("1", "true", "yes")


def _otp_secret() -> str:
    """Secret for OTP HMAC only; not used for refresh tokens. Uses canonical SECRET_KEY if OTP_SECRET unset."""
    return os.getenv("OTP_SECRET") or SECRET_KEY


def _otp_hmac(code: str) -> str:
    """HMAC-SHA256 of code (deterministic); avoids bcrypt 72-byte limit and passlib issues."""
    secret = _otp_secret().encode("utf-8")
    msg = code.encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _refresh_secret() -> str:
    """
    Secret for refresh-token hashing (HMAC). Must be stable across restarts.
    Prefer REFRESH_SECRET; fallback to canonical SECRET_KEY.
    """
    return os.getenv("REFRESH_SECRET") or SECRET_KEY


def _refresh_hmac(token: str) -> str:
    """HMAC-SHA256 of refresh token (deterministic). Safe for long tokens (no 72-byte bcrypt limit)."""
    secret = _refresh_secret().encode("utf-8")
    msg = (token or "").encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def resolve_lang(accept_language: Optional[str]) -> str:
    """
    V1 language policy: primary language is English (en) with full fa/ar support.
    Fallback must be en.
    """
    return parse_accept_language(accept_language)


def _hash_secret(secret: str) -> str:
    """Hash a secret (refresh token only; OTP uses _otp_hmac) with HMAC-SHA256."""
    return _refresh_hmac(secret)


def _verify_secret(plain: str, hashed: str) -> bool:
    """Verify plaintext against stored hash."""
    if not hashed:
        return False
    expected = _refresh_hmac(plain)
    return hmac.compare_digest(expected, hashed)


def normalize_phone(phone: str) -> str:
    """Minimal E.164-ish normalization: strip spaces, optional leading +."""
    s = (phone or "").strip().replace(" ", "").replace("-", "")
    if s.startswith("+"):
        return s
    # If digits only and starts with 0, could strip leading 0 (country-dependent). Keep simple.
    return s


def _mask_phone(phone: str) -> str:
    """Mask phone for logs (prefix only)."""
    s = (phone or "").strip()
    if len(s) <= 4:
        return "***"
    return s[:4] + "***"


def generate_otp_code() -> str:
    """Generate 6-digit numeric OTP."""
    return "".join(secrets.choice("0123456789") for _ in range(6))


def _generate_refresh_token() -> str:
    """Generate opaque refresh token plaintext (URL-safe, 32 bytes)."""
    return secrets.token_urlsafe(32)


def request_otp(
    db: Session,
    phone: str,
    accept_language: Optional[str] = None,
    *,
    purpose: str = OTP_PURPOSE_LOGIN,
    user_id: Optional[int] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Create or update OTP for phone+purpose; rate-limit; send SMS (or dev log).
    Returns (success, error_message, dev_code). On success error_message is "".
    LOGIN: purpose=LOGIN, user_id=None.
    PHONE_CHANGE: purpose=PHONE_CHANGE, user_id=authenticated account id.
    """
    purpose = (purpose or OTP_PURPOSE_LOGIN).strip().upper()
    if purpose not in _OTP_PURPOSES:
        return False, "Invalid OTP purpose", None
    if purpose == OTP_PURPOSE_PHONE_CHANGE and user_id is None:
        return False, "Authenticated account required", None
    if purpose == OTP_PURPOSE_LOGIN:
        user_id = None

    phone = normalize_phone(phone)
    if not phone or len(phone) < 8 or not phone.startswith("+"):
        # Login historically accepted non-+; keep login lenient, phone-change requires E.164 +.
        if purpose == OTP_PURPOSE_PHONE_CHANGE:
            return False, "Invalid phone number", None
        if not phone or len(phone) < 8:
            return False, "Invalid phone number", None

    now = datetime.utcnow()
    window_start = now - timedelta(minutes=OTP_RATE_LIMIT_WINDOW_MINUTES)

    # Rate limit: recent rows for this phone + purpose (+ user when bound)
    rl_q = db.query(models.OtpCode).filter(
        models.OtpCode.phone == phone,
        models.OtpCode.purpose == purpose,
        models.OtpCode.created_at >= window_start,
    )
    if user_id is not None:
        rl_q = rl_q.filter(models.OtpCode.user_id == user_id)
    recent = rl_q.all()
    total_sent = sum(r.sent_count for r in recent)
    if total_sent >= OTP_RATE_LIMIT_COUNT:
        return False, "Too many OTP requests. Try again later.", None

    code = generate_otp_code()
    code_hash = _otp_hmac(code)
    expires_at = now + timedelta(minutes=OTP_EXPIRE_MINUTES)

    # Upsert active OTP for (phone, purpose[, user_id])
    q = db.query(models.OtpCode).filter(
        models.OtpCode.phone == phone,
        models.OtpCode.purpose == purpose,
    )
    if purpose == OTP_PURPOSE_PHONE_CHANGE:
        q = q.filter(models.OtpCode.user_id == user_id)
    else:
        q = q.filter(models.OtpCode.user_id.is_(None))
    row = q.first()
    if row:
        row.code_hash = code_hash
        row.expires_at = expires_at
        row.attempts = 0
        row.sent_count += 1
        row.created_at = now
        row.purpose = purpose
        row.user_id = user_id
    else:
        row = models.OtpCode(
            phone=phone,
            code_hash=code_hash,
            expires_at=expires_at,
            attempts=0,
            sent_count=1,
            created_at=now,
            purpose=purpose,
            user_id=user_id,
        )
        db.add(row)
    db.commit()

    _sms_disabled = os.environ.get("SMS_DISABLED", "").strip().lower() in ("1", "true", "yes")
    if _sms_disabled:
        logger.warning(
            "[DEV OTP] purpose=%s phone=%s (SMS disabled)",
            purpose,
            _mask_phone(phone),
        )
        return True, "", code

    from backend.app.services.sms_gateway import get_sms_sender
    lang = resolve_lang(accept_language)
    sender = get_sms_sender()
    result = sender.send_otp(phone, code, lang)
    if not result.ok:
        err_msg = (result.error or "SMS delivery failed").strip()
        logger.warning(
            "[OTP] SMS send failed purpose=%s phone=%s provider=%s error=%s",
            purpose,
            _mask_phone(phone),
            result.provider,
            err_msg,
        )
        return False, err_msg or "SMS delivery failed. Please try again later.", None
    return True, "", None


def verify_otp(db: Session, phone: str, code: str) -> Tuple[Optional[models.User], str]:
    """
    Verify LOGIN OTP; increment attempts; create user if missing.
    Never consumes PHONE_CHANGE challenges.
    """
    phone = normalize_phone(phone)
    if not phone:
        return None, "Invalid phone number"
    code = (code or "").strip()
    if len(code) != 6 or not code.isdigit():
        return None, "Invalid code format"

    row = (
        db.query(models.OtpCode)
        .filter(
            models.OtpCode.phone == phone,
            models.OtpCode.purpose == OTP_PURPOSE_LOGIN,
        )
        .first()
    )
    # Backward-compat: legacy rows may lack purpose filter if purpose default not applied
    if not row:
        row = (
            db.query(models.OtpCode)
            .filter(
                models.OtpCode.phone == phone,
                models.OtpCode.purpose == OTP_PURPOSE_LOGIN,
                models.OtpCode.user_id.is_(None),
            )
            .first()
        )
    if not row:
        return None, "OTP not requested or expired"

    if now() > row.expires_at:
        return None, "OTP expired"

    if row.attempts >= OTP_MAX_ATTEMPTS:
        return None, "Too many failed attempts"

    row.attempts += 1
    db.commit()

    expected_hash = _otp_hmac(code)
    if not row.code_hash or not hmac.compare_digest(expected_hash, row.code_hash):
        return None, "Incorrect code"

    # Invalidate OTP after successful use (prevent reuse)
    row.expires_at = now()
    db.commit()

    # Get or create user by phone (LOGIN only)
    user = db.query(models.User).filter(models.User.phone == phone).first()
    if not user:
        user = models.User(
            phone=phone,
            name=None,
            secret_key="<otp>",  # placeholder; column NOT NULL
            preferred_language="en",
            created_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user, ""


def request_phone_change_otp(
    db: Session,
    user: models.User,
    new_phone: str,
    accept_language: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """Authenticated phone-change OTP to NEW number. Never mutates Account.phone."""
    new_phone = normalize_phone(new_phone)
    if not new_phone or len(new_phone) < 8 or not new_phone.startswith("+"):
        return False, "Invalid phone number", None

    current = normalize_phone(user.phone or "")
    if current and current == new_phone:
        return False, "Phone is already your current number", None

    other = (
        db.query(models.User)
        .filter(models.User.phone == new_phone, models.User.id != user.id)
        .first()
    )
    if other is not None:
        return False, "Phone number already in use", None

    return request_otp(
        db,
        new_phone,
        accept_language=accept_language,
        purpose=OTP_PURPOSE_PHONE_CHANGE,
        user_id=user.id,
    )


def verify_phone_change_otp(
    db: Session,
    user: models.User,
    new_phone: str,
    code: str,
) -> Tuple[Optional[models.User], str]:
    """
    Verify PHONE_CHANGE OTP for authenticated user; atomically update same Account.phone.
    Never creates a new Account. Never uses LOGIN get-or-create.
    """
    new_phone = normalize_phone(new_phone)
    if not new_phone or not new_phone.startswith("+"):
        return None, "Invalid phone number"
    code = (code or "").strip()
    if len(code) != 6 or not code.isdigit():
        return None, "Invalid code format"

    current = normalize_phone(user.phone or "")
    if current and current == new_phone:
        return None, "Phone is already your current number"

    row = (
        db.query(models.OtpCode)
        .filter(
            models.OtpCode.phone == new_phone,
            models.OtpCode.purpose == OTP_PURPOSE_PHONE_CHANGE,
            models.OtpCode.user_id == user.id,
        )
        .first()
    )
    if not row:
        return None, "OTP not requested or expired"

    if now() > row.expires_at:
        return None, "OTP expired"

    if row.attempts >= OTP_MAX_ATTEMPTS:
        return None, "Too many failed attempts"

    row.attempts += 1
    db.commit()

    expected_hash = _otp_hmac(code)
    if not row.code_hash or not hmac.compare_digest(expected_hash, row.code_hash):
        return None, "Incorrect code"

    # Final uniqueness recheck before mutation
    other = (
        db.query(models.User)
        .filter(models.User.phone == new_phone, models.User.id != user.id)
        .first()
    )
    if other is not None:
        return None, "Phone number already in use"

    # Consume OTP then mutate same Account
    row.expires_at = now()
    user.phone = new_phone
    db.add(user)
    db.add(row)
    db.commit()
    db.refresh(user)
    return user, ""


def now() -> datetime:
    return datetime.utcnow()


def issue_tokens(
    db: Session,
    user: models.User,
    device_info: Optional[str] = None,
    ip: Optional[str] = None,
) -> Tuple[str, str, int]:
    """
    Create access JWT and opaque refresh token; store refresh hash in DB.
    Returns (access_token, refresh_token_plain, expires_in_seconds).
    """
    access_token = create_access_token(
        {"user_id": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_plain = _generate_refresh_token()
    refresh_hash = _hash_secret(refresh_plain)
    expires_at = now() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    rt = models.RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=expires_at,
        revoked_at=None,
        created_at=now(),
        device_info=device_info,
        ip=ip,
    )
    db.add(rt)
    db.commit()

    return access_token, refresh_plain, ACCESS_TOKEN_EXPIRE_MINUTES * 60


def get_refresh_token_row(db: Session, refresh_token_plain: str) -> Optional[models.RefreshToken]:
    """Find refresh token row by plaintext (token_hash = _refresh_hmac(plain), not revoked, not expired)."""
    if not refresh_token_plain:
        return None
    token_hash = _refresh_hmac(refresh_token_plain)
    now_ = now()
    return (
        db.query(models.RefreshToken)
        .filter(
            models.RefreshToken.token_hash == token_hash,
            models.RefreshToken.revoked_at.is_(None),
            models.RefreshToken.expires_at > now_,
        )
        .first()
    )


def get_user_by_refresh_token(db: Session, refresh_token_plain: str) -> Optional[models.User]:
    """Find user by valid, non-revoked refresh token. Returns None if invalid."""
    row = get_refresh_token_row(db, refresh_token_plain)
    if not row:
        return None
    return db.query(models.User).filter(models.User.id == row.user_id).first()


def rotate_refresh_token(
    db: Session,
    refresh_token_plain: str,
    device_info: Optional[str] = None,
    ip: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """
    Validate refresh token, revoke it, issue new access + new refresh. Returns (access_token, new_refresh_plain, expires_in_seconds) or (None, None, None) if invalid.
    """
    row = get_refresh_token_row(db, refresh_token_plain)
    if not row:
        return None, None, None
    row.revoked_at = now()
    db.commit()
    user_id = row.user_id
    access_token = create_access_token(
        {"user_id": user_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    new_plain = _generate_refresh_token()
    new_hash = _refresh_hmac(new_plain)
    expires_at = now() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    new_row = models.RefreshToken(
        user_id=user_id,
        token_hash=new_hash,
        expires_at=expires_at,
        revoked_at=None,
        created_at=now(),
        device_info=device_info,
        ip=ip,
    )
    db.add(new_row)
    db.commit()
    return access_token, new_plain, ACCESS_TOKEN_EXPIRE_MINUTES * 60


def revoke_refresh_token(db: Session, refresh_token_plain: str) -> bool:
    """Revoke the refresh token (set revoked_at). Returns True if one was revoked."""
    if not refresh_token_plain:
        return False
    now_ = now()
    rows = (
        db.query(models.RefreshToken)
        .filter(
            models.RefreshToken.revoked_at.is_(None),
            models.RefreshToken.expires_at > now_,
        )
        .all()
    )
    for row in rows:
        if _verify_secret(refresh_token_plain, row.token_hash):
            row.revoked_at = now_
            db.commit()
            return True
    return False


# Alias for schema/docs
def hash_secret(secret: str) -> str:
    return _hash_secret(secret)


def verify_secret(plain: str, hashed: str) -> bool:
    return _verify_secret(plain, hashed)
