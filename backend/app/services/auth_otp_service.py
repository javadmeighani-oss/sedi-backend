# app/services/auth_otp_service.py – Stage 25 Phone OTP (production-oriented, minimal)
import os
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.core.security import SECRET_KEY, create_access_token

logger = logging.getLogger(__name__)

# Config from env
OTP_EXPIRE_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RATE_LIMIT_COUNT = 3
OTP_RATE_LIMIT_WINDOW_MINUTES = 10
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Fail-safe SMS: if SMS_DISABLED=true do not call provider; log [OTP_DEV] and return success (Stage 25 Step 2.2)
SMS_DISABLED = os.environ.get("SMS_DISABLED", "").strip().lower() in ("1", "true", "yes")


def resolve_lang(accept_language: Optional[str]) -> str:
    """Parse Accept-Language header to fa|en|ar. Iran-focused default: fa."""
    if not accept_language or not accept_language.strip():
        return "fa"
    # First preferred: "en-US,en;q=0.9,fa;q=0.8" -> take first segment, then language code
    first = accept_language.split(",")[0].strip().split("-")[0].strip().lower()[:2]
    if first in ("en", "fa", "ar"):
        return first
    return "fa"


def _hash_secret(secret: str) -> str:
    """Hash a secret (OTP or refresh token) with bcrypt."""
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return ctx.hash(secret)


def _verify_secret(plain: str, hashed: str) -> bool:
    """Verify plaintext against stored hash."""
    if not hashed:
        return False
    try:
        from passlib.context import CryptContext
        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return ctx.verify(plain, hashed)
    except Exception:
        return False


def normalize_phone(phone: str) -> str:
    """Minimal E.164-ish normalization: strip spaces, optional leading +."""
    s = (phone or "").strip().replace(" ", "").replace("-", "")
    if s.startswith("+"):
        return s
    # If digits only and starts with 0, could strip leading 0 (country-dependent). Keep simple.
    return s


def generate_otp_code() -> str:
    """Generate 6-digit numeric OTP."""
    return "".join(secrets.choice("0123456789") for _ in range(6))


def request_otp(
    db: Session,
    phone: str,
    accept_language: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Create or update OTP for phone; rate-limit; send SMS (or dev log).
    Returns (success, error_message). On success error_message is "".
    """
    phone = normalize_phone(phone)
    if not phone or len(phone) < 8:
        return False, "Invalid phone number"

    now = datetime.utcnow()
    window_start = now - timedelta(minutes=OTP_RATE_LIMIT_WINDOW_MINUTES)

    # Rate limit: count recent OTP rows for this phone
    recent = (
        db.query(models.OtpCode)
        .filter(models.OtpCode.phone == phone, models.OtpCode.created_at >= window_start)
        .all()
    )
    total_sent = sum(r.sent_count for r in recent)
    if total_sent >= OTP_RATE_LIMIT_COUNT:
        return False, "Too many OTP requests. Try again later."

    code = generate_otp_code()
    code_hash = _hash_secret(code)
    expires_at = now + timedelta(minutes=OTP_EXPIRE_MINUTES)

    # Upsert single OTP row per phone (one active at a time)
    row = db.query(models.OtpCode).filter(models.OtpCode.phone == phone).first()
    if row:
        row.code_hash = code_hash
        row.expires_at = expires_at
        row.attempts = 0
        row.sent_count += 1
        row.created_at = now
    else:
        row = models.OtpCode(
            phone=phone,
            code_hash=code_hash,
            expires_at=expires_at,
            attempts=0,
            sent_count=1,
            created_at=now,
        )
        db.add(row)
    db.commit()

    # SMS: when disabled log only; when enabled use gateway and 503 on failure (Stage 25 Step 2.2)
    if SMS_DISABLED:
        logger.info("[OTP_DEV] phone=%s code=%s", phone, code)
        return True, ""
    from backend.app.services.sms_gateway import get_sms_sender
    lang = resolve_lang(accept_language)
    sender = get_sms_sender()
    result = sender.send_otp(phone, code, lang)
    if not result.ok:
        logger.warning("SMS send failed provider=%s error=%s", result.provider, result.error)
        raise HTTPException(status_code=503, detail="SMS delivery unavailable")
    return True, ""


def verify_otp(db: Session, phone: str, code: str) -> Tuple[Optional[models.User], str]:
    """
    Verify OTP; increment attempts; create user if missing.
    Returns (user, error_message). On success error_message is "".
    """
    phone = normalize_phone(phone)
    if not phone:
        return None, "Invalid phone number"
    code = (code or "").strip()
    if len(code) != 6 or not code.isdigit():
        return None, "Invalid code format"

    row = db.query(models.OtpCode).filter(models.OtpCode.phone == phone).first()
    if not row:
        return None, "OTP not requested or expired"

    if now() > row.expires_at:
        return None, "OTP expired"

    if row.attempts >= OTP_MAX_ATTEMPTS:
        return None, "Too many failed attempts"

    row.attempts += 1
    db.commit()

    if not _verify_secret(code, row.code_hash):
        return None, "Incorrect code"

    # Invalidate OTP after successful use (prevent reuse)
    row.expires_at = now()
    db.commit()

    # Get or create user by phone
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
    refresh_plain = secrets.token_urlsafe(48)
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


def get_user_by_refresh_token(db: Session, refresh_token_plain: str) -> Optional[models.User]:
    """Find user by valid, non-revoked refresh token. Returns None if invalid."""
    if not refresh_token_plain:
        return None
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
            return db.query(models.User).filter(models.User.id == row.user_id).first()
    return None


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
